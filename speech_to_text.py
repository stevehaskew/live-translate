#!/usr/bin/env python3
"""
Speech-to-Text Application
Captures audio from microphone and converts it to text in real-time.
"""

import speech_recognition as sr
import socketio
import time
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
import threading
import queue

# Load environment variables
load_dotenv()


class SpeechToText:
    """Handles speech recognition and broadcasts text to server."""
    
    def __init__(self, server_url='http://localhost:5000', api_key=None):
        """
        Initialize the speech recognition system.
        
        Args:
            server_url: URL of the Flask server for broadcasting text
            api_key: API key for authentication (defaults to API_KEY env variable)
        """
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.sio = socketio.Client()
        self.server_url = server_url
        self.api_key = api_key or os.environ.get('API_KEY')
        self.is_running = False
        
        # Adjust recognizer settings for better performance
        self.recognizer.energy_threshold = 4000
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        
        # Queue for passing audio data between threads
        self.audio_queue = queue.Queue()
        
        # Thread for processing speech recognition
        self.recognition_thread = None
        
        # Setup SocketIO event handlers
        self.setup_socketio()
        
    def setup_socketio(self):
        """Setup SocketIO connection handlers."""
        @self.sio.on('connect')
        def on_connect():
            print(f"✓ Connected to server at {self.server_url}")
            
        @self.sio.on('disconnect')
        def on_disconnect():
            print("✗ Disconnected from server")
            
        @self.sio.on('connect_error')
        def on_connect_error(data):
            print(f"✗ Connection error: {data}")
    
    def connect_to_server(self):
        """Connect to the Flask server via SocketIO."""
        try:
            print(f"Connecting to server at {self.server_url}...")
            self.sio.connect(self.server_url)
            return True
        except Exception as e:
            print(f"✗ Failed to connect to server: {e}")
            return False
    
    def calibrate_microphone(self):
        """Calibrate microphone for ambient noise."""
        print("\nCalibrating microphone for ambient noise...")
        print("Please remain quiet for 2 seconds...")
        
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
        
        print(f"✓ Calibration complete. Energy threshold: {self.recognizer.energy_threshold}")
    
    def process_recognition(self):
        """
        Worker thread that processes audio recognition from the queue.
        Runs continuously until is_running is False and queue is empty.
        """
        while self.is_running or not self.audio_queue.empty():
            try:
                # Get audio from queue with timeout to allow checking is_running
                audio = self.audio_queue.get(timeout=0.5)
                
                try:
                    # Recognize speech using Google Speech Recognition
                    text = self.recognizer.recognize_google(audio)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    print(f"[{timestamp}] Recognized: {text}")
                    
                    # Broadcast to server
                    if self.sio.connected:
                        payload = {'text': text, 'timestamp': timestamp}
                        if self.api_key:
                            payload['api_key'] = self.api_key
                        self.sio.emit('new_text', payload)
                    else:
                        print("⚠ Not connected to server. Attempting to reconnect...")
                        self.connect_to_server()
                        
                except sr.UnknownValueError:
                    # Speech was unintelligible
                    pass
                except sr.RequestError as e:
                    print(f"✗ Could not request results from speech recognition service: {e}")
                    time.sleep(1)
                except Exception as e:
                    print(f"✗ Recognition error: {e}")
                
                # Mark task as done
                self.audio_queue.task_done()
                
            except queue.Empty:
                # No audio in queue, continue loop
                continue
            except Exception as e:
                print(f"✗ Error in recognition thread: {e}")
                time.sleep(1)
    
    def listen_and_transcribe(self):
        """
        Main loop: Listen for audio and queue it for transcription.
        Recognition is done in a separate thread to avoid listening delays.
        """
        self.is_running = True
        
        # Start the recognition worker thread
        self.recognition_thread = threading.Thread(target=self.process_recognition, daemon=True)
        self.recognition_thread.start()
        
        print("\n" + "="*60)
        print("SPEECH-TO-TEXT LIVE TRANSLATION")
        print("="*60)
        print("\nListening... Speak into your microphone.")
        print("Press Ctrl+C to stop.\n")
        
        while self.is_running:
            try:
                with self.microphone as source:
                    # Listen for audio (non-blocking for recognition)
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                # Queue audio for recognition in separate thread
                # This allows us to immediately start listening again
                self.audio_queue.put(audio)
                    
            except sr.WaitTimeoutError:
                # No speech detected within timeout
                pass
            except KeyboardInterrupt:
                print("\n\nStopping speech recognition...")
                self.is_running = False
                break
            except Exception as e:
                print(f"✗ Error: {e}")
                time.sleep(1)
        
        # Wait for recognition thread to finish processing remaining audio
        print("Waiting for remaining audio to be processed...")
        self.audio_queue.join()
        if self.recognition_thread:
            self.recognition_thread.join(timeout=5)
    
    def run(self):
        """Run the speech-to-text application."""
        try:
            # Check API key configuration
            if not self.api_key:
                print("\n⚠ Warning: API_KEY not set in environment.")
                print("Communication with the server will not be secured.")
                print("Set API_KEY in .env file for production use.\n")
            
            # Connect to server
            if not self.connect_to_server():
                print("\n⚠ Warning: Could not connect to server.")
                print("Make sure the Flask server is running.")
                response = input("Continue anyway? (y/n): ")
                if response.lower() != 'y':
                    return
            
            # Calibrate microphone
            self.calibrate_microphone()
            
            # Start listening
            self.listen_and_transcribe()
            
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        finally:
            if self.sio.connected:
                self.sio.disconnect()
            print("✓ Speech recognition stopped.")


def main():
    """Main entry point."""
    # Parse command line arguments
    server_url = 'http://localhost:5000'
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    
    print("="*60)
    print("Live Translation - Speech-to-Text")
    print("="*60)
    print(f"\nServer URL: {server_url}")
    
    # Create and run the application
    app = SpeechToText(server_url=server_url)
    app.run()


if __name__ == '__main__':
    main()
