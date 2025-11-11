package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming"
	"github.com/aws/aws-sdk-go-v2/service/transcribestreaming/types"
	"github.com/gordonklaus/portaudio"
	"github.com/joho/godotenv"
	socketio_client "github.com/zishang520/socket.io-client-go/socket"
)

const (
	sampleRate      = 16000
	framesPerBuffer = 8000 // 0.5 seconds of audio
	numChannels     = 1
	phraseTimeLimit = 10 * time.Second
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
	client            *socketio_client.Socket
	stream            *portaudio.Stream
	transcribeClient  *transcribestreaming.Client
	isRunning         bool
	ctx               context.Context
	awsRegion         string
}

// NewSpeechToText creates a new SpeechToText instance
func NewSpeechToText(ctx context.Context, serverURL, apiKey string, deviceIndex int, awsRegion string) (*SpeechToText, error) {
	return &SpeechToText{
		ctx:         ctx,
		serverURL:   serverURL,
		apiKey:      apiKey,
		deviceIndex: deviceIndex,
		isRunning:   false,
		awsRegion:   awsRegion,
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

	client, err := socketio_client.Connect(s.serverURL, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to server: %v", err)
	}

	s.client = client

	// Setup event handlers
	client.On("connect", func(args ...interface{}) {
		fmt.Printf("✓ Connected to server at %s\n", s.serverURL)
	})

	client.On("disconnect", func(args ...interface{}) {
		fmt.Println("✗ Disconnected from server")
	})

	client.On("connect_error", func(args ...interface{}) {
		fmt.Printf("✗ Connection error: %v\n", args)
	})

	// Optional server-side connection acknowledgement (from server.py -> connection_status)
	client.On("connection_status", func(args ...interface{}) {
		fmt.Printf("Server connection_status: %v\n", args)
	})

	// Wait a bit for connection to establish
	time.Sleep(1 * time.Second)

	return nil
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

	// Load AWS config
	cfg, err := config.LoadDefaultConfig(s.ctx, config.WithRegion(s.awsRegion))
	if err != nil {
		return fmt.Errorf("failed to load AWS config: %v", err)
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
								if s.client != nil {
									payload := map[string]interface{}{
										"text":      transcript,
										"timestamp": timestamp,
									}
									if s.apiKey != "" {
										payload["api_key"] = s.apiKey
									}
									// Emit event to server
									s.client.Emit("new_text", payload)
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
		for s.isRunning {
			select {
			case <-s.ctx.Done():
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
					if !s.isRunning {
						return
					}
				}
			}
		}
		eventStream.Close()
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
	if s.apiKey == "" {
		fmt.Println("\n⚠ Warning: API_KEY not set in environment.")
		fmt.Println("Communication with the server will not be secured.")
		fmt.Println("Set API_KEY in .env file for production use.\n")
	}

	// Connect to server
	if err := s.connectToServer(); err != nil {
		fmt.Println("\n⚠ Warning: Could not connect to server.")
		fmt.Println("Make sure the Flask server is running.")
		fmt.Print("Continue anyway? (y/n): ")

		var response string
		fmt.Scanln(&response)
		if strings.ToLower(response) != "y" {
			return nil
		}
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
	if s.client != nil {
		s.client.Close()
	}
	portaudio.Terminate()

	fmt.Println("✓ Speech recognition stopped.")
	return nil
}

func main() {
	// Load environment variables
	godotenv.Load()

	// Parse command-line flags
	listDevices := flag.Bool("l", false, "List all available audio input devices and exit")
	listDevicesLong := flag.Bool("list-devices", false, "List all available audio input devices and exit")
	deviceSpec := flag.String("d", "", "Select audio input device by index or name")
	deviceSpecLong := flag.String("device", "", "Select audio input device by index or name")

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
		fmt.Fprintf(os.Stderr, "  API_KEY             API key for server authentication\n")
		fmt.Fprintf(os.Stderr, "  AWS_DEFAULT_REGION  AWS region for Transcribe (default: us-east-1)\n")
		fmt.Fprintf(os.Stderr, "  AWS_ACCESS_KEY_ID   AWS access key (or use AWS CLI/IAM role)\n")
		fmt.Fprintf(os.Stderr, "  AWS_SECRET_ACCESS_KEY  AWS secret key (or use AWS CLI/IAM role)\n")
	}

	flag.Parse()

	// Handle list devices flag
	if *listDevices || *listDevicesLong {
		if err := listAudioDevices(); err != nil {
			log.Fatalf("Error: %v", err)
		}
		return
	}

	// Get server URL
	serverURL := "http://localhost:5050"
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

	// Get API key and AWS region
	apiKey := os.Getenv("API_KEY")
	awsRegion := os.Getenv("AWS_DEFAULT_REGION")
	if awsRegion == "" {
		awsRegion = "us-east-1" // Default region
	}

	// Print configuration
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("Live Translation - Speech-to-Text")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("\nServer URL: %s\n", serverURL)
	fmt.Printf("AWS Region: %s\n", awsRegion)
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

	// Handle interrupt signals
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		fmt.Println("\n\nStopping speech recognition...")
		cancel()
	}()

	// Create and run the application
	app, err := NewSpeechToText(ctx, serverURL, apiKey, deviceIndex, awsRegion)
	if err != nil {
		log.Fatalf("Error creating application: %v", err)
	}

	// Run the application
	if err := app.Run(); err != nil {
		log.Fatalf("Error: %v", err)
	}
}
