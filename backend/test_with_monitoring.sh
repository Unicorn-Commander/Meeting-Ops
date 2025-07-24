#!/bin/bash
# Test recording while monitoring server output

echo "🧪 Starting recording test..."

# Create session
SESSION_ID=$(curl -s -X POST "http://localhost:9050/api/recording-sessions" \
  -H "Content-Type: application/json" \
  -d '{"name": "Monitor Test", "description": "Testing with output monitoring"}' | \
  jq -r '.session.session_id')

echo "📝 Created session: $SESSION_ID"

# Start recording
echo "🎙️ Starting recording..."
curl -s -X POST "http://localhost:9050/api/recording-sessions/$SESSION_ID/start" | jq '.success'

# Record for 12 seconds (should get 1 chunk)
echo "⏰ Recording for 12 seconds..."
sleep 12

# Stop recording
echo "⏹️ Stopping recording..."
RESULT=$(curl -s -X POST "http://localhost:9050/api/recording-sessions/$SESSION_ID/stop")
echo "Duration: $(echo $RESULT | jq -r '.session.duration_seconds')s"

# Check file
FILE_SIZE=$(ls -la storage/audio_files/recordings/$SESSION_ID/*.wav 2>/dev/null | awk '{print $5}')
echo "📁 Audio file size: ${FILE_SIZE:-0} bytes"

# Check transcriptions
TRANSCRIPTIONS=$(curl -s "http://localhost:9050/api/recording-sessions/$SESSION_ID" | jq -r '.total_transcriptions')
echo "📝 Transcriptions: $TRANSCRIPTIONS"