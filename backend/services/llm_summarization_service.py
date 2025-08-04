"""
Advanced LLM Summarization Service
Provides intelligent meeting analysis, action item extraction, and insights
"""
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import httpx
from openai import OpenAI
from anthropic import Anthropic

logger = logging.getLogger(__name__)

class LLMSummarizationService:
    """Service for generating intelligent meeting summaries and insights"""
    
    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None
        self.ollama_url = None
        self.ollama_model = None
        self.llama_cpp_service = None
        self.setup_clients()
    
    def setup_clients(self):
        """Initialize LLM clients based on available API keys and configuration"""
        openai_key = os.getenv('OPENAI_API_KEY')
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        ollama_model = os.getenv('OLLAMA_MODEL', 'gemma3n:latest')
        
        if openai_key:
            try:
                self.openai_client = OpenAI(api_key=openai_key)
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize OpenAI client: {e}")
                self.openai_client = None
        
        
        
        # Check llama.cpp availability first (preferred for local inference)
        try:
            from .llama_cpp_service import llama_service
            if llama_service.is_available():
                self.llama_cpp_service = llama_service
                logger.info("✅ LLaMA.cpp service initialized with Vulkan acceleration")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize llama.cpp service: {e}")
        
        # Check Ollama availability as fallback
        if not self.llama_cpp_service:
            try:
                import httpx
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(f"{ollama_url}/api/tags")
                    if response.status_code == 200:
                        self.ollama_url = ollama_url
                        self.ollama_model = ollama_model
                        logger.info(f"✅ Ollama client initialized at {ollama_url} with model {ollama_model}")
                    else:
                        logger.warning(f"⚠️ Ollama server at {ollama_url} not responding properly")
            except Exception as e:
                logger.warning(f"⚠️ Could not connect to Ollama at {ollama_url}: {e}")
        
        if not (openai_key or anthropic_key or self.ollama_url or self.llama_cpp_service):
            logger.warning("⚠️ No LLM services available. Summarization will use fallback mode.")
    
    async def generate_comprehensive_summary(
        self,
        session_data: Dict[str, Any],
        transcriptions: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
        summary_style: str = "executive",
        focus_areas: List[str] = None,
        template_type: str = None,
        custom_instructions: str = None,
        llm_parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive meeting summary with multiple analysis types
        
        Args:
            session_data: Meeting session information
            transcriptions: List of transcription segments
            speakers: Speaker information
            summary_style: Style of summary (executive, detailed, bullet_points)
            focus_areas: Specific areas to focus on (decisions, action_items, issues)
        
        Returns:
            Dictionary containing various summary components
        """
        try:
            # Prepare transcript text
            full_transcript = self._prepare_transcript(transcriptions, speakers)
            
            if not full_transcript.strip():
                return self._generate_fallback_summary(session_data, transcriptions, speakers)
            
            # Generate different types of analysis
            summary_components = {}
            
            # Executive Summary
            summary_components['executive_summary'] = await self._generate_executive_summary(
                full_transcript, session_data, summary_style
            )
            
            # Action Items
            summary_components['action_items'] = await self._extract_action_items(full_transcript)
            
            # Key Decisions
            summary_components['key_decisions'] = await self._extract_key_decisions(full_transcript)
            
            # Discussion Topics
            summary_components['topics'] = await self._identify_topics(full_transcript)
            
            # Sentiment Analysis
            summary_components['sentiment'] = await self._analyze_sentiment(full_transcript)
            
            # Speaker Insights
            summary_components['speaker_insights'] = await self._analyze_speaker_contributions(
                transcriptions, speakers
            )
            
            # Meeting Quality Metrics
            summary_components['quality_metrics'] = self._calculate_quality_metrics(
                session_data, transcriptions, speakers
            )
            
            # Next Steps
            summary_components['next_steps'] = await self._suggest_next_steps(
                summary_components['action_items'], 
                summary_components['key_decisions']
            )
            
            return summary_components
            
        except Exception as e:
            logger.error(f"Error generating comprehensive summary: {e}")
            return self._generate_fallback_summary(session_data, transcriptions, speakers)
    
    def _prepare_transcript(self, transcriptions: List[Dict[str, Any]], speakers: List[Dict[str, Any]]) -> str:
        """Prepare transcript text with clear speaker labels for LLM understanding"""
        # Create speaker map with names if available
        speaker_map = {}
        for i, speaker in enumerate(speakers):
            speaker_id = speaker.get('speaker_id')
            speaker_name = speaker.get('name', f"Speaker {i+1}")
            speaker_role = speaker.get('role', '')
            
            if speaker_role:
                speaker_label = f"{speaker_name} ({speaker_role})"
            else:
                speaker_label = speaker_name
            
            speaker_map[speaker_id] = speaker_label
        
        # Format transcript with clear speaker changes
        formatted_transcript = []
        current_speaker = None
        current_segment = []
        
        for transcript in transcriptions:
            speaker_id = transcript.get('speaker_id')
            text = transcript.get('text', '').strip()
            timestamp = transcript.get('timestamp', '')
            
            if not text:
                continue
            
            # When speaker changes, add the previous segment
            if speaker_id != current_speaker and current_segment:
                speaker_label = speaker_map.get(current_speaker, "Unknown Speaker")
                segment_text = " ".join(current_segment)
                formatted_transcript.append(f"\n[{speaker_label}]: {segment_text}")
                current_segment = []
            
            current_speaker = speaker_id
            current_segment.append(text)
        
        # Don't forget the last segment
        if current_segment and current_speaker:
            speaker_label = speaker_map.get(current_speaker, "Unknown Speaker")
            segment_text = " ".join(current_segment)
            formatted_transcript.append(f"\n[{speaker_label}]: {segment_text}")
        
        # Add speaker summary at the beginning for context
        speaker_intro = "\nMeeting Participants:\n"
        for speaker_id, speaker_label in speaker_map.items():
            speaker_intro += f"- {speaker_label}\n"
        
        return speaker_intro + "\nTranscript:\n" + "".join(formatted_transcript)
    
    async def _generate_executive_summary(
        self, 
        transcript: str, 
        session_data: Dict[str, Any],
        style: str
    ) -> str:
        """Generate executive summary using LLM"""
        
        meeting_type = session_data.get('meeting_type', 'meeting')
        duration = session_data.get('duration_seconds', 0)
        
        prompt = f"""
        You are an expert meeting analyst. Please provide a {style} summary of this {meeting_type} 
        that lasted {duration//60} minutes.
        
        Meeting Context:
        - Type: {meeting_type}
        - Duration: {duration//60} minutes
        - Participants: {len(session_data.get('speakers', []))} people
        
        Transcript:
        {transcript[:8000]}  # Limit for API
        
        Please provide:
        1. A 2-3 sentence overview of the meeting's purpose and outcomes
        2. The most important discussion points (3-5 bullets)
        3. Any critical decisions made
        4. Overall tone and engagement level
        
        Keep the summary concise but comprehensive, suitable for executives who weren't present.
        """
        
        try:
            if self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.3
                )
                return response.choices[0].message.content.strip()
            
            
            
            elif self.llama_cpp_service:
                return await self.llama_cpp_service.summarize_transcript(full_transcript, session_data)
            elif self.ollama_url:
                return await self._call_ollama(prompt, max_tokens=500)
            
        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
        
        return self._generate_basic_summary(transcript, session_data)
    
    async def _extract_action_items(self, transcript: str) -> List[Dict[str, Any]]:
        """Extract action items from transcript"""
        prompt = f"""
        Extract all action items from this meeting transcript. Focus on:
        - Tasks assigned to specific people
        - Follow-up items mentioned
        - Deadlines or timeframes
        - Commitments made
        
        Transcript:
        {transcript[:6000]}
        
        Return as a JSON list where each item has:
        - "task": description of the action
        - "assignee": who is responsible (if mentioned)
        - "deadline": when it's due (if mentioned)
        - "priority": high/medium/low based on context
        
        Return only valid JSON, no other text.
        """
        
        try:
            if self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=600,
                    temperature=0.1
                )
                result = response.choices[0].message.content.strip()
                return json.loads(result)
            
            elif self.ollama_url:
                result = await self._call_ollama(prompt, max_tokens=600, temperature=0.1)
                return json.loads(result)
            
        except Exception as e:
            logger.error(f"Error extracting action items: {e}")
        
        return self._extract_basic_action_items(transcript)
    
    async def _extract_key_decisions(self, transcript: str) -> List[Dict[str, Any]]:
        """Extract key decisions from transcript"""
        prompt = f"""
        Identify key decisions made during this meeting. Look for:
        - Explicit decisions ("we decided to...", "the decision is...")
        - Consensus reached on topics
        - Approvals given
        - Plans adopted
        
        Transcript:
        {transcript[:6000]}
        
        Return as a JSON list where each decision has:
        - "decision": what was decided
        - "rationale": why (if mentioned)
        - "impact": who/what is affected
        - "confidence": how certain the decision seems (high/medium/low)
        
        Return only valid JSON, no other text.
        """
        
        try:
            if self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.1
                )
                result = response.choices[0].message.content.strip()
                return json.loads(result)
            
            elif self.ollama_url:
                result = await self._call_ollama(prompt, max_tokens=500, temperature=0.1)
                return json.loads(result)
                
        except Exception as e:
            logger.error(f"Error extracting key decisions: {e}")
        
        return []
    
    async def _identify_topics(self, transcript: str) -> List[Dict[str, Any]]:
        """Identify main discussion topics"""
        prompt = f"""
        Identify the main topics discussed in this meeting. For each topic:
        - Topic name
        - Time spent (approximate percentage)
        - Key points discussed
        - Resolution status (resolved/unresolved/deferred)
        
        Transcript:
        {transcript[:6000]}
        
        Return as a JSON list with "topic", "time_percent", "key_points", "status" fields.
        Return only valid JSON, no other text.
        """
        
        try:
            if self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                    temperature=0.2
                )
                result = response.choices[0].message.content.strip()
                return json.loads(result)
            
            elif self.ollama_url:
                result = await self._call_ollama(prompt, max_tokens=400, temperature=0.2)
                return json.loads(result)
                
        except Exception as e:
            logger.error(f"Error identifying topics: {e}")
        
        return []
    
    async def _analyze_sentiment(self, transcript: str) -> Dict[str, Any]:
        """Analyze overall meeting sentiment"""
        prompt = f"""
        Analyze the sentiment and tone of this meeting. Consider:
        - Overall emotional tone (positive/neutral/negative)
        - Energy level (high/medium/low)
        - Collaboration quality (excellent/good/poor)
        - Conflict level (none/minor/significant)
        - Engagement level (high/medium/low)
        
        Transcript:
        {transcript[:4000]}
        
        Return as JSON with "overall_tone", "energy_level", "collaboration", "conflict_level", "engagement" fields and a "summary" explanation.
        Return only valid JSON, no other text.
        """
        
        try:
            if self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.1
                )
                result = response.choices[0].message.content.strip()
                return json.loads(result)
            
            elif self.ollama_url:
                result = await self._call_ollama(prompt, max_tokens=300, temperature=0.1)
                return json.loads(result)
                
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
        
        return {
            "overall_tone": "neutral",
            "energy_level": "medium", 
            "collaboration": "good",
            "conflict_level": "none",
            "engagement": "medium",
            "summary": "Unable to analyze sentiment automatically."
        }
    
    async def _analyze_speaker_contributions(
        self, 
        transcriptions: List[Dict[str, Any]], 
        speakers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze individual speaker contributions and styles"""
        speaker_insights = []
        
        for speaker in speakers:
            speaker_id = speaker.get('speaker_id')
            speaker_transcripts = [t for t in transcriptions if t.get('speaker_id') == speaker_id]
            
            if not speaker_transcripts:
                continue
            
            # Calculate basic metrics
            total_words = sum(len(t.get('text', '').split()) for t in speaker_transcripts)
            avg_confidence = sum(t.get('confidence', 0) for t in speaker_transcripts) / len(speaker_transcripts)
            
            insight = {
                'speaker_id': speaker_id,
                'total_contributions': len(speaker_transcripts),
                'total_words': total_words,
                'avg_confidence': avg_confidence,
                'speaking_style': self._analyze_speaking_style(speaker_transcripts),
                'key_contributions': self._identify_key_contributions(speaker_transcripts)
            }
            
            speaker_insights.append(insight)
        
        return speaker_insights
    
    def _analyze_speaking_style(self, transcripts: List[Dict[str, Any]]) -> str:
        """Analyze speaking style based on transcript patterns"""
        if not transcripts:
            return "minimal participation"
        
        texts = [t.get('text', '') for t in transcripts]
        total_text = ' '.join(texts)
        
        # Simple heuristics for speaking style
        avg_length = len(total_text.split()) / len(transcripts)
        question_count = sum(text.count('?') for text in texts)
        
        if avg_length > 20:
            if question_count > len(transcripts) * 0.3:
                return "detailed questioner"
            else:
                return "detailed contributor"
        elif question_count > len(transcripts) * 0.5:
            return "frequent questioner"
        elif avg_length < 5:
            return "brief responses"
        else:
            return "balanced contributor"
    
    def _identify_key_contributions(self, transcripts: List[Dict[str, Any]]) -> List[str]:
        """Identify key contributions from a speaker"""
        # Simple extraction of longer statements (likely more important)
        key_contributions = []
        
        for transcript in transcripts:
            text = transcript.get('text', '')
            if len(text.split()) > 15:  # Longer statements
                # Truncate for brevity
                summary = text[:100] + "..." if len(text) > 100 else text
                key_contributions.append(summary)
        
        return key_contributions[:3]  # Top 3 contributions
    
    async def _suggest_next_steps(
        self, 
        action_items: List[Dict[str, Any]], 
        decisions: List[Dict[str, Any]]
    ) -> List[str]:
        """Suggest logical next steps based on action items and decisions"""
        suggestions = []
        
        # Priority action items
        high_priority_actions = [item for item in action_items if item.get('priority') == 'high']
        if high_priority_actions:
            suggestions.append("Address high-priority action items immediately")
        
        # Follow-up on decisions
        if decisions:
            suggestions.append("Communicate key decisions to stakeholders")
            suggestions.append("Document decision rationale for future reference")
        
        # General suggestions
        if action_items:
            suggestions.append("Schedule follow-up meeting to review action item progress")
        
        suggestions.append("Share meeting summary with all participants")
        
        return suggestions
    
    async def _call_ollama(
        self, 
        prompt: str, 
        max_tokens: int = 500, 
        temperature: float = 0.3
    ) -> str:
        """Call Ollama API for text generation"""
        try:
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": 0.9,
                    "stop": ["\n\n\n", "Human:", "Assistant:"],
                    "num_gpu": 999,  # Use all available GPU layers
                    "num_thread": 8,
                    "num_ctx": 2048  # Context window
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '').strip()
                else:
                    logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                    raise Exception(f"Ollama API returned status {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise
    
    def _calculate_quality_metrics(
        self, 
        session_data: Dict[str, Any], 
        transcriptions: List[Dict[str, Any]], 
        speakers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate meeting quality metrics"""
        duration = session_data.get('duration_seconds', 0)
        total_transcriptions = len(transcriptions)
        
        # Calculate participation balance
        speaker_counts = {}
        for transcript in transcriptions:
            speaker_id = transcript.get('speaker_id')
            speaker_counts[speaker_id] = speaker_counts.get(speaker_id, 0) + 1
        
        participation_balance = 1.0
        if len(speaker_counts) > 1:
            contributions = list(speaker_counts.values())
            avg_contribution = sum(contributions) / len(contributions)
            variance = sum((c - avg_contribution) ** 2 for c in contributions) / len(contributions)
            participation_balance = max(0, 1 - (variance / (avg_contribution ** 2)))
        
        return {
            'duration_minutes': duration // 60,
            'transcription_density': total_transcriptions / max(1, duration // 60),
            'speaker_participation_balance': round(participation_balance, 2),
            'total_speakers': len(speakers),
            'avg_confidence': round(sum(t.get('confidence', 0) for t in transcriptions) / max(1, len(transcriptions)), 2),
            'npu_accelerated': session_data.get('npu_accelerated', False)
        }
    
    def _generate_basic_summary(self, transcript: str, session_data: Dict[str, Any]) -> str:
        """Generate basic summary when LLM is not available"""
        duration = session_data.get('duration_seconds', 0)
        speaker_count = len(session_data.get('speakers', []))
        
        return f"""
        Meeting Summary (Auto-generated)
        
        This {session_data.get('meeting_type', 'meeting')} lasted {duration//60} minutes with {speaker_count} participants.
        
        The meeting covered various discussion points and involved active participation from attendees.
        A detailed transcript is available for review.
        
        Note: Advanced AI summarization requires API key configuration.
        """
    
    def _extract_basic_action_items(self, transcript: str) -> List[Dict[str, Any]]:
        """Extract basic action items using keyword matching"""
        action_keywords = ['todo', 'action', 'follow up', 'will do', 'need to', 'should', 'must']
        
        action_items = []
        sentences = transcript.split('.')
        
        for sentence in sentences:
            sentence = sentence.strip().lower()
            if any(keyword in sentence for keyword in action_keywords):
                action_items.append({
                    'task': sentence[:100] + '...' if len(sentence) > 100 else sentence,
                    'assignee': 'Unknown',
                    'deadline': 'Not specified',
                    'priority': 'medium'
                })
        
        return action_items[:5]  # Limit to 5 items
    
    def _generate_fallback_summary(
        self, 
        session_data: Dict[str, Any], 
        transcriptions: List[Dict[str, Any]], 
        speakers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate fallback summary when LLM processing fails"""
        return {
            'executive_summary': self._generate_basic_summary('', session_data),
            'action_items': [],
            'key_decisions': [],
            'topics': [],
            'sentiment': {
                'overall_tone': 'neutral',
                'energy_level': 'medium',
                'collaboration': 'good',
                'conflict_level': 'none',
                'engagement': 'medium',
                'summary': 'Automatic sentiment analysis not available.'
            },
            'speaker_insights': self._analyze_speaker_contributions(transcriptions, speakers),
            'quality_metrics': self._calculate_quality_metrics(session_data, transcriptions, speakers),
            'next_steps': ['Share meeting summary with participants', 'Schedule follow-up if needed']
        }

    def get_available_providers(self) -> List[str]:
        """Get list of available LLM providers"""
        providers = []
        if self.openai_client:
            providers.append('openai')
        if self.anthropic_client:
            providers.append('anthropic')
        if self.llama_cpp_service:
            providers.append('llama_cpp')
        if self.ollama_url:
            providers.append('ollama')
        return providers
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all LLM providers"""
        return {
            'openai_available': bool(self.openai_client),
            'anthropic_available': bool(self.anthropic_client),
            'llama_cpp_available': bool(self.llama_cpp_service),
            'ollama_available': bool(self.ollama_url),
            'ollama_url': self.ollama_url,
            'ollama_model': self.ollama_model,
            'available_providers': self.get_available_providers()
        }

# Global instance
llm_summarization_service = LLMSummarizationService()