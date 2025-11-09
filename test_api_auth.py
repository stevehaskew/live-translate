#!/usr/bin/env python3
"""
Test script to verify API key authentication works correctly.
Tests both authorized and unauthorized access scenarios.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os


class TestAPIKeyAuthentication(unittest.TestCase):
    """Test cases for API key authentication."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Import server module with mocked dependencies
        self.original_api_key = os.environ.get('API_KEY')
        
    def tearDown(self):
        """Clean up after tests."""
        # Restore original environment
        if self.original_api_key:
            os.environ['API_KEY'] = self.original_api_key
        elif 'API_KEY' in os.environ:
            del os.environ['API_KEY']
    
    @patch('server.socketio')
    @patch('server.emit')
    @patch('server.request')
    def test_new_text_with_valid_api_key(self, mock_request, mock_emit, mock_socketio):
        """Test that new_text succeeds with valid API key."""
        # Set up API key in environment
        os.environ['API_KEY'] = 'test-api-key-123'
        
        # Re-import to pick up new env variable
        import importlib
        import server
        importlib.reload(server)
        
        # Mock request sid
        mock_request.sid = 'test-client-123'
        
        # Test data with valid API key
        data = {
            'text': 'Hello world',
            'timestamp': '12:00:00',
            'api_key': 'test-api-key-123'
        }
        
        # Mock connected clients
        server.connected_clients = {
            'client1': {'language': 'en'}
        }
        
        # Call the handler
        server.handle_new_text(data)
        
        # Verify socketio.emit was called (translation was broadcasted)
        server.socketio.emit.assert_called()
    
    @patch('server.emit')
    @patch('server.request')
    @patch('server.logger')
    def test_new_text_with_invalid_api_key(self, mock_logger, mock_request, mock_emit):
        """Test that new_text is rejected with invalid API key."""
        # Set up API key in environment
        os.environ['API_KEY'] = 'test-api-key-123'
        
        # Re-import to pick up new env variable
        import importlib
        import server
        importlib.reload(server)
        
        # Mock request sid
        mock_request.sid = 'test-client-456'
        
        # Test data with invalid API key
        data = {
            'text': 'Hello world',
            'timestamp': '12:00:00',
            'api_key': 'wrong-api-key'
        }
        
        # Call the handler
        server.handle_new_text(data)
        
        # Verify error was emitted
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        self.assertEqual(call_args[0][0], 'error')
        self.assertIn('Unauthorized', call_args[0][1]['message'])
        
        # Verify warning was logged
        mock_logger.warning.assert_called()
    
    @patch('server.emit')
    @patch('server.request')
    def test_new_text_with_missing_api_key(self, mock_request, mock_emit):
        """Test that new_text is rejected when API key is missing from request."""
        # Set up API key in environment
        os.environ['API_KEY'] = 'test-api-key-123'
        
        # Re-import to pick up new env variable
        import importlib
        import server
        importlib.reload(server)
        
        # Mock request sid
        mock_request.sid = 'test-client-789'
        
        # Test data without API key
        data = {
            'text': 'Hello world',
            'timestamp': '12:00:00'
        }
        
        # Call the handler
        server.handle_new_text(data)
        
        # Verify error was emitted
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        self.assertEqual(call_args[0][0], 'error')
        self.assertIn('Unauthorized', call_args[0][1]['message'])
    
    @patch('server.socketio')
    @patch('server.request')
    def test_new_text_without_api_key_configured(self, mock_request, mock_socketio):
        """Test that new_text works without API key when not configured."""
        # Ensure no API key is set
        if 'API_KEY' in os.environ:
            del os.environ['API_KEY']
        
        # Re-import to pick up new env variable
        import importlib
        import server
        importlib.reload(server)
        
        # Mock request sid
        mock_request.sid = 'test-client-000'
        
        # Test data without API key
        data = {
            'text': 'Hello world',
            'timestamp': '12:00:00'
        }
        
        # Mock connected clients
        server.connected_clients = {
            'client1': {'language': 'en'}
        }
        
        # Call the handler - should not raise error
        server.handle_new_text(data)
        
        # Verify socketio.emit was called (translation was broadcasted)
        server.socketio.emit.assert_called()


class TestSpeechToTextAPIKey(unittest.TestCase):
    """Test cases for SpeechToText API key handling."""
    
    @patch('speech_to_text.sr.Microphone')
    @patch('speech_to_text.socketio.Client')
    def test_api_key_loaded_from_environment(self, mock_socketio, mock_microphone):
        """Test that API key is loaded from environment variable."""
        # Set API key in environment
        os.environ['API_KEY'] = 'env-api-key-123'
        
        # Re-import to pick up new env variable
        import importlib
        import speech_to_text
        importlib.reload(speech_to_text)
        
        # Create instance
        app = speech_to_text.SpeechToText()
        
        # Verify API key was loaded
        self.assertEqual(app.api_key, 'env-api-key-123')
    
    @patch('speech_to_text.sr.Microphone')
    @patch('speech_to_text.socketio.Client')
    def test_api_key_from_parameter_overrides_environment(self, mock_socketio, mock_microphone):
        """Test that API key parameter overrides environment variable."""
        # Set API key in environment
        os.environ['API_KEY'] = 'env-api-key-123'
        
        # Re-import to pick up new env variable
        import importlib
        import speech_to_text
        importlib.reload(speech_to_text)
        
        # Create instance with explicit API key
        app = speech_to_text.SpeechToText(api_key='param-api-key-456')
        
        # Verify parameter was used
        self.assertEqual(app.api_key, 'param-api-key-456')
    
    @patch('speech_to_text.sr.Microphone')
    @patch('speech_to_text.socketio.Client')
    def test_emit_includes_api_key_when_configured(self, mock_socketio, mock_microphone):
        """Test that emitted messages include API key when configured."""
        import importlib
        import speech_to_text
        importlib.reload(speech_to_text)
        
        # Create instance with API key
        app = speech_to_text.SpeechToText(api_key='test-key-789')
        
        # Mock the socket connection
        app.sio.connected = True
        app.sio.emit = Mock()
        
        # Mock recognizer
        mock_audio = Mock()
        app.recognizer.recognize_google = Mock(return_value="test text")
        
        # Add audio to queue and process
        app.audio_queue.put(mock_audio)
        app.is_running = True
        
        import threading
        app.recognition_thread = threading.Thread(target=app.process_recognition, daemon=True)
        app.recognition_thread.start()
        
        # Wait for processing
        app.audio_queue.join()
        app.is_running = False
        app.recognition_thread.join(timeout=2)
        
        # Verify emit was called with API key
        app.sio.emit.assert_called_once()
        call_args = app.sio.emit.call_args
        self.assertEqual(call_args[0][0], 'new_text')
        self.assertIn('api_key', call_args[0][1])
        self.assertEqual(call_args[0][1]['api_key'], 'test-key-789')


if __name__ == '__main__':
    print("Running API key authentication tests...")
    unittest.main(verbosity=2)
