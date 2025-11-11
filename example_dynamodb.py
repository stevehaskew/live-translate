#!/usr/bin/env python3
"""
Example: Using TranslationClientMapDynamoDB for cloud deployments.

This example shows how to use the DynamoDB-backed client map
instead of the in-memory version for distributed deployments.
"""

from client_map import TranslationClientMapDynamoDB
from message_handler import MessageHandler, TranslationService
import os


# Example 1: Initialize with DynamoDB
# Requires AWS credentials and a DynamoDB table
def example_dynamodb_setup():
    """Example of setting up the server with DynamoDB client map."""

    # Table should have:
    # - Primary key: client_id (String)
    # - Attributes: language (String)
    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "live-translate-clients")
    region_name = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    # Initialize DynamoDB client map
    client_map = TranslationClientMapDynamoDB(
        table_name=table_name, region_name=region_name
    )

    # Initialize translation service and message handler
    translation_service = TranslationService(region_name=region_name)
    message_handler = MessageHandler(
        translation_service, api_key=os.environ.get("API_KEY")
    )

    return client_map, message_handler


# Example 2: Using the client map in your Flask app
def example_flask_with_dynamodb():
    """Example of using DynamoDB client map in Flask."""

    from flask import Flask
    from flask_sock import Sock

    app = Flask(__name__)
    sock = Sock(app)

    # Use DynamoDB client map instead of in-memory
    client_map, message_handler = example_dynamodb_setup()

    @sock.route("/ws")
    def websocket_handler(ws):
        client_id = id(ws)
        client_map.add_client(client_id, language="en", ws=ws)

        # Rest of WebSocket handling logic...
        # See server.py for full implementation

        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
                # Handle messages using message_handler
        finally:
            client_map.delete_client(client_id)

    return app


# Example 3: Creating the DynamoDB table using boto3
def example_create_table():
    """Example of creating the DynamoDB table for client mapping."""

    import boto3

    dynamodb = boto3.client("dynamodb", region_name="us-east-1")

    try:
        response = dynamodb.create_table(
            TableName="live-translate-clients",
            KeySchema=[
                {"AttributeName": "client_id", "KeyType": "HASH"}  # Partition key
            ],
            AttributeDefinitions=[{"AttributeName": "client_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",  # On-demand billing
            Tags=[
                {"Key": "Application", "Value": "LiveTranslate"},
                {"Key": "Environment", "Value": "Production"},
            ],
        )
        print(f"Table created: {response['TableDescription']['TableName']}")
        print(f"Status: {response['TableDescription']['TableStatus']}")
    except Exception as e:
        print(f"Error creating table: {e}")


# Example 4: Switching between in-memory and DynamoDB
def example_configurable_client_map():
    """Example of making client map configurable via environment variable."""

    from client_map import TranslationClientMap, TranslationClientMapDynamoDB

    use_dynamodb = os.environ.get("USE_DYNAMODB", "false").lower() == "true"

    if use_dynamodb:
        table_name = os.environ.get("DYNAMODB_TABLE_NAME", "live-translate-clients")
        region_name = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        client_map = TranslationClientMapDynamoDB(table_name, region_name)
        print("Using DynamoDB client map")
    else:
        client_map = TranslationClientMap()
        print("Using in-memory client map")

    return client_map


if __name__ == "__main__":
    print("Live Translate - DynamoDB Client Map Examples")
    print("=" * 60)
    print("\nThis file contains examples of using DynamoDB for client mapping.")
    print("See the function docstrings for implementation details.\n")
    print("To use DynamoDB client map:")
    print("1. Create a DynamoDB table (see example_create_table)")
    print("2. Set environment variable USE_DYNAMODB=true")
    print("3. Set DYNAMODB_TABLE_NAME to your table name")
    print("4. Ensure AWS credentials are configured")
    print("\nFor local development, the in-memory client map is used by default.")
