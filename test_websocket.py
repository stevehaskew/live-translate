#!/usr/bin/env python3
"""
Test WebSocket client for Live Translation
Simulates the speech-to-text client sending messages to the server.
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import websocket

# Load environment variables
load_dotenv()

def test_websocket():
    """Test WebSocket connection and message exchange."""
    
    # Get API key from environment
    api_key = os.environ.get("API_KEY", "")
    
    # Create WebSocket connection
    ws_url = "ws://localhost:5050/ws"
    print(f"Connecting to {ws_url}...")
    
    ws = websocket.create_connection(ws_url)
    print("✓ Connected to server")
    
    # Receive connection status
    try:
        response = ws.recv()
        msg = json.loads(response)
        print(f"Received: {msg}")
        
        # Send language preference
        set_lang_msg = {
            "type": "set_language",
            "data": {"language": "es"}
        }
        ws.send(json.dumps(set_lang_msg))
        print(f"Sent: {set_lang_msg}")
        
        # Receive language set confirmation
        response = ws.recv()
        msg = json.loads(response)
        print(f"Received: {msg}")
        
        # Send test text (simulating speech-to-text)
        new_text_msg = {
            "type": "new_text",
            "data": {
                "text": "Hello, this is a test message",
                "timestamp": "12:34:56",
                "api_key": api_key
            }
        }
        ws.send(json.dumps(new_text_msg))
        # Log without sensitive data
        print(f"Sent: {{'type': 'new_text', 'data': {{'text': 'Hello, this is a test message', 'timestamp': '12:34:56', 'api_key': '***'}}}}")
        
        # Receive translated text
        response = ws.recv()
        msg = json.loads(response)
        print(f"Received translation: {msg}")
        
        print("\n✓ WebSocket test completed successfully!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        ws.close()
        print("Connection closed")

if __name__ == "__main__":
    try:
        test_websocket()
    except Exception as e:
        print(f"✗ Test failed: {e}")
