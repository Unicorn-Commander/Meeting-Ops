#!/usr/bin/env python3
"""
Verify that live/progressive summaries use GPU (port 11437) not CPU Ollama (port 11434)
"""
import asyncio
import logging
import psutil
import requests
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_ollama_cpu_usage():
    """Check if Ollama process is using high CPU"""
    for proc in psutil.process_iter(['name', 'cpu_percent']):
        try:
            if 'ollama' in proc.info['name'].lower():
                cpu = proc.cpu_percent(interval=1)
                return proc.info['name'], cpu
        except:
            pass
    return None, 0

def monitor_ai_backends():
    """Monitor which AI backend is being used"""
    print("\n🔍 Monitoring AI backends during recording...")
    print("=" * 60)
    
    # Check GPU backend
    gpu_calls = 0
    ollama_calls = 0
    
    print("Starting monitoring (press Ctrl+C to stop)...")
    print("\nExpected behavior during live recording:")
    print("- GPU llama.cpp (port 11437) should receive requests")
    print("- CPU Ollama should NOT spike to 100% CPU")
    print("- Logs should show: '⚡ LLAMACPP inference completed'")
    print("\n" + "=" * 60)
    
    try:
        while True:
            # Check Ollama CPU usage
            proc_name, cpu_usage = check_ollama_cpu_usage()
            if proc_name and cpu_usage > 50:
                print(f"⚠️  WARNING: {proc_name} using {cpu_usage:.1f}% CPU - should be using GPU!")
                ollama_calls += 1
            
            # You could also monitor network traffic to ports here
            # This is a simplified check
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        print(f"Results:")
        print(f"  Ollama CPU spikes detected: {ollama_calls}")
        if ollama_calls > 0:
            print("  ❌ Live summaries still using CPU Ollama!")
        else:
            print("  ✅ No CPU spikes detected - likely using GPU!")

async def test_progressive_summary_path():
    """Test that progressive summaries use GPU backend"""
    print("\n🧪 Testing progressive summary generation path...")
    print("=" * 60)
    
    # Import services
    from services.unified_agent_service import unified_agent_service
    from services.progressive_interval_manager import progressive_interval_manager
    from services.live_recording_transcription import LiveRecordingTranscriptionService
    
    # Check backend configuration
    print(f"Backend type: {unified_agent_service.backend_type}")
    print(f"Backend URL: {unified_agent_service.base_url}")
    print(f"Expected: llamacpp at http://localhost:11437")
    
    if unified_agent_service.backend_type != "llamacpp":
        print("❌ WRONG BACKEND! Should be 'llamacpp' not", unified_agent_service.backend_type)
    elif unified_agent_service.base_url != "http://localhost:11437":
        print("❌ WRONG URL! Should be port 11437 not", unified_agent_service.base_url)
    else:
        print("✅ Correct GPU backend configured!")
    
    # Test the call path
    print("\n📋 Call path for live summaries:")
    print("1. live_recording_transcription detects word threshold")
    print("2. Calls progressive_interval_manager.trigger_progressive_summary()")
    print("3. Which calls unified_agent_service._generate_progressive_summary()")
    print("4. Which calls _call_granite_model() with GPU backend")
    print("5. GPU llama.cpp at port 11437 generates summary")
    
    # Simulate a progressive summary trigger
    print("\n🎯 Simulating progressive summary trigger...")
    test_session_id = "test_gpu_verification"
    
    # Mock some transcript data
    service = LiveRecordingTranscriptionService()
    service.session_id = test_session_id
    service.transcript_buffer = [
        {"text": "This is a test meeting transcript with enough words to trigger a progressive summary."},
        {"text": "We are discussing the project timeline and budget allocations for the next quarter."},
        {"text": "John will handle the frontend development while Sarah manages the backend API."}
    ]
    
    # Start unified agent
    await unified_agent_service.start_meeting_analysis(test_session_id)
    
    # Trigger a summary
    print("Triggering summary at 50 words...")
    start_time = time.time()
    
    await progressive_interval_manager.trigger_progressive_summary(
        session_id=test_session_id,
        current_word_count=50,
        force=True
    )
    
    duration = time.time() - start_time
    print(f"Summary generation took {duration:.2f}s")
    
    if duration < 2:
        print("✅ Fast generation - likely using GPU!")
    else:
        print("⚠️ Slow generation - might be using CPU")
    
    # Stop the analysis
    await unified_agent_service.stop_meeting_analysis(test_session_id)

def check_services():
    """Check which services are running"""
    print("\n🔍 Checking AI services...")
    print("=" * 60)
    
    # Check GPU llama.cpp
    try:
        response = requests.post(
            "http://localhost:11437/completion",
            json={"prompt": "Test", "n_predict": 5},
            timeout=2
        )
        if response.status_code == 200:
            print("✅ GPU llama.cpp running on port 11437")
        else:
            print("⚠️ GPU llama.cpp not responding properly")
    except:
        print("❌ GPU llama.cpp NOT running on port 11437")
        print("   Start with: ./start-gpu-optimized.sh")
    
    # Check Ollama
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("⚠️ Ollama running on port 11434 (should not be used for live summaries)")
        else:
            print("✅ Ollama not accessible (good, forces GPU usage)")
    except:
        print("✅ Ollama not running (good, will use GPU)")

async def main():
    print("=" * 60)
    print("GPU LIVE SUMMARIES VERIFICATION")
    print("=" * 60)
    
    # Check services
    check_services()
    
    # Test the progressive summary path
    await test_progressive_summary_path()
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print("\nTo fully verify:")
    print("1. Start a real recording session")
    print("2. Speak 100+ words")
    print("3. Run 'top' or 'htop' - Ollama should NOT spike to 100% CPU")
    print("4. Check logs for '⚡ LLAMACPP inference completed'")
    print("5. Run 'docker logs [llama-container]' to see GPU inference")
    print("\nOr run the monitor:")
    print("python3 verify_gpu_live_summaries.py --monitor")

if __name__ == "__main__":
    import sys
    if "--monitor" in sys.argv:
        monitor_ai_backends()
    else:
        asyncio.run(main())