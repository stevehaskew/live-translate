package main

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming/types"
)

// AWSEngine implements TranscriptionEngine using AWS Transcribe Streaming.
type AWSEngine struct {
	stt *SpeechToText // back-reference for credentials & config
}

// NewAWSEngine creates an engine that streams audio to AWS Transcribe.
func NewAWSEngine(stt *SpeechToText) *AWSEngine {
	return &AWSEngine{stt: stt}
}

// Start implements TranscriptionEngine.  It opens an AWS Transcribe streaming
// session, feeds int16 PCM audio from audioIn, and emits final transcripts on
// the returned channel.  The channel is closed when the engine finishes.
func (e *AWSEngine) Start(ctx context.Context, audioIn <-chan []int16) (<-chan string, error) {
	out := make(chan string, 16)

	// Get AWS config (picks up latest token / local creds)
	cfg, err := e.getAWSConfig(ctx)
	if err != nil {
		close(out)
		return out, fmt.Errorf("failed to get AWS config: %w", err)
	}

	// Create AWS Transcribe Streaming client
	client := transcribestreaming.NewFromConfig(cfg)

	// Start transcription stream
	stream, err := client.StartStreamTranscription(ctx, &transcribestreaming.StartStreamTranscriptionInput{
		LanguageCode:         types.LanguageCodeEnUs,
		MediaSampleRateHertz: aws.Int32(sampleRate),
		MediaEncoding:        types.MediaEncodingPcm,
	})
	if err != nil {
		close(out)
		return out, fmt.Errorf("failed to start transcription stream: %w", err)
	}

	eventStream := stream.GetStream()
	var wg sync.WaitGroup

	// Goroutine: read transcription results
	wg.Add(1)
	go func() {
		defer wg.Done()
		for event := range eventStream.Events() {
			switch ev := event.(type) {
			case *types.TranscriptResultStreamMemberTranscriptEvent:
				for _, result := range ev.Value.Transcript.Results {
					if !result.IsPartial && len(result.Alternatives) > 0 && result.Alternatives[0].Transcript != nil {
						text := strings.TrimSpace(*result.Alternatives[0].Transcript)
						if text != "" {
							select {
							case out <- text:
							case <-ctx.Done():
								return
							}
						}
					}
				}
			}
		}
		// If the event stream itself returned an error, wrap token-expired
		// errors so the caller can decide to refresh.
		if err := eventStream.Err(); err != nil {
			if isTokenExpiredError(err) {
				log.Printf("AWS token expired during transcription: %v", err)
			} else {
				log.Printf("AWS event stream error: %v", err)
			}
		}
	}()

	// Goroutine: send audio chunks to AWS
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-ctx.Done():
				eventStream.Close()
				return
			case samples, ok := <-audioIn:
				if !ok {
					eventStream.Close()
					return
				}
				audioBytes := int16ToBytes(samples)
				if err := eventStream.Send(ctx, &types.AudioStreamMemberAudioEvent{
					Value: types.AudioEvent{AudioChunk: audioBytes},
				}); err != nil {
					if isTokenExpiredError(err) {
						log.Printf("AWS token expired during send: %v", err)
					} else if ctx.Err() == nil {
						log.Printf("Error sending audio to AWS: %v", err)
					}
					eventStream.Close()
					return
				}
			}
		}
	}()

	// Goroutine: wait for both to finish, then close output
	go func() {
		wg.Wait()
		close(out)
	}()

	return out, nil
}

// Close implements TranscriptionEngine.
func (e *AWSEngine) Close() error {
	return nil
}

// ---------------------------------------------------------------------------
// AWS credential helpers (moved from speech_to_text.go)
// ---------------------------------------------------------------------------

// dynamicCredentialsProvider implements aws.CredentialsProvider.
// It always retrieves the latest token from the SpeechToText instance.
type dynamicCredentialsProvider struct {
	stt *SpeechToText
}

// Retrieve implements aws.CredentialsProvider.
func (p *dynamicCredentialsProvider) Retrieve(ctx context.Context) (aws.Credentials, error) {
	p.stt.tokenMutex.RLock()
	token := p.stt.currentToken
	p.stt.tokenMutex.RUnlock()

	if token == nil {
		return aws.Credentials{}, fmt.Errorf("no AWS token available")
	}

	if p.stt.verbose {
		fmt.Printf("Using AWS credentials (expires: %s)\n", token.Credentials.Expiration)
	}

	return aws.Credentials{
		AccessKeyID:     token.Credentials.AccessKeyId,
		SecretAccessKey: token.Credentials.SecretAccessKey,
		SessionToken:    token.Credentials.SessionToken,
		Source:          "DynamicTokenProvider",
	}, nil
}

// getAWSConfig returns AWS config with appropriate credentials.
func (e *AWSEngine) getAWSConfig(ctx context.Context) (aws.Config, error) {
	s := e.stt
	if s.useLocalToken {
		if s.verbose {
			fmt.Println("Using local AWS credentials")
		}
		return awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(s.awsRegion))
	}

	s.tokenMutex.RLock()
	token := s.currentToken
	s.tokenMutex.RUnlock()

	if token == nil {
		return aws.Config{}, fmt.Errorf("no AWS token available")
	}

	return aws.Config{
		Region:      token.Region,
		Credentials: &dynamicCredentialsProvider{stt: s},
	}, nil
}

// requestToken requests a new AWS token from the server via WebSocket.
func (s *SpeechToText) requestToken() error {
	if s.apiKey == "" {
		return fmt.Errorf("API key is required for token generation")
	}
	if s.wsConn == nil {
		return fmt.Errorf("WebSocket connection not established")
	}

	tokenChan := make(chan *TokenResponse, 1)
	errorChan := make(chan error, 1)
	s.tokenResponseChan = tokenChan
	s.tokenErrorChan = errorChan

	message := WSMessage{
		Type: MessageTypeGenerateToken,
		Data: map[string]interface{}{
			"api_key": s.apiKey,
		},
	}
	if err := s.wsConn.WriteJSON(message); err != nil {
		return fmt.Errorf("failed to send token request: %v", err)
	}

	select {
	case tokenResp := <-tokenChan:
		s.tokenMutex.Lock()
		s.currentToken = tokenResp
		s.tokenMutex.Unlock()
		if s.verbose {
			fmt.Printf("✓ AWS token obtained (expires: %s, region: %s)\n", tokenResp.Credentials.Expiration, tokenResp.Region)
		}
		return nil
	case err := <-errorChan:
		return fmt.Errorf("token generation failed: %v", err)
	case <-time.After(10 * time.Second):
		return fmt.Errorf("token request timed out")
	}
}

// startTokenRefresher starts a goroutine that refreshes the token periodically.
func (s *SpeechToText) startTokenRefresher() {
	go func() {
		ticker := time.NewTicker(tokenRefreshInterval)
		defer ticker.Stop()

		for {
			select {
			case <-s.ctx.Done():
				if s.verbose {
					fmt.Println("Token refresher stopped (context cancelled)")
				}
				return
			case <-s.shutdownRequested:
				if s.verbose {
					fmt.Println("Token refresher stopped (shutdown requested)")
				}
				return
			case <-ticker.C:
				if s.verbose {
					fmt.Printf("⟳ Refreshing AWS token (interval: %v)...\n", tokenRefreshInterval)
				}
				if err := s.requestToken(); err != nil {
					log.Printf("✖ Failed to refresh token: %v", err)
				} else if s.verbose {
					fmt.Println("✓ Token refreshed successfully")
				}
			}
		}
	}()
}
