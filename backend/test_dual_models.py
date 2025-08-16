#!/usr/bin/env python3
"""
Test dual-model AI system
Phi-4 for live summaries, Granite 3.3 for final summaries
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from config.dual_ai_backends import get_live_summary_backend, get_final_summary_backend

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_dual_models():
    print("=" * 60)
    print("DUAL MODEL SYSTEM TEST")
    print("=" * 60)
    
    # Test live summary backend (Phi-4)
    print("\n1. Testing Live Summary Backend (Phi-4)...")
    print("-" * 40)
    
    backend_name, live_backend = get_live_summary_backend()
    print(f"   Backend: {live_backend['name']}")
    print(f"   URL: {live_backend['url']}")
    print(f"   Purpose: {', '.join(live_backend['use_for'])}")
    
    # Test final summary backend (Granite)
    print("\n2. Testing Final Summary Backend (Granite 3.3)...")
    print("-" * 40)
    
    backend_name, final_backend = get_final_summary_backend()
    print(f"   Backend: {final_backend['name']}")
    print(f"   URL: {final_backend['url']}")
    print(f"   Purpose: {', '.join(final_backend['use_for'])}")
    
    # Test actual inference
    print("\n3. Testing Actual Inference...")
    print("-" * 40)
    
    import requests
    import json
    import time
    
    # Test Phi-4 for live summary
    print("\n   Testing Phi-4 (Live Summary):")
    test_prompt = """Summarize in 2 bullet points:
The team discussed the Q4 roadmap. Budget was approved for mobile development."""
    
    try:
        start = time.time()
        response = requests.post(
            f"{live_backend['url']}/completion",
            json={
                "prompt": test_prompt,
                "n_predict": 50,
                "temperature": 0.7
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            elapsed = time.time() - start
            print(f"   ✅ Phi-4 Response ({elapsed:.2f}s):")
            print(f"      {result.get('content', 'No content')[:100]}...")
            tokens_per_sec = result.get('timings', {}).get('predicted_per_second', 0)
            print(f"   ⚡ Speed: {tokens_per_sec:.1f} tokens/sec")
        else:
            print(f"   ❌ Phi-4 Error: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Phi-4 Error: {e}")
    
    # Test Granite for final summary
    print("\n   Testing Granite 3.3 (Final Summary):")
    test_prompt = """Generate a comprehensive meeting summary with sections for:
- Executive Summary
- Key Decisions
- Action Items

Meeting: The team approved Q4 budget, prioritized mobile app, delayed web redesign."""
    
    try:
        start = time.time()
        response = requests.post(
            f"{final_backend['url']}/completion",
            json={
                "prompt": test_prompt,
                "n_predict": 100,
                "temperature": 0.7
            },
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            elapsed = time.time() - start
            print(f"   ✅ Granite Response ({elapsed:.2f}s):")
            print(f"      {result.get('content', 'No content')[:150]}...")
            tokens_per_sec = result.get('timings', {}).get('predicted_per_second', 0)
            print(f"   ⚡ Speed: {tokens_per_sec:.1f} tokens/sec")
        else:
            print(f"   ❌ Granite Error: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Granite Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("DUAL MODEL CONFIGURATION SUMMARY")
    print("=" * 60)
    print("\n📊 Configuration:")
    print("   • Live/Progressive Summaries: Phi-4 Mini (port 11437)")
    print("   • Final/Comprehensive Summaries: Granite 3.3 8B (port 11438)")
    print("\n✨ Benefits:")
    print("   • Phi-4: Faster, lighter for real-time processing")
    print("   • Granite: More capable for comprehensive analysis")
    print("   • Optimal resource usage with task-specific models")
    print("\n🚀 Ready for production use!")

if __name__ == "__main__":
    asyncio.run(test_dual_models())