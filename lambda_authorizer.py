#!/usr/bin/env python3
"""
Lambda authorizer for API Gateway WebSocket connections.
Validates API key in connection headers for speech-to-text client authentication.
"""

import os
import secrets
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
API_KEY = os.environ.get("API_KEY")


def lambda_handler(event, context):
    """
    Lambda authorizer handler for WebSocket $connect route.
    
    Checks for X-API-Key header and validates it against configured API key.
    If no API key is provided in headers, allows connection (for web clients).
    If API key is provided, validates it.
    
    Args:
        event: Lambda authorizer event from API Gateway
        context: Lambda context
        
    Returns:
        IAM policy document allowing or denying connection
    """
    # Get the API key from headers
    headers = event.get("headers", {})
    provided_key = headers.get("X-API-Key") or headers.get("x-api-key")
    
    # Get method ARN for policy
    method_arn = event["methodArn"]
    
    # Determine if this connection is authorized for sending new_text
    # Web clients won't send API key header, so they get basic access
    # Speech-to-text clients must provide valid API key
    is_authorized_sender = False
    
    if provided_key:
        # If API key is provided, validate it
        if API_KEY and secrets.compare_digest(provided_key, API_KEY):
            is_authorized_sender = True
            logger.info("Connection authorized with valid API key")
        else:
            # Invalid API key provided - deny connection
            logger.warning("Connection denied: invalid API key")
            return generate_policy("Deny", method_arn, {})
    else:
        # No API key provided - allow connection as web client (read-only)
        logger.info("Connection allowed as web client (no API key)")
    
    # Allow connection and pass authorization status in context
    return generate_policy("Allow", method_arn, {
        "isAuthorizedSender": is_authorized_sender
    })


def generate_policy(effect, resource, context_data):
    """
    Generate an IAM policy document.
    
    Args:
        effect: "Allow" or "Deny"
        resource: Method ARN
        context_data: Additional context to pass to Lambda integration
        
    Returns:
        Policy document dictionary
    """
    auth_response = {
        "principalId": "user",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource
                }
            ]
        },
        "context": context_data
    }
    
    return auth_response
