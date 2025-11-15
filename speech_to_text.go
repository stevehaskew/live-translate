package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"sync"
	"log"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming/types"
	"github.com/gordonklaus/portaudio"
	"github.com/gorilla/websocket"
	"github.com/joho/godotenv"
)

// Message types for WebSocket communication
const (
	MessageTypeConnect          = "connect"
	MessageTypeConnectionStatus = "connection_status"
	MessageTypeSetLanguage      = "set_language"
	MessageTypeLanguageSet      = "language_set"
	MessageTypeNewText          = "new_text"
	MessageTypeTranslatedText   = "translated_text"
	MessageTypeGenerateToken    = "generate_token"
	MessageTypeTokenResponse    = "token_response"
	MessageTypeError            = "error"
)

// WSMessage represents a WebSocket message
type WSMessage struct {
	Type string                 `json:"type"`
	Data map[string]interface{} `json:"data"`
}

// TokenResponse represents the response from the generate_token endpoint
type TokenResponse struct {
	Status      string            `json:"status"`
	Credentials AWSCredentials    `json:"credentials"`
	Region      string            `json:"region"`
	Error       string            `json:"error,omitempty"`
}

// AWSCredentials represents temporary AWS credentials
type AWSCredentials struct {
	AccessKeyId     string `json:"AccessKeyId"`
	SecretAccessKey string `json:"SecretAccessKey"`
	SessionToken    string `json:"SessionToken"`
	Expiration      string `json:"Expiration"`
}

const (
	sampleRate      = 16000
	framesPerBuffer = 8000 // 0.5 seconds of audio
	numChannels     = 1
	phraseTimeLimit = 10 * time.Second
	tokenRefreshInterval = 20 * time.Minute // Refresh token every 20 minutes
)

// AudioDevice represents an audio input device
type AudioDevice struct {
	Index    int
	Name     string
	Channels int
}

// SpeechToText handles speech recognition and broadcasting
type SpeechToText struct {
	serverURL         string
	apiKey            string
	deviceIndex       int
	wsConn            *websocket.Conn
	stream            *portaudio.Stream
	transcribeClient  *transcribestreaming.Client
	isRunning         bool
	ctx               context.Context
	awsRegion         string
	verbose           bool
	useLocalToken     bool // Use local AWS credentials instead of server token
	currentToken      *TokenResponse
	tokenMutex        sync.RWMutex
	tokenResponseChan chan *TokenResponse
	tokenErrorChan    chan error
	// connectedOnce is set to true once the socket has successfully connected
	connectedOnce     bool
	connMu            sync.RWMutex
	shutdownRequested chan struct{}
	shutdownOnce      sync.Once
}

// NewSpeechToText creates a new SpeechToText instance
func NewSpeechToText(ctx context.Context, serverURL, apiKey string, deviceIndex int, awsRegion string, verbose bool, useLocalToken bool) (*SpeechToText, error) {
	return &SpeechToText{
		ctx:               ctx,
		serverURL:         serverURL,
		apiKey:            apiKey,
		deviceIndex:       deviceIndex,
		isRunning:         false,
		awsRegion:         awsRegion,
		verbose:           verbose,
		useLocalToken:     useLocalToken,
		connectedOnce:     false,
		shutdownRequested: make(chan struct{}),
	}, nil
}

// getInputDevices returns a list of audio input devices
func getInputDevices() ([]AudioDevice, error) {
	devices := []AudioDevice{}

	if err := portaudio.Initialize(); err != nil {
		return nil, fmt.Errorf("failed to initialize PortAudio: %v", err)
	}
	defer portaudio.Terminate()

	// Get all devices
	allDevices, err := portaudio.Devices()
	if err != nil {
		return nil, fmt.Errorf("failed to get devices: %v", err)
	}

	for i, deviceInfo := range allDevices {
		// Only include input devices
		if deviceInfo.MaxInputChannels > 0 {
			devices = append(devices, AudioDevice{
				Index:    i,
				Name:     deviceInfo.Name,
				Channels: deviceInfo.MaxInputChannels,
			})
		}
	}

	return devices, nil
}

// listAudioDevices lists all available audio input devices
func listAudioDevices() error {
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("Available Audio Input Devices")
	fmt.Println(strings.Repeat("=", 60))

	devices, err := getInputDevices()
	if err != nil {
		return fmt.Errorf("error listing devices: %v", err)
	}

	if len(devices) == 0 {
		fmt.Println("No audio input devices found.")
		return nil
	}

	for _, device := range devices {
		fmt.Printf("%d: %s (%d channels)\n", device.Index, device.Name, device.Channels)
	}

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Printf("Total input devices: %d\n", len(devices))
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("\nTo use a specific device:")
	fmt.Println("  By index: -d <index>")
	fmt.Println("  By name:  -d \"<device_name>\"")
	fmt.Println("\nOr set permanently in .env:")
	fmt.Println("  LT_AUDIO_DEVICE=<index> or LT_AUDIO_DEVICE=\"<device_name>\"")

	return nil
}

// findDeviceIndexByName finds a device index by name
func findDeviceIndexByName(name string) (int, error) {
	devices, err := getInputDevices()
	if err != nil {
		return -1, err
	}

	for _, device := range devices {
		if device.Name == name {
			return device.Index, nil
		}
	}

	return -1, fmt.Errorf("device not found")
}

// connectToServer establishes connection to the server
func (s *SpeechToText) connectToServer() error {
	fmt.Printf("Connecting to server at %s...\n", s.serverURL)

	// Parse the URL and convert http/https to ws/wss
	u, err := url.Parse(s.serverURL)
	if err != nil {
		return fmt.Errorf("failed to parse server URL: %v", err)
	}

	// Convert http(s) to ws(s)
	if u.Scheme == "http" {
		u.Scheme = "ws"
	} else if u.Scheme == "https" {
		u.Scheme = "wss"
	} else if u.Scheme != "ws" && u.Scheme != "wss" {
		u.Scheme = "ws"
	}

	// Add /ws path for WebSocket endpoint
	// u.Path = "/ws"
	wsURL := u.String()

	// Connect to WebSocket
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		// Provide more verbose diagnostics when requested
		if s.verbose {
			fmt.Fprintf(os.Stderr, "\n✖ Failed to connect to server at %s\n", wsURL)
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			// If the dial returned an HTTP response, include its status and a small preview of the body
			if resp != nil {
				// Try to read up to 4KB of the response body for diagnostics
				var bodyPreview string
				if resp.Body != nil {
					limited := io.LimitReader(resp.Body, 4096)
					if b, rerr := io.ReadAll(limited); rerr == nil {
						bodyPreview = string(b)
					} else {
						bodyPreview = fmt.Sprintf("<failed to read body: %v>", rerr)
					}
					resp.Body.Close()
				}

				fmt.Fprintf(os.Stderr, "Response status: %s\n", resp.Status)
				if bodyPreview != "" {
					fmt.Fprintf(os.Stderr, "Response body (truncated to 4KB):\n%s\n", bodyPreview)
				}
			}
		}

		return fmt.Errorf("failed to connect to server %s: %v", wsURL, err)
	}

	s.wsConn = conn
	fmt.Printf("✓ Connected to server at %s\n", wsURL)

	// Start listening for messages from server
	go s.readMessages()

	return nil
}

// requestToken requests a new AWS token from the server via WebSocket
func (s *SpeechToText) requestToken() error {
	if s.apiKey == "" {
		return fmt.Errorf("API key is required for token generation")
	}

	if s.wsConn == nil {
		return fmt.Errorf("WebSocket connection not established")
	}

	// Create a channel to receive the token response
	tokenChan := make(chan *TokenResponse, 1)
	errorChan := make(chan error, 1)

	// Set up temporary message handler to capture token response
	s.tokenResponseChan = tokenChan
	s.tokenErrorChan = errorChan

	// Send generate_token message
	message := WSMessage{
		Type: MessageTypeGenerateToken,
		Data: map[string]interface{}{
			"api_key": s.apiKey,
		},
	}

	if err := s.wsConn.WriteJSON(message); err != nil {
		return fmt.Errorf("failed to send token request: %v", err)
	}

	// Wait for response with timeout
	select {
	case tokenResp := <-tokenChan:
		// Store token
		s.tokenMutex.Lock()
		s.currentToken = tokenResp
		s.tokenMutex.Unlock()

		if s.verbose {
			fmt.Printf("✓ AWS token obtained (expires: %s)\n", tokenResp.Credentials.Expiration)
		}
		return nil

	case err := <-errorChan:
		return fmt.Errorf("token generation failed: %v", err)

	case <-time.After(10 * time.Second):
		return fmt.Errorf("token request timed out")
	}
}

// startTokenRefresher starts a goroutine that refreshes the token periodically
func (s *SpeechToText) startTokenRefresher() {
	go func() {
		ticker := time.NewTicker(tokenRefreshInterval)
		defer ticker.Stop()

		for {
			select {
			case <-s.ctx.Done():
				return
			case <-s.shutdownRequested:
				return
			case <-ticker.C:
				if s.verbose {
					fmt.Println("Refreshing AWS token...")
				}
				if err := s.requestToken(); err != nil {
					log.Printf("Failed to refresh token: %v", err)
				}
			}
		}
	}()
}

// getAWSConfig returns AWS config with appropriate credentials
func (s *SpeechToText) getAWSConfig() (aws.Config, error) {
	if s.useLocalToken {
		// Use local AWS credentials
		if s.verbose {
			fmt.Println("Using local AWS credentials")
		}
		return config.LoadDefaultConfig(s.ctx, config.WithRegion(s.awsRegion))
	}

	// Use token from server
	s.tokenMutex.RLock()
	token := s.currentToken
	s.tokenMutex.RUnlock()

	if token == nil {
		return aws.Config{}, fmt.Errorf("no AWS token available")
	}

	// Create credentials provider from token
	credsProvider := credentials.NewStaticCredentialsProvider(
		token.Credentials.AccessKeyId,
		token.Credentials.SecretAccessKey,
		token.Credentials.SessionToken,
	)

	cfg := aws.Config{
		Region:      token.Region,
		Credentials: credsProvider,
	}

	return cfg, nil
}

// readMessages listens for incoming WebSocket messages
func (s *SpeechToText) readMessages() {
	defer func() {
		if s.wsConn != nil {
			s.wsConn.Close()
		}
	}()

	for {
		var msg WSMessage
		err := s.wsConn.ReadJSON(&msg)
		if err != nil {
			// If we're shutting down, avoid noisy error logs for closed connection.
			select {
			case <-s.shutdownRequested:
				return
			default:
			}
			if s.ctx != nil && s.ctx.Err() != nil {
				return
			}
			if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
				return
			}
			log.Printf("WebSocket read error: %v", err)
			return
		}

		// Handle incoming messages
		switch msg.Type {
		case MessageTypeConnectionStatus:
			if awsAvailable, ok := msg.Data["aws_available"].(bool); ok {
				fmt.Printf("Server connection status: aws_available=%v\n", awsAvailable)
			}
		case MessageTypeTokenResponse:
			// Handle token response
			if data, ok := msg.Data["data"].(map[string]interface{}); ok {
				if status, ok := data["status"].(string); ok && status == "success" {
					// Parse credentials
					if credsMap, ok := data["credentials"].(map[string]interface{}); ok {
						tokenResp := &TokenResponse{
							Status: status,
							Credentials: AWSCredentials{
								AccessKeyId:     credsMap["AccessKeyId"].(string),
								SecretAccessKey: credsMap["SecretAccessKey"].(string),
								SessionToken:    credsMap["SessionToken"].(string),
								Expiration:      credsMap["Expiration"].(string),
							},
							Region: data["region"].(string),
						}
						
						// Send to waiting channel
						if s.tokenResponseChan != nil {
							select {
							case s.tokenResponseChan <- tokenResp:
							default:
							}
						}
					}
				} else if errorMsg, ok := data["error"].(string); ok {
					// Send error to waiting channel
					if s.tokenErrorChan != nil {
						select {
						case s.tokenErrorChan <- fmt.Errorf(errorMsg):
						default:
						}
					}
				}
			}
		case MessageTypeError:
			if errMsg, ok := msg.Data["message"].(string); ok {
				fmt.Printf("Server error: %s\n", errMsg)
				// Check if this is a token error
				if s.tokenErrorChan != nil {
					select {
					case s.tokenErrorChan <- fmt.Errorf(errMsg):
					default:
					}
				}
			}
		}
	}
}

// sendMessage sends a WebSocket message to the server
func (s *SpeechToText) sendMessage(msgType string, data map[string]interface{}) error {
	if s.wsConn == nil {
		return fmt.Errorf("WebSocket connection not established")
	}

	msg := WSMessage{
		Type: msgType,
		Data: data,
	}

	return s.wsConn.WriteJSON(msg)
}

// calibrateMicrophone adjusts for ambient noise
func (s *SpeechToText) calibrateMicrophone() error {
	fmt.Println("\nCalibrating microphone for ambient noise...")
	if s.deviceIndex >= 0 {
		fmt.Printf("Using audio device index: %d\n", s.deviceIndex)
	} else {
		fmt.Println("Using default audio device")
	}
	fmt.Println("Please remain quiet for 2 seconds...")

	// Initialize PortAudio
	if err := portaudio.Initialize(); err != nil {
		return fmt.Errorf("failed to initialize PortAudio: %v", err)
	}

	// Get device info
	var device *portaudio.DeviceInfo
	var err error

	if s.deviceIndex >= 0 {
		allDevices, err := portaudio.Devices()
		if err != nil {
			portaudio.Terminate()
			return fmt.Errorf("failed to get devices: %v", err)
		}
		if s.deviceIndex >= len(allDevices) {
			portaudio.Terminate()
			return fmt.Errorf("device index %d out of range", s.deviceIndex)
		}
		device = allDevices[s.deviceIndex]
	} else {
		device, err = portaudio.DefaultInputDevice()
		if err != nil {
			portaudio.Terminate()
			return fmt.Errorf("failed to get default device: %v", err)
		}
	}

	// Create stream parameters
	params := portaudio.LowLatencyParameters(device, nil)
	params.Input.Channels = numChannels
	params.SampleRate = sampleRate
	params.FramesPerBuffer = framesPerBuffer

	// Open stream for calibration
	buffer := make([]int16, framesPerBuffer)
	stream, err := portaudio.OpenStream(params, buffer)
	if err != nil {
		portaudio.Terminate()
		return fmt.Errorf("failed to open stream: %v", err)
	}
	defer stream.Close()

	if err := stream.Start(); err != nil {
		portaudio.Terminate()
		return fmt.Errorf("failed to start stream: %v", err)
	}

	// Calibrate for 2 seconds
	time.Sleep(2 * time.Second)

	if err := stream.Stop(); err != nil {
		portaudio.Terminate()
		return fmt.Errorf("failed to stop stream: %v", err)
	}

	fmt.Println("✓ Calibration complete")
	return nil
}

// int16ToBytes converts int16 slice to byte slice
func int16ToBytes(samples []int16) []byte {
	buf := new(bytes.Buffer)
	binary.Write(buf, binary.LittleEndian, samples)
	return buf.Bytes()
}

// listenAndTranscribe starts listening and transcribing using AWS Transcribe Streaming
func (s *SpeechToText) listenAndTranscribe() error {
	s.isRunning = true
	defer func() {
		s.isRunning = false
	}()

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("SPEECH-TO-TEXT LIVE TRANSLATION")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("\nListening... Speak into your microphone.")
	fmt.Println("Press Ctrl+C to stop.\n")

	// Get AWS config (from token or local credentials)
	cfg, err := s.getAWSConfig()
	if err != nil {
		return fmt.Errorf("failed to get AWS config: %v", err)
	}

	// Create AWS Transcribe Streaming client
	transcribeClient := transcribestreaming.NewFromConfig(cfg)
	s.transcribeClient = transcribeClient

	// Get device info
	var device *portaudio.DeviceInfo
	if s.deviceIndex >= 0 {
		allDevices, err := portaudio.Devices()
		if err != nil {
			return fmt.Errorf("failed to get devices: %v", err)
		}
		if s.deviceIndex >= len(allDevices) {
			return fmt.Errorf("device index %d out of range", s.deviceIndex)
		}
		device = allDevices[s.deviceIndex]
	} else {
		device, err = portaudio.DefaultInputDevice()
		if err != nil {
			return fmt.Errorf("failed to get default device: %v", err)
		}
	}

	// Create stream parameters
	params := portaudio.LowLatencyParameters(device, nil)
	params.Input.Channels = numChannels
	params.SampleRate = sampleRate
	params.FramesPerBuffer = framesPerBuffer

	// Open audio stream
	buffer := make([]int16, framesPerBuffer)
	stream, err := portaudio.OpenStream(params, buffer)
	if err != nil {
		return fmt.Errorf("failed to open stream: %v", err)
	}
	s.stream = stream
	defer stream.Close()

	if err := stream.Start(); err != nil {
		return fmt.Errorf("failed to start stream: %v", err)
	}
	defer stream.Stop()

	// Start AWS Transcribe streaming session
	return s.startTranscribeStream(buffer)
}

// startTranscribeStream starts a streaming transcription session with AWS Transcribe

// startTranscribeStream starts a streaming transcription session with AWS Transcribe
func (s *SpeechToText) startTranscribeStream(buffer []int16) error {
	// Start transcription stream
	stream, err := s.transcribeClient.StartStreamTranscription(s.ctx, &transcribestreaming.StartStreamTranscriptionInput{
		LanguageCode:         types.LanguageCodeEnUs,
		MediaSampleRateHertz: aws.Int32(sampleRate),
		MediaEncoding:        types.MediaEncodingPcm,
	})
	if err != nil {
		return fmt.Errorf("failed to start transcription stream: %v", err)
	}

	// Get the event stream
	eventStream := stream.GetStream()

	// Channel to signal completion
	done := make(chan error, 1)

	// Start goroutine to handle transcription results
	go func() {
		defer close(done)
		
		for event := range eventStream.Events() {
			switch e := event.(type) {
			case *types.TranscriptResultStreamMemberTranscriptEvent:
				// Process transcription results
				for _, result := range e.Value.Transcript.Results {
					if !result.IsPartial {
						// Only process final results
						if len(result.Alternatives) > 0 && result.Alternatives[0].Transcript != nil {
							transcript := *result.Alternatives[0].Transcript
							if strings.TrimSpace(transcript) != "" {
								timestamp := time.Now().Format("15:04:05")
								fmt.Printf("[%s] Recognized: %s\n", timestamp, transcript)

								// Broadcast to server
								if s.wsConn != nil {
									data := map[string]interface{}{
										"text":      transcript,
										"timestamp": timestamp,
									}
									if s.apiKey != "" {
										data["api_key"] = s.apiKey
									}
									// Send WebSocket message
									if err := s.sendMessage(MessageTypeNewText, data); err != nil {
										log.Printf("Failed to send message: %v", err)
									}
								} else {
									fmt.Println("⚠ Not connected to server. Attempting to reconnect...")
									s.connectToServer()
								}
							}
						}
					}
				}
			default:
				// Handle other event types if needed
			}

			if !s.isRunning {
				return
			}
		}
		
		// Check for errors
		if err := eventStream.Err(); err != nil {
			done <- err
		}
	}()

	// Main audio capture loop
	go func() {
		for {
			select {
			case <-s.ctx.Done():
				// Context cancelled; close event stream and exit
				eventStream.Close()
				return
			case <-s.shutdownRequested:
				// Graceful shutdown requested: perform one final read/send if possible
				if s.stream != nil {
					if err := s.stream.Read(); err == nil {
						audioBytes := int16ToBytes(buffer)
						// Use background context for the final send so it can complete
						if err := eventStream.Send(context.Background(), &types.AudioStreamMemberAudioEvent{
							Value: types.AudioEvent{AudioChunk: audioBytes},
						}); err != nil {
							log.Printf("Error sending final audio chunk: %v", err)
						}
					}
				}
				eventStream.Close()
				return
			default:
				// Read audio data
				if err := s.stream.Read(); err != nil {
					log.Printf("Error reading from stream: %v", err)
					continue
				}

				// Convert int16 buffer to bytes
				audioBytes := int16ToBytes(buffer)

				// Send audio to transcription service
				err := eventStream.Send(s.ctx, &types.AudioStreamMemberAudioEvent{
					Value: types.AudioEvent{
						AudioChunk: audioBytes,
					},
				})
				if err != nil {
					log.Printf("Error sending audio: %v", err)
					// If we get an error and shutdown was requested, exit
					select {
					case <-s.shutdownRequested:
						eventStream.Close()
						return
					default:
					}
				}
			}
		}
	}()

	// Wait for completion or error
	err = <-done
	if err != nil {
		return fmt.Errorf("transcription error: %v", err)
	}

	return nil
}
// Run executes the main application logic
func (s *SpeechToText) Run() error {
	// Check API key configuration
	if s.apiKey == "" && !s.useLocalToken {
		fmt.Println("\n⚠ Warning: API_KEY not set in environment.")
		fmt.Println("Communication with the server will not be secured.")
		fmt.Println("Token generation will not be available.")
		fmt.Println("Set API_KEY in .env file for production use.\n")
	}

	// Connect to server
	if err := s.connectToServer(); err != nil {
		fmt.Println("\n⚠ Warning: Could not connect to server.")
		// When verbose, show the underlying error and helpful troubleshooting hints
		if s.verbose {
			fmt.Fprintf(os.Stderr, "Connection error details: %v\n", err)
		}

		fmt.Print("Continue anyway? (y/n): ")

		var response string
		fmt.Scanln(&response)
		if strings.ToLower(response) != "y" {
			return nil
		}
	}

	// Request AWS credentials token if not using local credentials
	if !s.useLocalToken {
		fmt.Println("Requesting AWS credentials from server...")
		if err := s.requestToken(); err != nil {
			return fmt.Errorf("failed to obtain AWS token: %v", err)
		}
		
		// Start token refresher in background
		s.startTokenRefresher()
	}

	// Calibrate microphone
	if err := s.calibrateMicrophone(); err != nil {
		return fmt.Errorf("calibration failed: %v", err)
	}

	// Start listening and transcribing
	if err := s.listenAndTranscribe(); err != nil {
		return fmt.Errorf("listen and transcribe failed: %v", err)
	}

	// Cleanup
	if s.wsConn != nil {
		s.wsConn.Close()
	}
	portaudio.Terminate()

	fmt.Println("✓ Speech recognition stopped.")
	return nil
}

// GracefulStop requests the speech-to-text process finish current work and stop.
// It closes the shutdownRequested channel once which is observed by the audio loop
// so the client will attempt to send one final audio chunk before closing.
func (s *SpeechToText) GracefulStop() {
	s.shutdownOnce.Do(func() {
		close(s.shutdownRequested)
	})
	s.connMu.Lock()
	s.isRunning = false
	s.connMu.Unlock()

	// Attempt a polite WebSocket close so the remote end knows we're shutting down.
	if s.wsConn != nil {
		// Best-effort: send a close control message, then close the connection.
		_ = s.wsConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, "client shutdown"))
		s.wsConn.Close()
	}
}

func main() {
	// Load environment variables
	godotenv.Load()

	// Parse command-line flags
	listDevices := flag.Bool("l", false, "List all available audio input devices and exit")
	listDevicesLong := flag.Bool("list-devices", false, "List all available audio input devices and exit")
	deviceSpec := flag.String("d", "", "Select audio input device by index or name")
	deviceSpecLong := flag.String("device", "", "Select audio input device by index or name")
    verboseShort := flag.Bool("v", false, "Enable verbose debug logging")
    verboseLong := flag.Bool("verbose", false, "Enable verbose debug logging")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options] [server_url]\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Speech-to-Text Application for Live Translation\n\n")
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExamples:\n")
		fmt.Fprintf(os.Stderr, "  %s                              # Use default device and server\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s http://example.com:5050      # Connect to remote server\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -l                           # List available audio devices\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d 1                         # Use audio device with index 1\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d \"USB Microphone\"          # Use audio device by name\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d 1 http://example.com:5050 # Use device 1 with remote server\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "\nEnvironment Variables:\n")
		fmt.Fprintf(os.Stderr, "  LT_AUDIO_DEVICE     Set default audio device (index or name)\n")
		fmt.Fprintf(os.Stderr, "  LT_LOCAL_TOKEN      Use local AWS credentials instead of server token (true/false)\n")
		fmt.Fprintf(os.Stderr, "  API_KEY             API key for server authentication\n")
		fmt.Fprintf(os.Stderr, "  AWS_DEFAULT_REGION  AWS region for Transcribe (default: us-east-1)\n")
		fmt.Fprintf(os.Stderr, "  AWS_ACCESS_KEY_ID   AWS access key (when LT_LOCAL_TOKEN=true)\n")
		fmt.Fprintf(os.Stderr, "  AWS_SECRET_ACCESS_KEY  AWS secret key (when LT_LOCAL_TOKEN=true)\n")
	}

	flag.Parse()

	// Verbose flag
	verbose := *verboseShort || *verboseLong

	// Handle list devices flag
	if *listDevices || *listDevicesLong {
		if err := listAudioDevices(); err != nil {
			log.Fatalf("Error: %v", err)
		}
		return
	}

	// Get server URL
	serverURL := "http://localhost:5050/ws"
	if flag.NArg() > 0 {
		serverURL = flag.Arg(0)
	}

	// Determine device specification
	device := *deviceSpec
	if device == "" {
		device = *deviceSpecLong
	}
	if device == "" {
		device = os.Getenv("LT_AUDIO_DEVICE")
	}

	// Parse device specification
	deviceIndex := -1
	deviceName := ""

	if device != "" {
		// Try to parse as integer
		if idx, err := strconv.Atoi(device); err == nil {
			deviceIndex = idx
		} else {
			// It's a device name
			deviceName = device
			idx, err := findDeviceIndexByName(deviceName)
			if err != nil {
				fmt.Printf("⚠ Warning: Audio device '%s' not found.\n", deviceName)
				fmt.Println("Use -l to list available devices. Using default device.")
				deviceIndex = -1
			} else {
				deviceIndex = idx
			}
		}
	}

	// Get API key, AWS region, and local token flag
	apiKey := os.Getenv("API_KEY")
	awsRegion := os.Getenv("AWS_DEFAULT_REGION")
	if awsRegion == "" {
		awsRegion = "us-east-1" // Default region
	}
	
	// Check if using local AWS credentials
	useLocalToken := strings.ToLower(os.Getenv("LT_LOCAL_TOKEN")) == "true"

	// Print configuration
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("Live Translation - Speech-to-Text")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("\nServer URL: %s\n", serverURL)
	fmt.Printf("AWS Region: %s\n", awsRegion)
	if useLocalToken {
		fmt.Println("Token Mode: Local AWS credentials")
	} else {
		fmt.Println("Token Mode: Server-provided session credentials")
	}
if verbose {
    fmt.Println("Verbose: true")
}
	if deviceIndex >= 0 {
		if deviceName != "" {
			fmt.Printf("Audio Device: %s (index %d)\n", deviceName, deviceIndex)
		} else {
			fmt.Printf("Audio Device Index: %d\n", deviceIndex)
		}
	} else {
		fmt.Println("Audio Device: Default")
	}

	// Setup context with cancellation
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Create the application
	app, err := NewSpeechToText(ctx, serverURL, apiKey, deviceIndex, awsRegion, verbose, useLocalToken)
	if err != nil {
		log.Fatalf("Error creating application: %v", err)
	}

	// Handle interrupt signals (Ctrl-C / SIGTERM) and request graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		fmt.Println("\n\nStopping speech recognition...")
		app.GracefulStop()
		// Give a short window for final audio to be sent, then cancel context to force cleanup
		time.Sleep(500 * time.Millisecond)
		cancel()
	}()

	// Ctrl-C / SIGTERM handling is the preferred way to stop the program.

	// Run the application
	if err := app.Run(); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
