#!/usr/bin/env python3
"""
Test the full transcription and summarization flow
"""

import requests
import json
import time

API_BASE = "http://localhost:9050/api"

def test_full_flow():
    """Test transcription and summarization"""
    
    # 1. Get list of sessions
    print("1. Getting list of sessions...")
    response = requests.get(f"{API_BASE}/sessions")
    sessions = response.json()["sessions"]
    
    if not sessions:
        print("No sessions found!")
        return
        
    # Use the smallest session for testing
    session = min(sessions, key=lambda s: s["size"])
    print(f"   Selected session: {session['session_id']} ({session['size']} bytes)")
    
    # 2. Transcribe the session
    print("\n2. Transcribing session...")
    start_time = time.time()
    
    response = requests.post(
        f"{API_BASE}/transcribe",
        params={"file_path": session["path"]}
    )
    
    transcription_result = response.json()
    transcription_time = time.time() - start_time
    
    print(f"   Status: {transcription_result.get('status')}")
    print(f"   Time: {transcription_time:.2f}s")
    
    if transcription_result.get("status") == "success":
        transcript_data = transcription_result.get("transcription", {})
        transcript_text = transcript_data.get("text", "")
        print(f"   NPU Accelerated: {transcript_data.get('npu_accelerated', False)}")
        print(f"   Speedup: {transcript_data.get('speedup', 0):.1f}x")
        print(f"   Transcript: {transcript_text[:100]}..." if len(transcript_text) > 100 else f"   Transcript: {transcript_text}")
        
        # 3. Summarize the transcription
        if transcript_text:
            print("\n3. Summarizing transcription...")
            start_time = time.time()
            
            response = requests.post(
                f"{API_BASE}/summarize",
                json={
                    "session_id": session["session_id"],
                    "text": transcript_text
                }
            )
            
            summary_result = response.json()
            summary_time = time.time() - start_time
            
            print(f"   Status: {summary_result.get('status')}")
            print(f"   Model: {summary_result.get('model')}")
            print(f"   Time: {summary_time:.2f}s")
            
            if summary_result.get("status") == "error":
                print(f"   Error: {summary_result.get('message', 'Unknown error')}")
            
            if summary_result.get("status") == "success":
                print(f"\n   Summary:\n{'-' * 50}")
                print(summary_result.get("summary", "No summary"))
                print(f"{'-' * 50}")
        else:
            print("\n   No transcript text available to summarize")
    else:
        print(f"   Error: {transcription_result.get('message', 'Unknown error')}")

if __name__ == "__main__":
    print("Testing Full Transcription and Summarization Flow")
    print("=" * 60)
    
    try:
        test_full_flow()
    except Exception as e:
        print(f"Error: {e}")
    
    print("\nTest complete!")