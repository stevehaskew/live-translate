#!/usr/bin/env python3
"""
Client mapping classes for managing connected translation clients.
Supports both in-memory and DynamoDB-backed storage.
"""

import logging
from typing import Dict, Optional, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class TranslationClientMap:
    """
    Base class for managing client-to-language mappings.
    Uses an in-memory dictionary for storage.
    """

    def __init__(self):
        """Initialize the client map with an empty dictionary."""
        self._clients: Dict[Any, Dict[str, Any]] = {}

    def add_client(self, client_id: Any, language: str = "en", ws: Any = None, is_authorized_sender: bool = False) -> None:
        """
        Add or update a client in the map.

        Args:
            client_id: Unique identifier for the client
            language: Preferred language code (default: "en")
            ws: WebSocket connection object
            is_authorized_sender: Whether client is authorized to send new_text (default: False)
        """
        self._clients[client_id] = {
            "lang": language, 
            "ws": ws,
            "is_authorized_sender": is_authorized_sender
        }
        logger.info(f"Client added: {client_id} (language: {language}, authorized_sender: {is_authorized_sender})")

    def delete_client(self, client_id: Any) -> None:
        """
        Remove a client from the map.

        Args:
            client_id: Unique identifier for the client
        """
        if client_id in self._clients:
            del self._clients[client_id]
            logger.info(f"Client deleted: {client_id}")

    def get_client(self, client_id: Any) -> Optional[Dict[str, Any]]:
        """
        Get client information.

        Args:
            client_id: Unique identifier for the client

        Returns:
            Dictionary with client info (language, ws) or None if not found
        """
        return self._clients.get(client_id)

    def get_all_clients(self) -> Dict[Any, Dict[str, Any]]:
        """
        Get all clients.

        Returns:
            Dictionary of all clients with their information
        """
        return self._clients.copy()

    def update_language(self, client_id: Any, language: str) -> bool:
        """
        Update the language preference for a client.

        Args:
            client_id: Unique identifier for the client
            language: New language code

        Returns:
            True if update was successful, False if client not found
        """
        if client_id in self._clients:
            self._clients[client_id]["lang"] = language
            logger.info(f"Client {client_id} language updated to: {language}")
            return True
        return False

    def count(self) -> int:
        """
        Get the number of connected clients.

        Returns:
            Number of clients
        """
        return len(self._clients)

    def exists(self, client_id: Any) -> bool:
        """
        Check if a client exists in the map.

        Args:
            client_id: Unique identifier for the client

        Returns:
            True if client exists, False otherwise
        """
        return client_id in self._clients


class TranslationClientMapDynamoDB(TranslationClientMap):
    """
    DynamoDB-backed client map for distributed deployments.
    Stores client mappings in a DynamoDB table.
    """

    def __init__(self, table_name: str, region_name: str = "us-east-1"):
        """
        Initialize the DynamoDB client map.

        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region for DynamoDB (default: "us-east-1")
        """
        super().__init__()  # Keep local cache for WebSocket objects
        self.table_name = table_name
        self.region_name = region_name

        try:
            self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
            self.table = self.dynamodb.Table(table_name)
            logger.info(f"DynamoDB client map initialized (table: {table_name})")
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB client map: {e}")
            raise

    def add_client(self, client_id: Any, language: str = "en", ws: Any = None, is_authorized_sender: bool = False) -> None:
        """
        Add or update a client in DynamoDB and local cache.

        Args:
            client_id: Unique identifier for the client
            language: Preferred language code (default: "en")
            ws: WebSocket connection object (stored only in local cache)
            is_authorized_sender: Whether client is authorized to send new_text (default: False)
        """
        # Store in DynamoDB
        try:
            self.table.put_item(
                Item={
                    "client_id": str(client_id),
                    "lang": language,
                    "is_authorized_sender": is_authorized_sender,
                }
            )
        except ClientError as e:
            logger.error(f"DynamoDB error adding client {client_id}: {e}")
            raise

        # Also keep in local cache for WebSocket reference
        self._clients[client_id] = {
            "lang": language, 
            "ws": ws,
            "is_authorized_sender": is_authorized_sender
        }
        logger.info(f"Client added to DynamoDB: {client_id} (language: {language}, authorized_sender: {is_authorized_sender})")

    def delete_client(self, client_id: Any) -> None:
        """
        Remove a client from DynamoDB and local cache.

        Args:
            client_id: Unique identifier for the client
        """
        # Remove from DynamoDB
        try:
            self.table.delete_item(Key={"client_id": str(client_id)})
        except ClientError as e:
            logger.error(f"DynamoDB error deleting client {client_id}: {e}")

        # Also remove from local cache
        if client_id in self._clients:
            del self._clients[client_id]
        logger.info(f"Client deleted from DynamoDB: {client_id}")

    def get_client(self, client_id: Any) -> Optional[Dict[str, Any]]:
        """
        Get client information from local cache first, then DynamoDB.

        Args:
            client_id: Unique identifier for the client

        Returns:
            Dictionary with client info or None if not found
        """
        # Check local cache first (has WebSocket reference)
        if client_id in self._clients:
            return self._clients[client_id]

        # Fallback to DynamoDB
        try:
            response = self.table.get_item(Key={"client_id": str(client_id)})
            if "Item" in response:
                return {
                    "lang": response["Item"].get("lang", "en"),
                    "ws": None,
                    "is_authorized_sender": response["Item"].get("is_authorized_sender", False),
                }
        except ClientError as e:
            logger.error(f"DynamoDB error getting client {client_id}: {e}")

        return None

    def update_language(self, client_id: Any, language: str) -> bool:
        """
        Update the language preference in DynamoDB and local cache.

        Args:
            client_id: Unique identifier for the client
            language: New language code

        Returns:
            True if update was successful, False otherwise
        """
        # Update in DynamoDB
        try:
            self.table.update_item(
                Key={"client_id": str(client_id)},
                UpdateExpression="SET lang = :lang",
                ExpressionAttributeValues={":lang": language},
            )
        except ClientError as e:
            logger.error(f"DynamoDB error updating client {client_id}: {e}")
            return False

        # Also update local cache if present
        if client_id in self._clients:
            self._clients[client_id]["lang"] = language

        logger.info(f"Client {client_id} language updated in DynamoDB to: {language}")
        return True

    def count(self) -> int:
        """
        Get the number of clients from local cache.
        Note: For distributed systems, this only counts locally connected clients.

        Returns:
            Number of locally connected clients
        """
        return len(self._clients)
