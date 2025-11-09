#!/usr/bin/env python3
"""
Test script for the live translation system.
Simulates speech input by sending test messages to the server.
"""

import socketio
import time
import sys

# Sample test phrases
TEST_PHRASES = [
    "Hello, welcome to the live translation demo.",
    "This is a test of the speech to text system.",
    "The weather is beautiful today.",
    "I love learning new languages.",
    "Technology is amazing.",
    "Have a wonderful day!",
]


def test_connection(server_url='http://localhost:5000'):
    """
    Test the connection to the server and send sample messages.
    
    Args:
        server_url: URL of the Flask server
    """
    print("="*60)
    print("Live Translation - Test Script")
    print("="*60)
    print(f"\nServer URL: {server_url}")
    print(f"Number of test phrases: {len(TEST_PHRASES)}")
    print("\nThis script will send test messages to simulate speech input.")
    print("-"*60)
    
    # Create SocketIO client
    sio = socketio.Client()
    
    @sio.on('connect')
    def on_connect():
        print("✓ Connected to server")
    
    @sio.on('disconnect')
    def on_disconnect():
        print("✗ Disconnected from server")
    
    @sio.on('connect_error')
    def on_connect_error(data):
        print(f"✗ Connection error: {data}")
    
    try:
        # Connect to server
        print("\nConnecting to server...")
        sio.connect(server_url)
        time.sleep(1)
        
        # Send test phrases
        print("\nSending test phrases:\n")
        for i, phrase in enumerate(TEST_PHRASES, 1):
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Phrase {i}/{len(TEST_PHRASES)}: {phrase}")
            
            sio.emit('new_text', {
                'text': phrase,
                'timestamp': timestamp
            })
            
            # Wait between messages
            time.sleep(3)
        
        print("\n" + "="*60)
        print("✓ All test phrases sent successfully!")
        print("="*60)
        print("\nCheck the web interface to see the translations.")
        print("The script will disconnect in 5 seconds...")
        
        time.sleep(5)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
    finally:
        if sio.connected:
            sio.disconnect()
        print("\n✓ Test completed.")


def main():
    """Main entry point."""
    # Parse command line arguments
    server_url = 'http://localhost:5000'
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    
    test_connection(server_url)


if __name__ == '__main__':
    main()
