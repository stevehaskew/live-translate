#!/bin/bash
#
# Quick Start Script for Live Translation
# This script helps you get started quickly by checking dependencies
# and providing helpful instructions.
#

set -e

echo "============================================================"
echo "Live Translation - Quick Start"
echo "============================================================"
echo ""

# Check Python version
echo "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ $PYTHON_VERSION found"
else
    echo "✗ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if running on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "Detected macOS system"
    echo "Checking for PortAudio (required for PyAudio)..."
    if command -v brew &> /dev/null; then
        if brew list portaudio &> /dev/null; then
            echo "✓ PortAudio is installed"
        else
            echo "⚠ PortAudio is not installed"
            echo ""
            read -p "Would you like to install PortAudio via Homebrew? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Installing PortAudio..."
                brew install portaudio
                echo "✓ PortAudio installed"
            else
                echo "Note: You'll need to install PortAudio manually for speech recognition to work."
            fi
        fi
    else
        echo "⚠ Homebrew is not installed. Install from https://brew.sh/"
        echo "Then run: brew install portaudio"
    fi
fi

echo ""
echo "Checking for virtual environment..."
if [ -d "venv" ]; then
    echo "✓ Virtual environment exists"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

echo ""
echo "Activating virtual environment..."
source venv/bin/activate

echo ""
echo "Checking dependencies..."
if pip show flask &> /dev/null; then
    echo "✓ Dependencies appear to be installed"
else
    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
fi

echo ""
echo "============================================================"
echo "Setup Complete!"
echo "============================================================"
echo ""
echo "To start the application:"
echo ""
echo "1. Start the web server (in this terminal):"
echo "   python server.py"
echo ""
echo "2. Open a web browser:"
echo "   http://localhost:5050"
echo ""
echo "3. Start speech recognition (in a new terminal):"
echo "   source venv/bin/activate"
echo "   python speech_to_text.py"
echo ""
echo "   OR test without a microphone:"
echo "   source venv/bin/activate"
echo "   python test_client.py"
echo ""
echo "Optional: Configure AWS Translate for multi-language support"
echo "   cp .env.example .env"
echo "   # Edit .env with your AWS credentials"
echo ""
echo "============================================================"
echo ""
read -p "Would you like to start the web server now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting web server..."
    python server.py
fi
