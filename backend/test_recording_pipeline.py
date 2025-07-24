#!/usr/bin/env python3
"""
Test the complete recording pipeline end-to-end
"""
import sys
import requests
import time
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:9050/api"

def test_recording_pipeline():
    """Test the complete recording pipeline"""
    try:
        logger.info("Testing complete recording pipeline...")
        
        # Step 1: Check system status
        logger.info("1. Checking system status...")
        response = requests.get(f"{BASE_URL}/status")
        if response.status_code != 200:
            logger.error(f"Failed to get system status: {response.status_code}")
            return False
        status = response.json()
        logger.info(f"   System status: {status}")
        
        # Step 2: Create a new recording session
        logger.info("2. Creating recording session...")
        session_data = {
            "name": "Test Recording Session",
            "description": "Automated test of recording pipeline"
        }
        response = requests.post(f"{BASE_URL}/recording-sessions", json=session_data)
        if response.status_code != 200:
            logger.error(f"Failed to create session: {response.status_code} - {response.text}")
            return False
        session_response = response.json()
        session = session_response.get("session", session_response)
        session_id = session["session_id"]
        logger.info(f"   Created session: {session_id}")
        
        # Step 3: Start recording
        logger.info("3. Starting recording...")
        response = requests.post(f"{BASE_URL}/recording-sessions/{session_id}/start")
        if response.status_code != 200:
            logger.error(f"Failed to start recording: {response.status_code} - {response.text}")
            return False
        logger.info("   Recording started successfully")
        
        # Step 4: Let it record for 5 seconds
        logger.info("4. Recording for 5 seconds...")
        time.sleep(5)
        
        # Step 5: Check audio level during recording
        response = requests.get(f"{BASE_URL}/audio-level")
        if response.status_code == 200:
            audio_level = response.json()
            logger.info(f"   Audio level: {audio_level}")
        
        # Step 6: Stop recording
        logger.info("5. Stopping recording...")
        response = requests.post(f"{BASE_URL}/recording-sessions/{session_id}/stop")
        if response.status_code != 200:
            logger.error(f"Failed to stop recording: {response.status_code} - {response.text}")
            return False
        logger.info("   Recording stopped successfully")
        
        # Step 7: Wait for processing
        logger.info("6. Waiting for processing...")
        time.sleep(3)
        
        # Step 8: Check session details
        logger.info("7. Checking session details...")
        response = requests.get(f"{BASE_URL}/recording-sessions/{session_id}")
        if response.status_code != 200:
            logger.error(f"Failed to get session details: {response.status_code}")
            return False
        session_details = response.json()
        logger.info(f"   Session status: {session_details.get('status')}")
        logger.info(f"   Duration: {session_details.get('duration', 0)} seconds")
        logger.info(f"   Transcriptions: {len(session_details.get('transcriptions', []))}")
        
        # Step 9: Check for files
        logger.info("8. Checking for recorded files...")
        response = requests.get(f"{BASE_URL}/files/session/{session_id}")
        if response.status_code == 200:
            files = response.json()
            logger.info(f"   Found {len(files)} files")
            for file in files[:2]:  # Show first 2 files
                logger.info(f"     - {file.get('filename', 'Unknown')} ({file.get('file_size', 0)} bytes)")
        else:
            logger.info("   No files found or files endpoint not available")
        
        # Success criteria
        if (session_details.get('status') == 'completed' and 
            session_details.get('duration', 0) > 0):
            logger.info("✅ Recording pipeline test PASSED!")
            logger.info("   - Session created successfully")
            logger.info("   - Recording started and stopped")
            logger.info("   - Session has duration > 0")
            return True
        else:
            logger.error("❌ Recording pipeline test FAILED!")
            logger.error("   - Session may not have recorded properly")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_recording_pipeline()
    sys.exit(0 if success else 1)