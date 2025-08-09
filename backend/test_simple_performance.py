#!/usr/bin/env python3
"""
Simple Performance Test using API calls
Tests real transcription models with TV audio via REST API
"""

import os
import time
import json
import requests
import subprocess
from datetime import datetime
from pathlib import Path

class SimplePerformanceTest:
    def __init__(self):
        self.api_base = "http://localhost:9050"
        self.results = {}
        
    def record_test_audio(self, duration=30):
        """Record test audio"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_file = f"/tmp/test_audio_{timestamp}.wav"
        
        print(f"🎙️ Recording {duration}s of TV audio...")
        
        try:
            # Record audio
            cmd = [
                "arecord", 
                "-D", "plughw:0,0",  # USB device is card 0
                "-f", "S16_LE",
                "-r", "44100", 
                "-c", "1",
                "-d", str(duration),
                audio_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10)
            
            if result.returncode == 0 and os.path.exists(audio_file):
                print(f"✅ Recorded: {audio_file}")
                return audio_file, duration
            else:
                print(f"❌ Recording failed: {result.stderr}")
                return None, 0
                
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None, 0
    
    def test_model_via_api(self, audio_file, audio_duration, model_id):
        """Test a model via API endpoint"""
        print(f"🧪 Testing {model_id}...")
        
        try:
            # Switch to model first
            switch_url = f"{self.api_base}/api/ai/models/switch"
            switch_data = {"model_id": model_id}
            
            switch_response = requests.post(switch_url, json=switch_data, timeout=30)
            if switch_response.status_code != 200:
                return {"model": model_id, "error": "Failed to switch model", "success": False}
            
            # Upload and transcribe
            transcribe_url = f"{self.api_base}/api/simple/transcribe-file"
            
            start_time = time.time()
            
            with open(audio_file, 'rb') as f:
                files = {'audio_file': f}
                response = requests.post(transcribe_url, files=files, timeout=120)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            if response.status_code == 200:
                result_data = response.json()
                text = result_data.get('text', '')
                
                # Calculate metrics
                real_time_factor = processing_time / audio_duration if audio_duration > 0 else 0
                speedup_factor = audio_duration / processing_time if processing_time > 0 else 0
                
                return {
                    "model": model_id,
                    "success": True,
                    "audio_duration": audio_duration,
                    "processing_time": processing_time,
                    "real_time_factor": real_time_factor,
                    "speedup_factor": speedup_factor,
                    "text_length": len(text),
                    "confidence": result_data.get('confidence', 0.0),
                    "segments_count": len(result_data.get('segments', [])),
                    "transcription_preview": text[:150] + "..." if len(text) > 150 else text
                }
            else:
                return {"model": model_id, "error": f"API error: {response.status_code}", "success": False}
                
        except Exception as e:
            return {"model": model_id, "error": str(e), "success": False}
    
    def run_benchmark(self, recording_duration=30):
        """Run the complete benchmark"""
        print("🚀 Starting Simple Performance Benchmark")
        print("📺 TV audio detected - starting automatic recording...")
        time.sleep(2)
        
        # Record test audio
        audio_file, audio_duration = self.record_test_audio(recording_duration)
        if not audio_file:
            return None
        
        # Models to test (in order of expected performance)
        models_to_test = [
            "whisper-base",          # Standard base model
            "whisper-small",         # Standard small model  
            "whisperx-npu-unified",  # NPU with diarization (default)
            "whisperx-npu",          # NPU without diarization
        ]
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "audio_file": audio_file,
            "audio_duration": audio_duration,
            "models": {}
        }
        
        for model_id in models_to_test:
            result = self.test_model_via_api(audio_file, audio_duration, model_id)
            results["models"][model_id] = result
            
            if result["success"]:
                print(f"✅ {model_id}: {result['processing_time']:.2f}s ({result['speedup_factor']:.1f}x speedup)")
            else:
                print(f"❌ {model_id}: {result['error']}")
            
            time.sleep(3)  # Brief pause between tests
        
        return results
    
    def print_results(self, results):
        """Print formatted results"""
        if not results:
            return
            
        print("\n" + "="*60)
        print("🏆 MODEL PERFORMANCE RESULTS")
        print("="*60)
        print(f"📊 Audio Duration: {results['audio_duration']:.1f}s")
        print(f"📅 Test Time: {results['timestamp']}")
        
        # Sort by speedup factor
        successful = [(k, v) for k, v in results["models"].items() if v.get("success")]
        successful.sort(key=lambda x: x[1].get("speedup_factor", 0), reverse=True)
        
        if successful:
            print("\n📈 PERFORMANCE RANKING:")
            for i, (model_id, result) in enumerate(successful, 1):
                print(f"\n{i}. {model_id}")
                print(f"   ⏱️  Processing: {result['processing_time']:.2f}s")
                print(f"   🚀 Speedup: {result['speedup_factor']:.1f}x")
                print(f"   📊 Real-time Factor: {result['real_time_factor']:.3f}x")
                print(f"   📝 Text Length: {result['text_length']} chars")
                print(f"   🎯 Segments: {result['segments_count']}")
                print(f"   📄 Preview: \"{result['transcription_preview']}\"")
        
        # Show failures
        failed = [(k, v) for k, v in results["models"].items() if not v.get("success")]
        if failed:
            print("\n❌ FAILED MODELS:")
            for model_id, result in failed:
                print(f"   • {model_id}: {result['error']}")
        
        print("\n" + "="*60)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"performance_results_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"💾 Results saved to: {results_file}")

def main():
    test = SimplePerformanceTest()
    results = test.run_benchmark(30)
    if results:
        test.print_results(results)
    else:
        print("❌ Benchmark failed")

if __name__ == "__main__":
    main()