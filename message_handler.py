#!/usr/bin/env python3
"""
Message handling logic for Live Translation.
Contains reusable business logic that can be used with Flask or AWS API Gateway.
"""

import logging
import secrets
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class TranslationService:
    """
    Service for handling text translation using AWS Translate.
    """

    def __init__(self, region_name: str = "us-east-1"):
        """
        Initialize the translation service.

        Args:
            region_name: AWS region for Translate service
        """
        self.region_name = region_name
        self.aws_available = False
        self.translate_client = None

        try:
            self.translate_client = boto3.client("translate", region_name=region_name)
            self.aws_available = True
            logger.info("✓ AWS Translate client initialized")
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"⚠ AWS Translate not available: {e}")
            logger.warning("Translation features will be limited.")

    def translate_text(
        self, text: str, target_language: str, source_language: str = "auto"
    ) -> str:
        """
        Translate text using AWS Translate.

        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'es' for Spanish)
            source_language: Source language code ('auto' for auto-detection)

        Returns:
            Translated text or original text if translation fails
        """
        if not self.aws_available:
            return text

        # Don't translate if target is English (source language)
        if target_language == "en":
            return text

        try:
            response = self.translate_client.translate_text(
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

    def is_available(self) -> bool:
        """
        Check if AWS Translate is available.

        Returns:
            True if AWS Translate is available, False otherwise
        """
        return self.aws_available


class MessageHandler:
    """
    Handles incoming WebSocket messages and coordinates responses.
    Reusable across different server implementations (Flask, API Gateway, etc.).
    """

    # Message type constants
    MESSAGE_TYPE_CONNECTION_STATUS = "connection_status"
    MESSAGE_TYPE_SET_LANGUAGE = "set_language"
    MESSAGE_TYPE_LANGUAGE_SET = "language_set"
    MESSAGE_TYPE_NEW_TEXT = "new_text"
    MESSAGE_TYPE_TRANSLATED_TEXT = "translated_text"
    MESSAGE_TYPE_REQUEST_TRANSLATION = "request_translation"
    MESSAGE_TYPE_TRANSLATION_RESULT = "translation_result"
    MESSAGE_TYPE_ERROR = "error"

    def __init__(
        self,
        translation_service: TranslationService,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the message handler.

        Args:
            translation_service: TranslationService instance
            api_key: Optional API key for authentication
        """
        self.translation_service = translation_service
        self.api_key = api_key

    def validate_api_key(self, provided_key: str) -> bool:
        """
        Validate an API key using constant-time comparison.

        Args:
            provided_key: API key to validate

        Returns:
            True if valid or no API key configured, False otherwise
        """
        if not self.api_key:
            return True  # No API key configured, allow access

        return secrets.compare_digest(provided_key, self.api_key)

    def handle_set_language(
        self, client_id: Any, language: str, client_map: Any
    ) -> Dict[str, Any]:
        """
        Handle language preference update from client.

        Args:
            client_id: Unique identifier for the client
            language: Preferred language code
            client_map: Client map instance

        Returns:
            Response message dictionary
        """
        success = client_map.update_language(client_id, language)
        if success:
            logger.info(f"Client {client_id} language set to: {language}")
            return {
                "type": self.MESSAGE_TYPE_LANGUAGE_SET,
                "data": {"language": language},
            }
        else:
            return {
                "type": self.MESSAGE_TYPE_ERROR,
                "data": {"message": "Failed to update language preference"},
            }

    def handle_new_text(
        self,
        text: str,
        timestamp: str,
        api_key: str,
        client_map: Any,
    ) -> Dict[str, Any]:
        """
        Handle new text from speech-to-text application.

        Args:
            text: Original text to translate
            timestamp: Timestamp of the text
            api_key: Provided API key for authentication
            client_map: Client map instance

        Returns:
            Result dictionary with status and translations or error
        """
        # Validate API key if configured
        if not self.validate_api_key(api_key):
            logger.warning("Unauthorized new_text attempt")
            return {
                "status": "error",
                "error": "Unauthorized: Invalid API key",
                "type": self.MESSAGE_TYPE_ERROR,
            }

        logger.info(f"New text received: {text}")

        # Prepare translations for all clients
        translations = []
        for client_id, client_info in client_map.get_all_clients().items():
            target_language = client_info.get("language", "en")

            if target_language == "en":
                translated_text = text
            else:
                translated_text = self.translation_service.translate_text(
                    text, target_language
                )

            translations.append(
                {
                    "client_id": client_id,
                    "translation": {
                        "text": translated_text,
                        "original": text,
                        "timestamp": timestamp,
                        "language": target_language,
                    },
                }
            )

        return {
            "status": "success",
            "translations": translations,
            "type": self.MESSAGE_TYPE_TRANSLATED_TEXT,
        }

    def handle_request_translation(
        self, text: str, target_language: str
    ) -> Dict[str, Any]:
        """
        Handle on-demand translation request from client.

        Args:
            text: Text to translate
            target_language: Target language code

        Returns:
            Response message dictionary
        """
        translated_text = self.translation_service.translate_text(text, target_language)

        return {
            "type": self.MESSAGE_TYPE_TRANSLATION_RESULT,
            "data": {
                "original": text,
                "translated": translated_text,
                "language": target_language,
            },
        }

    def create_connection_status_message(self) -> Dict[str, Any]:
        """
        Create a connection status message.

        Returns:
            Connection status message dictionary
        """
        return {
            "type": self.MESSAGE_TYPE_CONNECTION_STATUS,
            "data": {
                "status": "connected",
                "aws_available": self.translation_service.is_available(),
            },
        }

    def create_error_message(self, error_text: str) -> Dict[str, Any]:
        """
        Create an error message.

        Args:
            error_text: Error message text

        Returns:
            Error message dictionary
        """
        return {
            "type": self.MESSAGE_TYPE_ERROR,
            "data": {"message": error_text},
        }
