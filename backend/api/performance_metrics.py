"""
Performance Metrics API
======================
RESTful API for accessing model performance metrics, trends, and comparisons.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import logging

from auth.dependencies import require_permission
from auth.models import User
from services.performance_metrics_service import performance_metrics_service
from database.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/performance", tags=["performance_metrics"])

class ModelComparisonRequest(BaseModel):
    model_ids: List[str]

@router.get("/models/{model_id}/summary")
async def get_model_performance_summary(
    model_id: str,
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Get performance summary for a specific model"""
    try:
        summary = performance_metrics_service.get_model_performance_summary(model_id)
        return summary
    except Exception as e:
        logger.error(f"Error getting model performance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def get_all_models_performance(
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Get performance comparison across all models"""
    try:
        performance = performance_metrics_service.get_all_models_performance()
        return performance
    except Exception as e:
        logger.error(f"Error getting all models performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/{model_id}/trends")
async def get_performance_trends(
    model_id: str,
    hours: int = Query(24, description="Number of hours to analyze", ge=1, le=168),
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Analyze performance trends for a model over time"""
    try:
        trends = performance_metrics_service.get_performance_trends(model_id, hours)
        return trends
    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/recent")
async def get_recent_metrics(
    hours: int = Query(24, description="Hours of recent metrics", ge=1, le=168),
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    limit: int = Query(100, description="Maximum number of metrics", ge=1, le=1000),
    current_user: User = Depends(require_permission("ai.model.read"))
) -> List[Dict[str, Any]]:
    """Get recent performance metrics"""
    try:
        metrics = performance_metrics_service.get_recent_metrics(hours, model_id)
        return metrics[:limit]
    except Exception as e:
        logger.error(f"Error getting recent metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/compare")
async def compare_models(
    request: ModelComparisonRequest,
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Compare performance between multiple models"""
    try:
        if len(request.model_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 models required for comparison")
        
        if len(request.model_ids) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 models can be compared at once")
        
        comparison = performance_metrics_service.compare_models(request.model_ids)
        return comparison
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard")
async def get_performance_dashboard(
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Get comprehensive performance dashboard data"""
    try:
        # Get all models performance
        all_models = performance_metrics_service.get_all_models_performance()
        
        # Get recent metrics for the last 24 hours
        recent_metrics = performance_metrics_service.get_recent_metrics(24)
        
        # Identify top performing models
        top_models = []
        if "models" in all_models:
            model_performances = []
            for model_id, data in all_models["models"].items():
                if "error" not in data:
                    stats = data["statistics"]
                    model_performances.append({
                        "model_id": model_id,
                        "speedup_factor": stats["speedup_factor"],
                        "average_confidence": stats["average_confidence"],
                        "invocation_count": stats["invocation_count"]
                    })
            
            # Sort by speedup factor for top models
            model_performances.sort(key=lambda x: x["speedup_factor"], reverse=True)
            top_models = model_performances[:5]
        
        # Calculate system-wide statistics
        system_stats = {
            "total_models_tracked": len(all_models.get("models", {})),
            "total_audio_hours": sum(
                data["statistics"]["total_audio_hours"] 
                for data in all_models.get("models", {}).values() 
                if "error" not in data
            ),
            "recent_metrics_count": len(recent_metrics),
            "npu_models_available": all_models.get("summary", {}).get("npu_models_count", 0),
            "cpu_models_available": all_models.get("summary", {}).get("cpu_models_count", 0)
        }
        
        # Performance alerts
        alerts = []
        for model_id, data in all_models.get("models", {}).items():
            if "error" not in data:
                stats = data["statistics"]
                
                # Alert for poor performance
                if stats["average_rtf"] > 1.0:
                    alerts.append({
                        "type": "warning",
                        "model_id": model_id,
                        "message": f"Model {model_id} is slower than real-time (RTF: {stats['average_rtf']:.2f})",
                        "severity": "medium"
                    })
                
                # Alert for low confidence
                if stats["average_confidence"] < 0.8:
                    alerts.append({
                        "type": "warning",
                        "model_id": model_id,
                        "message": f"Model {model_id} has low confidence ({stats['average_confidence']:.1%})",
                        "severity": "low"
                    })
                
                # Alert for excellent performance
                if stats["speedup_factor"] > 100:
                    alerts.append({
                        "type": "success",
                        "model_id": model_id,
                        "message": f"Model {model_id} performing excellently ({stats['speedup_factor']:.0f}x speedup)",
                        "severity": "info"
                    })
        
        dashboard_data = {
            "system_statistics": system_stats,
            "top_performing_models": top_models,
            "recent_activity": recent_metrics[:10],  # Last 10 metrics
            "performance_alerts": alerts,
            "summary": all_models.get("summary", {}),
            "generated_at": performance_metrics_service.metrics_buffer[-1].timestamp.isoformat() if performance_metrics_service.metrics_buffer else None
        }
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error generating performance dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_performance_data(
    hours: int = Query(168, description="Hours of data to export", ge=1, le=720),
    format: str = Query("json", description="Export format (json, csv)"),
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Export performance data for external analysis"""
    try:
        if format not in ["json", "csv"]:
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
        
        # Get comprehensive data
        all_models = performance_metrics_service.get_all_models_performance()
        recent_metrics = performance_metrics_service.get_recent_metrics(hours)
        
        export_data = {
            "export_metadata": {
                "exported_at": performance_metrics_service.metrics_buffer[-1].timestamp.isoformat() if performance_metrics_service.metrics_buffer else None,
                "hours_covered": hours,
                "format": format,
                "total_metrics": len(recent_metrics)
            },
            "model_summaries": all_models.get("models", {}),
            "raw_metrics": recent_metrics,
            "system_summary": all_models.get("summary", {})
        }
        
        if format == "csv":
            # For CSV, flatten the metrics data
            csv_data = []
            for metric in recent_metrics:
                csv_data.append({
                    "timestamp": metric["timestamp"],
                    "model_id": metric["model_id"],
                    "model_name": metric["model_name"],
                    "audio_duration": metric["audio_duration"],
                    "processing_time": metric["processing_time"],
                    "rtf": metric["rtf"],
                    "npu_accelerated": metric["npu_accelerated"],
                    "confidence_avg": metric["confidence_avg"],
                    "words_transcribed": metric["words_transcribed"],
                    "speakers_detected": metric["speakers_detected"]
                })
            
            export_data["csv_metrics"] = csv_data
        
        return export_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting performance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/metrics")
async def clear_performance_metrics(
    confirm: bool = Query(False, description="Confirm deletion"),
    current_user: User = Depends(require_permission("ai.model.delete"))
) -> Dict[str, str]:
    """Clear all performance metrics (admin only)"""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Must set confirm=true to clear metrics"
            )
        
        # Clear in-memory data
        performance_metrics_service.metrics_buffer.clear()
        performance_metrics_service.model_stats.clear()
        
        # Clear persisted data
        db = next(get_db())
        try:
            from database.models import Settings
            setting = db.query(Settings).filter(
                Settings.key == "performance.metrics_data"
            ).first()
            
            if setting:
                db.delete(setting)
                db.commit()
            
        finally:
            db.close()
        
        logger.info(f"🗑️ Performance metrics cleared by user {current_user.username}")
        
        return {
            "message": "All performance metrics have been cleared",
            "cleared_by": current_user.username,
            "cleared_at": performance_metrics_service.metrics_buffer[-1].timestamp.isoformat() if performance_metrics_service.metrics_buffer else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))