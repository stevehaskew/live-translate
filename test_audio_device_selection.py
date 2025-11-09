#!/usr/bin/env python3
"""
Test script for audio device selection feature.
Tests command-line parsing and environment variable handling.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call
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
    
    def test_get_input_devices_filters_correctly(self):
        """Test that get_input_devices only returns input devices."""
        mock_pyaudio = MagicMock()
        mock_audio_instance = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_audio_instance
        
        # Mock 4 devices: 2 inputs, 1 output, 1 both
        mock_audio_instance.get_device_count.return_value = 4
        mock_audio_instance.get_device_info_by_index.side_effect = [
            {'name': 'Built-in Mic', 'maxInputChannels': 2, 'maxOutputChannels': 0},  # Input only
            {'name': 'Speakers', 'maxInputChannels': 0, 'maxOutputChannels': 2},      # Output only
            {'name': 'USB Mic', 'maxInputChannels': 1, 'maxOutputChannels': 0},       # Input only
            {'name': 'Headset', 'maxInputChannels': 1, 'maxOutputChannels': 2},       # Both
        ]
        
        # Patch the import inside the function
        with patch.dict('sys.modules', {'pyaudio': mock_pyaudio}):
            devices = speech_to_text.get_input_devices()
        
        # Should return 3 devices (all with maxInputChannels > 0)
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0][1], 'Built-in Mic')
        self.assertEqual(devices[1][1], 'USB Mic')
        self.assertEqual(devices[2][1], 'Headset')
    
    def test_find_device_index_by_name(self):
        """Test finding device index by name."""
        mock_devices = [
            (0, 'Built-in Mic', {'maxInputChannels': 2}),
            (2, 'USB Microphone', {'maxInputChannels': 1}),
            (5, 'Headset', {'maxInputChannels': 1}),
        ]
        
        with patch('speech_to_text.get_input_devices', return_value=mock_devices):
            # Test finding existing device
            self.assertEqual(speech_to_text.find_device_index_by_name('USB Microphone'), 2)
            self.assertEqual(speech_to_text.find_device_index_by_name('Headset'), 5)
            
            # Test non-existent device
            self.assertIsNone(speech_to_text.find_device_index_by_name('NonExistent'))
    
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
    
    @patch('sys.argv', ['speech_to_text.py', '-d', 'USB Microphone'])
    @patch('speech_to_text.find_device_index_by_name')
    @patch('speech_to_text.SpeechToText')
    def test_device_by_name(self, mock_stt_class, mock_find_device):
        """Test selecting device by name."""
        # Mock finding the device
        mock_find_device.return_value = 3
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify find_device_index_by_name was called
        mock_find_device.assert_called_once_with('USB Microphone')
        
        # Verify SpeechToText was called with found device_index
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=3
        )
    
    @patch('sys.argv', ['speech_to_text.py', '-d', 'NonExistent'])
    @patch('speech_to_text.find_device_index_by_name')
    @patch('speech_to_text.SpeechToText')
    @patch('sys.stdout', new_callable=StringIO)
    def test_device_name_not_found(self, mock_stdout, mock_stt_class, mock_find_device):
        """Test warning when device name is not found."""
        # Mock device not found
        mock_find_device.return_value = None
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify warning was printed
        output = mock_stdout.getvalue()
        self.assertIn("Audio device 'NonExistent' not found", output)
        
        # Verify SpeechToText was called with None (default)
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=None
        )
    
    @patch('sys.argv', ['speech_to_text.py'])
    @patch('speech_to_text.find_device_index_by_name')
    @patch('speech_to_text.SpeechToText')
    def test_env_variable_with_name(self, mock_stt_class, mock_find_device):
        """Test that LT_AUDIO_DEVICE environment variable works with device name."""
        # Set environment variable with device name
        os.environ['LT_AUDIO_DEVICE'] = 'USB Microphone'
        
        # Mock finding the device
        mock_find_device.return_value = 2
        
        mock_stt_instance = MagicMock()
        mock_stt_class.return_value = mock_stt_instance
        
        speech_to_text.main()
        
        # Verify SpeechToText was called with device_index from name lookup
        mock_stt_class.assert_called_once_with(
            server_url='http://localhost:5050',
            device_index=2
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
    
    @patch('speech_to_text.get_input_devices')
    def test_list_audio_devices_success(self, mock_get_devices):
        """Test list_audio_devices with available input devices."""
        # Mock input devices (index, name, info)
        mock_get_devices.return_value = [
            (0, 'Built-in Microphone', {'maxInputChannels': 2}),
            (2, 'USB Microphone', {'maxInputChannels': 1}),
            (5, 'Virtual Input', {'maxInputChannels': 1}),
        ]
        
        # Capture stdout
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            speech_to_text.list_audio_devices()
            output = mock_stdout.getvalue()
            
            # Verify output contains device list
            self.assertIn('Available Audio Input Devices', output)
            self.assertIn('0: Built-in Microphone', output)
            self.assertIn('2: USB Microphone', output)
            self.assertIn('5: Virtual Input', output)
            self.assertIn('Total input devices: 3', output)
    
    @patch('speech_to_text.get_input_devices')
    def test_list_audio_devices_error(self, mock_get_devices):
        """Test list_audio_devices when PyAudio is not available."""
        # Mock exception
        mock_get_devices.side_effect = Exception('Could not find PyAudio; check installation')
        
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
