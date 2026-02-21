"""
Unified LLM inference service for Meeting-Ops
Single Granite 3.3 2B model on llama.cpp Vulkan via OpenAI-compatible API
"""
import os
import json
import time
import logging
import threading
from typing import Optional, Dict, List

import requests

logger = logging.getLogger(__name__)

# Default endpoint for llama.cpp Vulkan server
LLAMACPP_URL = os.getenv("LLAMACPP_URL", "http://localhost:11437")
LLAMACPP_MODEL = "granite-3.3-2b-instruct"


class UnifiedLLMService:
    """Singleton LLM service using Granite 3.3 2B on llama.cpp Vulkan"""

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
        """Initialize unified LLM service with llama.cpp Vulkan backend"""
        if self._initialized:
            return
        self._initialized = True

        self.base_url = LLAMACPP_URL
        self.model_name = LLAMACPP_MODEL
        self.llamacpp_available = False

        # Check availability on startup
        self._check_available()

    def _check_available(self):
        """Check if llama.cpp Vulkan server is available"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            if response.status_code == 200:
                self.llamacpp_available = True
                logger.info(f"Unified LLM Service - Granite 3.3 2B available at {self.base_url}")
            else:
                self.llamacpp_available = False
                logger.warning(f"llama.cpp health check returned {response.status_code}")
        except Exception:
            self.llamacpp_available = False
            logger.warning(f"llama.cpp not available at {self.base_url} - LLM features disabled until server starts")

    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Call Granite 3.3 2B via OpenAI-compatible chat completions API"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return content.strip()
            else:
                logger.error(f"llama.cpp API error: {response.status_code} - {response.text[:200]}")
                return ""

        except requests.exceptions.Timeout:
            logger.error("llama.cpp request timed out")
            return ""
        except Exception as e:
            logger.error(f"llama.cpp call failed: {e}")
            return ""

    def generate_meeting_title(self, transcript: str) -> str:
        """Generate a meeting title from transcript"""
        if not self.llamacpp_available:
            self._check_available()

        if self.llamacpp_available:
            result = self._call_llm(
                system_prompt="You generate concise meeting titles. Respond with ONLY the title, no quotes or extra text.",
                user_prompt=f"Generate a concise title (max 5 words) for this meeting transcript:\n\n{transcript[:2000]}",
                max_tokens=20,
                temperature=0.3
            )
            if result:
                # Clean up the title
                title = result.replace('"', '').replace('\n', ' ').strip()
                return title[:100] if title else self._fallback_title(transcript)

        return self._fallback_title(transcript)

    def _fallback_title(self, transcript: str) -> str:
        """Generate a basic title from transcript when LLM is unavailable"""
        words = transcript.split()[:5]
        return " ".join(words) + "..." if len(words) >= 5 else "Meeting " + time.strftime("%Y%m%d")

    def summarize_meeting(self, transcript: str, template: str = "standard") -> Dict:
        """Generate a comprehensive meeting summary"""
        if not self.llamacpp_available:
            self._check_available()

        prompt = self._get_summary_prompt(template)

        if self.llamacpp_available:
            summary_text = self._call_llm(
                system_prompt="You are a meeting assistant. Provide clear, structured meeting summaries.",
                user_prompt=f"{prompt}\n\nTranscript:\n{transcript[:4000]}",
                max_tokens=500,
                temperature=0.7
            )
            if summary_text:
                return self._parse_summary_response(summary_text)

        # Fallback when LLM is unavailable
        word_count = len(transcript.split())
        return {
            "executive_summary": f"Meeting transcript with {word_count} words captured.",
            "key_points": ["Transcript captured successfully"],
            "action_items": [],
            "decisions": [],
            "next_steps": ["Review transcript for details"]
        }

    def _get_summary_prompt(self, template: str) -> str:
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
        summary = {
            "summary": response,
            "sections": {},
            "action_items": [],
            "key_decisions": [],
            "model": self.model_name
        }

        lines = response.split('\n')
        current_section = None
        current_content = []

        for line in lines:
            line = line.strip()

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

        if current_section and current_content:
            summary["sections"][current_section] = '\n'.join(current_content)

        if "action_items" in summary["sections"]:
            action_lines = summary["sections"]["action_items"].split('\n')
            summary["action_items"] = [
                line.strip('- *').strip()
                for line in action_lines
                if line.strip() and line.strip()[0] in '-*'
            ]

        return summary

    def get_status(self) -> Dict:
        """Get the status of the LLM service"""
        self._check_available()
        return {
            "llamacpp_available": self.llamacpp_available,
            "base_url": self.base_url,
            "model": self.model_name,
            "active_engine": "granite-3.3-2b-vulkan" if self.llamacpp_available else "none"
        }


# Global singleton instance
llm_service = UnifiedLLMService()
