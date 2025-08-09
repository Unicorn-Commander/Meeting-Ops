#!/usr/bin/env python3
"""
Test actual transcription speeds for different models
Uses the recorded audio file to measure real performance
"""

import time
import requests
import json
from datetime import datetime

# Audio file we recorded (37 seconds of TV audio)
TEST_AUDIO = "/home/ucadmin/Meeting-Ops/backend/recordings/recording_a80dd669-eb13-45d0-b3a7-b3b70bd3f0e0_20250809_211910.wav"
AUDIO_DURATION = 37.28  # seconds

def test_model(model_id):
    """Test a specific model and return performance metrics"""
    print(f"\n🧪 Testing {model_id}...")
    
    try:
        # Switch to the model
        switch_url = "http://localhost:9050/api/ai/models/switch"
        switch_response = requests.post(switch_url, json={"model_id": model_id}, timeout=30)
        
        if switch_response.status_code != 200:
            return {"model": model_id, "error": f"Failed to switch: {switch_response.status_code}"}
        
        print(f"   ✅ Switched to {model_id}")
        time.sleep(2)  # Give model time to load
        
        # Transcribe the file
        print(f"   🔄 Transcribing...")
        start_time = time.time()
        
        with open(TEST_AUDIO, 'rb') as f:
            response = requests.post(
                "http://localhost:9050/api/transcribe",
                files={'file': f},
                timeout=120
            )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('text', '')
            
            # Calculate performance metrics
            real_time_factor = processing_time / AUDIO_DURATION
            speedup = AUDIO_DURATION / processing_time
            
            print(f"   ✅ Success!")
            print(f"   ⏱️  Processing: {processing_time:.2f}s")
            print(f"   🚀 Speedup: {speedup:.1f}x")
            print(f"   📊 RTF: {real_time_factor:.3f}")
            print(f"   📝 Transcribed {len(text)} characters")
            
            return {
                "model": model_id,
                "success": True,
                "processing_time": processing_time,
                "speedup": speedup,
                "real_time_factor": real_time_factor,
                "text_length": len(text),
                "text_preview": text[:100] + "..." if len(text) > 100 else text
            }
        else:
            return {
                "model": model_id,
                "error": f"Transcription failed: {response.status_code}",
                "success": False
            }
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {"model": model_id, "error": str(e), "success": False}

def main():
    print("🚀 REAL NPU TRANSCRIPTION SPEED TEST")
    print("="*50)
    print(f"📊 Test Audio: {AUDIO_DURATION:.1f} seconds of TV dialogue")
    print(f"📁 File: {TEST_AUDIO}")
    print("="*50)
    
    # Models to test
    models = [
        "whisper-base",          # Standard Whisper base
        "whisperx-npu",          # NPU accelerated
        "whisperx-npu-unified",  # NPU with diarization (default)
    ]
    
    results = []
    
    for model_id in models:
        result = test_model(model_id)
        results.append(result)
        time.sleep(3)  # Pause between tests
    
    # Print summary
    print("\n" + "="*60)
    print("📊 PERFORMANCE SUMMARY")
    print("="*60)
    print(f"Audio Duration: {AUDIO_DURATION:.1f} seconds")
    print("\n🏆 Results (sorted by speed):")
    
    successful = [r for r in results if r.get("success")]
    successful.sort(key=lambda x: x["speedup"], reverse=True)
    
    for i, result in enumerate(successful, 1):
        print(f"\n{i}. {result['model']}")
        print(f"   Processing: {result['processing_time']:.2f}s")
        print(f"   Speedup: {result['speedup']:.1f}x faster than real-time")
        print(f"   RTF: {result['real_time_factor']:.3f}")
        print(f"   Text: \"{result['text_preview']}\"")
    
    # Show failures
    failed = [r for r in results if not r.get("success")]
    if failed:
        print("\n❌ Failed Models:")
        for result in failed:
            print(f"   {result['model']}: {result.get('error', 'Unknown error')}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"speed_test_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "audio_duration": AUDIO_DURATION,
            "audio_file": TEST_AUDIO,
            "results": results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {results_file}")

if __name__ == "__main__":
    main()