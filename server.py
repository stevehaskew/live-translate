#!/usr/bin/env python3
"""
Flask Web Server for Live Translation with WebSockets
Receives text from speech-to-text app and broadcasts translations to web clients.
"""

import os
import secrets
import json
import logging
import html
from flask import Flask, render_template, request
from flask_sock import Sock
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load API key for authentication
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    logger.warning("⚠ API_KEY not set in environment. Text input will not be secured.")
    logger.warning("Set API_KEY in .env file for production use.")

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-secret-key-change-in-production"
)

# Initialize WebSocket support
sock = Sock(app)

# Initialize AWS Translate client
try:
    translate_client = boto3.client(
        "translate",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    aws_available = True
    logger.info("✓ AWS Translate client initialized")
except (NoCredentialsError, Exception) as e:
    aws_available = False
    logger.warning(f"⚠ AWS Translate not available: {e}")
    logger.warning("Translation features will be limited.")

# Store connected clients with their preferred languages
connected_clients = {}

# Load UI customization settings
ui_config = {
    "logo_file": os.environ.get("LT_LOGO_FILE", ""),
    "page_title": html.escape(os.environ.get("LT_PAGE_TITLE", "🌍 Live Translation")),
    "contact_text": os.environ.get("LT_CONTACT_TEXT", ""),
}

# Message types for WebSocket communication
MESSAGE_TYPE_CONNECTION_STATUS = "connection_status"
MESSAGE_TYPE_SET_LANGUAGE = "set_language"
MESSAGE_TYPE_LANGUAGE_SET = "language_set"
MESSAGE_TYPE_NEW_TEXT = "new_text"
MESSAGE_TYPE_TRANSLATED_TEXT = "translated_text"
MESSAGE_TYPE_REQUEST_TRANSLATION = "request_translation"
MESSAGE_TYPE_TRANSLATION_RESULT = "translation_result"
MESSAGE_TYPE_ERROR = "error"


def translate_text(text, target_language, source_language="auto"):
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
    if target_language == "en":
        return text

    try:
        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode=source_language,
            TargetLanguageCode=target_language,
        )
        return response["TranslatedText"]
    except ClientError as e:
        logger.error(f"Translation error: {e}")
        return text
    except Exception as e:
        logger.error(f"Unexpected translation error: {e}")
        return text


def send_message(ws, msg_type, data):
    """Send a WebSocket message."""
    message = {"type": msg_type, "data": data}
    ws.send(json.dumps(message))


def broadcast_message(msg_type, data, exclude_client=None):
    """Broadcast a message to all connected clients except the excluded one."""
    message = {"type": msg_type, "data": data}
    message_json = json.dumps(message)

    clients_to_remove = []
    for client_id, client_info in connected_clients.items():
        if client_id == exclude_client:
            continue
        try:
            client_info["ws"].send(message_json)
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            clients_to_remove.append(client_id)

    # Remove disconnected clients
    for client_id in clients_to_remove:
        if client_id in connected_clients:
            del connected_clients[client_id]


@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template(
        "index.html",
        aws_available=aws_available,
        logo_file=ui_config["logo_file"],
        page_title=ui_config["page_title"],
        contact_text=ui_config["contact_text"],
    )


@app.route("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "aws_translate": aws_available,
        "connected_clients": len(connected_clients),
    }


@sock.route("/ws")
def websocket_handler(ws):
    """Handle WebSocket connections."""
    client_id = id(ws)
    connected_clients[client_id] = {"language": "en", "ws": ws}
    logger.info(f"Client connected: {client_id} (Total: {len(connected_clients)})")

    # Send connection status
    try:
        send_message(
            ws,
            MESSAGE_TYPE_CONNECTION_STATUS,
            {"status": "connected", "aws_available": aws_available},
        )
    except Exception as e:
        logger.error(f"Error sending connection status: {e}")

    try:
        while True:
            data = ws.receive()
            if data is None:
                break

            try:
                message = json.loads(data)
                msg_type = message.get("type")
                msg_data = message.get("data", {})

                if msg_type == MESSAGE_TYPE_SET_LANGUAGE:
                    # Handle language preference from client
                    language = msg_data.get("language", "en")
                    connected_clients[client_id]["language"] = language
                    logger.info(f"Client {client_id} language set to: {language}")
                    send_message(ws, MESSAGE_TYPE_LANGUAGE_SET, {"language": language})

                elif msg_type == MESSAGE_TYPE_NEW_TEXT:
                    # Handle new text from speech-to-text application
                    # Validate API key if configured
                    if API_KEY:
                        provided_key = msg_data.get("api_key", "")
                        # Use constant-time comparison to prevent timing attacks
                        if not secrets.compare_digest(provided_key, API_KEY):
                            logger.warning(
                                f"Unauthorized new_text attempt from {client_id}"
                            )
                            send_message(
                                ws,
                                MESSAGE_TYPE_ERROR,
                                {"message": "Unauthorized: Invalid API key"},
                            )
                            continue

                    original_text = msg_data.get("text", "")
                    timestamp = msg_data.get("timestamp", "")

                    logger.info(f"New text received: {original_text}")

                    # Broadcast to all clients with translation
                    for cid, client_info in list(connected_clients.items()):
                        target_language = client_info.get("language", "en")
                        client_ws = client_info.get("ws")

                        if target_language == "en":
                            translated_text = original_text
                        else:
                            translated_text = translate_text(
                                original_text, target_language
                            )

                        try:
                            send_message(
                                client_ws,
                                MESSAGE_TYPE_TRANSLATED_TEXT,
                                {
                                    "text": translated_text,
                                    "original": original_text,
                                    "timestamp": timestamp,
                                    "language": target_language,
                                },
                            )
                        except Exception as e:
                            logger.error(f"Error sending to client {cid}: {e}")

                elif msg_type == MESSAGE_TYPE_REQUEST_TRANSLATION:
                    # Handle on-demand translation request from client
                    text = msg_data.get("text", "")
                    target_language = msg_data.get("target_language", "en")

                    translated_text = translate_text(text, target_language)

                    send_message(
                        ws,
                        MESSAGE_TYPE_TRANSLATION_RESULT,
                        {
                            "original": text,
                            "translated": translated_text,
                            "language": target_language,
                        },
                    )

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        if client_id in connected_clients:
            del connected_clients[client_id]
        logger.info(
            f"Client disconnected: {client_id} (Total: {len(connected_clients)})"
        )


def main():
    """Run the Flask server."""
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    logger.info("=" * 60)
    logger.info("Live Translation Server (WebSocket)")
    logger.info("=" * 60)
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"AWS Translate: {'Available' if aws_available else 'Not Available'}")
    logger.info("=" * 60)

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
