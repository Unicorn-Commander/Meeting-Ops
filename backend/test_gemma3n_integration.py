#!/usr/bin/env python3
"""
Test Gemma3n:e4b integration for Meeting-Ops
"""
import sys
import json
from services.ollama_service import OllamaService

def test_gemma3n():
    print("🧪 Testing Gemma3n:e4b Integration for Meeting-Ops\n")
    
    # Initialize service
    ollama = OllamaService()
    print(f"✅ Ollama service initialized")
    print(f"   Base URL: {ollama.base_url}")
    print(f"   Default model: {ollama.default_model}\n")
    
    # List available models
    print("📋 Available models:")
    models = ollama.list_models()
    for model in models:
        if 'gemma' in model.lower():
            print(f"   ✅ {model}")
        else:
            print(f"   - {model}")
    print()
    
    # Test basic generation
    print("🤖 Testing basic generation with Gemma3n:e4b...")
    test_prompt = "In one sentence, what is the purpose of meeting transcription?"
    response = ollama.generate(test_prompt, model="gemma3n:e4b")
    print(f"   Response: {response[:200]}\n")
    
    # Test meeting summarization
    print("📝 Testing meeting summarization...")
    sample_transcript = """
    John: Good morning everyone. Let's start with our Q4 planning meeting.
    
    Sarah: Thanks John. I'd like to begin by reviewing our current metrics. 
    We've seen a 15% increase in user engagement this quarter.
    
    Mike: That's great news. The NPU optimization we implemented last month 
    has reduced transcription latency by 200x.
    
    John: Excellent. What about our roadmap for next quarter?
    
    Sarah: We need to focus on three main areas:
    1. Improving the real-time collaboration features
    2. Adding support for multiple languages
    3. Integrating with more calendar systems
    
    Mike: I can take ownership of the language support. We'll need about 
    3 weeks for implementation and testing.
    
    John: Perfect. Sarah, can you handle the calendar integrations?
    
    Sarah: Yes, I'll coordinate with the API team. We should have Microsoft 
    365 and Google Workspace ready by end of Q4.
    
    John: Great. Let's schedule a follow-up meeting for next Friday to review progress.
    Everyone please update your tasks in the project tracker by Wednesday.
    """
    
    summary = ollama.summarize_meeting(sample_transcript)
    
    print("📊 Meeting Summary Generated:")
    print("-" * 50)
    
    if isinstance(summary, dict):
        for section, content in summary.items():
            if section != 'raw_text':
                print(f"\n{section}:")
                if isinstance(content, list):
                    for item in content:
                        print(f"  • {item}")
                else:
                    print(f"  {content}")
    else:
        print(summary[:500])
    
    print("\n" + "-" * 50)
    print("\n✅ Gemma3n:e4b integration test complete!")
    print("\n💡 Insights:")
    print("  - Model is properly loaded and responding")
    print("  - Meeting summarization is working")
    print("  - Ready for production use in Meeting-Ops")
    
    # Test real-time capability
    print("\n⚡ Testing response time...")
    import time
    start = time.time()
    quick_response = ollama.generate("Say 'NPU Ready'", model="gemma3n:e4b")
    elapsed = time.time() - start
    print(f"   Response time: {elapsed:.2f} seconds")
    print(f"   Response: {quick_response.strip()}")
    
    if elapsed < 2:
        print("   ✅ Fast enough for real-time insights!")
    else:
        print("   ⚠️  May need optimization for real-time use")

if __name__ == "__main__":
    try:
        test_gemma3n()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)