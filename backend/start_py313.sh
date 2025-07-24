#!/bin/bash
# Start Unicorn Commander Backend with Python 3.13

echo "Starting Unicorn Commander Backend with Python 3.13..."

# Check if Python 3.13 is available
if ! command -v python3.13 &> /dev/null; then
    echo "Error: Python 3.13 not found. Please install Python 3.13"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv313" ]; then
    echo "Creating Python 3.13 virtual environment..."
    python3.13 -m venv venv313
fi

# Activate virtual environment
source venv313/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements-py313.txt

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN:-}"

# Check for NPU support
echo "Checking NPU support..."
python test_py313.py

# Run database migrations
echo "Running database migrations..."
python -c "from database import init_db; init_db()"

# Start the server
echo "Starting FastAPI server on port 80..."
sudo python -m uvicorn main:app --host 0.0.0.0 --port 80 --reload