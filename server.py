#!/usr/bin/env python3
"""
Flask Web Server for Live Translation
Receives text from speech-to-text app and broadcasts translations to web clients.
"""

import os
import secrets
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load API key for authentication
API_KEY = os.environ.get('API_KEY')
if not API_KEY:
    logger.warning("⚠ API_KEY not set in environment. Text input will not be secured.")
    logger.warning("Set API_KEY in .env file for production use.")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize SocketIO (auto-detects best async mode)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize AWS Translate client
try:
    translate_client = boto3.client(
        'translate',
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )
    aws_available = True
    logger.info("✓ AWS Translate client initialized")
except (NoCredentialsError, Exception) as e:
    aws_available = False
    logger.warning(f"⚠ AWS Translate not available: {e}")
    logger.warning("Translation features will be limited.")

# Store connected clients with their preferred languages
connected_clients = {}


def translate_text(text, target_language, source_language='auto'):
    """
    Translate text using AWS Translate.
    
    Args:
        text: Text to translate
        target_language: Target language code (e.g., 'es' for Spanish)
        source_language: Source language code ('auto' for auto-detection)
    
    Returns:
        Translated text or original text if translation fails
    """
    if not aws_available:
        return text
    
    # Don't translate if target is English (source language)
    if target_language == 'en':
        return text
    
    try:
        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode=source_language,
            TargetLanguageCode=target_language
        )
        return response['TranslatedText']
    except ClientError as e:
        logger.error(f"Translation error: {e}")
        return text
    except Exception as e:
        logger.error(f"Unexpected translation error: {e}")
        return text


@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html', aws_available=aws_available)


@app.route('/health')
def health():
    """Health check endpoint."""
    return {
        'status': 'healthy',
        'aws_translate': aws_available,
        'connected_clients': len(connected_clients)
    }


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    client_id = request.sid
    connected_clients[client_id] = {'language': 'en'}
    logger.info(f"Client connected: {client_id} (Total: {len(connected_clients)})")
    emit('connection_status', {'status': 'connected', 'aws_available': aws_available})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    client_id = request.sid
    if client_id in connected_clients:
        del connected_clients[client_id]
    logger.info(f"Client disconnected: {client_id} (Total: {len(connected_clients)})")


@socketio.on('set_language')
def handle_set_language(data):
    """
    Handle language preference from client.
    
    Args:
        data: Dictionary with 'language' key
    """
    client_id = request.sid
    language = data.get('language', 'en')
    
    if client_id in connected_clients:
        connected_clients[client_id]['language'] = language
        logger.info(f"Client {client_id} language set to: {language}")
        emit('language_set', {'language': language})


@socketio.on('new_text')
def handle_new_text(data):
    """
    Handle new text from speech-to-text application.
    Translates and broadcasts to all connected clients.
    
    Args:
        data: Dictionary with 'text', 'timestamp', and 'api_key' keys
    """
    # Validate API key if configured
    if API_KEY:
        provided_key = data.get('api_key', '')
        # Use constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(provided_key, API_KEY):
            logger.warning(f"Unauthorized new_text attempt from {request.sid}")
            emit('error', {'message': 'Unauthorized: Invalid API key'})
            return
    
    original_text = data.get('text', '')
    timestamp = data.get('timestamp', '')
    
    logger.info(f"New text received: {original_text}")
    
    # Broadcast original text to all English clients
    for client_id, client_info in connected_clients.items():
        target_language = client_info.get('language', 'en')
        
        if target_language == 'en':
            translated_text = original_text
        else:
            translated_text = translate_text(original_text, target_language)
        
        socketio.emit('translated_text', {
            'text': translated_text,
            'original': original_text,
            'timestamp': timestamp,
            'language': target_language
        }, room=client_id)


@socketio.on('request_translation')
def handle_request_translation(data):
    """
    Handle on-demand translation request from client.
    
    Args:
        data: Dictionary with 'text' and 'target_language' keys
    """
    text = data.get('text', '')
    target_language = data.get('target_language', 'en')
    
    translated_text = translate_text(text, target_language)
    
    emit('translation_result', {
        'original': text,
        'translated': translated_text,
        'language': target_language
    })


def main():
    """Run the Flask server."""
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info("="*60)
    logger.info("Live Translation Server")
    logger.info("="*60)
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"AWS Translate: {'Available' if aws_available else 'Not Available'}")
    logger.info("="*60)
    
    socketio.run(app, host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
