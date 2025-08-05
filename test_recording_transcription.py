
import requests
import time
import asyncio
import websockets
import json
import sys

BASE_URL = "http://localhost:9050"
HEADERS = {"Content-Type": "application/json"}

async def test_transcription_websocket(session_id):
    uri = f"ws://localhost:9050/api/recording-sessions/{session_id}/transcription-stream"
    async with websockets.connect(uri) as websocket:
        print("✅ WebSocket connected")
        try:
            async for message in websocket:
                data = json.loads(message)
                print(f"Received: {data.get('text', 'No text')} (speaker {data.get('speaker', 'unknown')})")
                if 'final' in data and data['final']:
                    break
            print("✅ Received final transcription")
        except Exception as e:
            print(f"❌ WebSocket error: {e}")

def test_recording():
    headers = HEADERS.copy()

    # Login to get token
    print("Step 1: Logging in...")
    login_response = requests.post(f"{BASE_URL}/api/auth/login", data={"username": "admin", "password": "password"})
    if login_response.status_code == 200:
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("✅ Token acquired")
    else:
        print(f"❌ Auth failed - check credentials: {login_response.status_code}")
        print(login_response.text)
        sys.exit(1)

    # 1. Create recording session
    print("\n1. Creating recording session...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions",
        headers=headers,
        json={"title": "Test Recording", "description": "Automated test"}
    )

    if response.status_code not in [200, 201]:
        print(f"❌ Failed to create session: {response.status_code}")
        print(response.text)
        sys.exit(1)

    session_id = response.json().get("id")
    print(f"✅ Session created: ID={session_id}")

    # 2. Start recording
    print("\n2. Starting recording...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/start",
        headers=headers
    )

    if response.status_code not in [200, 201]:
        print(f"❌ Failed to start recording: {response.status_code}")
        print(response.text)
        sys.exit(1)

    print("✅ Recording started")

    # 3. Test transcription WebSocket
    print("\n3. Testing live transcription...")
    asyncio.run(test_transcription_websocket(session_id))

    # 4. Let it record for 10 seconds
    print("\n4. Recording for 10 seconds...")
    for i in range(10):
        print(f"  {10 - i} seconds remaining...", end="\r")
        time.sleep(1)

    # 5. Stop recording
    print("\n\n5. Stopping recording...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/stop",
        headers=headers
    )

    if response.status_code not in [200, 201]:
        print(f"❌ Failed to stop recording: {response.status_code}")
        print(response.text)
        sys.exit(1)

    print("✅ Recording stopped")

    # 6. Get transcriptions
    print("\n6. Getting transcriptions...")
    response = requests.get(
        f"{BASE_URL}/api/recording-sessions/{session_id}/transcriptions",
        headers=headers
    )

    if response.status_code == 200:
        transcriptions = response.json()
        print(f"✅ Found {len(transcriptions)} transcriptions")
        for t in transcriptions[:3]:  # Show first 3
            print(f"   - {t.get('text', 'No text')}")
    else:
        print(f"❌ Failed to get transcriptions: {response.status_code}")

    # 7. Test summarization
    print("\n7. Testing summarization...")
    response = requests.post(
        f"{BASE_URL}/api/recording-sessions/{session_id}/summarize",
        headers=headers
    )

    if response.status_code in [200, 201]:
        print("✅ Summary requested")

        # Wait a bit for processing
        time.sleep(3)

        num_words = 100 if "num_words" not in locals() else num_words
        # Get summary
        response = requests.get(
            f"{BASE_URL}/api/recording-sessions/{session_id}/summary",
            headers=headers
        )

        if response.status_code == 200:
            summary = response.json()
            print(
                f"✅ Summary: {
                    summary.get(
                        'summary',
                        'No summary')[
                        :100]}...")
        else:
            print(f"❌ Failed to get summary: {response.status_code}")
    else:
        print(f"❌ Failed to request summary: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_recording()
