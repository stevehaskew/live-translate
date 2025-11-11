#!/usr/bin/env python3
"""
Unit tests for client mapping classes.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from client_map import TranslationClientMap, TranslationClientMapDynamoDB


class TestTranslationClientMap(unittest.TestCase):
    """Test cases for TranslationClientMap base class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client_map = TranslationClientMap()

    def test_add_client(self):
        """Test adding a client to the map."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        client = self.client_map.get_client("client1")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "es")
        self.assertEqual(client["ws"], ws_mock)

    def test_add_client_default_language(self):
        """Test adding a client with default language."""
        ws_mock = Mock()
        self.client_map.add_client("client2", ws=ws_mock)

        client = self.client_map.get_client("client2")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "en")

    def test_delete_client(self):
        """Test deleting a client from the map."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "fr", ws_mock)
        self.assertTrue(self.client_map.exists("client1"))

        self.client_map.delete_client("client1")
        self.assertFalse(self.client_map.exists("client1"))
        self.assertIsNone(self.client_map.get_client("client1"))

    def test_delete_nonexistent_client(self):
        """Test deleting a client that doesn't exist."""
        # Should not raise an exception
        self.client_map.delete_client("nonexistent")

    def test_get_client(self):
        """Test getting a client from the map."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "de", ws_mock)

        client = self.client_map.get_client("client1")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "de")
        self.assertEqual(client["ws"], ws_mock)

    def test_get_nonexistent_client(self):
        """Test getting a client that doesn't exist."""
        client = self.client_map.get_client("nonexistent")
        self.assertIsNone(client)

    def test_get_all_clients(self):
        """Test getting all clients."""
        ws1 = Mock()
        ws2 = Mock()
        self.client_map.add_client("client1", "es", ws1)
        self.client_map.add_client("client2", "fr", ws2)

        all_clients = self.client_map.get_all_clients()
        self.assertEqual(len(all_clients), 2)
        self.assertIn("client1", all_clients)
        self.assertIn("client2", all_clients)
        self.assertEqual(all_clients["client1"]["lang"], "es")
        self.assertEqual(all_clients["client2"]["lang"], "fr")

    def test_update_language(self):
        """Test updating a client's language preference."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        result = self.client_map.update_language("client1", "fr")
        self.assertTrue(result)

        client = self.client_map.get_client("client1")
        self.assertEqual(client["lang"], "fr")

    def test_update_language_nonexistent_client(self):
        """Test updating language for a nonexistent client."""
        result = self.client_map.update_language("nonexistent", "es")
        self.assertFalse(result)

    def test_count(self):
        """Test counting connected clients."""
        self.assertEqual(self.client_map.count(), 0)

        ws1 = Mock()
        ws2 = Mock()
        self.client_map.add_client("client1", "es", ws1)
        self.assertEqual(self.client_map.count(), 1)

        self.client_map.add_client("client2", "fr", ws2)
        self.assertEqual(self.client_map.count(), 2)

        self.client_map.delete_client("client1")
        self.assertEqual(self.client_map.count(), 1)

    def test_exists(self):
        """Test checking if a client exists."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        self.assertTrue(self.client_map.exists("client1"))
        self.assertFalse(self.client_map.exists("client2"))


class TestTranslationClientMapDynamoDB(unittest.TestCase):
    """Test cases for TranslationClientMapDynamoDB class."""

    @patch("client_map.boto3.resource")
    def setUp(self, mock_boto_resource):
        """Set up test fixtures with mocked DynamoDB."""
        self.mock_table = MagicMock()
        self.mock_dynamodb = MagicMock()
        self.mock_dynamodb.Table.return_value = self.mock_table
        mock_boto_resource.return_value = self.mock_dynamodb

        self.client_map = TranslationClientMapDynamoDB("test-table", "us-east-1")

    def test_initialization(self):
        """Test DynamoDB client map initialization."""
        self.assertIsNotNone(self.client_map.dynamodb)
        self.assertIsNotNone(self.client_map.table)
        self.assertEqual(self.client_map.table_name, "test-table")
        self.assertEqual(self.client_map.region_name, "us-east-1")

    def test_add_client(self):
        """Test adding a client to DynamoDB."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        # Verify DynamoDB put_item was called
        self.mock_table.put_item.assert_called_once_with(
            Item={"client_id": "client1", "lang": "es"}
        )

        # Verify local cache was updated
        client = self.client_map.get_client("client1")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "es")
        self.assertEqual(client["ws"], ws_mock)

    def test_delete_client(self):
        """Test deleting a client from DynamoDB."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        self.client_map.delete_client("client1")

        # Verify DynamoDB delete_item was called
        self.mock_table.delete_item.assert_called_once_with(
            Key={"client_id": "client1"}
        )

        # Verify local cache was cleared
        self.assertIsNone(self.client_map.get_client("client1"))

    def test_get_client_from_local_cache(self):
        """Test getting a client from local cache."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        client = self.client_map.get_client("client1")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "es")
        self.assertEqual(client["ws"], ws_mock)

        # DynamoDB get_item should not have been called
        self.mock_table.get_item.assert_not_called()

    def test_get_client_from_dynamodb(self):
        """Test getting a client from DynamoDB when not in local cache."""
        self.mock_table.get_item.return_value = {
            "Item": {"client_id": "client1", "lang": "es"}
        }

        client = self.client_map.get_client("client1")
        self.assertIsNotNone(client)
        self.assertEqual(client["lang"], "es")
        self.assertIsNone(client["ws"])  # WebSocket not stored in DynamoDB

        # Verify DynamoDB was queried
        self.mock_table.get_item.assert_called_once_with(Key={"client_id": "client1"})

    def test_update_language(self):
        """Test updating a client's language in DynamoDB."""
        ws_mock = Mock()
        self.client_map.add_client("client1", "es", ws_mock)

        result = self.client_map.update_language("client1", "fr")
        self.assertTrue(result)

        # Verify DynamoDB was updated
        self.mock_table.update_item.assert_called_once()
        call_args = self.mock_table.update_item.call_args
        self.assertEqual(call_args[1]["Key"], {"client_id": "client1"})
        self.assertEqual(call_args[1]["ExpressionAttributeValues"], {":lang": "fr"})

        # Verify local cache was updated
        client = self.client_map.get_client("client1")
        self.assertEqual(client["lang"], "fr")

    def test_count(self):
        """Test counting clients (local cache only)."""
        self.assertEqual(self.client_map.count(), 0)

        ws1 = Mock()
        ws2 = Mock()
        self.client_map.add_client("client1", "es", ws1)
        self.assertEqual(self.client_map.count(), 1)

        self.client_map.add_client("client2", "fr", ws2)
        self.assertEqual(self.client_map.count(), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
