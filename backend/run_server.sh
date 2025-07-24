#!/bin/bash
# Proper wrapper to start server with audio support

echo "🚀 Starting Unicorn Commander with audio support..."

# Set library path BEFORE Python starts
export LD_PRELOAD=/lib/x86_64-linux-gnu/libstdc++.so.6
export PYTHONUNBUFFERED=1

# Activate virtual environment
source venv313/bin/activate

# Test audio first
echo "🧪 Testing audio libraries..."
python -c "import sounddevice as sd; print(f'✅ Sounddevice works! Version: {sd.__version__}')" || {
    echo "❌ Audio test failed!"
    exit 1
}

# Start the server
echo "✅ Starting server..."
exec python main.py "$@"