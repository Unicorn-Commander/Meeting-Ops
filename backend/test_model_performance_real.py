#!/usr/bin/env python3
"""
Real Model Performance Benchmarking
Tests all working transcription models with actual audio input
Records true performance metrics for documentation
"""

import os
import sys
import time
import json
import logging
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add backend path
sys.path.append(str(Path(__file__).parent))

# Import transcription services
from services.transcription_service import transcription_service
from services.stt_model_manager import stt_model_manager
from services.simple_whisper_service import SimpleWhisperService
from services.whisperx_py313 import WhisperXPy313Service
from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngineReal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelPerformanceBenchmark:
    """Benchmarks all available transcription models"""
    
    def __init__(self):
        self.results = {}
        self.test_audio_file = None
        self.audio_duration = 0.0
        
        # Available models to test
        self.models_to_test = [
            "whisperx-npu-unified",  # Default with diarization
            "whisperx-npu",          # NPU without diarization  
            "whisper-onnx-npu",      # ONNX NPU
            "whisper-base",          # Standard base
            "whisper-small",         # Standard small
            "whisper-medium"         # Standard medium
        ]
    
    async def record_test_audio(self, duration: int = 30) -> str:
        """Record test audio from current input (TV dialogue)"""
        logger.info(f"🎙️ Recording {duration}s of test audio from current input...")
        
        # Create test audio file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_file = f"/tmp/benchmark_audio_{timestamp}.wav"
        
        try:
            # Record using arecord (same as the main system)
            cmd = [
                "arecord", 
                "-D", "plughw:1,0",  # USB microphone
                "-f", "S16_LE",
                "-r", "44100", 
                "-c", "1",
                "-d", str(duration),
                audio_file
            ]
            
            logger.info(f"📹 Recording command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10)
            
            if result.returncode != 0:
                logger.error(f"Recording failed: {result.stderr}")
                return None
                
            # Check if file was created and has content
            if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
                logger.info(f"✅ Recorded {duration}s audio: {audio_file}")
                self.test_audio_file = audio_file
                self.audio_duration = float(duration)
                return audio_file
            else:
                logger.error("❌ Audio file not created or too small")
                return None
                
        except Exception as e:
            logger.error(f"❌ Recording failed: {e}")
            return None
    
    async def benchmark_model(self, model_id: str) -> Dict:
        """Benchmark a specific model"""
        logger.info(f"🧪 Testing model: {model_id}")
        
        if not self.test_audio_file:
            logger.error("❌ No test audio available")
            return None
            
        start_time = time.time()
        
        try:
            # Switch to the model
            success = await stt_model_manager.switch_model(model_id)
            if not success:
                logger.error(f"❌ Failed to switch to model {model_id}")
                return {"model": model_id, "error": "Failed to load model", "success": False}
            
            # Test transcription
            logger.info(f"🔄 Transcribing with {model_id}...")
            transcription_start = time.time()
            
            # Use the transcription service
            result = transcription_service.transcribe_file(self.test_audio_file)
            
            transcription_end = time.time()
            processing_time = transcription_end - transcription_start
            
            if result and result.text:
                # Calculate metrics
                real_time_factor = processing_time / self.audio_duration
                speedup_factor = self.audio_duration / processing_time if processing_time > 0 else 0
                
                benchmark_result = {
                    "model": model_id,
                    "success": True,
                    "audio_duration": self.audio_duration,
                    "processing_time": processing_time,
                    "real_time_factor": real_time_factor,
                    "speedup_factor": speedup_factor,
                    "text_length": len(result.text),
                    "confidence": result.confidence if hasattr(result, 'confidence') else 0.0,
                    "has_diarization": len(result.segments) > 0 and any(seg.get('speaker') for seg in result.segments),
                    "segments_count": len(result.segments) if result.segments else 0,
                    "transcription_preview": result.text[:200] + "..." if len(result.text) > 200 else result.text
                }
                
                logger.info(f"✅ {model_id}: {processing_time:.2f}s processing ({real_time_factor:.3f}x realtime, {speedup_factor:.1f}x speedup)")
                return benchmark_result
                
            else:
                logger.error(f"❌ {model_id}: No transcription result")
                return {"model": model_id, "error": "No transcription output", "success": False}
                
        except Exception as e:
            logger.error(f"❌ {model_id} failed: {e}")
            return {"model": model_id, "error": str(e), "success": False}
    
    async def run_all_benchmarks(self, recording_duration: int = 30):
        """Run benchmarks for all available models"""
        logger.info("🚀 Starting comprehensive model performance benchmark")
        
        # Record test audio
        if not await self.record_test_audio(recording_duration):
            logger.error("❌ Could not record test audio - aborting benchmark")
            return None
        
        # Test each model
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "audio_file": self.test_audio_file,
            "audio_duration": self.audio_duration,
            "system_info": {
                "npu_available": os.path.exists("/dev/accel/accel0"),
                "python_version": sys.version,
                "hostname": os.uname().nodename
            },
            "models": {}
        }
        
        for model_id in self.models_to_test:
            logger.info(f"🔄 Benchmarking {model_id}...")
            result = await self.benchmark_model(model_id)
            if result:
                self.results["models"][model_id] = result
            
            # Brief pause between models
            await asyncio.sleep(2)
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save benchmark results to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"model_performance_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"💾 Results saved to: {filename}")
        return filename
    
    def print_summary(self):
        """Print a summary of results"""
        if not self.results or "models" not in self.results:
            logger.error("❌ No results to summarize")
            return
        
        print("\n" + "="*80)
        print("🏆 MODEL PERFORMANCE BENCHMARK RESULTS")
        print("="*80)
        print(f"📊 Audio Duration: {self.audio_duration:.1f}s")
        print(f"🖥️  NPU Available: {self.results['system_info']['npu_available']}")
        print(f"📅 Timestamp: {self.results['timestamp']}")
        print("\n📈 PERFORMANCE RESULTS:")
        
        # Sort by processing time (fastest first)
        successful_models = [(k, v) for k, v in self.results["models"].items() if v.get("success")]
        successful_models.sort(key=lambda x: x[1].get("processing_time", float('inf')))
        
        for model_id, result in successful_models:
            print(f"\n🔹 {model_id}:")
            print(f"   ⏱️  Processing Time: {result['processing_time']:.2f}s")
            print(f"   🚀 Speedup Factor: {result['speedup_factor']:.1f}x")
            print(f"   📊 Real-time Factor: {result['real_time_factor']:.3f}x")
            print(f"   🎯 Confidence: {result.get('confidence', 0.0):.1%}")
            print(f"   👥 Diarization: {'Yes' if result.get('has_diarization') else 'No'}")
            print(f"   📝 Segments: {result.get('segments_count', 0)}")
            print(f"   📄 Text Preview: \"{result.get('transcription_preview', '')[:100]}...\"")
        
        # Show failed models
        failed_models = [(k, v) for k, v in self.results["models"].items() if not v.get("success")]
        if failed_models:
            print("\n❌ FAILED MODELS:")
            for model_id, result in failed_models:
                print(f"   🔹 {model_id}: {result.get('error', 'Unknown error')}")
        
        print("\n" + "="*80)

async def main():
    """Main benchmark execution"""
    benchmark = ModelPerformanceBenchmark()
    
    print("🎬 Starting Model Performance Benchmark")
    print("📺 Make sure your TV audio is playing for realistic dialogue testing")
    print("⏱️  This will record 30 seconds of audio and test all models")
    
    input("Press Enter when ready to start recording...")
    
    # Run benchmarks
    results = await benchmark.run_all_benchmarks(30)
    
    if results:
        # Save results
        results_file = benchmark.save_results()
        
        # Print summary
        benchmark.print_summary()
        
        print(f"\n💾 Detailed results saved to: {results_file}")
        print("📋 Use this data to update your documentation with real performance numbers!")
    else:
        print("❌ Benchmark failed - check logs for details")

if __name__ == "__main__":
    asyncio.run(main())