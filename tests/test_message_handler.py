#!/usr/bin/env python3
"""
Unit tests for message handling logic.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from message_handler import TranslationService, MessageHandler


class TestTranslationService(unittest.TestCase):
    """Test cases for TranslationService class."""

    @patch("message_handler.boto3.client")
    def test_initialization_with_aws(self, mock_boto_client):
        """Test initialization when AWS is available."""
        mock_translate = MagicMock()
        mock_boto_client.return_value = mock_translate

        service = TranslationService("us-west-2")

        self.assertTrue(service.aws_available)
        self.assertIsNotNone(service.translate_client)
        mock_boto_client.assert_called_once_with("translate", region_name="us-west-2")

    @patch("message_handler.boto3.client")
    def test_initialization_without_aws(self, mock_boto_client):
        """Test initialization when AWS is not available."""
        mock_boto_client.side_effect = Exception("No credentials")

        service = TranslationService()

        self.assertFalse(service.aws_available)
        self.assertIsNone(service.translate_client)

    @patch("message_handler.boto3.client")
    def test_translate_text_success(self, mock_boto_client):
        """Test successful text translation."""
        mock_translate = MagicMock()
        mock_translate.translate_text.return_value = {"TranslatedText": "Hola mundo"}
        mock_boto_client.return_value = mock_translate

        service = TranslationService()
        result = service.translate_text("Hello world", "es")

        self.assertEqual(result, "Hola mundo")
        mock_translate.translate_text.assert_called_once_with(
            Text="Hello world",
            SourceLanguageCode="auto",
            TargetLanguageCode="es",
        )

    @patch("message_handler.boto3.client")
    def test_translate_text_to_english(self, mock_boto_client):
        """Test that translating to English returns original text."""
        mock_translate = MagicMock()
        mock_boto_client.return_value = mock_translate

        service = TranslationService()
        result = service.translate_text("Hello world", "en")

        self.assertEqual(result, "Hello world")
        mock_translate.translate_text.assert_not_called()

    @patch("message_handler.boto3.client")
    def test_translate_text_without_aws(self, mock_boto_client):
        """Test translation when AWS is not available."""
        mock_boto_client.side_effect = Exception("No credentials")

        service = TranslationService()
        result = service.translate_text("Hello world", "es")

        self.assertEqual(result, "Hello world")

    @patch("message_handler.boto3.client")
    def test_translate_text_with_error(self, mock_boto_client):
        """Test translation with AWS error."""
        mock_translate = MagicMock()
        mock_translate.translate_text.side_effect = Exception("Translation error")
        mock_boto_client.return_value = mock_translate

        service = TranslationService()
        result = service.translate_text("Hello world", "es")

        self.assertEqual(result, "Hello world")

    @patch("message_handler.boto3.client")
    def test_is_available(self, mock_boto_client):
        """Test checking if AWS Translate is available."""
        mock_translate = MagicMock()
        mock_boto_client.return_value = mock_translate

        service = TranslationService()
        self.assertTrue(service.is_available())

        # Test when not available
        mock_boto_client.side_effect = Exception("No credentials")
        service2 = TranslationService()
        self.assertFalse(service2.is_available())


class TestMessageHandler(unittest.TestCase):
    """Test cases for MessageHandler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_translation_service = Mock()
        self.api_key = "test-api-key-12345"
        self.handler = MessageHandler(self.mock_translation_service, self.api_key)

    def test_validate_api_key_correct(self):
        """Test API key validation with correct key."""
        result = self.handler.validate_api_key("test-api-key-12345")
        self.assertTrue(result)

    def test_validate_api_key_incorrect(self):
        """Test API key validation with incorrect key."""
        result = self.handler.validate_api_key("wrong-key")
        self.assertFalse(result)

    def test_validate_api_key_no_key_configured(self):
        """Test API key validation when no key is configured."""
        handler = MessageHandler(self.mock_translation_service, None)
        result = handler.validate_api_key("any-key")
        self.assertTrue(result)

    def test_handle_set_language_success(self):
        """Test handling language preference update."""
        mock_client_map = Mock()
        mock_client_map.update_language.return_value = True

        response = self.handler.handle_set_language("client1", "es", mock_client_map)

        self.assertEqual(response["type"], self.handler.MESSAGE_TYPE_LANGUAGE_SET)
        self.assertEqual(response["data"]["lang"], "es")
        mock_client_map.update_language.assert_called_once_with("client1", "es")

    def test_handle_set_language_failure(self):
        """Test handling language preference update failure."""
        mock_client_map = Mock()
        mock_client_map.update_language.return_value = False

        response = self.handler.handle_set_language("client1", "es", mock_client_map)

        self.assertEqual(response["type"], self.handler.MESSAGE_TYPE_ERROR)
        self.assertIn("Failed", response["data"]["message"])

    def test_handle_new_text_unauthorized(self):
        """Test that authorization is now handled at API Gateway/connection level, not in handle_new_text."""
        # This test is no longer relevant as authorization is handled at connection time
        # handle_new_text now assumes the caller has already validated authorization
        mock_client_map = Mock()
        mock_client_map.get_all_clients.return_value = {
            "client1": {"lang": "en", "ws": Mock()},
        }

        result = self.handler.handle_new_text(
            "Hello", "2024-01-01", mock_client_map
        )

        # Should succeed because authorization is assumed to be done before calling this
        self.assertEqual(result["status"], "success")

    def test_handle_new_text_success(self):
        """Test handling new text (authorization is now handled at API Gateway level)."""
        mock_client_map = Mock()
        mock_client_map.get_all_clients.return_value = {
            "client1": {"lang": "en", "ws": Mock()},
            "client2": {"lang": "es", "ws": Mock()},
        }
        self.mock_translation_service.translate_text.return_value = "Hola"

        result = self.handler.handle_new_text(
            "Hello", "2024-01-01", mock_client_map
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["translations"]), 2)
        self.assertEqual(result["translations"][0]["translation"]["text"], "Hello")
        self.assertEqual(result["translations"][1]["translation"]["text"], "Hola")
        self.mock_translation_service.translate_text.assert_called_once_with(
            "Hello", "es"
        )

    def test_handle_request_translation(self):
        """Test handling on-demand translation request."""
        self.mock_translation_service.translate_text.return_value = "Bonjour monde"

        response = self.handler.handle_request_translation("Hello world", "fr")

        self.assertEqual(response["type"], self.handler.MESSAGE_TYPE_TRANSLATION_RESULT)
        self.assertEqual(response["data"]["original"], "Hello world")
        self.assertEqual(response["data"]["translated"], "Bonjour monde")
        self.assertEqual(response["data"]["lang"], "fr")
        self.mock_translation_service.translate_text.assert_called_once_with(
            "Hello world", "fr"
        )

    def test_create_connection_status_message(self):
        """Test creating connection status message."""
        self.mock_translation_service.is_available.return_value = True

        message = self.handler.create_connection_status_message()

        self.assertEqual(message["type"], self.handler.MESSAGE_TYPE_CONNECTION_STATUS)
        self.assertEqual(message["data"]["status"], "connected")
        self.assertTrue(message["data"]["aws_available"])

    def test_create_error_message(self):
        """Test creating error message."""
        message = self.handler.create_error_message("Test error")

        self.assertEqual(message["type"], self.handler.MESSAGE_TYPE_ERROR)
        self.assertEqual(message["data"]["message"], "Test error")

    def test_message_type_constants(self):
        """Test that message type constants are defined."""
        self.assertEqual(
            self.handler.MESSAGE_TYPE_CONNECTION_STATUS, "connection_status"
        )
        self.assertEqual(self.handler.MESSAGE_TYPE_SET_LANGUAGE, "set_language")
        self.assertEqual(self.handler.MESSAGE_TYPE_LANGUAGE_SET, "language_set")
        self.assertEqual(self.handler.MESSAGE_TYPE_NEW_TEXT, "new_text")
        self.assertEqual(self.handler.MESSAGE_TYPE_TRANSLATED_TEXT, "translated_text")
        self.assertEqual(
            self.handler.MESSAGE_TYPE_REQUEST_TRANSLATION, "request_translation"
        )
        self.assertEqual(
            self.handler.MESSAGE_TYPE_TRANSLATION_RESULT, "translation_result"
        )
        self.assertEqual(self.handler.MESSAGE_TYPE_ERROR, "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
