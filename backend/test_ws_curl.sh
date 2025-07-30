#!/bin/bash

# Test WebSocket with curl
echo "Testing WebSocket endpoint..."

# Use websocat if available, otherwise use curl
if command -v websocat &> /dev/null; then
    echo "Using websocat..."
    echo '{"session_id": "curl_test"}' | websocat ws://localhost:9050/ws/transcription
else
    echo "websocat not found, using curl..."
    curl -i -N \
        -H "Connection: Upgrade" \
        -H "Upgrade: websocket" \
        -H "Sec-WebSocket-Version: 13" \
        -H "Sec-WebSocket-Key: REMOVED" \
        http://localhost:9050/ws/transcription
fi