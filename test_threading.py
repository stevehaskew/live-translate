#!/usr/bin/env python3
"""
Test script to verify the threaded audio processing works correctly.
This test simulates the audio processing without requiring a microphone.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import queue
import time
import threading
from speech_to_text import SpeechToText


class TestThreadedAudioProcessing(unittest.TestCase):
    """Test cases for threaded audio processing."""

    def setUp(self):
        """Set up test fixtures."""
        self.server_url = "http://localhost:5050"

    @patch("speech_to_text.sr.Microphone")
    @patch("speech_to_text.socketio.Client")
    def test_audio_queue_initialization(self, mock_socketio, mock_microphone):
        """Test that the audio queue is properly initialized."""
        app = SpeechToText(server_url=self.server_url)

        self.assertIsInstance(app.audio_queue, queue.Queue)
        self.assertTrue(app.audio_queue.empty())
        self.assertIsNone(app.recognition_thread)

    @patch("speech_to_text.sr.Microphone")
    @patch("speech_to_text.socketio.Client")
    def test_recognition_thread_processes_queue(self, mock_socketio, mock_microphone):
        """Test that the recognition thread processes audio from the queue."""
        app = SpeechToText(server_url=self.server_url)

        # Mock the recognizer to return a test string
        mock_audio = Mock()
        app.recognizer.recognize_google = Mock(return_value="test speech")
        app.sio.connected = True
        app.sio.emit = Mock()

        # Add audio to queue
        app.audio_queue.put(mock_audio)

        # Start recognition thread
        app.is_running = True
        app.recognition_thread = threading.Thread(
            target=app.process_recognition, daemon=True
        )
        app.recognition_thread.start()

        # Wait for processing
        app.audio_queue.join()
        app.is_running = False
        app.recognition_thread.join(timeout=2)

        # Verify recognition was called
        app.recognizer.recognize_google.assert_called_once_with(mock_audio)
        app.sio.emit.assert_called_once()

        # Verify the emit call had the correct structure
        call_args = app.sio.emit.call_args
        self.assertEqual(call_args[0][0], "new_text")
        self.assertIn("text", call_args[0][1])
        self.assertEqual(call_args[0][1]["text"], "test speech")

    @patch("speech_to_text.sr.Microphone")
    @patch("speech_to_text.socketio.Client")
    def test_multiple_audio_segments_processed(self, mock_socketio, mock_microphone):
        """Test that multiple audio segments are processed correctly."""
        app = SpeechToText(server_url=self.server_url)

        # Mock the recognizer to return different strings
        recognition_results = ["first speech", "second speech", "third speech"]
        mock_audios = [Mock(), Mock(), Mock()]

        app.recognizer.recognize_google = Mock(side_effect=recognition_results)
        app.sio.connected = True
        app.sio.emit = Mock()

        # Add multiple audio segments to queue
        for mock_audio in mock_audios:
            app.audio_queue.put(mock_audio)

        # Start recognition thread
        app.is_running = True
        app.recognition_thread = threading.Thread(
            target=app.process_recognition, daemon=True
        )
        app.recognition_thread.start()

        # Wait for all processing
        app.audio_queue.join()
        app.is_running = False
        app.recognition_thread.join(timeout=2)

        # Verify all recognitions were called
        self.assertEqual(app.recognizer.recognize_google.call_count, 3)
        self.assertEqual(app.sio.emit.call_count, 3)

        # Verify each emit call had the correct text
        emit_calls = app.sio.emit.call_args_list
        for i, call in enumerate(emit_calls):
            self.assertEqual(call[0][0], "new_text")
            self.assertEqual(call[0][1]["text"], recognition_results[i])

    @patch("speech_to_text.sr.Microphone")
    @patch("speech_to_text.socketio.Client")
    def test_queue_allows_concurrent_listening_and_recognition(
        self, mock_socketio, mock_microphone
    ):
        """Test that audio can be queued while recognition is processing."""
        app = SpeechToText(server_url=self.server_url)

        # Mock recognizer with a delay to simulate processing time
        def slow_recognition(audio):
            time.sleep(0.1)  # Simulate recognition taking time
            return f"recognized"

        app.recognizer.recognize_google = Mock(side_effect=slow_recognition)
        app.sio.connected = True
        app.sio.emit = Mock()

        # Start recognition thread
        app.is_running = True
        app.recognition_thread = threading.Thread(
            target=app.process_recognition, daemon=True
        )
        app.recognition_thread.start()

        # Quickly add multiple audio segments
        start_time = time.time()
        for i in range(3):
            mock_audio = Mock()
            app.audio_queue.put(mock_audio)
        queue_time = time.time() - start_time

        # Verify queuing was fast (should be nearly instantaneous)
        self.assertLess(queue_time, 0.05, "Queuing should be non-blocking")

        # Wait for all processing
        app.audio_queue.join()
        app.is_running = False
        app.recognition_thread.join(timeout=2)

        # Verify all items were processed
        self.assertEqual(app.recognizer.recognize_google.call_count, 3)


if __name__ == "__main__":
    print("Running threading tests...")
    unittest.main(verbosity=2)
