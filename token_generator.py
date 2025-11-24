#!/usr/bin/env python3
"""
AWS Token Generation Module for Live Translation.
Provides temporary session credentials for AWS Transcribe access.
This module is shared between Flask server and Lambda implementations.
"""

import logging
import os
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class TokenGenerator:
    """
    Generates temporary AWS session credentials for Transcribe access.
    Uses AWS STS AssumeRole to provide scoped, time-limited credentials.
    """

    def __init__(
        self,
        role_arn: Optional[str] = None,
        region_name: str = "us-east-1",
        session_duration: int = 3600,
    ):
        """
        Initialize the token generator.

        Args:
            role_arn: ARN of the IAM role to assume for Transcribe access
            region_name: AWS region for STS service
            session_duration: Duration in seconds for session credentials (max 3600)
        """
        self.role_arn = role_arn or os.environ.get("TRANSCRIBE_ROLE_ARN")
        self.region_name = region_name
        self.session_duration = min(session_duration, 3600)  # Max 3600 seconds
        self.sts_available = False
        self.sts_client = None

        if not self.role_arn:
            logger.warning(
                "⚠ TRANSCRIBE_ROLE_ARN not configured. Token generation unavailable."
            )
            return

        try:
            self.sts_client = boto3.client("sts", region_name=region_name)
            self.sts_available = True
            logger.info("✓ STS client initialized for token generation")
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"⚠ AWS STS not available: {e}")
            logger.warning("Token generation will not be available.")

    def generate_token(self, session_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate temporary AWS credentials for Transcribe access.

        Args:
            session_name: Optional name for the session (defaults to generated name)

        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - credentials: Dict with AccessKeyId, SecretAccessKey, SessionToken, Expiration
                - region: AWS region for Transcribe service
                - error: Error message (only if status is "error")
        """
        if not self.sts_available or not self.role_arn:
            logger.warning("Token generation attempted but not configured")
            return {
                "status": "error",
                "error": "Token generation not configured. TRANSCRIBE_ROLE_ARN required.",
            }

        try:
            # Generate unique session name if not provided
            if not session_name:
                import time

                session_name = f"live-translate-{int(time.time())}"

            logger.info(
                f"Generating AWS token (session: {session_name}, duration: {self.session_duration}s)"
            )

            # Assume role to get temporary credentials
            response = self.sts_client.assume_role(
                RoleArn=self.role_arn,
                RoleSessionName=session_name,
                DurationSeconds=self.session_duration,
            )

            credentials = response["Credentials"]

            logger.info(
                f"✓ Token generated successfully (expires: {credentials['Expiration'].isoformat()})"
            )

            return {
                "status": "success",
                "credentials": {
                    "AccessKeyId": credentials["AccessKeyId"],
                    "SecretAccessKey": credentials["SecretAccessKey"],
                    "SessionToken": credentials["SessionToken"],
                    "Expiration": credentials["Expiration"].isoformat(),
                },
                "region": self.region_name,
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Failed to generate token: {error_code} - {error_msg}")
            return {
                "status": "error",
                "error": f"Failed to generate credentials: {error_msg}",
            }
        except Exception as e:
            logger.error(f"Unexpected error generating token: {e}")
            return {"status": "error", "error": f"Unexpected error: {str(e)}"}

    def is_available(self) -> bool:
        """
        Check if token generation is available.

        Returns:
            True if token generation is available, False otherwise
        """
        return self.sts_available and self.role_arn is not None
