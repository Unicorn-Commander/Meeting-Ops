#!/usr/bin/env python3
"""Test summarization directly"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

import asyncio
from services.llm_summarization_service import llm_summarization_service

async def test_summarization():
    print("Testing Ollama summarization...")
    
    # Test data
    session_data = {
        "meeting_type": "Test Meeting",
        "duration_seconds": 300,
        "speakers": [{"speaker_id": "speaker1", "name": "Test Speaker"}]
    }
    
    transcriptions = [{
        "text": "Hello everyone, welcome to our test meeting. Today we'll discuss the project timeline and budget allocation. We need to ensure we stay on track.",
        "speaker_id": "speaker1",
        "start_time": 0,
        "end_time": 10
    }, {
        "text": "The main deliverables are due next month. We should prioritize the core features first before moving to nice-to-have items.",
        "speaker_id": "speaker1", 
        "start_time": 10,
        "end_time": 20
    }]
    
    speakers = [{"speaker_id": "speaker1", "name": "Test Speaker"}]
    
    try:
        # Test basic summary
        summary = await llm_summarization_service.generate_comprehensive_summary(
            session_data=session_data,
            transcriptions=transcriptions,
            speakers=speakers,
            summary_style="executive"
        )
        
        print("✅ Summary generated:")
        print(f"Executive Summary: {summary.get('executive_summary', 'N/A')[:200]}...")
        print(f"Action Items: {summary.get('action_items', [])}")
        print(f"Key Decisions: {summary.get('key_decisions', [])}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_summarization())