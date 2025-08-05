#!/bin/bash

# FastAPI Terminal Runner Script

echo "Starting FastAPI Terminal..."
echo "================================"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if pip is available
if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
    echo "Error: pip is not installed"
    exit 1
fi

# Install requirements if they don't exist
echo "Installing requirements..."
pip install -r requirements.txt

echo ""
echo "Starting the FastAPI Terminal application..."
echo "Open your browser and go to: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================"

# Run the application
python3 main.py
