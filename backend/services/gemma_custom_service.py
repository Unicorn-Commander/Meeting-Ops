"""
Custom Gemma3n inference service for Meeting-Ops
Uses custom inference engine if available, falls back to Ollama or mock
"""
import os
import json
import time
import logging
import subprocess
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)

class GemmaCustomService:
    def __init__(self):
        """Initialize Gemma3n service with custom engine detection"""
        self.engine_path = os.getenv("GEMMA_ENGINE_PATH", "/home/ucadmin/gemma-engine/")
        self.model_path = os.getenv("GEMMA_MODEL_PATH", "/home/ucadmin/gemma-engine/models/gemma3n.gguf")
        self.use_custom = os.getenv("USE_CUSTOM_GEMMA", "false").lower() == "true"
        
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
        
        # Check for Ollama API (Docker or local)
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                self.ollama_available = True
                logger.info("✅ Ollama API available at http://localhost:11434")
                # Check if gemma3n:e4b model is available
                models = response.json().get('models', [])
                has_gemma = any('gemma3n:e4b' in model.get('name', '') for model in models)
                if has_gemma:
                    logger.info("✅ Gemma3n:e4b model available in Ollama")
                else:
                    logger.warning("⚠️ Gemma3n:e4b model not found, will try to use it anyway")
        except:
            pass
            
        if not self.engine_available and not self.ollama_available:
            logger.warning("⚠️ No inference engine available, will use mock responses")
    
    def generate_meeting_title(self, transcript: str) -> str:
        """Generate a meeting title from transcript"""
        
        if self.engine_available:
            return self._generate_with_custom_engine(
                transcript, 
                "Generate a concise title (max 5 words) for this meeting transcript:"
            )
        elif self.ollama_available:
            return self._generate_with_ollama(
                transcript,
                "Generate a concise title (max 5 words) for this meeting transcript:"
            )
        else:
            return self._generate_mock_title(transcript)
    
    def summarize_meeting(self, transcript: str, template: str = "standard") -> Dict:
        """Generate a comprehensive meeting summary"""
        
        prompt = self._get_summary_prompt(transcript, template)
        
        if self.engine_available:
            summary_text = self._generate_with_custom_engine(transcript, prompt)
            return self._parse_summary_response(summary_text)
        elif self.ollama_available:
            summary_text = self._generate_with_ollama(transcript, prompt)
            return self._parse_summary_response(summary_text)
        else:
            return self._generate_mock_summary(transcript)
    
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
    
    def _generate_with_ollama(self, context: str, prompt: str) -> str:
        """Generate text using Ollama"""
        try:
            import requests
            
            full_prompt = f"{prompt}\n\nContext:\n{context}\n\nResponse:"
            
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "gemma3n:e4b",  # Use the loaded model
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 500
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code}")
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
    
    def _generate_mock_title(self, transcript: str) -> str:
        """Generate a mock title when no engine is available"""
        # Simple heuristic - look for key words
        words = transcript.lower().split()
        
        if "standup" in words or "daily" in words:
            return "Daily Standup Meeting"
        elif "sprint" in words:
            return "Sprint Planning"
        elif "review" in words:
            return "Code Review Session"
        elif "design" in words:
            return "Design Discussion"
        else:
            return "Team Meeting"
    
    def _generate_mock_summary(self, transcript: str) -> Dict:
        """Generate a mock summary when no engine is available"""
        return {
            "summary": "Meeting summary generation requires Gemma3n or Ollama to be running.",
            "sections": {
                "note": "Install custom Gemma engine or Ollama for real summaries"
            },
            "action_items": [],
            "key_decisions": [],
            "model": "mock",
            "template": "standard"
        }
    
    def get_status(self) -> Dict:
        """Get the status of the summarization service"""
        return {
            "custom_engine_available": self.engine_available,
            "ollama_available": self.ollama_available,
            "engine_path": self.engine_path if self.engine_available else None,
            "model_path": self.model_path if self.engine_available else None,
            "active_engine": "gemma3n-custom" if self.engine_available else "ollama" if self.ollama_available else "none"
        }

# Global instance
gemma_service = GemmaCustomService()