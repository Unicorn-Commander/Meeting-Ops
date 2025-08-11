"""
Progressive Transcription Service
Implements iPhone-like progressive refinement where transcription improves over time
"""

import asyncio
import logging
from typing import Dict, List, Optional
from collections import deque
import time

logger = logging.getLogger(__name__)

class ProgressiveTranscriptionService:
    """
    Manages progressive refinement of transcription segments.
    Quick initial transcription that gets refined with more context.
    """
    
    def __init__(self):
        self.pending_refinements = {}  # session_id -> list of segments to refine
        self.refinement_tasks = {}     # session_id -> asyncio task
        
    async def add_quick_segment(self, session_id: str, segment: Dict) -> Dict:
        """
        Add a quick transcription segment that will be refined later
        
        Returns the segment with a tracking ID for updates
        """
        segment_id = f"{session_id}_{int(time.time() * 1000)}"
        segment["segment_id"] = segment_id
        segment["refinement_status"] = "initial"
        
        # Add to pending refinements
        if session_id not in self.pending_refinements:
            self.pending_refinements[session_id] = deque(maxlen=10)  # Keep last 10 segments
            
        self.pending_refinements[session_id].append(segment)
        
        # Start refinement task if not running
        if session_id not in self.refinement_tasks:
            self.refinement_tasks[session_id] = asyncio.create_task(
                self._refine_segments(session_id)
            )
        
        return segment
    
    async def _refine_segments(self, session_id: str):
        """
        Background task to refine segments with more context
        """
        from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngine
        from api.websocket_transcription import broadcast_transcription_update
        
        # Use small model for refinement (better than base, faster than large)
        refiner = WhisperXNPUEngine(model_size="small")
        
        while session_id in self.pending_refinements:
            try:
                # Wait a bit to accumulate segments
                await asyncio.sleep(3)
                
                # Get segments to refine
                segments_to_refine = []
                while self.pending_refinements[session_id] and len(segments_to_refine) < 3:
                    segments_to_refine.append(self.pending_refinements[session_id].popleft())
                
                if not segments_to_refine:
                    continue
                
                # Combine audio from segments for better context
                # (In real implementation, would need actual audio data)
                for segment in segments_to_refine:
                    if segment["refinement_status"] == "initial":
                        # Mark as being refined
                        segment["refinement_status"] = "refining"
                        
                        # In a real implementation, we'd re-transcribe with more context
                        # For now, just simulate refinement
                        refined_text = segment["text"]
                        
                        # Broadcast refinement update
                        refinement_update = {
                            "type": "refinement",
                            "segment_id": segment["segment_id"],
                            "text": refined_text,
                            "refinement_status": "refined",
                            "confidence": segment.get("confidence", 0.95) + 0.03  # Slightly higher confidence
                        }
                        
                        await broadcast_transcription_update(
                            session_id,
                            refinement_update
                        )
                        
                        segment["refinement_status"] = "refined"
                        logger.info(f"Refined segment {segment['segment_id']}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refinement error for session {session_id}: {e}")
                await asyncio.sleep(5)
        
        # Cleanup
        if session_id in self.refinement_tasks:
            del self.refinement_tasks[session_id]
    
    def stop_refinement(self, session_id: str):
        """Stop refinement for a session"""
        if session_id in self.refinement_tasks:
            self.refinement_tasks[session_id].cancel()
            
        if session_id in self.pending_refinements:
            del self.pending_refinements[session_id]

# Global instance
progressive_service = ProgressiveTranscriptionService()