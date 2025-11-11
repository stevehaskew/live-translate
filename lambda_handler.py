#!/usr/bin/env python3
"""
AWS Lambda handler for API Gateway WebSocket connections.
Handles WebSocket lifecycle and message routing for Live Translation.
"""

import json
import logging
import os
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Import our existing modules
from client_map import TranslationClientMapDynamoDB
from message_handler import MessageHandler, TranslationService

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "live-translate-connections")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
API_KEY = os.environ.get("API_KEY")

# Initialize services
translation_service = TranslationService(region_name=AWS_REGION)
message_handler = MessageHandler(translation_service, API_KEY)

# Initialize client map with DynamoDB
try:
    client_map = TranslationClientMapDynamoDB(
        table_name=DYNAMODB_TABLE_NAME, region_name=AWS_REGION
    )
except Exception as e:
    logger.error(f"Failed to initialize DynamoDB client map: {e}")
    # Fall back to in-memory map for local testing
    from client_map import TranslationClientMap
    client_map = TranslationClientMap()

# API Gateway Management API client (initialized per request)
apigw_management_client = None


def get_apigw_management_client(event: Dict[str, Any]):
    """
    Get or create API Gateway Management API client for sending messages to clients.
    
    Args:
        event: Lambda event containing request context
        
    Returns:
        boto3 API Gateway Management API client
    """
    global apigw_management_client
    
    if apigw_management_client is None:
        # Extract endpoint from event
        domain_name = event["requestContext"]["domainName"]
        stage = event["requestContext"]["stage"]
        endpoint_url = f"https://{domain_name}/{stage}"
        
        apigw_management_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=endpoint_url,
            region_name=AWS_REGION,
        )
    
    return apigw_management_client


def send_message_to_connection(
    connection_id: str, message: Dict[str, Any], apigw_client
) -> bool:
    """
    Send a message to a specific WebSocket connection.
    
    Args:
        connection_id: WebSocket connection ID
        message: Message dictionary to send
        apigw_client: API Gateway Management API client
        
    Returns:
        True if successful, False otherwise
    """
    try:
        apigw_client.post_to_connection(
            ConnectionId=connection_id, Data=json.dumps(message).encode("utf-8")
        )
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "GoneException":
            logger.info(f"Connection {connection_id} is gone, removing from map")
            client_map.delete_client(connection_id)
        else:
            logger.error(f"Error sending to connection {connection_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to connection {connection_id}: {e}")
        return False


def broadcast_message(
    message: Dict[str, Any], apigw_client, exclude_connection: Optional[str] = None
) -> None:
    """
    Broadcast a message to all connected clients.
    
    Args:
        message: Message dictionary to broadcast
        apigw_client: API Gateway Management API client
        exclude_connection: Optional connection ID to exclude from broadcast
    """
    failed_connections = []
    
    for client_id, client_info in client_map.get_all_clients().items():
        if client_id == exclude_connection:
            continue
            
        if not send_message_to_connection(client_id, message, apigw_client):
            failed_connections.append(client_id)
    
    # Clean up failed connections
    for client_id in failed_connections:
        client_map.delete_client(client_id)


def handle_connect(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket $connect route.
    
    Args:
        event: Lambda event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    connection_id = event["requestContext"]["connectionId"]
    
    try:
        # Add client with default language
        client_map.add_client(connection_id, language="en", ws=None)
        logger.info(f"Client connected: {connection_id}")
        
        return {"statusCode": 200, "body": "Connected"}
    except Exception as e:
        logger.error(f"Error handling connect: {e}")
        return {"statusCode": 500, "body": "Failed to connect"}


def handle_disconnect(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket $disconnect route.
    
    Args:
        event: Lambda event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    connection_id = event["requestContext"]["connectionId"]
    
    try:
        client_map.delete_client(connection_id)
        logger.info(f"Client disconnected: {connection_id}")
        
        return {"statusCode": 200, "body": "Disconnected"}
    except Exception as e:
        logger.error(f"Error handling disconnect: {e}")
        return {"statusCode": 500, "body": "Failed to disconnect"}


def handle_message(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket messages ($default route).
    
    Args:
        event: Lambda event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    connection_id = event["requestContext"]["connectionId"]
    apigw_client = get_apigw_management_client(event)
    
    try:
        # Parse message body
        body = event.get("body", "{}")
        message = json.loads(body)
        msg_type = message.get("type")
        msg_data = message.get("data", {})
        
        logger.info(f"Received message from {connection_id}: type={msg_type}")
        
        if msg_type == message_handler.MESSAGE_TYPE_SET_LANGUAGE:
            # Handle language preference
            language = msg_data.get("language", "en")
            response = message_handler.handle_set_language(
                connection_id, language, client_map
            )
            send_message_to_connection(connection_id, response, apigw_client)
            
        elif msg_type == message_handler.MESSAGE_TYPE_NEW_TEXT:
            # Handle new text from speech-to-text application
            original_text = msg_data.get("text", "")
            timestamp = msg_data.get("timestamp", "")
            provided_key = msg_data.get("api_key", "")
            
            result = message_handler.handle_new_text(
                original_text, timestamp, provided_key, client_map
            )
            
            if result["status"] == "error":
                logger.warning(f"Unauthorized new_text attempt from {connection_id}")
                error_msg = message_handler.create_error_message(result["error"])
                send_message_to_connection(connection_id, error_msg, apigw_client)
                return {"statusCode": 401, "body": "Unauthorized"}
            
            # Broadcast translations to all clients
            for translation_info in result["translations"]:
                target_client_id = translation_info["client_id"]
                translation = translation_info["translation"]
                
                message_to_send = {
                    "type": message_handler.MESSAGE_TYPE_TRANSLATED_TEXT,
                    "data": translation,
                }
                send_message_to_connection(
                    target_client_id, message_to_send, apigw_client
                )
                
        elif msg_type == message_handler.MESSAGE_TYPE_REQUEST_TRANSLATION:
            # Handle on-demand translation request
            text = msg_data.get("text", "")
            target_language = msg_data.get("target_language", "en")
            
            response = message_handler.handle_request_translation(text, target_language)
            send_message_to_connection(connection_id, response, apigw_client)
            
        else:
            logger.warning(f"Unknown message type from {connection_id}: {msg_type}")
            error_msg = message_handler.create_error_message(
                f"Unknown message type: {msg_type}"
            )
            send_message_to_connection(connection_id, error_msg, apigw_client)
        
        # Send connection status on first message
        if msg_type == message_handler.MESSAGE_TYPE_SET_LANGUAGE:
            status_msg = message_handler.create_connection_status_message()
            send_message_to_connection(connection_id, status_msg, apigw_client)
        
        return {"statusCode": 200, "body": "Message processed"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from connection {connection_id}: {e}")
        return {"statusCode": 400, "body": "Invalid JSON"}
    except Exception as e:
        logger.error(f"Error processing message from {connection_id}: {e}")
        return {"statusCode": 500, "body": "Internal server error"}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for API Gateway WebSocket events.
    Routes to appropriate handler based on route key.
    
    Args:
        event: Lambda event from API Gateway
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    route_key = event["requestContext"]["routeKey"]
    
    logger.info(f"Processing route: {route_key}")
    
    if route_key == "$connect":
        return handle_connect(event, context)
    elif route_key == "$disconnect":
        return handle_disconnect(event, context)
    elif route_key == "$default":
        return handle_message(event, context)
    else:
        logger.warning(f"Unknown route: {route_key}")
        return {"statusCode": 400, "body": f"Unknown route: {route_key}"}
