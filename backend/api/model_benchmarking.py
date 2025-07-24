"""
Model Benchmarking API
=====================
RESTful API for comprehensive model benchmarking with real audio samples.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging
import tempfile
import os

from auth.dependencies import require_permission
from auth.models import User
from services.model_benchmarking_service import model_benchmarking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmarks", tags=["model_benchmarking"])

class BenchmarkRequest(BaseModel):
    model_id: str
    sample_ids: Optional[List[str]] = None

class ModelComparisonRequest(BaseModel):
    model_ids: List[str]
    sample_ids: Optional[List[str]] = None

class CustomSampleMetadata(BaseModel):
    reference_speakers: Optional[List[str]] = ["SPEAKER_01"]
    difficulty_level: Optional[str] = "medium"
    audio_quality: Optional[str] = "clean"
    language: Optional[str] = "en"
    description: Optional[str] = None

@router.get("/samples")
async def get_available_samples(
    current_user: User = Depends(require_permission("ai.model.read"))
) -> List[Dict[str, Any]]:
    """Get list of available benchmark samples"""
    try:
        samples = model_benchmarking_service.get_available_samples()
        return samples
    except Exception as e:
        logger.error(f"Error getting benchmark samples: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/samples/upload")
async def upload_custom_sample(
    audio_file: UploadFile = File(...),
    name: str = Form(...),
    reference_text: str = Form(...),
    reference_speakers: Optional[str] = Form("SPEAKER_01"),
    difficulty_level: Optional[str] = Form("medium"),
    audio_quality: Optional[str] = Form("clean"),
    language: Optional[str] = Form("en"),
    description: Optional[str] = Form(None),
    current_user: User = Depends(require_permission("ai.model.write"))
) -> Dict[str, Any]:
    """Upload a custom benchmark sample"""
    try:
        # Validate file type
        if not audio_file.filename.lower().endswith(('.wav', '.mp3', '.flac', '.m4a')):
            raise HTTPException(status_code=400, detail="Invalid audio file format")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.filename)[1]) as tmp_file:
            content = await audio_file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        try:
            # Parse reference speakers
            speakers_list = [s.strip() for s in reference_speakers.split(',') if s.strip()]
            if not speakers_list:
                speakers_list = ["SPEAKER_01"]
            
            # Create metadata
            metadata = {
                "reference_speakers": speakers_list,
                "difficulty_level": difficulty_level,
                "audio_quality": audio_quality,
                "language": language,
                "description": description or f"Custom sample uploaded by {current_user.username}"
            }
            
            # Add to benchmarking service
            success = model_benchmarking_service.add_custom_sample(
                name=name,
                audio_file_path=tmp_file_path,
                reference_text=reference_text,
                metadata=metadata
            )
            
            if success:
                return {
                    "success": True,
                    "message": f"Custom benchmark sample '{name}' uploaded successfully",
                    "uploaded_by": current_user.username
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to add custom sample")
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_file_path)
            except:
                pass
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading custom sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/{model_id}/benchmark")
async def benchmark_model(
    model_id: str,
    sample_ids: Optional[List[str]] = Query(None, description="Specific sample IDs to test"),
    current_user: User = Depends(require_permission("ai.model.test"))
) -> Dict[str, Any]:
    """Benchmark a specific model against audio samples"""
    try:
        logger.info(f"🎯 Starting benchmark for model {model_id} by user {current_user.username}")
        
        result = model_benchmarking_service.benchmark_model(model_id, sample_ids)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error benchmarking model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/compare")
async def compare_models(
    request: ModelComparisonRequest,
    current_user: User = Depends(require_permission("ai.model.test"))
) -> Dict[str, Any]:
    """Compare multiple models on the same benchmark samples"""
    try:
        if len(request.model_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 models required for comparison")
        
        if len(request.model_ids) > 6:
            raise HTTPException(status_code=400, detail="Maximum 6 models can be compared at once")
        
        logger.info(f"🏁 Starting model comparison: {', '.join(request.model_ids)} by user {current_user.username}")
        
        result = model_benchmarking_service.compare_models(request.model_ids, request.sample_ids)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leaderboard")
async def get_benchmark_leaderboard(
    sample_filter: Optional[str] = Query(None, description="Filter by difficulty level"),
    limit: int = Query(10, description="Number of top models", ge=1, le=50),
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Get benchmark leaderboard showing top performing models"""
    try:
        # Get all unique models that have been benchmarked
        all_results = model_benchmarking_service.benchmark_results
        
        if not all_results:
            return {
                "leaderboard": [],
                "message": "No benchmark results available. Run benchmarks first.",
                "total_models": 0
            }
        
        # Group by model
        model_stats = {}
        for result in all_results:
            model_id = result.model_id
            
            # Filter by sample difficulty if requested
            if sample_filter:
                sample = next((s for s in model_benchmarking_service.benchmark_samples if s.id == result.sample_id), None)
                if not sample or sample.difficulty_level != sample_filter:
                    continue
            
            if model_id not in model_stats:
                model_stats[model_id] = {
                    "model_id": model_id,
                    "model_name": result.model_name,
                    "results": [],
                    "npu_accelerated": result.npu_accelerated
                }
            
            model_stats[model_id]["results"].append(result)
        
        # Calculate averages for each model
        leaderboard = []
        for model_id, data in model_stats.items():
            results = data["results"]
            
            if not results:
                continue
            
            avg_word_accuracy = sum(r.word_accuracy for r in results) / len(results)
            avg_char_accuracy = sum(r.character_accuracy for r in results) / len(results)
            avg_confidence = sum(r.confidence_avg for r in results) / len(results)
            avg_rtf = sum(r.rtf for r in results) / len(results)
            avg_similarity = sum(r.text_similarity for r in results) / len(results)
            avg_speaker_accuracy = sum(r.speaker_accuracy for r in results) / len(results)
            
            # Calculate overall score
            overall_score = (
                avg_word_accuracy * 0.3 +
                avg_char_accuracy * 0.2 +
                avg_confidence * 0.2 +
                avg_similarity * 0.15 +
                avg_speaker_accuracy * 0.1 +
                (1.0 / max(avg_rtf, 0.01)) * 0.05
            )
            
            # Assign grade
            grade = "A+" if overall_score >= 0.95 else \
                    "A" if overall_score >= 0.9 else \
                    "B+" if overall_score >= 0.85 else \
                    "B" if overall_score >= 0.8 else \
                    "C+" if overall_score >= 0.75 else \
                    "C" if overall_score >= 0.7 else \
                    "D" if overall_score >= 0.6 else "F"
            
            leaderboard.append({
                "rank": 0,  # Will be set after sorting
                "model_id": model_id,
                "model_name": data["model_name"],
                "grade": grade,
                "overall_score": round(overall_score, 3),
                "samples_tested": len(results),
                "metrics": {
                    "word_accuracy": round(avg_word_accuracy, 3),
                    "character_accuracy": round(avg_char_accuracy, 3),
                    "confidence": round(avg_confidence, 3),
                    "text_similarity": round(avg_similarity, 3),
                    "speaker_accuracy": round(avg_speaker_accuracy, 3),
                    "rtf": round(avg_rtf, 4),
                    "speedup_factor": round(1/avg_rtf, 1) if avg_rtf > 0 else 0
                },
                "npu_accelerated": data["npu_accelerated"],
                "last_tested": max(r.timestamp for r in results).isoformat()
            })
        
        # Sort by overall score and assign ranks
        leaderboard.sort(key=lambda x: x["overall_score"], reverse=True)
        for i, entry in enumerate(leaderboard[:limit]):
            entry["rank"] = i + 1
        
        return {
            "leaderboard": leaderboard[:limit],
            "filter_applied": sample_filter,
            "total_models": len(model_stats),
            "generated_at": model_benchmarking_service.benchmark_results[-1].timestamp.isoformat() if model_benchmarking_service.benchmark_results else None
        }
        
    except Exception as e:
        logger.error(f"Error generating leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/results/history")
async def get_benchmark_history(
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    sample_id: Optional[str] = Query(None, description="Filter by sample ID"),
    limit: int = Query(50, description="Number of results", ge=1, le=500),
    current_user: User = Depends(require_permission("ai.model.read"))
) -> List[Dict[str, Any]]:
    """Get historical benchmark results"""
    try:
        results = model_benchmarking_service.benchmark_results
        
        # Apply filters
        filtered_results = results
        if model_id:
            filtered_results = [r for r in filtered_results if r.model_id == model_id]
        if sample_id:
            filtered_results = [r for r in filtered_results if r.sample_id == sample_id]
        
        # Sort by timestamp descending and limit
        filtered_results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return [r.to_dict() for r in filtered_results[:limit]]
        
    except Exception as e:
        logger.error(f"Error getting benchmark history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/{model_id}/analysis")
async def get_model_analysis(
    model_id: str,
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Get detailed analysis for a specific model"""
    try:
        # Get all results for this model
        model_results = [r for r in model_benchmarking_service.benchmark_results if r.model_id == model_id]
        
        if not model_results:
            raise HTTPException(status_code=404, detail=f"No benchmark results found for model {model_id}")
        
        # Group by sample difficulty and audio quality
        difficulty_stats = {}
        quality_stats = {}
        
        for result in model_results:
            # Find the sample
            sample = next((s for s in model_benchmarking_service.benchmark_samples if s.id == result.sample_id), None)
            
            if sample:
                # Group by difficulty
                difficulty = sample.difficulty_level
                if difficulty not in difficulty_stats:
                    difficulty_stats[difficulty] = []
                difficulty_stats[difficulty].append(result)
                
                # Group by quality
                quality = sample.audio_quality
                if quality not in quality_stats:
                    quality_stats[quality] = []
                quality_stats[quality].append(result)
        
        # Calculate stats for each group
        def calculate_group_stats(results_group):
            if not results_group:
                return {}
            
            return {
                "sample_count": len(results_group),
                "avg_word_accuracy": round(sum(r.word_accuracy for r in results_group) / len(results_group), 3),
                "avg_confidence": round(sum(r.confidence_avg for r in results_group) / len(results_group), 3),
                "avg_rtf": round(sum(r.rtf for r in results_group) / len(results_group), 4),
                "avg_speedup": round(sum(1/r.rtf for r in results_group if r.rtf > 0) / len(results_group), 1)
            }
        
        difficulty_analysis = {level: calculate_group_stats(results) for level, results in difficulty_stats.items()}
        quality_analysis = {quality: calculate_group_stats(results) for quality, results in quality_stats.items()}
        
        # Overall stats
        overall_stats = calculate_group_stats(model_results)
        
        # Best and worst performances
        best_result = max(model_results, key=lambda r: r.word_accuracy)
        worst_result = min(model_results, key=lambda r: r.word_accuracy)
        
        best_sample = next((s for s in model_benchmarking_service.benchmark_samples if s.id == best_result.sample_id), None)
        worst_sample = next((s for s in model_benchmarking_service.benchmark_samples if s.id == worst_result.sample_id), None)
        
        return {
            "model_id": model_id,
            "model_name": model_results[0].model_name,
            "total_benchmarks": len(model_results),
            "overall_statistics": overall_stats,
            "performance_by_difficulty": difficulty_analysis,
            "performance_by_audio_quality": quality_analysis,
            "best_performance": {
                "sample_id": best_result.sample_id,
                "sample_name": best_sample.name if best_sample else "Unknown",
                "word_accuracy": best_result.word_accuracy,
                "rtf": best_result.rtf
            },
            "worst_performance": {
                "sample_id": worst_result.sample_id,
                "sample_name": worst_sample.name if worst_sample else "Unknown",
                "word_accuracy": worst_result.word_accuracy,
                "rtf": worst_result.rtf
            },
            "npu_accelerated": model_results[0].npu_accelerated,
            "first_tested": min(r.timestamp for r in model_results).isoformat(),
            "last_tested": max(r.timestamp for r in model_results).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/results")
async def clear_benchmark_results(
    confirm: bool = Query(False, description="Confirm deletion"),
    current_user: User = Depends(require_permission("ai.model.delete"))
) -> Dict[str, str]:
    """Clear all benchmark results (admin only)"""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Must set confirm=true to clear benchmark results"
            )
        
        # Clear results
        results_count = len(model_benchmarking_service.benchmark_results)
        model_benchmarking_service.benchmark_results.clear()
        
        logger.info(f"🗑️ Benchmark results cleared by user {current_user.username}")
        
        return {
            "message": f"Cleared {results_count} benchmark results",
            "cleared_by": current_user.username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing benchmark results: {e}")
        raise HTTPException(status_code=500, detail=str(e))