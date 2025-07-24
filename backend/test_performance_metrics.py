#!/usr/bin/env python3
"""
Test Performance Metrics System
==============================
Tests the performance metrics collection and API endpoints.
"""

import time
import numpy as np
import logging
from services.performance_metrics_service import performance_metrics_service

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_performance_metrics():
    """Test performance metrics collection and analysis"""
    logger.info("🧪 Testing Performance Metrics System")
    logger.info("="*60)
    
    # Simulate different model performances
    models_to_test = [
        {
            "model_id": "whisper-base",
            "model_name": "Whisper Base (CPU)",
            "rtf_range": (0.8, 1.2),  # CPU performance
            "confidence_range": (0.85, 0.95),
            "npu_accelerated": False
        },
        {
            "model_id": "whisper-small", 
            "model_name": "Whisper Small (CPU)",
            "rtf_range": (1.0, 1.5),  # Slower but more accurate
            "confidence_range": (0.88, 0.96),
            "npu_accelerated": False
        },
        {
            "model_id": "whisperx-npu-unified",
            "model_name": "WhisperX NPU Unified (Recommended)",
            "rtf_range": (0.02, 0.08),  # NPU super fast
            "confidence_range": (0.92, 0.98),
            "npu_accelerated": True
        },
        {
            "model_id": "whisperx-npu",
            "model_name": "WhisperX NPU Transcription",
            "rtf_range": (0.05, 0.12),  # NPU fast
            "confidence_range": (0.90, 0.96),
            "npu_accelerated": True
        }
    ]
    
    # Generate test data
    logger.info("📊 Generating performance test data...")
    session_id = "test_session_001"
    
    for model in models_to_test:
        logger.info(f"\n🔄 Testing model: {model['model_name']}")
        
        # Simulate 10 transcription operations per model
        for i in range(10):
            # Simulate audio duration (1-30 seconds)
            audio_duration = np.random.uniform(1.0, 30.0)
            
            # Calculate processing time based on RTF range
            rtf = np.random.uniform(*model["rtf_range"])
            processing_time = rtf * audio_duration
            
            # Simulate confidence
            confidence = np.random.uniform(*model["confidence_range"])
            
            # Simulate transcription results
            words_transcribed = int(audio_duration * np.random.uniform(2, 5))  # 2-5 words per second
            speakers_detected = np.random.randint(1, 4)  # 1-3 speakers
            
            # Record performance metric
            performance_metrics_service.record_model_performance(
                session_id=f"{session_id}_{i}",
                model_id=model["model_id"],
                model_name=model["model_name"],
                audio_duration=audio_duration,
                processing_time=processing_time,
                npu_accelerated=model["npu_accelerated"],
                confidence_avg=confidence,
                words_transcribed=words_transcribed,
                speakers_detected=speakers_detected
            )
            
            logger.debug(f"  Operation {i+1}: {audio_duration:.1f}s audio, RTF={rtf:.3f}, {words_transcribed} words")
    
    logger.info("\n✅ Test data generation complete!")
    
    # Test performance analysis
    logger.info("\n📈 Testing Performance Analysis...")
    
    # Test individual model summaries
    for model in models_to_test:
        summary = performance_metrics_service.get_model_performance_summary(model["model_id"])
        if "error" not in summary:
            stats = summary["statistics"]
            logger.info(f"\n📊 {model['model_name']} Performance:")
            logger.info(f"  Average RTF: {stats['average_rtf']:.4f} ({stats['speedup_factor']:.1f}x speedup)")
            logger.info(f"  Average Confidence: {stats['average_confidence']:.1%}")
            logger.info(f"  Total Operations: {stats['invocation_count']}")
            logger.info(f"  Audio Processed: {stats['total_audio_hours']:.2f} hours")
        else:
            logger.error(f"  Error getting summary: {summary['error']}")
    
    # Test overall performance comparison
    logger.info("\n🏆 Overall Performance Comparison:")
    all_performance = performance_metrics_service.get_all_models_performance()
    
    if "models" in all_performance:
        summary = all_performance["summary"]
        logger.info(f"  Total Models Tested: {summary['total_models_tested']}")
        logger.info(f"  NPU Models: {summary['npu_models_count']}")
        logger.info(f"  CPU Models: {summary['cpu_models_count']}")
        logger.info(f"  Total Audio: {summary['total_audio_processed']:.2f} hours")
        
        if summary.get("best_speed_model"):
            best_speed = summary["best_speed_model"]
            logger.info(f"  🥇 Fastest Model: {best_speed['model_id']} ({best_speed['speedup']:.1f}x speedup)")
        
        if summary.get("best_accuracy_model"):
            best_accuracy = summary["best_accuracy_model"]
            logger.info(f"  🎯 Most Accurate: {best_accuracy['model_id']} ({best_accuracy['confidence']:.1%})")
    
    # Test model comparison
    logger.info("\n⚖️ Model Comparison (NPU vs CPU):")
    comparison = performance_metrics_service.compare_models([
        "whisperx-npu-unified", 
        "whisper-base"
    ])
    
    if "models" in comparison and "winners" in comparison:
        winners = comparison["winners"]
        logger.info(f"  Fastest: {winners['fastest']['model_id']}")
        logger.info(f"  Most Accurate: {winners['most_accurate']['model_id']}")
        logger.info(f"  Most Used: {winners['most_used']['model_id']}")
    
    # Test recent metrics
    logger.info("\n🕒 Recent Activity:")
    recent_metrics = performance_metrics_service.get_recent_metrics(hours=1)
    logger.info(f"  Recent Metrics (last hour): {len(recent_metrics)}")
    
    if recent_metrics:
        latest = recent_metrics[0]
        logger.info(f"  Latest: {latest['model_id']} - RTF: {latest['rtf']:.3f}")
    
    logger.info("\n🎉 Performance Metrics Test Complete!")
    logger.info(f"📊 Dashboard endpoints available at:")
    logger.info(f"  GET /api/performance/models - All models performance")
    logger.info(f"  GET /api/performance/dashboard - Complete dashboard")
    logger.info(f"  GET /api/performance/models/whisperx-npu-unified/summary - Model summary")
    logger.info(f"  POST /api/performance/models/compare - Compare models")

if __name__ == "__main__":
    test_performance_metrics()