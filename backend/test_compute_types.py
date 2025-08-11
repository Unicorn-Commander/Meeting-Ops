#!/usr/bin/env python3
"""
Test which compute types are supported for Whisper models
"""

from faster_whisper import WhisperModel
import sys

def test_compute_type(model_size, compute_type):
    """Test if a compute type works for a model"""
    try:
        print(f"Testing {model_size} with {compute_type}...", end=" ")
        model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        print("✅ SUCCESS")
        return True
    except ValueError as e:
        print(f"❌ FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    # Test different combinations
    models = ["base", "small", "large-v3"]
    compute_types = ["int8", "int8_float16", "float16", "float32", "auto"]
    
    print("=" * 60)
    print("Testing Whisper Compute Types")
    print("=" * 60)
    
    results = {}
    
    for model_size in models:
        print(f"\n📦 Model: {model_size}")
        print("-" * 40)
        results[model_size] = {}
        
        for compute_type in compute_types:
            success = test_compute_type(model_size, compute_type)
            results[model_size][compute_type] = success
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY - Recommended Compute Types")
    print("=" * 60)
    
    for model_size in models:
        working = [ct for ct, success in results[model_size].items() if success]
        if working:
            # Prefer in this order: int8, float16, auto, float32
            if "int8" in working:
                recommended = "int8"
            elif "float16" in working:
                recommended = "float16"
            elif "auto" in working:
                recommended = "auto"
            else:
                recommended = working[0]
            
            print(f"{model_size}: {recommended} (alternatives: {', '.join(working)})")
        else:
            print(f"{model_size}: No compute types worked!")

if __name__ == "__main__":
    main()