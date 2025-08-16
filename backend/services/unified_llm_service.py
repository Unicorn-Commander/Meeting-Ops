"""
Unified LLM inference service for Meeting-Ops
Supports multiple models: Gemma3n, Granite, Phi4-mini
Uses Ollama as the primary inference engine with singleton pattern
"""
import os
import json
import time
import logging
import subprocess
import threading
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)

class UnifiedLLMService:
    """Singleton LLM service supporting multiple providers"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize unified LLM service with Ollama support"""
        # Only initialize once
        if self._initialized:
            return
        self._initialized = True
        self.engine_path = os.getenv("GEMMA_ENGINE_PATH", "/home/ucadmin/gemma-engine/")
        self.model_path = os.getenv("GEMMA_MODEL_PATH", "/home/ucadmin/gemma-engine/models/gemma3n.gguf")
        self.use_custom = os.getenv("USE_CUSTOM_GEMMA", "false").lower() == "true"
        
        # Support for multiple models
        self.supported_models = {
            'gemma3n:e4b': 'Gemma3n (6.9B parameters)',
            'granite3.3:8b': 'Granite 3.3 (8.2B parameters)', 
            'phi4-mini:3.8b': 'Phi4-mini (3.8B parameters)'
        }
        
        self.engine_available = False
        self.ollama_available = False
        
        # Check what's available
        self._check_available_engines()
        
    def _check_available_engines(self):
        """Check which inference engines are available"""
        
        # Check for custom Gemma engine
        if self.use_custom and os.path.exists(self.engine_path):
            engine_binary = os.path.join(self.engine_path, "gemma-cli")
            if os.path.isfile(engine_binary) and os.access(engine_binary, os.X_OK):
                self.engine_available = True
                logger.info(f"✅ Custom Gemma engine found at {engine_binary}")
                
                # Check if model exists
                if os.path.exists(self.model_path):
                    logger.info(f"✅ Gemma3n model found at {self.model_path}")
                else:
                    logger.warning(f"⚠️ Gemma3n model not found at {self.model_path}")
                    self.engine_available = False
        
        # Check for GPU-accelerated llama.cpp (our primary inference engine)
        self.llamacpp_available = False
        try:
            import requests
            # Check Phi-4 endpoint (port 11437)
            response = requests.get("http://localhost:11437/health", timeout=2)
            if response.status_code == 200:
                self.llamacpp_available = True
                logger.info("✅ Unified LLM Service - GPU llama.cpp (Phi-4) available at http://localhost:11437")
        except:
            pass
        
        if not self.llamacpp_available:
            try:
                # Check Granite endpoint (port 11438) as fallback
                import requests
                response = requests.get("http://localhost:11438/health", timeout=2)
                if response.status_code == 200:
                    self.llamacpp_available = True
                    logger.info("✅ Unified LLM Service - GPU llama.cpp (Granite) available at http://localhost:11438")
            except:
                pass
            
        if not self.engine_available and not self.llamacpp_available:
            logger.error("❌ No inference engine available - llama.cpp containers not running")
            logger.error("   Start with: docker compose -f docker-compose-vulkan-780m.yml up -d")
    
    def generate_meeting_title(self, transcript: str) -> str:
        """Generate a meeting title from transcript"""
        
        if self.engine_available:
            return self._generate_with_custom_engine(
                transcript, 
                "Generate a concise title (max 5 words) for this meeting transcript:"
            )
        elif self.llamacpp_available:
            return self._generate_with_llamacpp(
                transcript,
                "Generate a concise title (max 5 words) for this meeting transcript:"
            )
        else:
            # No mock responses - use transcript-based title
            words = transcript.split()[:5]
            return " ".join(words) + "..." if len(words) >= 5 else "Meeting " + time.strftime("%Y%m%d")
    
    def summarize_meeting(self, transcript: str, template: str = "standard") -> Dict:
        """Generate a comprehensive meeting summary"""
        
        prompt = self._get_summary_prompt(transcript, template)
        
        if self.engine_available:
            summary_text = self._generate_with_custom_engine(transcript, prompt)
            return self._parse_summary_response(summary_text)
        elif self.llamacpp_available:
            summary_text = self._generate_with_llamacpp(transcript, prompt)
            return self._parse_summary_response(summary_text)
        else:
            # No mock responses - return structured data from transcript
            word_count = len(transcript.split())
            return {
                "executive_summary": f"Meeting transcript with {word_count} words captured.",
                "key_points": ["Transcript captured successfully"],
                "action_items": [],
                "decisions": [],
                "next_steps": ["Review transcript for details"]
            }
    
    def _generate_with_custom_engine(self, context: str, prompt: str) -> str:
        """Generate text using custom Gemma engine"""
        try:
            engine_binary = os.path.join(self.engine_path, "gemma-cli")
            
            # Prepare input
            full_prompt = f"{prompt}\n\nContext:\n{context}\n\nResponse:"
            
            # Run inference
            cmd = [
                engine_binary,
                "--model", self.model_path,
                "--prompt", full_prompt,
                "--max-tokens", "500",
                "--temperature", "0.7",
                "--top-p", "0.9"
            ]
            
            logger.info("Running custom Gemma inference...")
            start_time = time.time()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            inference_time = time.time() - start_time
            
            if result.returncode == 0:
                response = result.stdout.strip()
                logger.info(f"✅ Custom inference completed in {inference_time:.2f}s")
                return response
            else:
                logger.error(f"Custom engine error: {result.stderr}")
                return ""
                
        except subprocess.TimeoutExpired:
            logger.error("Custom engine timeout")
            return ""
        except Exception as e:
            logger.error(f"Custom engine error: {e}")
            return ""
    
    def _generate_with_llamacpp(self, context: str, prompt: str) -> str:
        """Generate text using GPU-accelerated llama.cpp"""
        try:
            import requests
            
            full_prompt = f"{prompt}\n\nContext:\n{context}\n\nResponse:"
            
            # Use Phi-4 endpoint by default
            response = requests.post(
                "http://localhost:11437/completion",
                json={
                    "prompt": full_prompt,
                    "n_predict": 500,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("content", "")
            else:
                logger.error(f"llama.cpp error: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return ""
    
    def _get_summary_prompt(self, transcript: str, template: str) -> str:
        """Get the appropriate summary prompt based on template"""
        
        if template == "executive":
            return """Create an executive summary with:
1. Key Decisions (bullet points)
2. Action Items with owners
3. Strategic Implications
4. Next Steps
Keep it concise and actionable."""
        
        elif template == "technical":
            return """Create a technical summary with:
1. Technical Topics Discussed
2. Architecture Decisions
3. Implementation Details
4. Technical Debt Items
5. Dependencies and Blockers"""
        
        else:  # standard
            return """Create a meeting summary with:
1. Main Topics (3-5 bullet points)
2. Key Decisions Made
3. Action Items (who, what, when)
4. Follow-up Required
Keep it clear and organized."""
    
    def _parse_summary_response(self, response: str) -> Dict:
        """Parse LLM response into structured summary"""
        
        # Try to extract sections
        summary = {
            "summary": response,
            "sections": {},
            "action_items": [],
            "key_decisions": [],
            "model": "gemma3n-custom" if self.engine_available else "gemma:2b"
        }
        
        # Simple parsing - look for common headers
        lines = response.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            
            # Check for section headers
            if any(header in line.lower() for header in ['action items', 'action points']):
                if current_section:
                    summary["sections"][current_section] = '\n'.join(current_content)
                current_section = "action_items"
                current_content = []
            elif any(header in line.lower() for header in ['decisions', 'key decisions']):
                if current_section:
                    summary["sections"][current_section] = '\n'.join(current_content)
                current_section = "decisions"
                current_content = []
            elif any(header in line.lower() for header in ['topics', 'main topics']):
                if current_section:
                    summary["sections"][current_section] = '\n'.join(current_content)
                current_section = "topics"
                current_content = []
            elif line and not line.endswith(':'):
                current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            summary["sections"][current_section] = '\n'.join(current_content)
        
        # Extract action items as list
        if "action_items" in summary["sections"]:
            action_lines = summary["sections"]["action_items"].split('\n')
            summary["action_items"] = [
                line.strip('- •*').strip() 
                for line in action_lines 
                if line.strip() and line.strip()[0] in '-•*'
            ]
        
        return summary
    
    
    def get_status(self) -> Dict:
        """Get the status of the summarization service"""
        return {
            "custom_engine_available": self.engine_available,
            "llamacpp_available": self.llamacpp_available,
            "engine_path": self.engine_path if self.engine_available else None,
            "model_path": self.model_path if self.engine_available else None,
            "active_engine": "gemma3n-custom" if self.engine_available else "gpu-llamacpp" if self.llamacpp_available else "none"
        }

# Global singleton instance  
llm_service = UnifiedLLMService()

# Legacy alias for backward compatibility
gemma_service = llm_service
GemmaCustomService = UnifiedLLMService