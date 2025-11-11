#!/usr/bin/env python3
"""
Unit tests for Lambda WebSocket handler.
"""

import json
import unittest
from unittest.mock import MagicMock, patch, call
import os
import sys

# Mock boto3 before importing lambda_handler
sys.modules["boto3"] = MagicMock()


class TestLambdaHandler(unittest.TestCase):
    """Test cases for Lambda handler functions."""

    def setUp(self):
        """Set up test fixtures."""
        # Set environment variables
        os.environ["DYNAMODB_TABLE_NAME"] = "test-connections"
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["API_KEY"] = "test-api-key-123"

        # Import lambda_handler after setting env vars
        import lambda_handler

        self.lambda_handler = lambda_handler

        # Create a fresh client map for each test
        from client_map import TranslationClientMap

        self.lambda_handler.client_map = TranslationClientMap()

    def test_handle_connect(self):
        """Test handling WebSocket connect event."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$connect",
            }
        }
        context = {}

        response = self.lambda_handler.handle_connect(event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "Connected")

        # Verify client was added to map
        client = self.lambda_handler.client_map.get_client("test-connection-123")
        self.assertIsNotNone(client)
        self.assertEqual(client["language"], "en")

    def test_handle_disconnect(self):
        """Test handling WebSocket disconnect event."""
        # First add a client
        self.lambda_handler.client_map.add_client("test-connection-123", language="en")

        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$disconnect",
            }
        }
        context = {}

        response = self.lambda_handler.handle_disconnect(event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "Disconnected")

        # Verify client was removed from map
        client = self.lambda_handler.client_map.get_client("test-connection-123")
        self.assertIsNone(client)

    @patch("lambda_handler.get_apigw_management_client")
    def test_handle_message_set_language(self, mock_get_client):
        """Test handling set_language message."""
        # Add client first
        self.lambda_handler.client_map.add_client("test-connection-123", language="en")

        mock_apigw = MagicMock()
        mock_get_client.return_value = mock_apigw

        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$default",
                "domainName": "test.execute-api.us-east-1.amazonaws.com",
                "stage": "production",
            },
            "body": json.dumps({"type": "set_language", "data": {"language": "es"}}),
        }
        context = {}

        response = self.lambda_handler.handle_message(event, context)

        self.assertEqual(response["statusCode"], 200)

        # Verify language was updated
        client = self.lambda_handler.client_map.get_client("test-connection-123")
        self.assertEqual(client["language"], "es")

        # Verify messages were sent
        self.assertTrue(mock_apigw.post_to_connection.called)

    @patch("lambda_handler.get_apigw_management_client")
    def test_handle_message_new_text_unauthorized(self, mock_get_client):
        """Test handling new_text message with invalid API key."""
        mock_apigw = MagicMock()
        mock_get_client.return_value = mock_apigw

        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$default",
                "domainName": "test.execute-api.us-east-1.amazonaws.com",
                "stage": "production",
            },
            "body": json.dumps(
                {
                    "type": "new_text",
                    "data": {
                        "text": "Hello world",
                        "timestamp": "12:00:00",
                        "api_key": "wrong-key",
                    },
                }
            ),
        }
        context = {}

        response = self.lambda_handler.handle_message(event, context)

        self.assertEqual(response["statusCode"], 401)
        self.assertEqual(response["body"], "Unauthorized")

    @patch("lambda_handler.get_apigw_management_client")
    def test_handle_message_new_text_authorized(self, mock_get_client):
        """Test handling new_text message with valid API key."""
        # Add a client
        self.lambda_handler.client_map.add_client("test-connection-123", language="en")

        mock_apigw = MagicMock()
        mock_get_client.return_value = mock_apigw

        event = {
            "requestContext": {
                "connectionId": "test-connection-456",
                "routeKey": "$default",
                "domainName": "test.execute-api.us-east-1.amazonaws.com",
                "stage": "production",
            },
            "body": json.dumps(
                {
                    "type": "new_text",
                    "data": {
                        "text": "Hello world",
                        "timestamp": "12:00:00",
                        "api_key": "test-api-key-123",
                    },
                }
            ),
        }
        context = {}

        response = self.lambda_handler.handle_message(event, context)

        self.assertEqual(response["statusCode"], 200)

        # Verify translation was sent to connected client
        self.assertTrue(mock_apigw.post_to_connection.called)
        calls = mock_apigw.post_to_connection.call_args_list
        self.assertTrue(len(calls) > 0)

        # Check that the message was sent to the right connection
        sent_to_connections = [call[1]["ConnectionId"] for call in calls]
        self.assertIn("test-connection-123", sent_to_connections)

    def test_lambda_handler_connect_route(self):
        """Test main lambda_handler with $connect route."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$connect",
            }
        }
        context = {}

        response = self.lambda_handler.lambda_handler(event, context)

        self.assertEqual(response["statusCode"], 200)

    def test_lambda_handler_disconnect_route(self):
        """Test main lambda_handler with $disconnect route."""
        # Add client first
        self.lambda_handler.client_map.add_client("test-connection-123", language="en")

        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$disconnect",
            }
        }
        context = {}

        response = self.lambda_handler.lambda_handler(event, context)

        self.assertEqual(response["statusCode"], 200)

    def test_lambda_handler_unknown_route(self):
        """Test main lambda_handler with unknown route."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-123",
                "routeKey": "$unknown",
            }
        }
        context = {}

        response = self.lambda_handler.lambda_handler(event, context)

        self.assertEqual(response["statusCode"], 400)
        self.assertIn("Unknown route", response["body"])

    @patch("lambda_handler.get_apigw_management_client")
    def test_send_message_to_connection_success(self, mock_get_client):
        """Test successfully sending message to a connection."""
        mock_apigw = MagicMock()
        mock_get_client.return_value = mock_apigw

        message = {"type": "test", "data": {"foo": "bar"}}
        result = self.lambda_handler.send_message_to_connection(
            "test-connection-123", message, mock_apigw
        )

        self.assertTrue(result)
        mock_apigw.post_to_connection.assert_called_once()

    @patch("lambda_handler.get_apigw_management_client")
    def test_send_message_to_connection_gone(self, mock_get_client):
        """Test sending message to gone connection (410 error)."""
        from botocore.exceptions import ClientError

        mock_apigw = MagicMock()
        mock_apigw.post_to_connection.side_effect = ClientError(
            {"Error": {"Code": "GoneException"}}, "post_to_connection"
        )
        mock_get_client.return_value = mock_apigw

        # Add client first
        self.lambda_handler.client_map.add_client("test-connection-123", language="en")

        message = {"type": "test", "data": {"foo": "bar"}}
        result = self.lambda_handler.send_message_to_connection(
            "test-connection-123", message, mock_apigw
        )

        self.assertFalse(result)

        # Verify client was removed from map
        client = self.lambda_handler.client_map.get_client("test-connection-123")
        self.assertIsNone(client)

    def test_get_apigw_management_client(self):
        """Test getting API Gateway management client."""
        with patch("lambda_handler.boto3.client") as mock_boto_client:
            event = {
                "requestContext": {
                    "domainName": "test.execute-api.us-east-1.amazonaws.com",
                    "stage": "production",
                }
            }

            # Reset global client
            self.lambda_handler.apigw_management_client = None

            client = self.lambda_handler.get_apigw_management_client(event)

            self.assertIsNotNone(client)
            mock_boto_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
