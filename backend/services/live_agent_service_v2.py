"""
Live Agent Service V2
Decoupled from model configuration, supports multiple providers
"""
import asyncio
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import deque
import re

try:
    from backend.models.agent_config import AgentConfiguration, AgentExecution
    from backend.models.model_config import ModelConfiguration
    from backend.models.recording_session import RecordingSession
    from backend.services.model_providers import ModelProviderFactory, ModelParameters
    from backend.database import SessionLocal
except ImportError:
    from models.agent_config import AgentConfiguration, AgentExecution
    from models.model_config import ModelConfiguration
    from models.recording_session import RecordingSession
    from services.model_providers import ModelProviderFactory, ModelParameters
    from database import SessionLocal


class SessionState:
    """Track state for an active recording session"""
    
    def __init__(self, session_id: str, agent_config: AgentConfiguration, model_config: Optional[ModelConfiguration] = None):
        self.session_id = session_id
        self.agent_config = agent_config
        self.model_config = model_config
        self.started_at = time.time()
        self.last_update_time = 0
        self.accumulated_text = []
        self.word_count = 0
        self.silence_start = None
        self.total_updates = 0
        self.last_content = ""
        
        # Initialize model provider
        self.provider = self._initialize_provider()
    
    def _initialize_provider(self):
        """Initialize the appropriate model provider"""
        if self.model_config:
            # Use dedicated model configuration
            return ModelProviderFactory.create_provider(
                provider_type=self.model_config.provider,
                host=self.model_config.api_endpoint,
                model_name=self.model_config.model_name,
                api_key=self.model_config.api_key
            )
        elif self.agent_config.fallback_provider:
            # Use fallback configuration
            return ModelProviderFactory.create_provider(
                provider_type=self.agent_config.fallback_provider,
                model_name=self.agent_config.fallback_model_name
            )
        else:
            # Default to Ollama with Granite
            return ModelProviderFactory.create_provider(
                provider_type="ollama",
                model_name="granite3.3:8b"
            )
    
    def add_text(self, text: str):
        """Add new transcript text"""
        if text.strip():
            self.accumulated_text.append(text)
            self.word_count += len(text.split())
            self.silence_start = None
        else:
            if self.silence_start is None:
                self.silence_start = time.time()
    
    def get_accumulated_text(self) -> str:
        """Get all accumulated text"""
        return " ".join(self.accumulated_text)
    
    def clear_accumulated_text(self):
        """Clear accumulated text after update"""
        self.accumulated_text = []
        self.word_count = 0


class LiveAgentManager:
    """Manages live agent execution with decoupled model configuration"""
    
    def __init__(self):
        self.active_sessions: Dict[str, SessionState] = {}
        self.update_lock = asyncio.Lock()
    
    async def start_session(
        self,
        session_id: str,
        agent_config_id: str,
        model_config_id: Optional[str] = None
    ):
        """Initialize tracking for a new session"""
        db = SessionLocal()
        try:
            # Load agent configuration
            agent_config = db.query(AgentConfiguration).filter_by(id=agent_config_id).first()
            if not agent_config:
                raise ValueError(f"Agent configuration {agent_config_id} not found")
            
            # Load model configuration if specified
            model_config = None
            if model_config_id:
                model_config = db.query(ModelConfiguration).filter_by(id=model_config_id).first()
            elif agent_config.model_config_id:
                model_config = db.query(ModelConfiguration).filter_by(id=agent_config.model_config_id).first()
            
            # Create session state
            self.active_sessions[session_id] = SessionState(
                session_id=session_id,
                agent_config=agent_config,
                model_config=model_config
            )
            
            # Health check the provider
            provider = self.active_sessions[session_id].provider
            if not await provider.health_check():
                raise Exception(f"Provider {provider.__class__.__name__} health check failed")
                
        finally:
            db.close()
    
    def stop_session(self, session_id: str):
        """Stop tracking a session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
    
    async def process_transcript_chunk(
        self,
        session_id: str,
        text: str,
        force_update: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Process new transcript chunk and determine if update needed"""
        
        if session_id not in self.active_sessions:
            return None
        
        state = self.active_sessions[session_id]
        state.add_text(text)
        
        # Check if update should trigger
        should_update, reason = self._should_trigger_update(state, force_update)
        
        if should_update:
            async with self.update_lock:
                return await self._execute_update(state, reason)
        
        return None
    
    def _should_trigger_update(self, state: SessionState, force: bool) -> tuple[bool, str]:
        """Determine if an update should be triggered"""
        
        if force:
            return True, "Manual trigger"
        
        current_time = time.time()
        time_since_update = current_time - state.last_update_time
        
        # Use agent-specific update intervals
        min_interval = state.agent_config.update_interval_min
        max_interval = state.agent_config.update_interval_max
        min_words = state.agent_config.min_words_trigger
        silence_trigger = state.agent_config.silence_trigger_seconds
        
        # Check time-based triggers
        if time_since_update > max_interval:
            return True, f"Maximum interval reached ({max_interval}s)"
        
        if time_since_update < min_interval:
            return False, "Too soon since last update"
        
        # Check content-based triggers
        if state.word_count >= min_words:
            return True, f"Word count threshold reached ({state.word_count} words)"
        
        # Check silence trigger
        if state.silence_start and (current_time - state.silence_start) > silence_trigger:
            return True, f"Silence detected ({silence_trigger}s)"
        
        # Check priority keywords
        if state.agent_config.priority_keywords:
            text_lower = state.get_accumulated_text().lower()
            for keyword in state.agent_config.priority_keywords:
                if keyword.lower() in text_lower:
                    return True, f"Priority keyword detected: {keyword}"
        
        return False, "No trigger conditions met"
    
    async def _execute_update(self, state: SessionState, trigger_reason: str) -> Dict[str, Any]:
        """Execute an agent update using the configured model"""
        
        start_time = time.time()
        accumulated_text = state.get_accumulated_text()
        
        if not accumulated_text.strip():
            return None
        
        try:
            # Build parameters from model config or defaults
            parameters = self._build_parameters(state)
            
            # Generate response
            response = await state.provider.generate(
                prompt=self._build_prompt(state, accumulated_text),
                system_prompt=state.agent_config.system_prompt,
                parameters=parameters
            )
            
            # Parse and structure the response
            result = self._parse_response(response.content, state.agent_config.agent_type)
            
            # Record execution
            await self._record_execution(
                state=state,
                input_text=accumulated_text,
                output=result,
                execution_time_ms=int((time.time() - start_time) * 1000),
                trigger_reason=trigger_reason,
                model_used=response.model,
                tokens_used=response.usage.get('total_tokens', 0) if response.usage else 0
            )
            
            # Update state
            state.last_update_time = time.time()
            state.total_updates += 1
            state.last_content = json.dumps(result)
            state.clear_accumulated_text()
            
            return {
                "type": "agent_update",
                "agent_type": state.agent_config.agent_type,
                "content": result,
                "metadata": {
                    "trigger_reason": trigger_reason,
                    "update_number": state.total_updates,
                    "model": response.model,
                    "provider": response.provider,
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                }
            }
            
        except Exception as e:
            print(f"Agent update failed: {str(e)}")
            return {
                "type": "agent_error",
                "error": str(e),
                "trigger_reason": trigger_reason
            }
    
    def _build_parameters(self, state: SessionState) -> ModelParameters:
        """Build model parameters from configuration"""
        
        # Start with model defaults if available
        if state.model_config:
            params = ModelParameters(
                temperature=state.model_config.temperature / 10.0,  # Convert from 0-10 to 0-1
                max_tokens=state.model_config.max_tokens,
                top_p=state.model_config.top_p / 10.0,
                frequency_penalty=state.model_config.frequency_penalty / 10.0,
                presence_penalty=state.model_config.presence_penalty / 10.0
            )
            
            # Add provider-specific parameters
            if state.model_config.provider == "ollama":
                params.provider_params = {
                    "num_ctx": state.model_config.context_window,
                    "num_gpu": state.model_config.gpu_layers,
                    "repeat_penalty": state.model_config.repeat_penalty / 10.0 if state.model_config.repeat_penalty else 1.1,
                    "seed": state.model_config.seed
                }
        else:
            # Use defaults
            params = ModelParameters()
        
        # Apply agent-specific overrides
        if state.agent_config.parameter_overrides:
            overrides = state.agent_config.parameter_overrides
            if "temperature" in overrides:
                params.temperature = overrides["temperature"]
            if "max_tokens" in overrides:
                params.max_tokens = overrides["max_tokens"]
            if "top_p" in overrides:
                params.top_p = overrides["top_p"]
        
        return params
    
    def _build_prompt(self, state: SessionState, text: str) -> str:
        """Build the prompt for the model"""
        
        if state.agent_config.agent_type == "live_enhancement":
            return f"""
            Analyze this meeting transcript segment and provide structured insights.
            
            TRANSCRIPT:
            {text}
            
            Generate:
            1. Key Points (2-3 bullet points)
            2. Decisions or important statements
            3. Action items if any
            4. Questions raised
            
            Be concise and focus on substance, not filler words.
            Format as JSON.
            """
        
        elif state.agent_config.agent_type == "final_analysis":
            return f"""
            Provide a comprehensive analysis of this meeting segment.
            
            TRANSCRIPT:
            {text}
            
            Generate:
            1. Detailed summary
            2. All action items with owners
            3. Key decisions made
            4. Topics discussed
            5. Next steps
            6. Sentiment analysis
            
            Format as JSON with these exact keys.
            """
        
        else:
            # Use custom instructions if available
            if state.agent_config.custom_instructions:
                return state.agent_config.custom_instructions.replace("{text}", text)
            else:
                return f"Analyze this text: {text}"
    
    def _parse_response(self, response: str, agent_type: str) -> Dict[str, Any]:
        """Parse the model response into structured format"""
        
        try:
            # Try to parse as JSON first
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback to text parsing
            if agent_type == "live_enhancement":
                return {
                    "key_points": [response[:200]],
                    "decisions": [],
                    "action_items": [],
                    "questions": [],
                    "raw_response": response
                }
            else:
                return {
                    "summary": response,
                    "action_items": [],
                    "decisions": [],
                    "topics": [],
                    "next_steps": [],
                    "sentiment": "neutral",
                    "raw_response": response
                }
    
    async def _record_execution(
        self,
        state: SessionState,
        input_text: str,
        output: Dict[str, Any],
        execution_time_ms: int,
        trigger_reason: str,
        model_used: str,
        tokens_used: int
    ):
        """Record the agent execution in the database"""
        
        db = SessionLocal()
        try:
            execution = AgentExecution(
                agent_id=state.agent_config.id,
                session_id=state.session_id,
                execution_type="triggered",
                trigger_reason=trigger_reason,
                input_text=input_text,
                input_word_count=len(input_text.split()),
                output_content=output,
                execution_time_ms=execution_time_ms,
                tokens_used=tokens_used,
                model_used=model_used,
                status="success",
                completed_at=datetime.utcnow()
            )
            db.add(execution)
            db.commit()
        except Exception as e:
            print(f"Failed to record execution: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    async def get_session_updates(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all updates for a session from the database"""
        
        db = SessionLocal()
        try:
            executions = db.query(AgentExecution).filter_by(
                session_id=session_id
            ).order_by(AgentExecution.started_at).all()
            
            return [
                {
                    "id": exec.id,
                    "agent_type": exec.agent.agent_type if exec.agent else "unknown",
                    "content": exec.output_content,
                    "trigger_reason": exec.trigger_reason,
                    "model_used": exec.model_used,
                    "execution_time_ms": exec.execution_time_ms,
                    "timestamp": exec.started_at.isoformat()
                }
                for exec in executions
            ]
        finally:
            db.close()


# Global manager instance
live_agent_manager = LiveAgentManager()