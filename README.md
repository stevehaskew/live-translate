# Live Translation

A real-time speech-to-text translation application that captures audio from a microphone, converts it to text, and provides live translations to web clients in their preferred languages.

## Features

- 🎤 **Speech-to-Text**: Real-time audio capture and speech recognition
- 🌍 **Multi-Language Translation**: Support for 15+ languages via AWS Translate
- 🔄 **Real-Time Updates**: WebSocket-based live streaming to connected clients
- 💻 **Web Interface**: Clean, modern UI for viewing translations
- 🍎 **Mac Compatible**: Optimized for macOS with PyAudio support
- ⚡ **Dual Mode**: Works with or without AWS Translate

## Architecture

The application consists of two main components:

1. **Speech-to-Text Application** (`speech_to_text.py`): Captures audio from the microphone and converts speech to text using Google Speech Recognition API
2. **Web Server** (`server.py`): Flask-based server with WebSocket support that receives text, translates it using AWS Translate, and broadcasts to connected web clients

## Requirements

- Python 3.9+ (tested on Python 3.9-3.12)
- Microphone (for speech input)
- AWS Account (optional, for translation features)
- Internet connection (for speech recognition and translation APIs)

### macOS Specific Requirements

On macOS, you'll need to install PortAudio for PyAudio:

```bash
brew install portaudio
```

## Installation

1. **Clone the repository**:
```bash
git clone https://github.com/stevehaskew/live-translate.git
cd live-translate
```

2. **Quick Start (Recommended for macOS/Linux)**:
```bash
./start.sh
```
This script will automatically:
- Check Python version
- Install PortAudio on macOS (if needed)
- Create a virtual environment
- Install dependencies
- Provide instructions to start the application

3. **Manual Installation**:

Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**:

Create a `.env` file from the example:
```bash
cp .env.example .env
```

Edit `.env` and configure the following:

**Security (Required for Production)**:
```
API_KEY=your-secure-api-key-here
```
The API key secures communication between the speech-to-text client and the server. Generate a strong random key and use the same value on both sides. Example:
```bash
# Generate a secure random API key (macOS/Linux)
openssl rand -base64 32
```

**AWS Credentials (Optional, for translation)**:
```
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=us-east-1
```

Alternatively, use AWS CLI to configure credentials:
```bash
aws configure
```

**Note**: 
- The application works without AWS credentials, but translation will be disabled (English-only mode).
- Without an API_KEY set, the server will accept text from any client. Set API_KEY for production deployments.

## Usage

### Step 1: Start the Web Server

In one terminal window, start the Flask server:

```bash
python server.py
```

The server will start on `http://localhost:5050` by default.

### Step 2: Open the Web Interface

Open a web browser and navigate to:
```
http://localhost:5050
```

You can open multiple browser windows/tabs to simulate multiple users with different language preferences.

### Step 3: Start Speech Recognition

In another terminal window, start the speech-to-text application:

```bash
python speech_to_text.py
```

The application will:
1. Connect to the web server
2. Calibrate the microphone for ambient noise
3. Start listening for speech

Now speak into your microphone, and the text will appear in real-time on all connected web clients, translated to their selected languages.

### Testing Without a Microphone

If you want to test the system without a microphone or speech input, use the test client:

```bash
python test_client.py
```

This will send sample phrases to the server, allowing you to see how the translation system works.

### Command Line Options

**Web Server**:
```bash
# Use environment variables or .env file
FLASK_HOST=0.0.0.0 FLASK_PORT=5050 python server.py
```

**Speech-to-Text Application**:
```bash
# List available audio input devices
python speech_to_text.py -l

# Connect to default server with default audio device
python speech_to_text.py

# Connect to a remote server
python speech_to_text.py http://example.com:5050

# Use a specific audio input device by index (from -l output)
python speech_to_text.py -d 1

# Use a specific audio input device by name
python speech_to_text.py -d "USB Microphone"

# Use a specific device with a remote server
python speech_to_text.py -d 1 http://example.com:5050

# Set default audio device via environment variable (by index)
LT_AUDIO_DEVICE=1 python speech_to_text.py

# Set default audio device via environment variable (by name)
LT_AUDIO_DEVICE="USB Microphone" python speech_to_text.py
```

You can also set the audio device permanently in your `.env` file:
- By index: `LT_AUDIO_DEVICE=1`
- By name: `LT_AUDIO_DEVICE="USB Microphone"`

Using device names is more stable when devices are added/removed from the system.

## Supported Languages

The application supports translation to the following languages:

- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Chinese (zh)
- Japanese (ja)
- Korean (ko)
- Arabic (ar)
- Russian (ru)
- Hindi (hi)
- Dutch (nl)
- Polish (pl)
- Turkish (tr)

## How It Works

1. **Audio Capture**: The speech-to-text app captures audio from the microphone using PyAudio
2. **Speech Recognition**: Audio is processed by Google Speech Recognition API to convert speech to text
3. **Broadcasting**: Recognized text is sent to the Flask server via WebSocket
4. **Translation**: Server translates text to each connected client's preferred language using AWS Translate
5. **Display**: Translated text is sent to web clients and displayed in real-time

## Architecture Diagram

```
┌─────────────────┐
│   Microphone    │
└────────┬────────┘
         │ Audio
         ▼
┌─────────────────┐      WebSocket     ┌──────────────────┐
│  Speech-to-Text │ ──────────────────▶│  Flask Server    │
│   Application   │      (Text)        │  (server.py)     │
└─────────────────┘                    └────────┬─────────┘
                                                 │
                                                 │ AWS Translate
                                                 │ (Optional)
                                                 ▼
                                       ┌─────────────────┐
                                       │ Web Clients     │
                                       │ (Browsers)      │
                                       └─────────────────┘
```

## Troubleshooting

### PyAudio Installation Issues (macOS)

If you encounter issues installing PyAudio on macOS:

```bash
# Install PortAudio first
brew install portaudio

# Then install PyAudio with specific flags
pip install --global-option='build_ext' --global-option='-I/opt/homebrew/include' --global-option='-L/opt/homebrew/lib' pyaudio

# You may need to install flac (on macOS silicon devices), which is a dependency of the SpeechRecognition library
brew install flac

```

### aifc Deprecation Warning

If you see a deprecation warning about the `aifc` module (Python 3.11+):
- This is a known issue with older versions of the SpeechRecognition library
- We've updated to SpeechRecognition 3.14.3 which has better Python 3.11+ compatibility
- The warning should not affect functionality
- Make sure you're using Python 3.9-3.12 for best compatibility

### Microphone Permission (macOS)

Make sure to grant microphone access to Terminal or your Python IDE in System Preferences → Security & Privacy → Microphone.

### AWS Translate Not Working

1. Verify AWS credentials are correctly set in `.env` or via AWS CLI
2. Ensure your AWS account has permissions for AWS Translate
3. Check that the AWS region supports Translate service
4. The application will work in English-only mode if AWS is not configured

## AWS IAM Policy (Translate)

To allow the server to call AWS Translate's TranslateText API, attach a minimal IAM policy to the role or user the server runs under (for example: ECS task role, EC2 instance profile, or Lambda execution role). AWS Translate actions are service-level and do not support resource-level ARNs, so the policy uses a wildcard resource.

Minimal policy (TranslateText only):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "translate:TranslateText",
        "comprehend:DetectDominantLanguage"
      ],
      "Resource": "*"
    }
  ]
}
```

Optional: restrict to a single region (example `us-east-1`) using a condition:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "translate:TranslateText",
        "comprehend:DetectDominantLanguage"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

Recommendations
- Attach this policy to an IAM role rather than distributing long-lived user credentials.
- For ECS, use a task role; for EKS use IRSA; for EC2 use an instance profile; for Lambda attach to the execution role.
- Monitor and log Translate API usage with CloudTrail.
- Never commit credentials into source control; use the role or a secret manager.


### Connection Issues

If the speech-to-text app can't connect to the server:
1. Ensure the Flask server is running
2. Check firewall settings
3. Verify the server URL is correct

### SocketIO Async Mode Issues

If you get an error about invalid async_mode when starting the server:

The application uses Flask-SocketIO's default threading mode, which works out of the box. For better performance with more concurrent connections, you can optionally install an async library:

**Recommended: gevent** (better performance and stability)
```bash
pip install gevent gevent-websocket
```

**Alternative: eventlet**
```bash
pip install eventlet
```

The server will automatically detect and use gevent or eventlet if installed. No configuration changes needed.

## Development

### Project Structure

```
live-translate/
├── speech_to_text.py      # Speech recognition application
├── server.py              # Flask web server
├── test_client.py         # Test script (no microphone needed)
├── start.sh               # Quick start script (macOS/Linux)
├── templates/
│   └── index.html        # Web interface
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── .gitignore           # Git ignore rules
├── LICENSE              # License file
└── README.md            # This file
```

### Running in Development Mode

Enable Flask debug mode by setting in `.env`:
```
FLASK_DEBUG=True
```

### Performance Optimization

For production use or handling many concurrent connections, install gevent for better performance:

```bash
pip install gevent gevent-websocket
```

Flask-SocketIO will automatically detect and use gevent, providing:
- Better scalability with concurrent WebSocket connections
- Lower memory usage per connection
- Improved performance for real-time updates

The application works fine with the default threading mode for testing and small deployments.

## Security Notes

### API Key Authentication

The application uses API key authentication to secure text input between the speech-to-text client and the server:

- **Required for Production**: Always set `API_KEY` in your `.env` file for production deployments
- **Same Key Required**: The API key must be identical in both the server and client `.env` files
- **Key Generation**: Use a cryptographically secure random generator to create your API key:
  ```bash
  # Generate a secure random API key (macOS/Linux)
  openssl rand -base64 32
  ```
- **Warning Mode**: If no API_KEY is set, both server and client will display warnings and operate in an unsecured mode

### General Security Best Practices

- Never commit `.env` file or AWS credentials to version control
- Use IAM roles with minimal permissions for production deployments
- Consider using AWS Secrets Manager for credential management in production
- Implement authentication for production web interface
- Rotate API keys periodically
- Use HTTPS/WSS in production environments

## License

This project is licensed under the terms specified in the LICENSE file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Future Enhancements

- [ ] Support for additional speech recognition engines
- [ ] Recording and playback of sessions
- [ ] User authentication and session management
- [ ] Mobile app support
- [ ] Custom vocabulary and language models
- [ ] Speaker diarization (multiple speakers)
- [ ] Offline translation support