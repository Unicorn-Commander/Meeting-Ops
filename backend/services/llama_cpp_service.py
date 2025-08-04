#!/usr/bin/env python3
"""
LLaMA.cpp Service for Meeting Summarization
Uses llama.cpp with Vulkan acceleration for fast inference
"""

import asyncio
import subprocess
import json
import logging
from typing import Optional, Dict, Any
import os
import tempfile

logger = logging.getLogger(__name__)

class LlamaCppService:
    """Service for running LLM inference using llama.cpp"""
    
    def __init__(self):
        self.llama_executable = None
        self.model_path = None
        self.initialized = False
        
        # Search for llama.cpp executable
        possible_paths = [
            "/home/ucadmin/Unicorn-Execution-Engine/llama-cli",
            "/home/ucadmin/llama.cpp/build/bin/llama-cli",
            "/usr/local/bin/llama-cli",
            "/usr/bin/llama-cli"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self.llama_executable = path
                logger.info(f"Found llama.cpp at: {path}")
                break
        
        # Search for model
        self._find_model()
        
        if self.llama_executable and self.model_path:
            self.initialized = True
            logger.info(f"✅ LlamaCpp service initialized with model: {self.model_path}")
        else:
            logger.warning("⚠️ LlamaCpp service not initialized - missing executable or model")
    
    def _find_model(self):
        """Find a suitable GGUF model"""
        # Look for gemma models
        model_dirs = [
            "/home/ucadmin/models",
            "/home/ucadmin/Development/AI-Models",
            "/home/ucadmin/Unicorn-Execution-Engine/models",
            "/home/ucadmin/.cache/huggingface"
        ]
        
        model_patterns = [
            "gemma-2-2b*q4*.gguf",
            "gemma*2b*.gguf",
            "gemma*3n*e4b*.gguf",
            "*.gguf"  # Any GGUF model as fallback
        ]
        
        for model_dir in model_dirs:
            if os.path.exists(model_dir):
                for pattern in model_patterns:
                    cmd = f"find {model_dir} -name '{pattern}' -type f | head -1"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    if result.stdout.strip():
                        self.model_path = result.stdout.strip()
                        return
    
    def is_available(self) -> bool:
        """Check if the service is available"""
        return self.initialized
    
    async def summarize_transcript(
        self, 
        transcript: str, 
        session_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a summary of the transcript using llama.cpp
        
        Args:
            transcript: The transcript text to summarize
            session_info: Optional session metadata
            
        Returns:
            Generated summary text
        """
        if not self.initialized:
            return "LLM service not available. Please check llama.cpp installation and model availability."
        
        # Create a focused prompt for meeting summarization
        prompt = f"""<|system|>
You are a helpful assistant that creates concise meeting summaries. Focus on key points, decisions, and action items.
<|user|>
Please summarize the following meeting transcript:

{transcript[:3000]}  # Limit context to avoid overwhelming the model

Provide a summary with:
1. Main topics discussed
2. Key decisions made
3. Action items and assignments
4. Next steps

<|assistant|>
Meeting Summary:

"""
        
        try:
            # Run llama.cpp with optimal settings
            cmd = [
                self.llama_executable,
                "-m", self.model_path,
                "-p", prompt,
                "-n", "200",  # Max tokens to generate
                "--temp", "0.3",  # Lower temperature for more focused output
                "--top-k", "40",
                "--top-p", "0.9",
                "--repeat-penalty", "1.1",
                "--n-gpu-layers", "999",  # Use GPU acceleration
                "--ctx-size", "4096",  # Context size
                "--no-display-prompt"  # Don't echo the prompt
            ]
            
            logger.info("Running llama.cpp for summarization...")
            
            # Run with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30.0  # 30 second timeout
            )
            
            if process.returncode != 0:
                logger.error(f"llama.cpp error: {stderr.decode()}")
                return "Error generating summary"
            
            # Extract the generated text
            output = stdout.decode().strip()
            
            # Clean up the output (remove any prompt echoes if present)
            if "Meeting Summary:" in output:
                output = output.split("Meeting Summary:", 1)[1].strip()
            
            return output
            
        except asyncio.TimeoutError:
            logger.error("llama.cpp timed out")
            return "Summary generation timed out"
        except Exception as e:
            logger.error(f"Error running llama.cpp: {str(e)}")
            return f"Error generating summary: {str(e)}"
    
    async def test_inference(self) -> bool:
        """Test if inference is working"""
        if not self.initialized:
            return False
        
        try:
            result = await self.summarize_transcript("This is a test transcript.")
            return len(result) > 0
        except:
            return False

# Singleton instance
llama_service = LlamaCppService()