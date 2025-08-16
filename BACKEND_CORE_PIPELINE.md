# Backend Developer - Core Recording Pipeline Fix
**Priority:** IMMEDIATE - Get basic functionality working before analytics

---

## 🎯 Mission: Fix Core Recording Pipeline

Based on your earlier reports, the core recording pipeline has some remaining issues that need fixing before we build advanced features.

### Current Status Issues to Fix:
1. **Transcription Segments** - Not saving to DB (column name mismatch)
2. **UnifiedAgentService.analyze_meeting** - Method implementation may need refinement
3. **Live Transcription** - WebSocket parameter mismatch in start_monitoring
4. **Audio File Paths** - Potential duplication issues

---

## 📋 Priority Tasks (3-4 hours)

### Task 1: Fix Transcription Segments Storage (1 hour)
**Issue:** Transcription segments not saving to database

```python
# Check /backend/services/real_whisper_service.py
# Ensure transcription segments are saved with correct column names:

# Problem: Using 'timestamp' instead of 'created_at'
# Fix: Update save_transcription_segment method

async def save_transcription_segment(self, session_id: str, segment: dict):
    """Save individual transcription segment to database"""
    try:
        transcription = Transcription(
            session_id=session_id,
            text=segment['text'],
            speaker=segment.get('speaker', 'Unknown'),
            speaker_id=segment.get('speaker_id'),
            start_time=segment['start'],
            end_time=segment['end'],
            confidence=segment.get('confidence', 1.0),
            created_at=datetime.utcnow()  # Use created_at, not timestamp
        )
        
        async with AsyncSession(engine) as session:
            session.add(transcription)
            await session.commit()
            
    except Exception as e:
        logger.error(f"Failed to save transcription segment: {e}")
```

### Task 2: Complete UnifiedAgentService Integration (1 hour)
**Issue:** Make sure analyze_meeting method properly integrates with recording pipeline

```python
# In /backend/services/unified_agent_service.py
# Ensure this method is called after transcription completes

async def analyze_meeting(self, session_id: str, transcript: str) -> dict:
    """Analyze completed meeting transcript"""
    try:
        # Get current agent configuration
        agent = self.get_current_agent()
        
        # Build analysis prompt
        prompt = f"""
{agent.system_prompt}

Please analyze this meeting transcript and provide:
1. Executive Summary (2-3 sentences)
2. Key Discussion Points (3-5 bullet points)
3. Action Items (with owners if mentioned)
4. Important Decisions Made
5. Suggested Meeting Title

TRANSCRIPT:
{transcript}

Format as structured JSON.
"""
        
        # Call Ollama
        response = await self._call_ollama(
            prompt=prompt,
            model=agent.model_name,
            options={
                "num_gpu": 0,  # Force CPU mode for stability
                "temperature": 0.7,
                "num_ctx": 4096
            }
        )
        
        # Parse and structure response
        analysis = self._parse_analysis_response(response)
        
        # Save to database
        await self._save_analysis_to_session(session_id, analysis)
        
        return {
            "success": True,
            "analysis": analysis,
            "agent_id": str(agent.id)
        }
        
    except Exception as e:
        logger.error(f"Meeting analysis failed for session {session_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback_summary": "Meeting analysis unavailable"
        }

async def _save_analysis_to_session(self, session_id: str, analysis: dict):
    """Save analysis results to recording session"""
    try:
        async with AsyncSession(engine) as session:
            # Update session with summary and title
            stmt = select(RecordingSession).where(RecordingSession.session_id == session_id)
            result = await session.execute(stmt)
            recording_session = result.scalar_one_or_none()
            
            if recording_session:
                recording_session.summary = analysis.get('executive_summary', '')
                recording_session.title = analysis.get('suggested_title', 'Meeting Session')
                recording_session.updated_at = datetime.utcnow()
                
                await session.commit()
                logger.info(f"Saved analysis for session {session_id}")
                
    except Exception as e:
        logger.error(f"Failed to save analysis to session: {e}")
```

### Task 3: Fix Live Transcription Parameters (30 minutes)
**Issue:** WebSocket parameter mismatch

```python
# In /backend/api/simple_recording_db.py
# Fix the start_monitoring call (remove extra parameter)

# Current (broken):
# asyncio.create_task(live_recording_transcription.start_monitoring(
#     session_id=session_id,
#     audio_file_path=file_path  # Remove this
# ))

# Fixed:
asyncio.create_task(live_recording_transcription.start_monitoring(
    session_id=session_id
))
```

### Task 4: Complete Pipeline Integration (1 hour)
**Goal:** Ensure recording → transcription → analysis → storage works end-to-end

```python
# In /backend/api/simple_recording_db.py
# Enhance the stop_recording endpoint to trigger full pipeline

@router.post("/recording-sessions/{session_id}/stop")
async def stop_recording(session_id: str):
    """Stop recording and trigger complete processing pipeline"""
    try:
        # 1. Stop audio recording
        success = working_audio_service.stop_recording(session_id)
        if not success:
            raise HTTPException(400, "Failed to stop recording")
        
        # 2. Update session status to processing
        await update_session_status(session_id, "processing")
        
        # 3. Get audio file path
        audio_file_path = get_session_audio_path(session_id)
        
        # 4. Trigger full transcription (not live chunks)
        transcript_result = await real_whisper_service.transcribe_full_session(
            audio_file_path, session_id
        )
        
        # 5. Trigger AI analysis
        if transcript_result and transcript_result.get('text'):
            analysis_result = await unified_agent_service.analyze_meeting(
                session_id, transcript_result['text']
            )
        
        # 6. Update session to completed
        await update_session_status(session_id, "completed")
        
        return {
            "success": True,
            "session_id": session_id,
            "status": "completed",
            "transcript_available": bool(transcript_result),
            "analysis_available": bool(analysis_result.get('success'))
        }
        
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        await update_session_status(session_id, "error")
        raise HTTPException(500, f"Recording stop failed: {str(e)}")
```

### Task 5: Test Complete Pipeline (30 minutes)
**Verify the entire flow works:**

```bash
# Test the complete pipeline:

# 1. Create session
SESSION_ID=$(curl -s -X POST http://localhost:9050/api/simple/recording-sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "Pipeline Test"}' | jq -r .session_id)

# 2. Start recording  
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION_ID/start

# 3. Wait 30 seconds (record something)
sleep 30

# 4. Stop recording
curl -X POST http://localhost:9050/api/simple/recording-sessions/$SESSION_ID/stop

# 5. Wait for processing
sleep 10

# 6. Check results
curl http://localhost:9050/api/simple/recording-sessions/$SESSION_ID

# Expected: Session should have:
# - status: "completed"
# - transcript: [array of segments]  
# - summary: "Executive summary..."
# - title: "Generated meeting title"
```

---

## ✅ Success Criteria

The core pipeline is working when:
- [ ] Recording creates database session
- [ ] Audio file saves to correct path (no duplication)
- [ ] Transcription segments save to database
- [ ] Full transcript is available in session
- [ ] AI analysis generates summary and title
- [ ] Session status progresses: active → recording → processing → completed
- [ ] Session can be retrieved with all work products
- [ ] No 500 errors in logs during pipeline
- [ ] WebSocket connections work without parameter errors

---

## 🐛 Debugging Checklist

If pipeline fails, check:

```bash
# 1. Database connectivity
curl http://localhost:9050/health

# 2. Audio recording
ls -la recordings/  # Check if files are created

# 3. Ollama connectivity  
curl http://localhost:11434/api/tags

# 4. Transcription service
# Check logs for whisper errors

# 5. Database tables
# Verify transcriptions table has data
```

---

## 📝 Update COORDINATION.md

When you complete each task:
1. Mark task as COMPLETED
2. Update your status  
3. Note any issues for frontend dev
4. Indicate when ready for testing

**Focus:** Get the basic recording → transcription → summarization working perfectly before building advanced features.

**Analytics:** Moved to future roadmap. We'll build that after core pipeline is solid.