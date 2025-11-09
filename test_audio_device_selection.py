#!/usr/bin/env python3
"""
Test script for audio device selection feature.
Tests command-line parsing and environment variable handling.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

# Import the module to test
import speech_to_text


class TestAudioDeviceSelection(unittest.TestCase):
    """Test cases for audio device selection functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clear any existing LT_AUDIO_DEVICE environment variable
        if 'LT_AUDIO_DEVICE' in os.environ:
            del os.environ['LT_AUDIO_DEVICE']
    
    def tearDown(self):
        """Clean up after tests."""
        # Clear any LT_AUDIO_DEVICE that was set during tests
        if 'LT_AUDIO_DEVICE' in os.environ:
            del os.environ['LT_AUDIO_DEVICE']
    
    def test_speech_to_text_with_device_index(self):
        """Test that SpeechToText accepts and stores device_index."""
        with patch('speech_to_text.sr.Microphone') as mock_microphone:
            app = speech_to_text.SpeechToText(device_index=2)
            
            # Verify Microphone was called with correct device_index
            mock_microphone.assert_called_once_with(device_index=2)
            
            # Verify device_index is stored
            self.assertEqual(app.device_index, 2)
    
    def test_speech_to_text_without_device_index(self):
        """Test that SpeechToText works without device_index (default)."""
        with patch('speech_to_text.sr.Microphone') as mock_microphone:
            app = speech_to_text.SpeechToText()
            
            # Verify Microphone was called with None
            mock_microphone.assert_called_once_with(device_index=None)
            
            # Verify device_index is None
            self.assertIsNone(app.device_index)
    
    @patch('sys.argv', ['speech_to_text.py', '-l'])
    @patch('speech_to_text.list_audio_devices')
    def test_list_devices_flag(self, mock_list_devices):
        """Test that -l flag calls list_audio_devices and exits."""
        speech_to_text.main()
        
        # Verify list_audio_devices was called
        mock_list_devices.assert_called_once()
    
    @patch('sys.argv', ['speech_to_text.py', '-d', '3'])
    @patch('speech_to_text.SpeechToText')
    def test_device_flag(self, mock_stt_class):
        """Test that -d flag passes device_index to SpeechToText."""
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify SpeechToText was called with device_index=3
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=3
        )
    
    @patch('sys.argv', ['speech_to_text.py'])
    @patch('speech_to_text.SpeechToText')
    def test_env_variable(self, mock_stt_class):
        """Test that LT_AUDIO_DEVICE environment variable is used."""
        # Set environment variable
        os.environ['LT_AUDIO_DEVICE'] = '5'
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify SpeechToText was called with device_index=5
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=5
        )
    
    @patch('sys.argv', ['speech_to_text.py', '-d', '2'])
    @patch('speech_to_text.SpeechToText')
    def test_cli_overrides_env(self, mock_stt_class):
        """Test that command-line argument overrides environment variable."""
        # Set environment variable
        os.environ['LT_AUDIO_DEVICE'] = '5'
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify SpeechToText was called with device_index=2 (from CLI)
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=2
        )
    
    @patch('sys.argv', ['speech_to_text.py'])
    @patch('speech_to_text.SpeechToText')
    @patch('sys.stdout', new_callable=StringIO)
    def test_invalid_env_variable(self, mock_stdout, mock_stt_class):
        """Test that invalid LT_AUDIO_DEVICE shows warning."""
        # Set invalid environment variable
        os.environ['LT_AUDIO_DEVICE'] = 'invalid'
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify warning was printed
        output = mock_stdout.getvalue()
        self.assertIn("Invalid LT_AUDIO_DEVICE", output)
        
        # Verify SpeechToText was called with None (default)
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=None
        )
    
    @patch('sys.argv', ['speech_to_text.py', '-d', '1', 'http://example.com:8080'])
    @patch('speech_to_text.SpeechToText')
    def test_device_and_server_url(self, mock_stt_class):
        """Test that both device and server URL can be specified."""
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify SpeechToText was called with correct parameters
        mock_stt_class.assert_called_once_with(
            server_url='http://example.com:8080',
            device_index=1
        )
    
    @patch('speech_to_text.sr.Microphone')
    def test_list_audio_devices_success(self, mock_microphone):
        """Test list_audio_devices with available devices."""
        # Mock list_microphone_names to return some devices
        mock_microphone.list_microphone_names.return_value = [
            'Device 0: Built-in Microphone',
            'Device 1: USB Microphone',
            'Device 2: Virtual Input'
        ]
        
        # Capture stdout
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            speech_to_text.list_audio_devices()
            output = mock_stdout.getvalue()
            
            # Verify output contains device list
            self.assertIn('Available Audio Input Devices', output)
            self.assertIn('0: Device 0: Built-in Microphone', output)
            self.assertIn('1: Device 1: USB Microphone', output)
            self.assertIn('2: Device 2: Virtual Input', output)
            self.assertIn('Total devices: 3', output)
    
    @patch('speech_to_text.sr.Microphone')
    def test_list_audio_devices_error(self, mock_microphone):
        """Test list_audio_devices when PyAudio is not available."""
        # Mock list_microphone_names to raise an exception
        mock_microphone.list_microphone_names.side_effect = Exception('Could not find PyAudio')
        
        # Capture stdout
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            speech_to_text.list_audio_devices()
            output = mock_stdout.getvalue()
            
            # Verify error message is shown
            self.assertIn('Error listing audio devices', output)
            self.assertIn('Could not find PyAudio', output)


if __name__ == '__main__':
    # Run tests
    unittest.main()
