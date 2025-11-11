#!/usr/bin/env python3
"""
Integration tests for the refactored server.
Tests WebSocket functionality with the new modules.
"""

import unittest
from unittest.mock import Mock, patch


class TestServerIntegration(unittest.TestCase):
    """Integration tests for the Flask server."""

    def setUp(self):
        """Set up test fixtures."""
        # Import server modules here to avoid interfering with other tests
        from server import app, client_map, message_handler

        self.app = app
        self.client_map = client_map
        self.message_handler = message_handler
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_health_endpoint(self):
        """Test the health endpoint returns expected data."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn("status", data)
        self.assertIn("aws_translate", data)
        self.assertIn("connected_clients", data)
        self.assertEqual(data["status"], "healthy")

    def test_index_endpoint(self):
        """Test the index endpoint returns HTML."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertGreater(len(response.data), 0)

    def test_client_map_integration(self):
        """Test that the global client_map works correctly."""
        # Initial count should be 0
        initial_count = self.client_map.count()

        # Add a client
        ws_mock = Mock()
        self.client_map.add_client("test_client", "es", ws_mock)
        self.assertEqual(self.client_map.count(), initial_count + 1)

        # Get the client
        client = self.client_map.get_client("test_client")
        self.assertIsNotNone(client)
        self.assertEqual(client["language"], "es")

        # Update language
        result = self.client_map.update_language("test_client", "fr")
        self.assertTrue(result)
        client = self.client_map.get_client("test_client")
        self.assertEqual(client["language"], "fr")

        # Delete the client
        self.client_map.delete_client("test_client")
        self.assertEqual(self.client_map.count(), initial_count)

    def test_message_handler_integration(self):
        """Test that the global message_handler works correctly."""
        # Test connection status message
        msg = self.message_handler.create_connection_status_message()
        self.assertEqual(msg["type"], "connection_status")
        self.assertIn("aws_available", msg["data"])

        # Test error message
        error_msg = self.message_handler.create_error_message("Test error")
        self.assertEqual(error_msg["type"], "error")
        self.assertEqual(error_msg["data"]["message"], "Test error")

    def test_message_handler_with_client_map(self):
        """Test message handler interacting with client map."""
        # Set up test clients
        ws1 = Mock()
        ws2 = Mock()
        self.client_map.add_client("client1", "en", ws1)
        self.client_map.add_client("client2", "es", ws2)

        # Test handle_set_language
        response = self.message_handler.handle_set_language(
            "client1", "de", self.client_map
        )
        self.assertEqual(response["type"], "language_set")
        self.assertEqual(response["data"]["language"], "de")

        # Verify the language was updated
        client = self.client_map.get_client("client1")
        self.assertEqual(client["language"], "de")

        # Clean up
        self.client_map.delete_client("client1")
        self.client_map.delete_client("client2")

    @patch("server.message_handler")
    def test_message_handler_new_text_flow(self, mock_handler):
        """Test the full new_text message flow."""
        # Get the real handler from setUp
        real_handler = self.message_handler

        # Set up mock translation on the real handler's translation service
        with patch.object(
            real_handler.translation_service, "translate_text"
        ) as mock_translate:
            mock_translate.return_value = "Hola mundo"

            # Set up test clients
            ws1 = Mock()
            ws2 = Mock()
            self.client_map.add_client("client1", "en", ws1)
            self.client_map.add_client("client2", "es", ws2)

            # Simulate new text with no API key required (handler has None key)
            result = real_handler.handle_new_text(
                "Hello world", "2024-01-01T00:00:00", "", self.client_map
            )

            # Verify result
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["translations"]), 2)

            # English client should get original text
            en_translation = next(
                t for t in result["translations"] if t["client_id"] == "client1"
            )
            self.assertEqual(en_translation["translation"]["text"], "Hello world")

            # Spanish client should get translated text
            es_translation = next(
                t for t in result["translations"] if t["client_id"] == "client2"
            )
            self.assertEqual(es_translation["translation"]["text"], "Hola mundo")

            # Clean up
            self.client_map.delete_client("client1")
            self.client_map.delete_client("client2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
