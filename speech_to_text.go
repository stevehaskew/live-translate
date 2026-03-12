package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

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
	Status      string         `json:"status"`
	Credentials AWSCredentials `json:"credentials"`
	Region      string         `json:"region"`
	Error       string         `json:"error,omitempty"`
}

// AWSCredentials represents temporary AWS credentials
type AWSCredentials struct {
	AccessKeyId     string `json:"AccessKeyId"`
	SecretAccessKey string `json:"SecretAccessKey"`
	SessionToken    string `json:"SessionToken"`
	Expiration      string `json:"Expiration"`
}

const (
	sampleRate             = 16000
	framesPerBuffer        = 8000 // 0.5 seconds of audio
	numChannels            = 1
	phraseTimeLimit        = 5 * time.Second
	tokenRefreshInterval   = 20 * time.Minute // Refresh token every 20 minutes
	maxRetries             = 5                // Maximum number of retry attempts for websocket connection
	initialRetryDelay      = 1 * time.Second  // Initial retry delay
	maxTokenRefreshRetries = 3                // Maximum retries for token refresh during transcription
)

// Error patterns for detecting specific error conditions
var (
	tokenExpiredPatterns = []string{
		"expiredtokenexception",                                 // AWS SDK exception type
		"the security token included in the request is expired", // Full AWS error message
		"token has expired",                                     // Generic token expiration
		"security token expired",                                // Alternative AWS message format
		"credentials have expired",                              // AWS credentials expiration
	}

	websocketClosedPatterns = []string{
		"websocket: close sent",            // Websocket already closed
		"websocket: close received",        // Received close frame
		"use of closed network connection", // Network connection closed
		"broken pipe",                      // Broken connection
		"connection reset by peer",         // Connection reset
		"websocket: connection closed",     // Connection closed
	}
)

// TokenExpiredError indicates that the AWS credentials have expired
type TokenExpiredError struct {
	Err error
}

func (e *TokenExpiredError) Error() string {
	return fmt.Sprintf("AWS token expired: %v", e.Err)
}

func (e *TokenExpiredError) Unwrap() error {
	return e.Err
}

// containsAnyPattern checks if the error string contains any of the given patterns
func containsAnyPattern(errStr string, patterns []string) bool {
	for _, pattern := range patterns {
		if strings.Contains(errStr, pattern) {
			return true
		}
	}
	return false
}

// isTokenExpiredError checks if the error indicates an expired AWS token
func isTokenExpiredError(err error) bool {
	if err == nil {
		return false
	}
	errStr := strings.ToLower(err.Error())
	return containsAnyPattern(errStr, tokenExpiredPatterns)
}

// isWebSocketClosedError checks if the error indicates a closed or broken websocket connection
func isWebSocketClosedError(err error) bool {
	if err == nil {
		return false
	}
	errStr := strings.ToLower(err.Error())
	return containsAnyPattern(errStr, websocketClosedPatterns)
}

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
	retryCount        int // Current retry attempt count
	retryMutex        sync.Mutex
	// engine is the pluggable speech-to-text backend (AWS or Whisper)
	engine     TranscriptionEngine
	engineName string // "aws" or "local"
	modelPath  string // resolved whisper model path (local engine only)
}

// NewSpeechToText creates a new SpeechToText instance
func NewSpeechToText(ctx context.Context, serverURL, apiKey string, deviceIndex int, awsRegion string, verbose bool, useLocalToken bool, engineName string) (*SpeechToText, error) {
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
		engineName:        engineName,
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
				Name:     strings.TrimSpace(deviceInfo.Name),
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
		fmt.Printf("%d: \"%s\"\n", device.Index, device.Name)
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

// calculateRetryDelay calculates the exponential backoff delay for retry attempts
func calculateRetryDelay(retryCount int) time.Duration {
	// Exponential backoff: 1s, 2s, 4s, 8s, 16s
	delay := initialRetryDelay * time.Duration(1<<uint(retryCount))
	// Cap at 16 seconds to avoid very long waits
	if delay > 16*time.Second {
		delay = 16 * time.Second
	}
	return delay
}

// connectToServerWithRetry attempts to connect to the server with retry logic
func (s *SpeechToText) connectToServerWithRetry() error {
	var lastErr error

	for attempt := 0; attempt <= maxRetries; attempt++ {
		s.retryMutex.Lock()
		s.retryCount = attempt
		s.retryMutex.Unlock()

		if attempt > 0 {
			delay := calculateRetryDelay(attempt - 1)
			fmt.Printf("Retry attempt %d/%d after %v...\n", attempt, maxRetries, delay)

			// Wait with cancellation support
			select {
			case <-time.After(delay):
			case <-s.ctx.Done():
				return fmt.Errorf("connection cancelled")
			case <-s.shutdownRequested:
				return fmt.Errorf("shutdown requested")
			}
		}

		err := s.connectToServer()
		if err == nil {
			// Reset retry count on successful connection
			s.retryMutex.Lock()
			s.retryCount = 0
			s.retryMutex.Unlock()
			return nil
		}

		lastErr = err

		if attempt < maxRetries {
			if s.verbose {
				fmt.Printf("Connection failed: %v\n", err)
			} else {
				fmt.Printf("Connection failed, will retry...\n")
			}
		}
	}

	// All retries exhausted
	fmt.Printf("\n✖ Failed to connect after %d attempts\n", maxRetries+1)
	return fmt.Errorf("exhausted all retry attempts: %v", lastErr)
}

// handleWebSocketReconnection handles reconnection and token refresh after a websocket failure
func (s *SpeechToText) handleWebSocketReconnection() error {
	// Close the broken connection if still open
	if s.wsConn != nil {
		s.wsConn.Close()
		s.wsConn = nil
	}

	// Try to reconnect with retry logic
	if reconnectErr := s.connectToServerWithRetry(); reconnectErr != nil {
		return fmt.Errorf("failed to reconnect: %v", reconnectErr)
	}

	fmt.Println("✓ Reconnected successfully")

	// If we're not using local tokens, request a new token after reconnection
	if !s.useLocalToken {
		fmt.Println("Requesting new AWS credentials...")
		if tokenErr := s.requestToken(); tokenErr != nil {
			fmt.Printf("⚠ Failed to obtain token after reconnect: %v\n", tokenErr)
			return fmt.Errorf("failed to obtain token: %v", tokenErr)
		}
	}

	return nil
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
				fmt.Println("WebSocket closed normally")
				return
			}

			// Unexpected websocket closure - attempt to reconnect
			fmt.Printf("WebSocket connection lost: %v\n", err)
			fmt.Println("Attempting to reconnect...")

			// Handle reconnection and token refresh
			if reconnectErr := s.handleWebSocketReconnection(); reconnectErr != nil {
				log.Printf("Reconnection failed: %v", reconnectErr)
				fmt.Println("\n✖ Unable to reconnect to server. Exiting...")
				// Signal the application to stop
				s.GracefulStop()
				return
			}

			// Continue reading messages from the new connection
			continue
		}

		if s.verbose {
			fmt.Printf("Received message: %s\n", msg.Type)
		}

		// Handle incoming messages
		switch msg.Type {
		case MessageTypeConnectionStatus:
			if awsAvailable, ok := msg.Data["aws_available"].(bool); ok {
				fmt.Printf("Server connection status: aws_available=%v\n", awsAvailable)
			}
		case MessageTypeTokenResponse:
			// Handle token response
			var data map[string]interface{}
			data = msg.Data
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
					case s.tokenErrorChan <- fmt.Errorf("%s", errorMsg):
					default:
					}
				}
			} else {
				// Unknown token response format
				if s.tokenErrorChan != nil {
					select {
					case s.tokenErrorChan <- fmt.Errorf("unknown token response format"):
					default:
					}
				}
			}
		case MessageTypeError:
			if errMsg, ok := msg.Data["message"].(string); ok {
				fmt.Printf("Server error: %s\n", errMsg)
				// Check if this is a token error
				if s.tokenErrorChan != nil {
					select {
					case s.tokenErrorChan <- fmt.Errorf("%s", errMsg):
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

// listenAndTranscribe starts listening and transcribing using the configured engine.
func (s *SpeechToText) listenAndTranscribe() error {
	s.isRunning = true
	defer func() {
		s.isRunning = false
	}()

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("SPEECH-TO-TEXT LIVE TRANSLATION")
	fmt.Println(strings.Repeat("=", 60))
	if s.engineName == "local" {
		fmt.Printf("Engine : Local (whisper.cpp)\n")
		fmt.Printf("Model  : %s\n", filepath.Base(s.modelPath))
	} else {
		fmt.Printf("Engine : AWS Transcribe Streaming\n")
		fmt.Printf("Region : %s\n", s.awsRegion)
	}
	fmt.Println("\nListening... Speak into your microphone.")
	fmt.Println("Press Ctrl+C to stop.")

	// Get device info
	var device *portaudio.DeviceInfo
	var err error
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
	paStream, err := portaudio.OpenStream(params, buffer)
	if err != nil {
		return fmt.Errorf("failed to open stream: %v", err)
	}
	s.stream = paStream
	defer paStream.Close()

	if err := paStream.Start(); err != nil {
		return fmt.Errorf("failed to start stream: %v", err)
	}
	defer paStream.Stop()

	// Create a cancellable context for the engine
	engineCtx, cancelEngine := context.WithCancel(s.ctx)
	defer cancelEngine()

	// Audio channel — PortAudio reads are pushed here
	audioIn := make(chan []int16, 32)

	// Start the engine
	textOut, err := s.engine.Start(engineCtx, audioIn)
	if err != nil {
		return fmt.Errorf("failed to start transcription engine: %v", err)
	}

	// Goroutine: read PortAudio → audioIn channel
	go func() {
		defer close(audioIn)
		for {
			select {
			case <-engineCtx.Done():
				return
			case <-s.shutdownRequested:
				// Stream has already been stopped in GracefulStop; just exit.
				return
			default:
				if err := s.stream.Read(); err != nil {
					// If shutdown was requested the stream was stopped intentionally;
					// exit cleanly without logging noise.
					select {
					case <-s.shutdownRequested:
						return
					default:
					}
					log.Printf("Error reading from stream: %v", err)
					continue
				}
				chunk := make([]int16, len(buffer))
				copy(chunk, buffer)
				select {
				case audioIn <- chunk:
				case <-engineCtx.Done():
					return
				}
			}
		}
	}()

	// Read transcripts from engine → send to server.
	// Use a select so context cancellation can break the loop even if the
	// engine channel is slow to close (e.g. blocked inside whisper inference).
loop:
	for {
		select {
		case text, ok := <-textOut:
			if !ok {
				break loop
			}
			timestamp := time.Now().Format("15:04:05")
			fmt.Printf("[%s] Recognized: %s\n", timestamp, text)

			// Broadcast to server
			if s.wsConn != nil {
				data := map[string]interface{}{
					"text":      text,
					"timestamp": timestamp,
				}
				if s.apiKey != "" {
					data["api_key"] = s.apiKey
				}
				if err := s.sendMessage(MessageTypeNewText, data); err != nil {
					log.Printf("Failed to send message: %v", err)
					if isWebSocketClosedError(err) {
						// Don't attempt reconnection during shutdown
						if engineCtx.Err() != nil {
							break loop
						}
						fmt.Println("⚠ WebSocket connection broken. Attempting to reconnect...")
						if reconnectErr := s.handleWebSocketReconnection(); reconnectErr != nil {
							log.Printf("Reconnection failed: %v", reconnectErr)
							fmt.Println("⚠ Unable to reconnect. Transcription continues but messages won't be sent.")
						}
					}
				}
			} else {
				if engineCtx.Err() == nil {
					fmt.Println("⚠ Not connected to server. Attempting to reconnect...")
					if err := s.connectToServerWithRetry(); err != nil {
						log.Printf("Failed to reconnect: %v", err)
					}
				}
			}
		case <-engineCtx.Done():
			break loop
		}
	}

	return nil
}

// Run executes the main application logic
func (s *SpeechToText) Run() error {
	// Check API key configuration
	if s.apiKey == "" && s.engineName == "aws" && !s.useLocalToken {
		fmt.Println("\n⚠ Warning: API_KEY not set in environment.")
		fmt.Println("Communication with the server will not be secured.")
		fmt.Println("Token generation will not be available.")
		fmt.Println("Set API_KEY in .env file for production use.")
	}

	// Connect to server with retry logic
	if err := s.connectToServerWithRetry(); err != nil {
		fmt.Println("\n⚠ Warning: Could not connect to server after multiple attempts.")
		if s.verbose {
			fmt.Fprintf(os.Stderr, "Connection error details: %v\n", err)
		}

		fmt.Print("Continue anyway? (y/n): ")

		var response string
		fmt.Scanln(&response)
		if strings.ToLower(response) != "y" {
			return fmt.Errorf("unable to connect to server: %v", err)
		}
	}

	// Request AWS credentials token if using AWS engine and not using local credentials
	if s.engineName == "aws" && !s.useLocalToken && s.wsConn != nil {
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
	if s.engine != nil {
		s.engine.Close()
	}
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

	// Stop the PortAudio stream immediately so any blocked Read() call returns.
	// This unblocks the audio goroutine without waiting for the next buffer.
	if s.stream != nil {
		s.stream.Stop()
	}

	// Attempt a polite WebSocket close so the remote end knows we're shutting down.
	if s.wsConn != nil {
		// Best-effort: send a close control message, then close the connection.
		_ = s.wsConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, "client shutdown"))
		s.wsConn.Close()
	}
}

func main() {
	// Load environment variables from user home config (~/.yot/config)
	if home, err := os.UserHomeDir(); err == nil {
		_ = godotenv.Load(filepath.Join(home, ".yot", "config"))
	}
	// Also load project .env (if present)
	godotenv.Load()

	// Parse command-line flags
	listDevices := flag.Bool("l", false, "List all available audio input devices and exit")
	listDevicesLong := flag.Bool("list-devices", false, "List all available audio input devices and exit")
	deviceSpec := flag.String("d", "", "Select audio input device by index or name")
	deviceSpecLong := flag.String("device", "", "Select audio input device by index or name")
	verboseShort := flag.Bool("v", false, "Enable verbose debug logging")
	verboseLong := flag.Bool("verbose", false, "Enable verbose debug logging")
	engineFlag := flag.String("engine", "", "STT engine: 'local' (whisper.cpp, default) or 'aws' (AWS Transcribe)")
	modelFlag := flag.String("model", "", "Path to a whisper.cpp ggml model file (overrides --model-size)")
	modelSizeFlag := flag.String("model-size", "", "Whisper model size to auto-download: tiny.en, base.en, small.en (default: base.en)")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options] [server_url]\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Speech-to-Text Application for Live Translation\n\n")
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExamples:\n")
		fmt.Fprintf(os.Stderr, "  %s                              # Use default device and server (local whisper)\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --engine=aws                 # Use AWS Transcribe instead of local\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --model-size=tiny.en          # Use smaller/faster whisper model\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --model /path/to/ggml.bin     # Use a custom whisper model file\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s http://example.com:5050       # Connect to remote server\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -l                            # List available audio devices\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d 1                          # Use audio device with index 1\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d \"USB Microphone\"           # Use audio device by name\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -d 1 http://example.com:5050  # Use device 1 with remote server\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "\nEnvironment Variables:\n")
		fmt.Fprintf(os.Stderr, "  LT_ENGINE           STT engine: 'local' or 'aws' (default: local)\n")
		fmt.Fprintf(os.Stderr, "  LT_WHISPER_MODEL    Path to a custom whisper model file\n")
		fmt.Fprintf(os.Stderr, "  LT_WHISPER_MODEL_SIZE  Model size to auto-download (default: base.en)\n")
		fmt.Fprintf(os.Stderr, "  LT_AUDIO_DEVICE     Set default audio device (index or name)\n")
		fmt.Fprintf(os.Stderr, "  LT_LOCAL_TOKEN      Use local AWS credentials instead of server token (true/false)\n")
		fmt.Fprintf(os.Stderr, "  LT_ENDPOINT         Server endpoint (e.g. wss://api.mychurch.yot.church)\n")
		fmt.Fprintf(os.Stderr, "  API_KEY             API key for server authentication\n")
		fmt.Fprintf(os.Stderr, "  AWS_DEFAULT_REGION  AWS region for Transcribe (default: eu-west-2)\n")
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
	// Priority: CLI arg > LT_ENDPOINT env var > default
	if flag.NArg() > 0 {
		serverURL = flag.Arg(0)
	} else if envEndpoint := os.Getenv("LT_ENDPOINT"); envEndpoint != "" {
		serverURL = envEndpoint
	}

	// If the provided serverURL doesn't contain an explicit scheme, assume http://
	if !strings.Contains(serverURL, "://") {
		serverURL = "http://" + serverURL
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
		awsRegion = "eu-west-2" // Default region
	}

	// Check if using local AWS credentials
	useLocalToken := strings.ToLower(os.Getenv("LT_LOCAL_TOKEN")) == "true"

	// Resolve engine choice: flag > env > default
	engineName := *engineFlag
	if engineName == "" {
		engineName = os.Getenv("LT_ENGINE")
	}
	if engineName == "" {
		engineName = "local"
	}
	if engineName != "local" && engineName != "aws" {
		log.Fatalf("Invalid --engine value %q (must be 'local' or 'aws')", engineName)
	}

	// Resolve whisper model path / size (only relevant for local engine)
	modelPath := *modelFlag
	if modelPath == "" {
		modelPath = os.Getenv("LT_WHISPER_MODEL")
	}
	modelSize := *modelSizeFlag
	if modelSize == "" {
		modelSize = os.Getenv("LT_WHISPER_MODEL_SIZE")
	}
	if modelSize == "" {
		modelSize = "base.en"
	}

	// Print configuration
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("Live Translation - Speech-to-Text")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("\nServer URL: %s\n", serverURL)
	if engineName == "aws" {
		fmt.Printf("Engine: AWS Transcribe Streaming\n")
		fmt.Printf("AWS Region: %s\n", awsRegion)
		if useLocalToken {
			fmt.Println("Token Mode: Local AWS credentials")
		} else {
			fmt.Println("Token Mode: Server-provided session credentials")
		}
	} else {
		fmt.Printf("Engine: Local (whisper.cpp)\n")
		if modelPath != "" {
			fmt.Printf("Model: %s\n", modelPath)
		} else {
			fmt.Printf("Model size: %s (auto-download to ~/.yot/models/)\n", modelSize)
		}
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
	app, err := NewSpeechToText(ctx, serverURL, apiKey, deviceIndex, awsRegion, verbose, useLocalToken, engineName)
	if err != nil {
		log.Fatalf("Error creating application: %v", err)
	}

	// Initialise the chosen transcription engine
	switch engineName {
	case "local":
		// Ensure the model is available (auto-download if needed)
		resolvedModel, err := EnsureModel(modelSize, modelPath)
		if err != nil {
			log.Fatalf("Failed to prepare whisper model: %v", err)
		}
		engine, err := NewWhisperEngine(resolvedModel, "en")
		if err != nil {
			log.Fatalf("Failed to initialise whisper engine: %v", err)
		}
		app.engine = engine
		app.modelPath = resolvedModel
	case "aws":
		app.engine = NewAWSEngine(app)
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
		// Second Ctrl-C (or SIGTERM) hard-kills the process if graceful shutdown stalls.
		<-sigChan
		fmt.Println("Force quit.")
		os.Exit(1)
	}()

	// Run the application
	if err := app.Run(); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
