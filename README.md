# Live Translation

A real-time speech-to-text translation application that captures audio from a microphone, converts it to text, and provides live translations to web clients in their preferred languages.

![](/docs/screenshot.png)

## Features

- 🎤 **Speech-to-Text**: Real-time audio capture and speech recognition
- 🌍 **Multi-Language Translation**: Support for 15+ languages via AWS Translate
- 🔄 **Real-Time Updates**: WebSocket-based live streaming to connected clients
- 💻 **Web Interface**: Clean, modern UI for viewing translations
- 🍎 **Mac Compatible**: Optimized for macOS
- ☁️ **Multiple Deployment Options**: Run locally with Flask or deploy to AWS with Lambda + API Gateway

## Deployment Options

This application supports two deployment modes:

1. **Local/Traditional Deployment** (Flask-based)
   - Quick setup for local development or small-scale deployments
   - Uses Flask web server with WebSocket support
   - Suitable for single-server deployments
   - See [Usage](#usage) section below

2. **AWS Cloud Deployment** (Serverless)
   - Scalable, serverless architecture using AWS Lambda + API Gateway
   - Static website hosting via S3 + CloudFront
   - Distributed client storage with DynamoDB
   - Automatic scaling and high availability
   - See [terraform/README.md](terraform/README.md) for deployment instructions

## Architecture

The application consists of two main components:

1. **Speech-to-Text Client** (`speech_to_text.go`): Captures audio from the microphone and converts speech to text
2. **Web Server** (`server.py`): Flask-based server with native WebSocket support (using flask-sock) that receives text, translates it using AWS Translate, and broadcasts to connected web clients

**Note**: For AWS cloud deployment, the Flask server is replaced with AWS Lambda functions and API Gateway. See the [Deployment Options](#deployment-options) section above.

### Communication Protocol

The application uses websockets for real-time communication between all components:
- Speech-to-text clients connect via WebSocket and send recognized text
- Web browser clients connect via WebSocket to receive translations

## Requirements

### For the Web Server
- Python 3.11+ (tested on Python 3.11-3.12)
- Internet connection (for AWS Translate API)

### For the Speech-to-Text Client

- Go 1.25+ (for building from source)
- PortAudio library
  - **Linux**: `sudo apt-get install portaudio19-dev`
  - **macOS**: `brew install portaudio`
  - **Windows**: Download from [PortAudio website](http://www.portaudio.com/)
- AWS credentials for Transcribe Streaming API
- Microphone/Audio Input Device (for speech input)
- Internet connection (for speech recognition API)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/stevehaskew/live-translate.git
cd live-translate
```

### 2. Install PortAudio (Required for Speech Client)
```bash
# Linux
sudo apt-get install portaudio19-dev

# macOS
brew install portaudio

# Windows - Download from http://www.portaudio.com/
```

### 3. Install Your Speech Client

#### Option A: Go Client (Recommended)

**Pre-built binaries**: Download from the [Releases page](https://github.com/stevehaskew/live-translate/releases)

**Build from source**:
```bash
# Install Go 1.19+ if not already installed
# https://golang.org/dl/

# Build the client
make build

# Or build manually
go build -o speech_to_text_go speech_to_text.go

# The executable will be created: ./speech_to_text_go
```

**Cross-platform builds**:
```bash
# Build for all platforms
make build-all

# Or build for specific platforms
make build-linux    # Linux (amd64)
make build-darwin   # macOS (amd64 and arm64)
make build-windows  # Windows (amd64)
```

### 4. Configure environment variables

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

**AWS Credentials Configuration**:

The application supports two modes for AWS Transcribe credentials:

1. **Server-Provided Token Mode** (Recommended for Production):
   - The Go client requests temporary session credentials from the server
   - The server uses AWS STS AssumeRole to generate time-limited credentials
   - Tokens are automatically refreshed every 20 minutes
   - More secure: clients never need permanent AWS credentials

2. **Local Credentials Mode** (For Development):
   - The Go client uses local AWS credentials directly
   - Useful for local testing and development

**Server Configuration** (for token generation):
```
# IAM Role ARN that the server will assume to generate Transcribe credentials
TRANSCRIBE_ROLE_ARN=arn:aws:iam::123456789012:role/LiveTranslateTranscribeRole

# Server's own AWS credentials (to call STS AssumeRole)
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=us-east-1
```

**Client Configuration**:
```
# Set to "true" to use local AWS credentials instead of server tokens
# Default: false (use server-provided tokens)
LT_LOCAL_TOKEN=false

# Only needed if LT_LOCAL_TOKEN=true
# AWS_ACCESS_KEY_ID=your_access_key_here
# AWS_SECRET_ACCESS_KEY=your_secret_key_here
# AWS_DEFAULT_REGION=us-east-1
```

The server also requires AWS credentials for translation (AWS Translate). You can configure AWS credentials in several ways:

1. **Environment variables** (as shown above)
2. **AWS CLI configuration**:
   ```bash
   aws configure
   ```
3. **IAM roles** (recommended for EC2, ECS, Lambda deployments)

**Note**: 
- In Server-Provided Token mode (recommended), only the server needs AWS credentials
- The client will request temporary credentials from the server via the `/generate_token` endpoint
- Tokens are valid for 1 hour and automatically refreshed every 20 minutes
- Without AWS credentials, the server will work in English-only mode (no translation)
- Without an API_KEY set, the server will accept text from any client. Set API_KEY for production deployments

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

In another terminal window, start the speech-to-text client:

```bash
./speech_to_text_go
```

The client will:
1. Connect to the web server
2. Calibrate the microphone for ambient noise
3. Start listening for speech

Now speak into your microphone, and the text will appear in real-time on all connected web clients, translated to their selected languages.

### Command Line Options

**Web Server**:
```bash
# Use environment variables or .env file
FLASK_HOST=0.0.0.0 FLASK_PORT=5050 python server.py
```

**Speech-to-Text Client**:
```bash
# List available audio input devices
./speech_to_text_go -l

# Connect to default server with default audio device
./speech_to_text_go

# Connect to a remote server
./speech_to_text_go http://example.com:5050

# Use a specific audio input device by index (from -l output)
./speech_to_text_go -d 1

# Use a specific audio input device by name
./speech_to_text_go -d "USB Microphone"

# Use a specific device with a remote server
./speech_to_text_go -d 1 http://example.com:5050

# Set default audio device via environment variable (by index)
LT_AUDIO_DEVICE=1 ./speech_to_text_go

# Set default audio device via environment variable (by name)
LT_AUDIO_DEVICE="USB Microphone" ./speech_to_text_go
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

1. **Audio Capture**: The speech-to-text client captures audio from the microphone using PortAudio
2. **Speech Recognition**: Audio is streamed to AWS Transcribe Streaming for real-time speech-to-text conversion
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

### Microphone Permission (macOS)

Make sure to grant microphone access to Terminal in System Preferences → Security & Privacy → Microphone.

### AWS Translate Not Working

1. Verify AWS credentials are correctly set in `.env` or via AWS CLI
2. Ensure your AWS account has permissions for AWS Translate
3. Check that the AWS region supports Translate service
4. The application will work in English-only mode if AWS is not configured

## AWS IAM Policies

### Required Permissions for Server

#### 1. AWS Translate Policy (for translation service)

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

Optional: restrict to a single region (example `eu-west-2`) using a condition:

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
          "aws:RequestedRegion": "eu-west-2"
        }
      }
    }
  ]
}
```

#### 2. STS AssumeRole Policy (for token generation)

To allow the server to generate temporary credentials for clients, attach this policy to the server's IAM role or user:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::123456789012:role/LiveTranslateTranscribeRole"
    }
  ]
}
```

Replace `123456789012` with your AWS account ID and adjust the role name if different.

#### 3. Transcribe Role (assumed by server to generate client tokens)

Create an IAM role (e.g., `LiveTranslateTranscribeRole`) with the following trust policy to allow your server to assume it:

Trust policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/YourServerRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "live-translate"
        }
      }
    }
  ]
}
```

Permissions policy for the Transcribe role:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "transcribe:StartStreamTranscription"
      ],
      "Resource": "*"
    }
  ]
}
```

### Configuration Summary

1. **Server Role** needs:
   - `translate:TranslateText` and `comprehend:DetectDominantLanguage` (for translation)
   - `sts:AssumeRole` permission for the Transcribe role (for token generation)

2. **Transcribe Role** (assumed by server) needs:
   - `transcribe:StartStreamTranscription` (clients use this via temporary credentials)
   - Trust policy allowing the server role to assume it

3. **Client** needs:
   - Only the API key (no AWS credentials required in server-provided token mode)
   - Or local AWS credentials if `LT_LOCAL_TOKEN=true` (development only)

### Recommendations

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
          "aws:RequestedRegion": "eu-west-2"
        }
      }
    }
  ]
}
```

### Recommendations
- **Use IAM roles** instead of long-lived credentials for all deployments
- For ECS, use a task role; for EKS use IRSA; for EC2 use an instance profile; for Lambda attach to the execution role
- **Enable CloudTrail logging** to monitor AWS API usage (Translate, Transcribe, STS)
- **Rotate credentials** regularly if using access keys for development
- **Never commit credentials** into source control; use environment variables, IAM roles, or a secret manager
- **Set session duration** appropriately for the Transcribe role (default: 1 hour, max: 12 hours for roles)
- **Use condition keys** in trust policies to add an extra layer of security (e.g., `sts:ExternalId`)
- **Monitor token generation** frequency to ensure clients are refreshing tokens appropriately


### Connection Issues

If the speech-to-text app can't connect to the server:
1. Ensure the Flask server is running
2. Check firewall settings
3. Verify the server URL is correct
4. If using server-provided tokens, ensure `TRANSCRIBE_ROLE_ARN` is configured
5. Check server logs for token generation errors

## AWS Cloud Deployment

For production deployments requiring high availability, automatic scaling, and serverless architecture, you can deploy to AWS using:

- **API Gateway** (WebSocket API) for real-time communication
- **AWS Lambda** for serverless compute
- **DynamoDB** for distributed client connection storage
- **S3 + CloudFront** for static website hosting
- **Terraform** for infrastructure as code

### Quick Start (AWS Deployment)

1. **Build Lambda Deployment Package**:
   ```bash
   ./scripts/build_lambda.sh
   ```

2. **Configure Terraform Variables**:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your settings
   ```

3. **Deploy Infrastructure**:
   ```bash
   terraform init
   terraform apply
   ```

4. **Upload Static Website Files**:
   ```bash
   BUCKET_NAME=$(terraform output -raw s3_bucket_name)
   aws s3 sync ../static/ s3://$BUCKET_NAME/
   ```

5. **Create Configuration File**:
   ```bash
   cat > config.json << EOF
   {
     "logoFile": "",
     "pageTitle": "🌍 Live Translation",
     "contactText": "support@example.com",
     "websocketUrl": "$(terraform output -raw websocket_api_endpoint)"
   }
   EOF
   aws s3 cp config.json s3://$BUCKET_NAME/
   ```

For detailed AWS deployment instructions, see **[terraform/README.md](terraform/README.md)**.

### AWS vs Flask Deployment

| Feature | Flask (Local) | AWS (Serverless) |
|---------|---------------|------------------|
| Setup Complexity | Low | Medium |
| Scalability | Single server | Auto-scaling |
| Availability | Single point of failure | High availability |
| Cost (low traffic) | ~$5-10/month (VPS) | ~$1-5/month |
| Cost (high traffic) | Fixed | Pay-per-use |
| Maintenance | Manual updates | Managed services |
| Geographic Distribution | Single region | Global (CloudFront) |

## Development

### Project Structure

```
live-translate/
├── speech_to_text.go      # Go speech recognition client (recommended)
├── server.py              # Flask web server (local deployment)
├── lambda_handler.py      # AWS Lambda handler (cloud deployment)
├── client_map.py          # Client connection management (shared)
├── message_handler.py     # Message handling logic (shared)
├── Makefile               # Build system for Go client
├── go.mod                 # Go module dependencies
├── go.sum                 # Go module checksums
├── static/
│   ├── index.html        # Static web interface (AWS S3)
│   ├── main.css          # Stylesheet
│   └── config.json.example # Configuration template (AWS)
├── terraform/             # AWS infrastructure as code
│   ├── main.tf           # Terraform configuration
│   ├── variables.tf      # Input variables
│   ├── outputs.tf        # Output values
│   ├── resources.tf      # AWS resources
│   └── README.md         # AWS deployment guide
├── scripts/
│   └── build_lambda.sh   # Build Lambda deployment package
├── requirements.txt      # Python dependencies for server
├── .env.example          # Environment variables template
├── .gitignore            # Git ignore rules
├── LICENSE               # License file
└── README.md             # This file
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

The included Dockerfile shows deployment of the application with Gunicorn using gevent in a Docker environment.

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
- **Token Generation**: The API key is also used to authenticate requests to the `/generate_token` endpoint

### AWS Credentials Token Provisioning

The application uses a secure token provisioning system for AWS Transcribe access:

- **Server-Provided Tokens** (Default): The Go client requests temporary session credentials from the server via the `/generate_token` endpoint
- **Time-Limited**: Tokens are valid for 1 hour (AWS STS default) and automatically refreshed every 20 minutes
- **Principle of Least Privilege**: Temporary credentials only grant access to `transcribe:StartStreamTranscription`
- **No Client Credentials**: Clients never need permanent AWS credentials, reducing security risk
- **Local Mode**: Set `LT_LOCAL_TOKEN=true` for development to use local AWS credentials instead

### General Security Best Practices

- Never commit `.env` file or AWS credentials to version control
- Use IAM roles with minimal permissions for production deployments
- Configure the `TRANSCRIBE_ROLE_ARN` to limit scope of assumed role permissions
- Consider using AWS Secrets Manager for credential management in production
- Implement authentication for production web interface
- Rotate API keys and review IAM policies periodically
- Use HTTPS/WSS in production environments
- Monitor CloudTrail logs for unusual token generation or AWS API activity

## License

This project is licensed under the terms specified in the LICENSE file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
