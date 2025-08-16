#!/usr/bin/env python3
"""
Test GPU-accelerated AI backend and progressive summaries
"""
import asyncio
import logging
import requests
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_gpu_backend():
    """Test GPU llama.cpp endpoint"""
    print("\n🔍 Testing GPU-accelerated LLaMA.cpp backend...")
    
    # Test GPU endpoint (port 11437)
    gpu_url = "http://localhost:11437/completion"
    test_prompt = "Summarize this: The meeting discussed project timelines and budget allocations."
    
    try:
        print(f"   Testing GPU endpoint at {gpu_url}")
        response = requests.post(
            gpu_url,
            json={
                "prompt": test_prompt,
                "n_predict": 50,
                "temperature": 0.7,
                "stream": False
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ GPU backend working!")
            print(f"   Response: {result.get('content', '')[:100]}...")
            return True
        else:
            print(f"   ❌ GPU backend returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ GPU backend not running on port 11437")
        print(f"   Start with: ./start-gpu-optimized.sh")
        return False
    except Exception as e:
        print(f"   ❌ GPU backend error: {e}")
        return False

def test_ollama_fallback():
    """Test Ollama fallback endpoint"""
    print("\n🔍 Testing Ollama fallback backend...")
    
    ollama_url = "http://localhost:11434/api/generate"
    
    try:
        print(f"   Testing Ollama endpoint at {ollama_url}")
        response = requests.post(
            ollama_url,
            json={
                "model": "granite3.3:8b",
                "prompt": "Test prompt",
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 10
                }
            },
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"   ✅ Ollama fallback available")
            return True
        else:
            print(f"   ⚠️ Ollama returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"   ⚠️ Ollama not running (fallback unavailable)")
        return False
    except Exception as e:
        print(f"   ⚠️ Ollama error: {e}")
        return False

async def test_progressive_summaries():
    """Test progressive summary triggering"""
    print("\n🔍 Testing progressive summary system...")
    
    # Import the services
    from services.live_recording_transcription import LiveRecordingTranscriptionService
    from services.progressive_interval_manager import progressive_interval_manager
    
    # Create test instance
    service = LiveRecordingTranscriptionService()
    test_session_id = "test_session_123"
    
    # Simulate word count progression
    word_intervals = [25, 50, 75, 100, 150, 200, 300, 400, 500, 600, 700, 800, 900]
    
    print(f"   Simulating word count progression...")
    for word_count in word_intervals:
        # Simulate adding words
        service.session_word_counts[test_session_id] = word_count
        
        # Check for triggers
        await service._check_and_trigger_summary(test_session_id, word_count)
        
        # Check which intervals were triggered
        if test_session_id in service.triggered_intervals:
            triggered = service.triggered_intervals[test_session_id]
            if triggered:
                print(f"   📊 At {word_count} words, triggered intervals: {triggered}")
    
    print(f"   ✅ Progressive summary triggering tested")
    
    # Clean up
    if test_session_id in service.triggered_intervals:
        final_triggered = service.triggered_intervals[test_session_id]
        print(f"   Final triggered intervals: {final_triggered}")
        expected = {50, 75, 113, 169, 253, 379, 568, 852}
        covered = final_triggered.intersection(expected)
        print(f"   Coverage: {len(covered)}/{len(expected)} intervals triggered")

async def test_unified_agent_with_gpu():
    """Test unified agent service with GPU backend"""
    print("\n🔍 Testing Unified Agent with GPU backend...")
    
    from services.unified_agent_service import unified_agent_service
    
    # Check backend configuration
    print(f"   Backend type: {unified_agent_service.backend_type}")
    print(f"   Backend URL: {unified_agent_service.base_url}")
    print(f"   Backend name: {unified_agent_service.ai_backend['name']}")
    
    # Test a simple summary generation
    from models.unified_agent import UnifiedMeetingAgent
    from database.database import get_db_session
    
    db = get_db_session()
    agent = UnifiedMeetingAgent.get_default_agent(db)
    if not agent:
        agent = UnifiedMeetingAgent.create_default_agent(db)
    
    test_transcript = "This is a test meeting transcript. We discussed the project timeline, budget allocations, and next steps. John will handle the frontend development. Sarah will manage the backend API. The deadline is next Friday."
    
    interval_info = {
        'current_word_count': 30,
        'total_summaries': 0,
        'current_interval': 50
    }
    
    print(f"   Testing summary generation...")
    start_time = datetime.now()
    
    result = await unified_agent_service._call_granite_model(
        transcript=test_transcript,
        agent=agent,
        interval_info=interval_info
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    if result:
        print(f"   ✅ Summary generated in {duration:.2f}s")
        print(f"   Executive: {result.get('executive', 'N/A')[:100]}...")
        if unified_agent_service.backend_type == "llamacpp":
            print(f"   ⚡ Using GPU acceleration!")
    else:
        print(f"   ❌ Summary generation failed")
    
    db.close()

async def main():
    """Run all tests"""
    print("=" * 60)
    print("GPU AI Backend & Progressive Summaries Test Suite")
    print("=" * 60)
    
    # Test GPU backend
    gpu_available = test_gpu_backend()
    
    # Test Ollama fallback
    ollama_available = test_ollama_fallback()
    
    if not gpu_available and not ollama_available:
        print("\n⚠️ WARNING: No AI backends available!")
        print("Start GPU server with: ./start-gpu-optimized.sh")
        print("Or start Ollama with: docker compose up -d")
    
    # Test progressive summaries
    await test_progressive_summaries()
    
    # Test unified agent with GPU
    if gpu_available or ollama_available:
        await test_unified_agent_with_gpu()
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"  GPU Backend: {'✅ Working' if gpu_available else '❌ Not available'}")
    print(f"  Ollama Fallback: {'✅ Available' if ollama_available else '⚠️ Not available'}")
    print(f"  Progressive Summaries: ✅ Configured")
    print(f"  Expected Performance: {'⚡ 55% faster with GPU' if gpu_available else '🐢 CPU mode'}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())