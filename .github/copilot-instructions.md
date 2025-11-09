# GitHub Copilot Instructions for Live-Translate

## Project Overview

Live-Translate is a real-time speech-to-text translation application built with Python. It captures audio from a microphone, converts speech to text using Google Speech Recognition API, and provides live translations to multiple web clients in their preferred languages via WebSockets.

### Key Components

1. **Speech-to-Text Application** (`speech_to_text.py`): Captures audio and converts speech to text
2. **Web Server** (`server.py`): Flask-based server with WebSocket support for real-time translation
3. **Web Interface** (`templates/index.html`): Client-side UI for viewing translations

## Tech Stack

- **Language**: Python 3.9-3.12
- **Web Framework**: Flask 3.1.2
- **WebSocket**: Flask-SocketIO 5.5.1, python-socketio 5.14.3
- **Speech Recognition**: SpeechRecognition 3.14.3, PyAudio 0.2.14
- **Translation**: AWS Translate (via boto3)
- **Configuration**: python-dotenv for environment variables
- **Testing**: Python unittest framework

### Optional Dependencies

- **gevent** (recommended) or **eventlet** for better WebSocket performance
- AWS credentials for translation features (application works in English-only mode without AWS)

## Development Setup

### Prerequisites

- Python 3.9+ (tested on Python 3.9-3.12)
- PortAudio (macOS: `brew install portaudio`)
- Microphone for speech input
- Optional: AWS account for translation features

### Installation

1. Use `./start.sh` for automated setup (macOS/Linux)
2. Or manually:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # Configure .env with API_KEY and optionally AWS credentials
   ```

### Running the Application

1. Start server: `python server.py`
2. Open web interface: `http://localhost:5050`
3. Start speech recognition: `python speech_to_text.py`

### Testing Without Microphone

Use `python test_client.py` to send test phrases to the server.

## Testing Approach

### Test Files

- `test_api_auth.py`: API key authentication tests
- `test_audio_device_selection.py`: Audio device selection tests
- `test_threading.py`: Threading and concurrency tests
- `test_ui_customization.py`: UI customization tests
- `test_client.py`: Manual testing script (not unit tests)

### Running Tests

```bash
# Run all tests
python -m unittest discover -s . -p 'test_*.py'

# Run specific test file
python -m unittest test_api_auth

# Note: Tests require Flask and other dependencies to be installed
```

### Test Patterns

- Use Python's `unittest` framework
- Mock external dependencies (Flask-SocketIO, AWS, microphone)
- Test both success and error scenarios
- Include security tests (API key validation)

## Coding Standards

### Python Style

- Follow PEP 8 style guidelines
- Use docstrings for functions and classes
- Keep functions focused and modular
- Use meaningful variable names

### Security Practices

- **Never commit secrets**: Use `.env` for sensitive data
- **API Key Required**: Set `API_KEY` in `.env` for production
- **AWS Credentials**: Use IAM roles or AWS CLI, never hardcode
- **Input Validation**: Validate all client inputs
- **HTTPS/WSS**: Use secure protocols in production

### Error Handling

- Log errors appropriately
- Provide user-friendly error messages
- Handle missing dependencies gracefully
- Include fallback behavior (e.g., English-only mode without AWS)

## Architecture Patterns

### WebSocket Communication

- Server broadcasts translations to all connected clients
- Each client subscribes to their preferred language
- API key authentication for text input from speech client
- Real-time updates using Socket.IO events

### Translation Workflow

1. Speech → Text (Google Speech Recognition)
2. Text → Server (WebSocket with API key)
3. Text → AWS Translate (per client language)
4. Translation → Clients (WebSocket broadcast)

### State Management

- Server maintains client sessions with language preferences
- No persistent storage (in-memory only)
- Stateless translation (each phrase independent)

## Common Workflows

### Adding a New Language

1. Add language code to `SUPPORTED_LANGUAGES` in `server.py`
2. Add language option to `templates/index.html`
3. Ensure AWS Translate supports the language

### Modifying WebSocket Events

1. Update event handlers in `server.py`
2. Update corresponding client-side code in `templates/index.html`
3. Maintain API key validation for security-sensitive events

### Adding New Tests

1. Create test file with `test_` prefix
2. Inherit from `unittest.TestCase`
3. Mock external dependencies (Flask-SocketIO, boto3, PyAudio)
4. Test both success and failure scenarios

## Project-Specific Considerations

### Audio Device Selection

- Support device selection by index or name
- Device names are more stable than indices
- Environment variable: `LT_AUDIO_DEVICE`
- Command-line options: `-l` (list), `-d <device>` (select)

### API Key Authentication

- Used only for text input from speech client
- Not required for WebSocket connections from web browsers
- Server and client must use the same key
- Generate with: `openssl rand -base64 32`

### macOS Compatibility

- PyAudio requires PortAudio: `brew install portaudio`
- May need flac on Apple Silicon: `brew install flac`
- Grant microphone permissions in System Preferences

### AWS Integration

- Translation is optional (graceful degradation)
- Server checks for AWS credentials at startup
- Requires `translate:TranslateText` and `comprehend:DetectDominantLanguage` permissions
- Use minimal IAM policies (see README)

## Environment Variables

### Required for Production

- `API_KEY`: Secure communication between client and server

### Optional

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`: For translation
- `FLASK_HOST`, `FLASK_PORT`: Server configuration
- `FLASK_DEBUG`: Development mode
- `LT_AUDIO_DEVICE`: Default audio input device

## File Structure

```
live-translate/
├── .github/
│   ├── copilot-instructions.md  # This file
│   └── workflows/               # CI/CD workflows
├── templates/
│   └── index.html              # Web interface
├── static/                     # Static assets (if any)
├── server.py                   # Flask server with WebSocket
├── speech_to_text.py           # Speech recognition client
├── test_*.py                   # Unit tests
├── test_client.py              # Manual testing tool
├── start.sh                    # Setup script
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
└── README.md                   # User documentation
```

## When Making Changes

### Before Coding

1. Review existing code patterns in the file you're modifying
2. Check if similar functionality exists elsewhere
3. Understand security implications (especially for API endpoints)
4. Consider backward compatibility

### While Coding

1. Maintain consistent style with existing code
2. Add or update docstrings
3. Handle errors gracefully
4. Consider performance (WebSocket broadcasts to many clients)

### After Coding

1. Run relevant tests: `python -m unittest test_<module>`
2. Test manually with real server and clients
3. Check for security issues (API key validation, input sanitization)
4. Update documentation if behavior changes

## Dependencies Management

### Adding New Dependencies

1. Add to appropriate requirements file:
   - `requirements.txt`: Core dependencies for all modes
   - `server-requirements.txt`: Server-only dependencies
   - `client-requirements.txt`: Client-only dependencies
2. Keep versions pinned for reproducibility
3. Test with minimum Python version (3.9)
4. Consider optional dependencies for non-critical features

### Updating Dependencies

1. Check compatibility with Python 3.9-3.12
2. Review security advisories
3. Test thoroughly after updates
4. Update version pins in requirements.txt

## Debugging Tips

### Common Issues

1. **PyAudio Installation**: Install PortAudio first on macOS
2. **Microphone Permission**: Grant access in System Preferences
3. **WebSocket Connection**: Check server is running and firewall settings
4. **AWS Translate**: Verify credentials and IAM permissions
5. **API Key Mismatch**: Ensure same key in server and client `.env`

### Logging

- Server logs to console (stdout)
- Use Python's `logging` module for structured logs
- Log level can be controlled via `FLASK_DEBUG`

## Performance Considerations

- **WebSocket Scaling**: Consider gevent for many concurrent clients
- **Translation API Calls**: One call per client per message
- **Audio Processing**: Runs in separate thread/process
- **Memory Usage**: In-memory state only, no persistence

## Security Checklist

When reviewing or modifying code, ensure:

- [ ] No secrets in source code
- [ ] API key validation for sensitive operations
- [ ] Input sanitization for user-provided data
- [ ] Error messages don't leak sensitive information
- [ ] HTTPS/WSS in production recommendations documented
- [ ] IAM roles used instead of long-lived credentials
- [ ] Dependencies don't have known vulnerabilities
