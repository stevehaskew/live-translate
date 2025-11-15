#!/usr/bin/env python3
"""
Flask Web Server for Live Translation with WebSockets
Receives text from speech-to-text app and broadcasts translations to web clients.
"""

import os
import json
import logging
from flask import Flask, send_from_directory, jsonify
from flask_sock import Sock
from dotenv import load_dotenv

# Import our refactored modules
from client_map import TranslationClientMap
from message_handler import MessageHandler, TranslationService
from token_generator import TokenGenerator

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

# Initialize translation service
translation_service = TranslationService(
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
)
aws_available = translation_service.is_available()

# Initialize token generator for AWS Transcribe credentials
my_token_generator = TokenGenerator(
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
)

# Initialize message handler with token generator
message_handler = MessageHandler(translation_service, API_KEY, my_token_generator)


# Initialize client map
client_map = TranslationClientMap()

# Load UI customization settings (for config.json endpoint)
ui_config = {
    "logoFile": os.environ.get("LT_LOGO_FILE", ""),
    "pageTitle": os.environ.get("LT_PAGE_TITLE", "🌍 Live Translation"),
    "contactText": os.environ.get("LT_CONTACT_TEXT", "your support team"),
    "websocketUrl": "",  # Auto-detected by the client
}

# Message type constants (for backward compatibility)
MESSAGE_TYPE_CONNECTION_STATUS = message_handler.MESSAGE_TYPE_CONNECTION_STATUS
MESSAGE_TYPE_SET_LANGUAGE = message_handler.MESSAGE_TYPE_SET_LANGUAGE
MESSAGE_TYPE_LANGUAGE_SET = message_handler.MESSAGE_TYPE_LANGUAGE_SET
MESSAGE_TYPE_NEW_TEXT = message_handler.MESSAGE_TYPE_NEW_TEXT
MESSAGE_TYPE_TRANSLATED_TEXT = message_handler.MESSAGE_TYPE_TRANSLATED_TEXT
MESSAGE_TYPE_REQUEST_TRANSLATION = message_handler.MESSAGE_TYPE_REQUEST_TRANSLATION
MESSAGE_TYPE_TRANSLATION_RESULT = message_handler.MESSAGE_TYPE_TRANSLATION_RESULT
MESSAGE_TYPE_GENERATE_TOKEN = message_handler.MESSAGE_TYPE_GENERATE_TOKEN
MESSAGE_TYPE_TOKEN_RESPONSE = message_handler.MESSAGE_TYPE_TOKEN_RESPONSE
MESSAGE_TYPE_ERROR = message_handler.MESSAGE_TYPE_ERROR


def send_message(ws, msg_type, data):
    """Send a WebSocket message."""
    message = {"type": msg_type, "data": data}
    ws.send(json.dumps(message))


def broadcast_message(msg_type, data, exclude_client=None):
    """Broadcast a message to all connected clients except the excluded one."""
    message = {"type": msg_type, "data": data}
    message_json = json.dumps(message)

    clients_to_remove = []
    for client_id, client_info in client_map.get_all_clients().items():
        if client_id == exclude_client:
            continue
        try:
            client_info["ws"].send(message_json)
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            clients_to_remove.append(client_id)

    # Remove disconnected clients
    for client_id in clients_to_remove:
        client_map.delete_client(client_id)


@app.route("/")
def index():
    """Serve the main web interface."""
    return send_from_directory("static", "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    """Serve static files (CSS, images, etc.)."""
    return send_from_directory("static", filename)


@app.route("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "aws_translate": aws_available,
        "connected_clients": client_map.count(),
    }


@sock.route("/ws")
def websocket_handler(ws):
    """Handle WebSocket connections."""
    client_id = id(ws)
    client_map.add_client(client_id, language="en", ws=ws)
    logger.info(f"Client connected: {client_id} (Total: {client_map.count()})")

    # Send connection status
    try:
        connection_msg = message_handler.create_connection_status_message()
        send_message(ws, connection_msg["type"], connection_msg["data"])
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
                    language = msg_data.get("lang", "en")
                    response = message_handler.handle_set_language(
                        client_id, language, client_map
                    )
                    send_message(ws, response["type"], response["data"])

                elif msg_type == MESSAGE_TYPE_GENERATE_TOKEN:
                    # Handle token generation request from speech-to-text client
                    provided_key = msg_data.get("api_key", "")
                    response = message_handler.handle_generate_token(provided_key)
                    send_message(ws, response["type"], response["data"])

                elif msg_type == MESSAGE_TYPE_NEW_TEXT:
                    # Handle new text from speech-to-text application
                    original_text = msg_data.get("text", "")
                    timestamp = msg_data.get("timestamp", "")
                    provided_key = msg_data.get("api_key", "")

                    result = message_handler.handle_new_text(
                        original_text, timestamp, provided_key, client_map
                    )

                    if result["status"] == "error":
                        logger.warning(
                            f"Unauthorized new_text attempt from {client_id}"
                        )
                        error_msg = message_handler.create_error_message(
                            result["error"]
                        )
                        send_message(ws, error_msg["type"], error_msg["data"])
                        continue

                    # Broadcast translations to all clients
                    for translation_info in result["translations"]:
                        target_client_id = translation_info["client_id"]
                        translation = translation_info["translation"]
                        client_info = client_map.get_client(target_client_id)

                        if client_info and client_info.get("ws"):
                            try:
                                send_message(
                                    client_info["ws"],
                                    MESSAGE_TYPE_TRANSLATED_TEXT,
                                    translation,
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error sending to client {target_client_id}: {e}"
                                )

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        client_map.delete_client(client_id)
        logger.info(f"Client disconnected: {client_id} (Total: {client_map.count()})")


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
