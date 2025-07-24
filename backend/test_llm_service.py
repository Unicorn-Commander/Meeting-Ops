#!/usr/bin/env python3
"""Test LLM service initialization"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

print("Testing LLM service...")
try:
    from services.llm_summarization_service import LLMSummarizationService
    print("✅ Import successful")
    
    service = LLMSummarizationService()
    print("✅ Service initialized")
    
    print(f"Ollama URL: {service.ollama_url}")
    print(f"Ollama Model: {service.ollama_model}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()