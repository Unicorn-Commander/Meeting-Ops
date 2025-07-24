#!/usr/bin/env python3
"""Test server startup step by step"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

print("1. Setting up environment...")
import sys
sys.path.append('.')

print("2. Importing FastAPI...")
from fastapi import FastAPI

print("3. Creating app...")
app = FastAPI()

print("4. Importing services...")
try:
    from services.llm_summarization_service import llm_summarization_service
    print("   ✅ LLM service imported")
except Exception as e:
    print(f"   ❌ LLM service error: {e}")

print("5. Running uvicorn...")
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=9050)