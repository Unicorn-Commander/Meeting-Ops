#!/bin/bash
# Start the server with correct audio library paths

echo "🚀 Starting Unicorn Commander backend with audio support..."

# Use system libstdc++ to avoid GLIBCXX conflicts
export LD_PRELOAD=/lib/x86_64-linux-gnu/libstdc++.so.6

# Activate Python 3.13 environment
source venv313/bin/activate

# Start the server
echo "✅ Audio libraries configured, starting server..."
python main.py