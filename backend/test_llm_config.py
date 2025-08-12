#!/usr/bin/env python3
"""
Test script for LLM configuration system
Tests both local and remote endpoints
"""

import sys
import os
import json
import requests
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.llm_config import llm_config_manager, LLMProvider

def test_endpoint(name: str):
    """Test a specific endpoint"""
    print(f"\n{'='*50}")
    print(f"Testing endpoint: {name}")
    print('='*50)
    
    result = llm_config_manager.test_endpoint(name)
    
    if result.get("success"):
        print(f"✅ Connection successful!")
        print(f"   Status: {result.get('status')}")
        print(f"   Has configured model: {result.get('has_configured_model')}")
        if result.get('models'):
            print(f"   Available models:")
            for model in result.get('models', []):
                print(f"     - {model}")
    else:
        print(f"❌ Connection failed!")
        print(f"   Error: {result.get('error')}")
    
    return result

def test_generation(endpoint_name: str):
    """Test actual generation with an endpoint"""
    print(f"\n{'='*50}")
    print(f"Testing generation with: {endpoint_name}")
    print('='*50)
    
    # Set as active endpoint
    llm_config_manager.set_active_endpoint(endpoint_name)
    endpoint = llm_config_manager.config.get_active_endpoint()
    
    if not endpoint:
        print("❌ No active endpoint found")
        return False
    
    print(f"Using: {endpoint.url} with model {endpoint.model}")
    
    try:
        import ollama
        client = ollama.Client(host=endpoint.url)
        
        # Simple test prompt
        prompt = "What is 2+2? Give a one-word answer."
        
        print(f"Sending prompt: '{prompt}'")
        print("Waiting for response...")
        
        start_time = time.time()
        response = client.generate(
            model=endpoint.model,
            prompt=prompt,
            options={
                "temperature": 0.1,
                "num_predict": 10
            }
        )
        end_time = time.time()
        
        print(f"✅ Response received in {end_time - start_time:.2f} seconds")
        print(f"   Answer: {response['response']}")
        return True
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        return False

def main():
    print("🚀 LLM Configuration System Test")
    print("="*50)
    
    # Load current configuration
    config = llm_config_manager.config
    print(f"\nLoaded {len(config.endpoints)} endpoints:")
    for ep in config.endpoints:
        status = "✓ Enabled" if ep.enabled else "✗ Disabled"
        active = " [ACTIVE]" if ep.name == config.active_endpoint else ""
        print(f"  - {ep.name}: {ep.provider} ({status}){active}")
        print(f"    URL: {ep.url}")
        print(f"    Model: {ep.model}")
    
    print(f"\nFallback enabled: {config.fallback_enabled}")
    print(f"Active endpoint: {config.active_endpoint}")
    
    # Test remote Gemma3 27B endpoint
    print("\n" + "="*70)
    print("TESTING REMOTE GEMMA3 27B (192.168.1.135:11434)")
    print("="*70)
    
    remote_result = test_endpoint("remote_gemma3_27b")
    
    if remote_result.get("success"):
        # Try generation with remote
        test_generation("remote_gemma3_27b")
    
    # Test local endpoint if available
    print("\n" + "="*70)
    print("TESTING LOCAL GEMMA3N E4B (localhost:11434)")
    print("="*70)
    
    local_result = test_endpoint("local_gemma3n")
    
    if local_result.get("success"):
        # Try generation with local
        test_generation("local_gemma3n")
    
    # Test fallback mechanism
    print("\n" + "="*70)
    print("TESTING FALLBACK MECHANISM")
    print("="*70)
    
    if config.fallback_enabled:
        print("Fallback is enabled")
        fallbacks = config.get_fallback_endpoints()
        if fallbacks:
            print(f"Fallback chain ({len(fallbacks)} endpoints):")
            for i, fb in enumerate(fallbacks, 1):
                print(f"  {i}. {fb.name} (priority: {fb.priority})")
        else:
            print("No fallback endpoints configured")
    else:
        print("Fallback is disabled")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    working_endpoints = []
    failed_endpoints = []
    
    for ep in config.endpoints:
        if ep.enabled:
            result = llm_config_manager.test_endpoint(ep.name)
            if result.get("success"):
                working_endpoints.append(ep.name)
            else:
                failed_endpoints.append(ep.name)
    
    print(f"\n✅ Working endpoints: {', '.join(working_endpoints) if working_endpoints else 'None'}")
    print(f"❌ Failed endpoints: {', '.join(failed_endpoints) if failed_endpoints else 'None'}")
    
    if working_endpoints:
        print(f"\n🎯 Recommended active endpoint: {working_endpoints[0]}")
        if working_endpoints[0] != config.active_endpoint:
            print(f"   (Currently using: {config.active_endpoint})")
            print(f"   Run this to switch: llm_config_manager.set_active_endpoint('{working_endpoints[0]}')")

if __name__ == "__main__":
    main()