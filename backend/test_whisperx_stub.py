from stt_engine.whisperx_npu_engine import WhisperXNPUEngine
import numpy as np

engine = WhisperXNPUEngine()

# Test chunk transcription
audio_chunk = np.random.randn(16000)  # 1 second of audio
result = engine.transcribe_chunk(audio_chunk)
print("Chunk result:", result)

# Test file transcription
result = engine.transcribe_file("test_audio.wav")
print("File result:", result)
