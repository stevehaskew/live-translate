#!/usr/bin/env python3
"""
Unit tests for the TokenGenerator class.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError
from token_generator import TokenGenerator


class TestTokenGenerator(unittest.TestCase):
    """Test cases for TokenGenerator class."""

    @patch("token_generator.boto3.client")
    def test_initialization_with_role_arn(self, mock_boto_client):
        """Test successful initialization with role ARN."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        self.assertTrue(generator.is_available())
        self.assertEqual(generator.role_arn, "arn:aws:iam::123456789012:role/TestRole")
        self.assertEqual(generator.region_name, "us-east-1")
        mock_boto_client.assert_called_once_with("sts", region_name="us-east-1")

    @patch("token_generator.boto3.client")
    def test_initialization_without_role_arn(self, mock_boto_client):
        """Test initialization without role ARN."""
        generator = TokenGenerator(role_arn=None, region_name="us-east-1")

        self.assertFalse(generator.is_available())
        self.assertIsNone(generator.role_arn)
        mock_boto_client.assert_not_called()

    @patch("token_generator.boto3.client")
    def test_initialization_with_env_var(self, mock_boto_client):
        """Test initialization with role ARN from environment variable."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        with patch.dict(
            "os.environ",
            {"TRANSCRIBE_ROLE_ARN": "arn:aws:iam::123456789012:role/EnvRole"},
        ):
            generator = TokenGenerator(region_name="us-east-1")

            self.assertTrue(generator.is_available())
            self.assertEqual(
                generator.role_arn, "arn:aws:iam::123456789012:role/EnvRole"
            )

    @patch("token_generator.boto3.client")
    def test_initialization_no_credentials(self, mock_boto_client):
        """Test initialization fails gracefully without AWS credentials."""
        mock_boto_client.side_effect = NoCredentialsError()

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        self.assertFalse(generator.is_available())

    @patch("token_generator.boto3.client")
    def test_generate_token_success(self, mock_boto_client):
        """Test successful token generation."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        # Mock assume_role response
        expiration = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIATESTACCESSKEY",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": expiration,
            }
        }

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        result = generator.generate_token(session_name="test-session")

        self.assertEqual(result["status"], "success")
        self.assertIn("credentials", result)
        self.assertEqual(result["credentials"]["AccessKeyId"], "ASIATESTACCESSKEY")
        self.assertEqual(result["credentials"]["SecretAccessKey"], "test-secret-key")
        self.assertEqual(result["credentials"]["SessionToken"], "test-session-token")
        self.assertEqual(result["region"], "us-east-1")

        # Verify assume_role was called correctly
        mock_sts.assume_role.assert_called_once()
        call_args = mock_sts.assume_role.call_args
        self.assertEqual(
            call_args[1]["RoleArn"], "arn:aws:iam::123456789012:role/TestRole"
        )
        self.assertEqual(call_args[1]["RoleSessionName"], "test-session")
        self.assertEqual(call_args[1]["DurationSeconds"], 3600)

    @patch("token_generator.boto3.client")
    def test_generate_token_auto_session_name(self, mock_boto_client):
        """Test token generation with auto-generated session name."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        expiration = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIATESTACCESSKEY",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": expiration,
            }
        }

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        result = generator.generate_token()

        self.assertEqual(result["status"], "success")

        # Verify session name was auto-generated
        mock_sts.assume_role.assert_called_once()
        call_args = mock_sts.assume_role.call_args
        session_name = call_args[1]["RoleSessionName"]
        self.assertTrue(session_name.startswith("live-translate-"))

    @patch("token_generator.boto3.client")
    def test_generate_token_not_available(self, mock_boto_client):
        """Test token generation when service is not available."""
        generator = TokenGenerator(role_arn=None, region_name="us-east-1")

        result = generator.generate_token()

        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)
        self.assertIn("not configured", result["error"])

    @patch("token_generator.boto3.client")
    def test_generate_token_client_error(self, mock_boto_client):
        """Test token generation with AWS client error."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        # Mock client error
        error_response = {
            "Error": {"Code": "AccessDenied", "Message": "User is not authorized"}
        }
        mock_sts.assume_role.side_effect = ClientError(error_response, "AssumeRole")

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        result = generator.generate_token()

        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)
        self.assertIn("User is not authorized", result["error"])

    @patch("token_generator.boto3.client")
    def test_generate_token_unexpected_error(self, mock_boto_client):
        """Test token generation with unexpected error."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        mock_sts.assume_role.side_effect = Exception("Unexpected error")

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        result = generator.generate_token()

        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)
        self.assertIn("Unexpected error", result["error"])

    @patch("token_generator.boto3.client")
    def test_session_duration_max_limit(self, mock_boto_client):
        """Test that session duration is capped at 3600 seconds."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        # Try to set duration longer than max
        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
            session_duration=7200,  # 2 hours
        )

        self.assertEqual(generator.session_duration, 3600)  # Should be capped to 1 hour

    @patch("token_generator.boto3.client")
    def test_is_available_true(self, mock_boto_client):
        """Test is_available returns True when properly configured."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        self.assertTrue(generator.is_available())

    @patch("token_generator.boto3.client")
    def test_is_available_false_no_role(self, mock_boto_client):
        """Test is_available returns False without role ARN."""
        generator = TokenGenerator(role_arn=None, region_name="us-east-1")

        self.assertFalse(generator.is_available())

    @patch("token_generator.boto3.client")
    def test_is_available_false_no_credentials(self, mock_boto_client):
        """Test is_available returns False without credentials."""
        mock_boto_client.side_effect = NoCredentialsError()

        generator = TokenGenerator(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region_name="us-east-1",
        )

        self.assertFalse(generator.is_available())


if __name__ == "__main__":
    unittest.main()
