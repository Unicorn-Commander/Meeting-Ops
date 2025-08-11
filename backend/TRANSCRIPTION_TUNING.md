# Transcription Tuning Guide

## Current Settings (Optimized for Long Meetings)

### Chunk Processing
- **Chunk Duration**: 15 seconds
- **Chunk Overlap**: 3 seconds  
- **Update Frequency**: Every 12 seconds (15 - 3 overlap)

This means for a typical meeting:
- 5 updates per minute
- 300 updates per hour
- Good balance between responsiveness and accuracy

### VAD (Voice Activity Detection)

**What VAD Does**:
- Removes long silences from processing (saves compute)
- Helps Whisper focus on actual speech
- Reduces "hallucinations" (fake words in silence)

**Current VAD Settings** (Very Permissive):
- `min_silence_duration_ms`: 1500ms - Only removes silences > 1.5 seconds
- `speech_pad_ms`: 1000ms - Keeps 1 second before/after speech
- `threshold`: 0.25 - Very low threshold, catches soft speech

## Tuning Options

### For More Real-Time Feel
```python
# In live_recording_transcription.py
chunk_duration = 10  # Faster updates
chunk_overlap = 2   # Less overlap
# Result: Updates every 8 seconds
```

### For Better Accuracy
```python
# In live_recording_transcription.py  
chunk_duration = 30  # More context
chunk_overlap = 5   # More overlap
# Result: Updates every 25 seconds
```

### To Disable VAD Completely
```bash
# Run backend with VAD disabled
export DISABLE_VAD=true
cd /home/ucadmin/Meeting-Ops/backend
./start-backend.sh
```

### To Test Different Settings
```bash
# Test without VAD
DISABLE_VAD=true python test_better_transcription.py

# Test with aggressive VAD (not recommended)
VAD_THRESHOLD=0.5 python test_better_transcription.py
```

## Speaker Diarization (Who's Talking)

This is separate from VAD and uses:
1. **Pause patterns** - Long pauses suggest speaker change
2. **Question detection** - "?" often means next segment is different speaker
3. **Conversational markers** - "Yes,", "No,", "Well," suggest responses
4. **Voice characteristics** - From Whisper's word timestamps

Currently supports up to 4 speakers (SPEAKER_00 through SPEAKER_03).

## Recommended Settings by Use Case

### Board Meetings (Formal, Clear Speech)
- Chunk: 20 seconds
- Overlap: 3 seconds
- VAD: Enabled (default settings)

### Brainstorming Sessions (Overlapping Speech)
- Chunk: 15 seconds
- Overlap: 5 seconds
- VAD: Disabled or very permissive

### Interviews (Two Speakers, Turn-Taking)
- Chunk: 30 seconds
- Overlap: 5 seconds
- VAD: Enabled (default settings)

### Presentations (One Main Speaker)
- Chunk: 60 seconds
- Overlap: 10 seconds
- VAD: Enabled with longer silence threshold

## Performance Impact

| Setting | CPU Usage | Accuracy | Latency |
|---------|-----------|----------|---------|
| 10s chunks | ~5% | Good | 10s |
| 15s chunks | ~4% | Better | 15s |
| 30s chunks | ~3% | Best | 30s |
| VAD Enabled | -1% | Better | Same |
| VAD Disabled | +1% | Variable | Same |

## Current Production Settings

```python
# Balanced for long meetings
chunk_duration = 15  # Good context
chunk_overlap = 3   # Avoid cut-offs
use_vad = True      # Remove silence
vad_threshold = 0.25 # Catch soft speech
```

These settings provide:
- Updates every 12 seconds
- Good accuracy with context
- Catches soft speakers
- Removes long silences
- ~4% CPU usage during transcription