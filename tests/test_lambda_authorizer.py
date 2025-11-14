#!/usr/bin/env python3
"""
Unit tests for Lambda authorizer.
"""

import unittest
import os
import sys

# Set up test environment
os.environ["API_KEY"] = "test-api-key-123"


class TestLambdaAuthorizer(unittest.TestCase):
    """Test cases for Lambda authorizer functions."""

    def setUp(self):
        """Set up test fixtures."""
        # Import lambda_authorizer after setting env vars
        import lambda_authorizer
        self.lambda_authorizer = lambda_authorizer

    def test_authorizer_no_api_key_header(self):
        """Test authorizer with no API key in headers (web client)."""
        event = {
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            "headers": {},
        }
        context = {}

        response = self.lambda_authorizer.lambda_handler(event, context)

        self.assertEqual(response["policyDocument"]["Statement"][0]["Effect"], "Allow")
        self.assertFalse(response["context"]["isAuthorizedSender"])

    def test_authorizer_valid_api_key(self):
        """Test authorizer with valid API key (speech-to-text client)."""
        event = {
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            "headers": {
                "X-API-Key": "test-api-key-123"
            },
        }
        context = {}

        response = self.lambda_authorizer.lambda_handler(event, context)

        self.assertEqual(response["policyDocument"]["Statement"][0]["Effect"], "Allow")
        self.assertTrue(response["context"]["isAuthorizedSender"])

    def test_authorizer_invalid_api_key(self):
        """Test authorizer with invalid API key."""
        event = {
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            "headers": {
                "X-API-Key": "wrong-key"
            },
        }
        context = {}

        response = self.lambda_authorizer.lambda_handler(event, context)

        self.assertEqual(response["policyDocument"]["Statement"][0]["Effect"], "Deny")

    def test_authorizer_case_insensitive_header(self):
        """Test authorizer with lowercase header name."""
        event = {
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            "headers": {
                "x-api-key": "test-api-key-123"
            },
        }
        context = {}

        response = self.lambda_authorizer.lambda_handler(event, context)

        self.assertEqual(response["policyDocument"]["Statement"][0]["Effect"], "Allow")
        self.assertTrue(response["context"]["isAuthorizedSender"])

    def test_generate_policy_allow(self):
        """Test generating Allow policy."""
        policy = self.lambda_authorizer.generate_policy(
            "Allow",
            "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            {"isAuthorizedSender": True}
        )

        self.assertEqual(policy["principalId"], "user")
        self.assertEqual(policy["policyDocument"]["Statement"][0]["Effect"], "Allow")
        self.assertEqual(policy["policyDocument"]["Statement"][0]["Action"], "execute-api:Invoke")
        self.assertTrue(policy["context"]["isAuthorizedSender"])

    def test_generate_policy_deny(self):
        """Test generating Deny policy."""
        policy = self.lambda_authorizer.generate_policy(
            "Deny",
            "arn:aws:execute-api:us-east-1:123456789012:abcdef123/$connect",
            {}
        )

        self.assertEqual(policy["principalId"], "user")
        self.assertEqual(policy["policyDocument"]["Statement"][0]["Effect"], "Deny")
        self.assertEqual(policy["policyDocument"]["Statement"][0]["Action"], "execute-api:Invoke")


if __name__ == "__main__":
    unittest.main()
