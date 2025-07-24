"""
Model Benchmarking Service
=========================
Comprehensive benchmarking of STT models using real audio samples.
Evaluates accuracy, performance, and quality metrics.
"""

import os
import time
import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np
import librosa
from difflib import SequenceMatcher

from services.transcription_service import transcription_service
from services.performance_metrics_service import performance_metrics_service
from services.settings_manager import settings_manager
from database.database import get_db
from database.models import Settings

logger = logging.getLogger(__name__)

@dataclass
class BenchmarkAudioSample:
    """Audio sample for benchmarking"""
    id: str
    name: str
    file_path: str
    duration: float
    sample_rate: int
    reference_text: str
    reference_speakers: List[str]
    difficulty_level: str  # easy, medium, hard
    audio_quality: str     # clean, noisy, reverb
    language: str
    description: str

@dataclass
class BenchmarkResult:
    """Result of benchmarking a model on a sample"""
    sample_id: str
    model_id: str
    model_name: str
    timestamp: datetime
    
    # Performance metrics
    processing_time: float
    rtf: float  # Real-time factor
    memory_usage_mb: Optional[float]
    
    # Transcription results
    transcribed_text: str
    confidence_avg: float
    detected_speakers: List[str]
    
    # Accuracy metrics
    word_accuracy: float      # Word Error Rate (WER) based
    character_accuracy: float # Character Error Rate (CER) based
    speaker_accuracy: float   # Speaker identification accuracy
    
    # Quality metrics
    text_similarity: float    # Semantic similarity
    timing_accuracy: float    # Word timing accuracy
    
    # Additional metrics
    words_transcribed: int
    speakers_detected_count: int
    npu_accelerated: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result

class ModelBenchmarkingService:
    """Service for comprehensive model benchmarking"""
    
    def __init__(self):
        self.benchmark_samples: List[BenchmarkAudioSample] = []
        self.benchmark_results: List[BenchmarkResult] = []
        self.benchmark_directory = Path("benchmark_samples")
        
        # Create benchmark directory if it doesn't exist
        self.benchmark_directory.mkdir(exist_ok=True)
        
        # Initialize with built-in test samples
        self._initialize_test_samples()
        
        logger.info("🎯 Model Benchmarking Service initialized")
    
    def _initialize_test_samples(self):
        """Initialize with synthetic and real test samples"""
        # Create synthetic audio samples for testing
        self._create_synthetic_samples()
        
        # Look for real audio samples in benchmark directory
        self._load_real_samples()
    
    def _create_synthetic_samples(self):
        """Create synthetic audio samples for benchmarking"""
        synthetic_samples = [
            {
                "id": "synthetic_clean_short",
                "name": "Clean Short Speech",
                "reference_text": "Hello everyone, welcome to our meeting today.",
                "reference_speakers": ["SPEAKER_01"],
                "difficulty_level": "easy",
                "audio_quality": "clean",
                "duration": 3.0,
                "description": "Short, clear speech sample"
            },
            {
                "id": "synthetic_multi_speaker",
                "name": "Multi-Speaker Conversation",
                "reference_text": "Person A says hello. Person B responds with good morning. Person A continues with how are you today.",
                "reference_speakers": ["SPEAKER_01", "SPEAKER_02"],
                "difficulty_level": "medium",
                "audio_quality": "clean",
                "duration": 8.0,
                "description": "Multi-speaker conversation"
            },
            {
                "id": "synthetic_technical_content",
                "name": "Technical Discussion",
                "reference_text": "We need to optimize the neural processing unit acceleration for the machine learning workloads. The INT8 quantization should improve performance by approximately two hundred percent.",
                "reference_speakers": ["SPEAKER_01"],
                "difficulty_level": "hard",
                "audio_quality": "clean",
                "duration": 12.0,
                "description": "Technical vocabulary and numbers"
            },
            {
                "id": "synthetic_noisy_environment",
                "name": "Noisy Environment",
                "reference_text": "Can you hear me clearly with all this background noise?",
                "reference_speakers": ["SPEAKER_01"],
                "difficulty_level": "hard",
                "audio_quality": "noisy",
                "duration": 4.0,
                "description": "Speech with background noise"
            }
        ]
        
        for sample_data in synthetic_samples:
            sample_path = self.benchmark_directory / f"{sample_data['id']}.wav"
            
            # Create synthetic audio if it doesn't exist
            if not sample_path.exists():
                self._generate_synthetic_audio(sample_data, sample_path)
            
            # Add to benchmark samples
            if sample_path.exists():
                sample = BenchmarkAudioSample(
                    id=sample_data["id"],
                    name=sample_data["name"],
                    file_path=str(sample_path),
                    duration=sample_data["duration"],
                    sample_rate=16000,
                    reference_text=sample_data["reference_text"],
                    reference_speakers=sample_data["reference_speakers"],
                    difficulty_level=sample_data["difficulty_level"],
                    audio_quality=sample_data["audio_quality"],
                    language="en",
                    description=sample_data["description"]
                )
                self.benchmark_samples.append(sample)
    
    def _generate_synthetic_audio(self, sample_data: Dict, output_path: Path):
        """Generate synthetic audio for testing"""
        try:
            import scipy.signal
            
            sample_rate = 16000
            duration = sample_data["duration"]
            
            # Generate synthetic speech-like signal
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            
            # Create speech-like signal with formants
            fundamental_freq = 120  # Male voice fundamental frequency
            
            # Generate multiple harmonics for speech-like sound
            signal = np.zeros_like(t)
            for harmonic in range(1, 8):
                freq = fundamental_freq * harmonic
                amplitude = 1.0 / harmonic  # Decreasing amplitude
                signal += amplitude * np.sin(2 * np.pi * freq * t)
            
            # Add formant-like filtering
            formant_freqs = [800, 1200, 2400]  # Typical formant frequencies
            for formant_freq in formant_freqs:
                # Simple bandpass filter effect
                modulation = 1 + 0.3 * np.sin(2 * np.pi * formant_freq * t / 10)
                signal *= modulation
            
            # Add speech-like envelope
            words = sample_data["reference_text"].split()
            word_duration = duration / len(words)
            
            for i, word in enumerate(words):
                start_idx = int(i * word_duration * sample_rate)
                end_idx = int((i + 1) * word_duration * sample_rate)
                
                if end_idx <= len(signal):
                    # Word envelope (attack, sustain, decay)
                    word_signal = signal[start_idx:end_idx]
                    envelope = np.ones_like(word_signal)
                    
                    # Attack
                    attack_samples = len(word_signal) // 10
                    envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
                    
                    # Decay
                    decay_samples = len(word_signal) // 10
                    if decay_samples > 0:
                        envelope[-decay_samples:] = np.linspace(1, 0, decay_samples)
                    
                    signal[start_idx:end_idx] *= envelope
                    
                    # Add silence between words
                    if i < len(words) - 1:
                        silence_start = end_idx
                        silence_end = min(silence_start + sample_rate // 20, len(signal))  # 50ms silence
                        signal[silence_start:silence_end] *= 0.1
            
            # Add noise based on quality
            if sample_data["audio_quality"] == "noisy":
                noise = np.random.normal(0, 0.1, len(signal))
                signal += noise
            elif sample_data["audio_quality"] == "reverb":
                # Simple reverb effect
                delay_samples = int(0.1 * sample_rate)  # 100ms delay
                reverb = np.zeros_like(signal)
                reverb[delay_samples:] = signal[:-delay_samples] * 0.3
                signal += reverb
            
            # Normalize
            signal = signal / np.max(np.abs(signal)) * 0.8
            
            # Convert to 16-bit
            signal_int16 = (signal * 32767).astype(np.int16)
            
            # Save as WAV
            import soundfile as sf
            sf.write(output_path, signal_int16, sample_rate)
            
            logger.info(f"📢 Generated synthetic audio: {output_path.name}")
            
        except ImportError as e:
            logger.warning(f"Cannot generate synthetic audio (missing dependencies): {e}")
        except Exception as e:
            logger.error(f"Error generating synthetic audio: {e}")
    
    def _load_real_samples(self):
        """Load real audio samples from benchmark directory"""
        try:
            # Look for audio files with associated reference text files
            audio_extensions = ['.wav', '.mp3', '.flac', '.m4a']
            
            for audio_file in self.benchmark_directory.iterdir():
                if audio_file.suffix.lower() in audio_extensions:
                    # Look for corresponding reference text file
                    ref_file = audio_file.with_suffix('.txt')
                    metadata_file = audio_file.with_suffix('.json')
                    
                    if ref_file.exists():
                        try:
                            # Load reference text
                            reference_text = ref_file.read_text().strip()
                            
                            # Load metadata if available
                            metadata = {}
                            if metadata_file.exists():
                                metadata = json.loads(metadata_file.read_text())
                            
                            # Get audio duration
                            try:
                                audio, sr = librosa.load(str(audio_file), sr=None)
                                duration = len(audio) / sr
                                sample_rate = sr
                            except:
                                duration = metadata.get("duration", 10.0)
                                sample_rate = metadata.get("sample_rate", 16000)
                            
                            # Create sample
                            sample = BenchmarkAudioSample(
                                id=audio_file.stem,
                                name=metadata.get("name", audio_file.stem),
                                file_path=str(audio_file),
                                duration=duration,
                                sample_rate=sample_rate,
                                reference_text=reference_text,
                                reference_speakers=metadata.get("reference_speakers", ["SPEAKER_01"]),
                                difficulty_level=metadata.get("difficulty_level", "medium"),
                                audio_quality=metadata.get("audio_quality", "clean"),
                                language=metadata.get("language", "en"),
                                description=metadata.get("description", f"Real audio sample: {audio_file.name}")
                            )
                            
                            self.benchmark_samples.append(sample)
                            logger.info(f"📁 Loaded real audio sample: {audio_file.name}")
                            
                        except Exception as e:
                            logger.warning(f"Error loading sample {audio_file.name}: {e}")
            
        except Exception as e:
            logger.error(f"Error loading real samples: {e}")
    
    def benchmark_model(self, model_id: str, sample_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Benchmark a model against audio samples"""
        try:
            logger.info(f"🎯 Benchmarking model: {model_id}")
            
            # Filter samples
            samples_to_test = self.benchmark_samples
            if sample_ids:
                samples_to_test = [s for s in self.benchmark_samples if s.id in sample_ids]
            
            if not samples_to_test:
                return {"error": "No samples found for benchmarking"}
            
            # Switch to the model
            if not transcription_service.switch_model(model_id):
                return {"error": f"Failed to switch to model {model_id}"}
            
            model_info = transcription_service.get_current_model_info()
            model_name = model_info.get("name", model_id)
            
            results = []
            total_start_time = time.time()
            
            for sample in samples_to_test:
                logger.info(f"  📊 Testing sample: {sample.name}")
                
                try:
                    # Load audio
                    audio, sr = librosa.load(sample.file_path, sr=16000)
                    
                    # Benchmark transcription
                    start_time = time.time()
                    transcription_result = transcription_service.process_audio_file(sample.file_path)
                    processing_time = time.time() - start_time
                    
                    if transcription_result:
                        result_dict = transcription_result.to_dict()
                        transcribed_text = result_dict.get("text", "")
                        confidence = result_dict.get("confidence", 0.0)
                        segments = result_dict.get("segments", [])
                        
                        # Extract speakers
                        detected_speakers = []
                        if segments:
                            for segment in segments:
                                if isinstance(segment, dict) and "speaker" in segment:
                                    speaker = segment["speaker"]
                                    if speaker not in detected_speakers:
                                        detected_speakers.append(speaker)
                        
                        # Calculate accuracy metrics
                        word_accuracy = self._calculate_word_accuracy(sample.reference_text, transcribed_text)
                        char_accuracy = self._calculate_character_accuracy(sample.reference_text, transcribed_text)
                        speaker_accuracy = self._calculate_speaker_accuracy(sample.reference_speakers, detected_speakers)
                        text_similarity = self._calculate_text_similarity(sample.reference_text, transcribed_text)
                        
                        # Create benchmark result
                        benchmark_result = BenchmarkResult(
                            sample_id=sample.id,
                            model_id=model_id,
                            model_name=model_name,
                            timestamp=datetime.utcnow(),
                            processing_time=processing_time,
                            rtf=processing_time / sample.duration,
                            memory_usage_mb=None,  # Could be added with psutil
                            transcribed_text=transcribed_text,
                            confidence_avg=confidence,
                            detected_speakers=detected_speakers,
                            word_accuracy=word_accuracy,
                            character_accuracy=char_accuracy,
                            speaker_accuracy=speaker_accuracy,
                            text_similarity=text_similarity,
                            timing_accuracy=0.9,  # Placeholder - would need detailed timing analysis
                            words_transcribed=len(transcribed_text.split()) if transcribed_text else 0,
                            speakers_detected_count=len(detected_speakers),
                            npu_accelerated="npu" in model_id.lower()
                        )
                        
                        results.append(benchmark_result)
                        self.benchmark_results.append(benchmark_result)
                        
                        logger.info(f"    ✅ Word Accuracy: {word_accuracy:.1%}, RTF: {benchmark_result.rtf:.3f}")
                        
                    else:
                        logger.warning(f"    ❌ Transcription failed for {sample.name}")
                        
                except Exception as e:
                    logger.error(f"    ❌ Error testing sample {sample.name}: {e}")
                    continue
            
            total_time = time.time() - total_start_time
            
            # Calculate summary statistics
            if results:
                summary = self._calculate_benchmark_summary(results, total_time)
                return {
                    "model_id": model_id,
                    "model_name": model_name,
                    "results": [r.to_dict() for r in results],
                    "summary": summary,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "model_id": model_id,
                    "error": "No successful transcriptions",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error benchmarking model {model_id}: {e}")
            return {"model_id": model_id, "error": str(e)}
    
    def _calculate_word_accuracy(self, reference: str, hypothesis: str) -> float:
        """Calculate word-level accuracy (1 - WER)"""
        ref_words = reference.lower().split()
        hyp_words = hypothesis.lower().split()
        
        if not ref_words:
            return 1.0 if not hyp_words else 0.0
        
        # Simple edit distance based WER calculation
        matcher = SequenceMatcher(None, ref_words, hyp_words)
        matches = sum(triple.size for triple in matcher.get_matching_blocks())
        wer = 1 - (matches / len(ref_words))
        
        return max(0.0, 1.0 - wer)
    
    def _calculate_character_accuracy(self, reference: str, hypothesis: str) -> float:
        """Calculate character-level accuracy (1 - CER)"""
        if not reference:
            return 1.0 if not hypothesis else 0.0
        
        matcher = SequenceMatcher(None, reference.lower(), hypothesis.lower())
        matches = sum(triple.size for triple in matcher.get_matching_blocks())
        cer = 1 - (matches / len(reference))
        
        return max(0.0, 1.0 - cer)
    
    def _calculate_speaker_accuracy(self, reference_speakers: List[str], detected_speakers: List[str]) -> float:
        """Calculate speaker identification accuracy"""
        if not reference_speakers:
            return 1.0 if not detected_speakers else 0.0
        
        # Simple count-based accuracy
        ref_count = len(reference_speakers)
        det_count = len(detected_speakers)
        
        # Accuracy based on how close the detected count is to reference
        if ref_count == det_count:
            return 1.0
        else:
            return max(0.0, 1.0 - abs(ref_count - det_count) / ref_count)
    
    def _calculate_text_similarity(self, reference: str, hypothesis: str) -> float:
        """Calculate semantic text similarity"""
        if not reference and not hypothesis:
            return 1.0
        if not reference or not hypothesis:
            return 0.0
        
        # Simple word overlap similarity
        ref_words = set(reference.lower().split())
        hyp_words = set(hypothesis.lower().split())
        
        if not ref_words and not hyp_words:
            return 1.0
        
        intersection = ref_words.intersection(hyp_words)
        union = ref_words.union(hyp_words)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _calculate_benchmark_summary(self, results: List[BenchmarkResult], total_time: float) -> Dict[str, Any]:
        """Calculate summary statistics for benchmark results"""
        if not results:
            return {}
        
        # Calculate averages
        avg_word_accuracy = sum(r.word_accuracy for r in results) / len(results)
        avg_char_accuracy = sum(r.character_accuracy for r in results) / len(results)
        avg_speaker_accuracy = sum(r.speaker_accuracy for r in results) / len(results)
        avg_confidence = sum(r.confidence_avg for r in results) / len(results)
        avg_rtf = sum(r.rtf for r in results) / len(results)
        avg_similarity = sum(r.text_similarity for r in results) / len(results)
        
        total_audio_duration = 0
        for r in results:
            sample = next((s for s in self.benchmark_samples if s.id == r.sample_id), None)
            if sample:
                total_audio_duration += sample.duration
            else:
                # Default duration if sample not found
                total_audio_duration += 10.0
        
        # Grade calculation
        overall_score = (
            avg_word_accuracy * 0.3 +
            avg_char_accuracy * 0.2 +
            avg_confidence * 0.2 +
            avg_similarity * 0.15 +
            avg_speaker_accuracy * 0.1 +
            (1.0 / max(avg_rtf, 0.01)) * 0.05  # Performance bonus
        )
        
        grade = "A+" if overall_score >= 0.95 else \
                "A" if overall_score >= 0.9 else \
                "B+" if overall_score >= 0.85 else \
                "B" if overall_score >= 0.8 else \
                "C+" if overall_score >= 0.75 else \
                "C" if overall_score >= 0.7 else \
                "D" if overall_score >= 0.6 else "F"
        
        return {
            "samples_tested": len(results),
            "total_audio_duration": round(total_audio_duration, 2),
            "total_processing_time": round(total_time, 2),
            "average_metrics": {
                "word_accuracy": round(avg_word_accuracy, 3),
                "character_accuracy": round(avg_char_accuracy, 3),
                "speaker_accuracy": round(avg_speaker_accuracy, 3),
                "confidence": round(avg_confidence, 3),
                "text_similarity": round(avg_similarity, 3),
                "rtf": round(avg_rtf, 4),
                "speedup_factor": round(1/avg_rtf, 1) if avg_rtf > 0 else 0
            },
            "performance_grade": grade,
            "overall_score": round(overall_score, 3),
            "npu_accelerated": any(r.npu_accelerated for r in results)
        }
    
    def compare_models(self, model_ids: List[str], sample_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Compare multiple models on the same benchmark samples"""
        logger.info(f"🏁 Comparing models: {', '.join(model_ids)}")
        
        comparison_results = {}
        
        for model_id in model_ids:
            logger.info(f"\n🔄 Benchmarking {model_id}...")
            result = self.benchmark_model(model_id, sample_ids)
            comparison_results[model_id] = result
        
        # Create comparison summary
        summary = self._create_comparison_summary(comparison_results)
        
        return {
            "models": comparison_results,
            "comparison": summary,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _create_comparison_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Create comparison summary between models"""
        winners = {
            "fastest": {"model_id": None, "rtf": float('inf')},
            "most_accurate": {"model_id": None, "word_accuracy": 0},
            "highest_confidence": {"model_id": None, "confidence": 0},
            "best_overall": {"model_id": None, "score": 0}
        }
        
        model_summaries = []
        
        for model_id, result in results.items():
            if "error" in result or "summary" not in result:
                continue
                
            summary = result["summary"]
            metrics = summary["average_metrics"]
            
            model_summaries.append({
                "model_id": model_id,
                "model_name": result.get("model_name", model_id),
                "grade": summary["performance_grade"],
                "score": summary["overall_score"],
                "rtf": metrics["rtf"],
                "word_accuracy": metrics["word_accuracy"],
                "confidence": metrics["confidence"],
                "speedup": metrics["speedup_factor"],
                "npu_accelerated": summary["npu_accelerated"]
            })
            
            # Update winners
            if metrics["rtf"] < winners["fastest"]["rtf"]:
                winners["fastest"] = {"model_id": model_id, "rtf": metrics["rtf"]}
                
            if metrics["word_accuracy"] > winners["most_accurate"]["word_accuracy"]:
                winners["most_accurate"] = {"model_id": model_id, "word_accuracy": metrics["word_accuracy"]}
                
            if metrics["confidence"] > winners["highest_confidence"]["confidence"]:
                winners["highest_confidence"] = {"model_id": model_id, "confidence": metrics["confidence"]}
                
            if summary["overall_score"] > winners["best_overall"]["score"]:
                winners["best_overall"] = {"model_id": model_id, "score": summary["overall_score"]}
        
        # Sort by overall score
        model_summaries.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "model_rankings": model_summaries,
            "winners": winners,
            "total_models_compared": len(model_summaries)
        }
    
    def get_available_samples(self) -> List[Dict[str, Any]]:
        """Get list of available benchmark samples"""
        return [
            {
                "id": sample.id,
                "name": sample.name,
                "duration": sample.duration,
                "difficulty_level": sample.difficulty_level,
                "audio_quality": sample.audio_quality,
                "language": sample.language,
                "description": sample.description,
                "reference_text_preview": sample.reference_text[:100] + "..." if len(sample.reference_text) > 100 else sample.reference_text,
                "speaker_count": len(sample.reference_speakers)
            }
            for sample in self.benchmark_samples
        ]
    
    def add_custom_sample(self, name: str, audio_file_path: str, reference_text: str, 
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a custom benchmark sample"""
        try:
            # Generate ID from file hash
            with open(audio_file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()[:8]
            
            sample_id = f"custom_{file_hash}"
            
            # Get audio info
            audio, sr = librosa.load(audio_file_path, sr=None)
            duration = len(audio) / sr
            
            # Copy file to benchmark directory
            dest_path = self.benchmark_directory / f"{sample_id}.wav"
            import shutil
            shutil.copy2(audio_file_path, dest_path)
            
            # Save reference text
            ref_path = dest_path.with_suffix('.txt')
            ref_path.write_text(reference_text)
            
            # Save metadata
            if metadata:
                metadata_path = dest_path.with_suffix('.json')
                metadata_path.write_text(json.dumps(metadata, indent=2))
            
            # Create sample
            sample = BenchmarkAudioSample(
                id=sample_id,
                name=name,
                file_path=str(dest_path),
                duration=duration,
                sample_rate=sr,
                reference_text=reference_text,
                reference_speakers=metadata.get("reference_speakers", ["SPEAKER_01"]) if metadata else ["SPEAKER_01"],
                difficulty_level=metadata.get("difficulty_level", "medium") if metadata else "medium",
                audio_quality=metadata.get("audio_quality", "clean") if metadata else "clean",
                language=metadata.get("language", "en") if metadata else "en",
                description=metadata.get("description", f"Custom sample: {name}") if metadata else f"Custom sample: {name}"
            )
            
            self.benchmark_samples.append(sample)
            logger.info(f"✅ Added custom benchmark sample: {name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding custom sample: {e}")
            return False

# Global benchmarking service instance
model_benchmarking_service = ModelBenchmarkingService()