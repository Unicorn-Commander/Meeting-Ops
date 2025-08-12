"""
Live Agent Service
Manages smart update intervals and live content generation
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
    from backend.models.recording_session import RecordingSession
    from backend.database import SessionLocal
except ImportError:
    from models.agent_config import AgentConfiguration, AgentExecution
    from models.recording_session import RecordingSession
    from database import SessionLocal


class LiveAgentManager:
    """Manages live agent execution with smart update intervals and dual-model pipeline"""
    
    def __init__(self):
        self.active_sessions: Dict[str, SessionState] = {}
        self.update_lock = asyncio.Lock()
        
    def start_session(self, session_id: str, agent_config: AgentConfiguration, pipeline_config: dict = None):
        """Initialize tracking for a new session with optional pipeline configuration"""
        
        # Default pipeline configuration
        default_pipeline = {
            "enabled": True,
            "early_model": "phi4-mini:3.8b",  # Fast model for first phase
            "early_duration_minutes": 10,      # Use fast model for first 10 minutes
            "early_interval_seconds": 20,      # Update every 20s in early phase
            "late_model": "granite3.3:8b",     # Deeper model for later phase
            "late_interval_min": 60,           # Update every 60-120s in late phase
            "late_interval_max": 120,
            "transition_overlap_minutes": 2    # Overlap period for smooth transition
        }
        
        pipeline = pipeline_config or default_pipeline
        
        self.active_sessions[session_id] = SessionState(
            session_id=session_id,
            agent_config=agent_config,
            started_at=time.time(),
            pipeline_config=pipeline
        )
    
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
    
    def _should_trigger_update(self, state: 'SessionState', force: bool) -> tuple[bool, str]:
        """Determine if an update should be triggered based on pipeline configuration"""
        
        if force:
            return True, "Manual trigger"
        
        current_time = time.time()
        time_since_update = current_time - state.last_update_time
        meeting_duration_seconds = current_time - state.started_at
        meeting_duration_minutes = meeting_duration_seconds / 60
        
        # Get pipeline config
        pipeline = state.pipeline_config
        
        # Determine which phase we're in
        if pipeline.get("enabled", True):
            if meeting_duration_minutes < pipeline["early_duration_minutes"]:
                # Early phase - use faster intervals
                min_interval = pipeline["early_interval_seconds"]
                max_interval = pipeline["early_interval_seconds"] * 2
                min_words = 100  # Lower threshold for early phase
                model_phase = "early"
            else:
                # Late phase - use deeper, less frequent intervals
                min_interval = pipeline["late_interval_min"]
                max_interval = pipeline["late_interval_max"]
                min_words = 200  # Higher threshold for late phase
                model_phase = "late"
        else:
            # No pipeline, use agent's default settings
            min_interval = state.agent_config.update_interval_min
            max_interval = state.agent_config.update_interval_max
            min_words = state.agent_config.min_words_trigger
            model_phase = "default"
        
        # Store phase for execute_update
        state.current_phase = model_phase
        
        # Special handling for very early meeting (first 2 minutes)
        if meeting_duration_seconds < 120:
            if time_since_update >= 20 and state.pending_word_count > 30:
                return True, f"Very early meeting update (20s)"
        
        # Check word count threshold
        if state.pending_word_count >= min_words:
            return True, f"Word threshold reached ({state.pending_word_count} words) - {model_phase} phase"
        
        # Check for natural pauses
        if state.detect_pause() and state.pending_word_count > 50:
            return True, f"Natural pause detected - {model_phase} phase"
        
        # Check for priority keywords
        keywords_found = state.check_priority_keywords()
        if keywords_found and time_since_update >= 15:
            return True, f"Priority keywords ({', '.join(keywords_found)}) - {model_phase} phase"
        
        # Maximum interval check
        if time_since_update >= max_interval:
            if state.pending_word_count > 30:
                return True, f"Maximum interval ({max_interval}s) - {model_phase} phase"
        
        # Minimum interval enforcement
        if time_since_update < min_interval:
            return False, "Below minimum interval"
        
        return False, ""
    
    async def _execute_update(self, state: 'SessionState', reason: str) -> Dict[str, Any]:
        """Execute the live agent with appropriate model based on pipeline phase"""
        
        # Get all pending text
        text_to_process = state.get_pending_text()
        
        if not text_to_process:
            return None
        
        # Import here to avoid circular dependency
        from backend.api.agent_system import agent_service
        
        # Determine which model to use based on current phase
        original_model = state.agent_config.model_name
        if hasattr(state, 'current_phase') and state.pipeline_config.get("enabled", True):
            if state.current_phase == "early":
                # Override with fast model for early phase
                state.agent_config.model_name = state.pipeline_config["early_model"]
                # Also adjust temperature for faster model
                original_temp = state.agent_config.temperature
                state.agent_config.temperature = 5  # 0.5 for more focused output
            elif state.current_phase == "late":
                # Use deeper model for late phase
                state.agent_config.model_name = state.pipeline_config["late_model"]
        
        # Execute agent with appropriate model
        result = await agent_service.execute_agent(
            agent_config=state.agent_config,
            input_text=text_to_process,
            session_id=state.session_id,
            execution_type="scheduled"
        )
        
        # Restore original model name (in case config is reused)
        state.agent_config.model_name = original_model
        if hasattr(state, 'current_phase') and state.current_phase == "early":
            state.agent_config.temperature = original_temp
        
        # Update state
        state.mark_update_complete()
        
        # Add context about the update
        result["update_reason"] = reason
        result["words_processed"] = len(text_to_process.split())
        result["session_duration"] = int(time.time() - state.started_at)
        
        # Store in session state for incremental updates
        if result["success"] and "output" in result:
            state.last_output = result["output"]
            
            # Merge with previous output for continuous narrative
            if state.accumulated_output:
                result["output"] = self._merge_outputs(
                    state.accumulated_output, 
                    result["output"]
                )
            
            state.accumulated_output = result["output"]
        
        return result
    
    def _merge_outputs(self, previous: Dict, current: Dict) -> Dict:
        """Merge current output with previous, updating rather than replacing"""
        
        merged = current.copy()
        
        # Append to transcript
        if "formatted_transcript" in previous and "formatted_transcript" in current:
            merged["formatted_transcript"] = previous["formatted_transcript"] + "\n\n" + current["formatted_transcript"]
        
        # Update summary (replace with new comprehensive one)
        # Keep current summary as it should be cumulative
        
        # Merge lists (action items, decisions, key points)
        for key in ["action_items", "decisions", "key_points"]:
            if key in previous and key in current:
                # Combine and deduplicate
                prev_items = previous.get(key, [])
                curr_items = current.get(key, [])
                
                # For action items, check for updates
                if key == "action_items":
                    merged[key] = self._merge_action_items(prev_items, curr_items)
                else:
                    # Simple deduplication for other lists
                    all_items = prev_items + curr_items
                    seen = set()
                    unique = []
                    for item in all_items:
                        item_str = json.dumps(item) if isinstance(item, dict) else str(item)
                        if item_str not in seen:
                            seen.add(item_str)
                            unique.append(item)
                    merged[key] = unique
        
        return merged
    
    def _merge_action_items(self, previous: List, current: List) -> List:
        """Intelligently merge action items, updating existing ones"""
        
        merged = {}
        
        # Add previous items
        for item in previous:
            if isinstance(item, dict) and "task" in item:
                key = item["task"].lower()[:50]  # Use first 50 chars as key
                merged[key] = item
        
        # Update or add current items
        for item in current:
            if isinstance(item, dict) and "task" in item:
                key = item["task"].lower()[:50]
                if key in merged:
                    # Update existing item
                    merged[key].update(item)
                else:
                    merged[key] = item
        
        return list(merged.values())


class SessionState:
    """Tracks state for a single recording session"""
    
    def __init__(self, session_id: str, agent_config: AgentConfiguration, started_at: float, pipeline_config: dict = None):
        self.session_id = session_id
        self.agent_config = agent_config
        self.started_at = started_at
        self.last_update_time = started_at
        self.pipeline_config = pipeline_config or {}
        
        # Text management
        self.pending_text = []
        self.pending_word_count = 0
        self.processed_text = []
        
        # Pause detection
        self.recent_chunks = deque(maxlen=10)  # Last 10 chunks for pause detection
        self.last_chunk_time = started_at
        
        # Output accumulation
        self.last_output = None
        self.accumulated_output = None
        
    def add_text(self, text: str):
        """Add new text chunk"""
        if text.strip():
            self.pending_text.append(text)
            self.pending_word_count += len(text.split())
            
            # Track for pause detection
            current_time = time.time()
            self.recent_chunks.append({
                "text": text,
                "time": current_time,
                "gap": current_time - self.last_chunk_time
            })
            self.last_chunk_time = current_time
    
    def get_pending_text(self) -> str:
        """Get all pending text as a single string"""
        return " ".join(self.pending_text)
    
    def mark_update_complete(self):
        """Mark that an update was completed"""
        self.processed_text.extend(self.pending_text)
        self.pending_text = []
        self.pending_word_count = 0
        self.last_update_time = time.time()
    
    def detect_pause(self) -> bool:
        """Detect if there's a natural pause in speech"""
        if len(self.recent_chunks) < 2:
            return False
        
        # Check if recent gap is larger than threshold
        latest = self.recent_chunks[-1]
        if latest["gap"] >= self.agent_config.silence_trigger_seconds:
            return True
        
        # Check for sentence endings followed by pause
        if len(self.recent_chunks) >= 3:
            prev_text = self.recent_chunks[-2]["text"].strip()
            if prev_text and prev_text[-1] in ".!?" and latest["gap"] >= 3:
                return True
        
        return False
    
    def check_priority_keywords(self) -> List[str]:
        """Check if priority keywords are in pending text"""
        if not self.pending_text:
            return []
        
        text_lower = " ".join(self.pending_text).lower()
        found = []
        
        for keyword in self.agent_config.priority_keywords:
            if keyword.lower() in text_lower:
                found.append(keyword)
        
        return found


# Global instance
live_agent_manager = LiveAgentManager()


# WebSocket handler for live updates
async def handle_live_agent_updates(websocket, session_id: str):
    """Handle WebSocket connection for live agent updates"""
    
    db = SessionLocal()
    try:
        # Get agent configuration
        agent = db.query(AgentConfiguration).filter_by(
            agent_type="live_enhancement",
            is_default=True
        ).first()
        
        if not agent:
            await websocket.send_json({
                "type": "error",
                "message": "No live agent configured"
            })
            return
        
        # Start session tracking
        live_agent_manager.start_session(session_id, agent)
        
        # Send initial status
        await websocket.send_json({
            "type": "agent_ready",
            "agent_name": agent.name,
            "model": agent.model_name,
            "update_intervals": {
                "min": agent.update_interval_min,
                "max": agent.update_interval_max
            }
        })
        
        # Listen for transcript chunks and process
        async for message in websocket.iter_json():
            if message.get("type") == "transcript_chunk":
                text = message.get("text", "")
                force = message.get("force_update", False)
                
                # Process chunk
                result = await live_agent_manager.process_transcript_chunk(
                    session_id=session_id,
                    text=text,
                    force_update=force
                )
                
                if result:
                    # Send update to client
                    await websocket.send_json({
                        "type": "agent_update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "content": result.get("output"),
                        "update_reason": result.get("update_reason"),
                        "words_processed": result.get("words_processed"),
                        "execution_time_ms": result.get("execution_time_ms")
                    })
            
            elif message.get("type") == "stop":
                break
        
    finally:
        # Cleanup
        live_agent_manager.stop_session(session_id)
        db.close()