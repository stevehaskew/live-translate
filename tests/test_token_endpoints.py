#!/usr/bin/env python3
"""
Integration tests for token generation endpoints.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timezone
from server import app
from lambda_handler import lambda_handler, handle_http_generate_token


class TestServerTokenEndpoint(unittest.TestCase):
    """Test cases for Flask server token generation endpoint."""

    def setUp(self):
        """Set up test client."""
        self.app = app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    @patch("server.token_generator")
    def test_generate_token_success(self, mock_token_generator):
        """Test successful token generation via Flask endpoint."""
        # Mock successful token generation
        expiration = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        mock_token_generator.generate_token.return_value = {
            "status": "success",
            "credentials": {
                "AccessKeyId": "ASIATESTACCESSKEY",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": expiration.isoformat(),
            },
            "region": "us-east-1",
        }

        # Make request with valid API key
        response = self.client.post(
            "/generate_token",
            headers={"Authorization": "Bearer test-api-key"},
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertIn("credentials", data)
        self.assertEqual(data["credentials"]["AccessKeyId"], "ASIATESTACCESSKEY")

    def test_generate_token_missing_auth_header(self):
        """Test token generation without Authorization header."""
        response = self.client.post("/generate_token")

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("Unauthorized", data["error"])

    def test_generate_token_invalid_auth_format(self):
        """Test token generation with invalid Authorization header format."""
        response = self.client.post(
            "/generate_token",
            headers={"Authorization": "InvalidFormat test-api-key"},
        )

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn("error", data)

    @patch("server.token_generator")
    @patch("server.message_handler")
    def test_generate_token_invalid_api_key(self, mock_message_handler, mock_token_generator):
        """Test token generation with invalid API key."""
        # Mock API key validation to fail
        mock_message_handler.validate_api_key.return_value = False
        
        # Make request with invalid API key
        response = self.client.post(
            "/generate_token",
            headers={"Authorization": "Bearer wrong-key"},
        )

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("Invalid API key", data["error"])

    @patch("server.token_generator")
    def test_generate_token_generation_error(self, mock_token_generator):
        """Test token generation when generator returns error."""
        # Mock failed token generation
        mock_token_generator.generate_token.return_value = {
            "status": "error",
            "error": "Failed to assume role",
        }

        response = self.client.post(
            "/generate_token",
            headers={"Authorization": "Bearer test-api-key"},
        )

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertIn("error", data)


class TestLambdaTokenHandler(unittest.TestCase):
    """Test cases for Lambda token generation handler."""

    @patch("lambda_handler.token_generator")
    @patch("lambda_handler.message_handler")
    def test_handle_http_generate_token_success(
        self, mock_message_handler, mock_token_generator
    ):
        """Test successful token generation via Lambda handler."""
        # Mock API key validation
        mock_message_handler.validate_api_key.return_value = True

        # Mock successful token generation
        expiration = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        mock_token_generator.generate_token.return_value = {
            "status": "success",
            "credentials": {
                "AccessKeyId": "ASIATESTACCESSKEY",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": expiration.isoformat(),
            },
            "region": "us-east-1",
        }

        # Create Lambda event
        event = {
            "requestContext": {"http": {"method": "POST", "path": "/generate_token"}},
            "headers": {"Authorization": "Bearer test-api-key"},
        }

        # Call handler
        response = handle_http_generate_token(event, None)

        self.assertEqual(response["statusCode"], 200)
        data = json.loads(response["body"])
        self.assertEqual(data["status"], "success")
        self.assertIn("credentials", data)

    @patch("lambda_handler.message_handler")
    def test_handle_http_generate_token_missing_auth(self, mock_message_handler):
        """Test token generation without Authorization header."""
        event = {
            "requestContext": {"http": {"method": "POST", "path": "/generate_token"}},
            "headers": {},
        }

        response = handle_http_generate_token(event, None)

        self.assertEqual(response["statusCode"], 401)
        data = json.loads(response["body"])
        self.assertIn("error", data)

    @patch("lambda_handler.message_handler")
    def test_handle_http_generate_token_invalid_key(self, mock_message_handler):
        """Test token generation with invalid API key."""
        # Mock API key validation to fail
        mock_message_handler.validate_api_key.return_value = False

        event = {
            "requestContext": {"http": {"method": "POST", "path": "/generate_token"}},
            "headers": {"Authorization": "Bearer wrong-key"},
        }

        response = handle_http_generate_token(event, None)

        self.assertEqual(response["statusCode"], 401)
        data = json.loads(response["body"])
        self.assertIn("error", data)

    @patch("lambda_handler.token_generator")
    @patch("lambda_handler.message_handler")
    def test_lambda_handler_http_route(
        self, mock_message_handler, mock_token_generator
    ):
        """Test Lambda handler routing for HTTP generate_token endpoint."""
        # Mock API key validation
        mock_message_handler.validate_api_key.return_value = True

        # Mock successful token generation
        mock_token_generator.generate_token.return_value = {
            "status": "success",
            "credentials": {
                "AccessKeyId": "ASIATESTACCESSKEY",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": "2024-12-31T23:59:59+00:00",
            },
            "region": "us-east-1",
        }

        # Create Lambda event for HTTP request
        event = {
            "requestContext": {"http": {"method": "POST", "path": "/generate_token"}},
            "headers": {"Authorization": "Bearer test-api-key"},
            "path": "/generate_token",
            "httpMethod": "POST",
        }

        response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        data = json.loads(response["body"])
        self.assertEqual(data["status"], "success")

    def test_lambda_handler_http_not_found(self):
        """Test Lambda handler for unknown HTTP route."""
        event = {
            "requestContext": {"http": {"method": "GET", "path": "/unknown"}},
            "headers": {},
            "path": "/unknown",
            "httpMethod": "GET",
        }

        response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 404)

    @patch("lambda_handler.client_map")
    def test_lambda_handler_websocket_route(self, mock_client_map):
        """Test Lambda handler still handles WebSocket routes."""
        # Mock client map
        mock_client_map.add_client = MagicMock()

        # Create Lambda event for WebSocket connect
        event = {
            "requestContext": {
                "routeKey": "$connect",
                "connectionId": "test-connection-id",
            }
        }

        response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        mock_client_map.add_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
