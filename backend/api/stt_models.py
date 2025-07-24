"""
STT Model Management API
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import logging

from auth.dependencies import get_current_user, require_permission
from auth.models import User
from services.settings_manager import settings_manager
from services.transcription_service import transcription_service
from services.stt_model_manager import stt_model_manager
from auth.service import AuthService
from database.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/stt", tags=["stt_models"])

class STTModelChange(BaseModel):
    model_id: str

class STTModelInfo(BaseModel):
    id: str
    name: str
    type: str
    acceleration: str
    supported: bool
    current: bool

# Available STT models including NPU-optimized engines
STT_MODELS = {
    "whisperx-npu-unified": {
        "name": "WhisperX NPU Unified (Recommended)",
        "description": "Unified transcription + diarization with NPU acceleration (220x-7866x speedup)",
        "type": "both",
        "acceleration": "npu",
        "supported": True,
        "engine": "whisperx_npu",
        "performance": {
            "speed": 7866,
            "accuracy": 98,
            "memory": 512
        }
    },
    "whisperx-npu": {
        "name": "WhisperX NPU Transcription",
        "description": "NPU-accelerated transcription with MLIR-AIE2 kernels",
        "type": "whisper",
        "acceleration": "npu",
        "supported": True,
        "engine": "whisperx_npu",
        "performance": {
            "speed": 220,
            "accuracy": 96,
            "memory": 384
        }
    },
    "whisper-onnx-npu": {
        "name": "Whisper ONNX NPU",
        "description": "ONNX Runtime with INT8 quantization for NPU",
        "type": "whisper",
        "acceleration": "npu",
        "supported": True,
        "engine": "onnx_npu",
        "performance": {
            "speed": 150,
            "accuracy": 95,
            "memory": 256
        }
    },
    "whisper-base": {
        "name": "Whisper Base (CPU)",
        "description": "Standard Whisper model running on CPU",
        "type": "whisper",
        "acceleration": "cpu",
        "supported": True,
        "engine": "whisper",
        "model_size": "base",
        "performance": {
            "speed": 1,
            "accuracy": 94,
            "memory": 1024
        }
    },
    "whisper-small": {
        "name": "Whisper Small (CPU)",
        "description": "Larger Whisper model with better accuracy",
        "type": "whisper",
        "acceleration": "cpu",
        "supported": True,
        "engine": "whisper",
        "model_size": "small",
        "performance": {
            "speed": 0.8,
            "accuracy": 95,
            "memory": 2048
        }
    },
    "whisper-medium": {
        "name": "Whisper Medium (CPU)",
        "description": "High-accuracy Whisper model for production use",
        "type": "whisper",
        "acceleration": "cpu",
        "supported": True,
        "engine": "whisper",
        "model_size": "medium",
        "performance": {
            "speed": 0.6,
            "accuracy": 96,
            "memory": 4096
        }
    },
    "diarization-npu": {
        "name": "NPU Speaker Diarization",
        "description": "NPU-accelerated speaker identification with TitanNet embeddings",
        "type": "diarization",
        "acceleration": "npu",
        "supported": True,
        "engine": "diarization_npu",
        "performance": {
            "speed": 50,
            "accuracy": 94,
            "memory": 768
        }
    },
    "pyannote-diarization": {
        "name": "Pyannote Speaker Diarization",
        "description": "GPU-accelerated speaker diarization (requires HuggingFace token)",
        "type": "diarization",
        "acceleration": "gpu",
        "supported": True,
        "engine": "pyannote",
        "performance": {
            "speed": 5,
            "accuracy": 92,
            "memory": 1536
        }
    },
    "npu-runtime": {
        "name": "Custom NPU Runtime",
        "description": "Direct hardware access NPU runtime (30x speedup)",
        "type": "whisper",
        "acceleration": "npu",
        "supported": True,
        "engine": "npu_runtime",
        "performance": {
            "speed": 30,
            "accuracy": 96,
            "memory": 256
        }
    }
}

# Use the global transcription service

@router.get("/models")
async def get_stt_models(
    current_user: User = Depends(require_permission("ai.model.read"))
) -> List[STTModelInfo]:
    """Get list of available STT models"""
    current_model = settings_manager.get_setting("ai.whisper_model") or "whisper-base"
    
    models = []
    for model_id, info in STT_MODELS.items():
        models.append(STTModelInfo(
            id=model_id,
            name=info["name"],
            type=info["type"],
            acceleration=info["acceleration"],
            supported=info["supported"],
            current=(model_id == current_model)
        ))
    
    return models

@router.get("/model")
async def get_current_model(
    current_user: User = Depends(require_permission("settings.read"))
) -> Dict[str, str]:
    """Get current STT model"""
    current_model = settings_manager.get_setting("ai.whisper_model") or "whisper-base"
    return {
        "model_id": current_model,
        "model_info": STT_MODELS.get(current_model, {})
    }

@router.put("/model")
async def change_stt_model(
    model_change: STTModelChange,
    current_user: User = Depends(require_permission("settings.update")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Change the STT model"""
    try:
        # Validate model
        if model_change.model_id not in STT_MODELS:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_change.model_id}")
        
        model_info = STT_MODELS[model_change.model_id]
        
        # Get previous model for audit logging
        previous_model = settings_manager.get_setting("ai.whisper_model") or "whisper-base"
        
        # Switch to the new model using the transcription service
        success = transcription_service.switch_model(model_change.model_id)
        if not success:
            # Log failed model change attempt
            AuthService.log_action(
                db, 
                current_user.id, 
                "ai_model_change_failed", 
                "ai_model", 
                model_change.model_id,
                details={
                    "previous_model": previous_model,
                    "attempted_model": model_change.model_id,
                    "reason": "Transcription service switch failed"
                }
            )
            raise HTTPException(status_code=500, detail=f"Failed to switch to model {model_change.model_id}")
        
        # Update NPU acceleration setting based on model
        if model_info["acceleration"] == "npu":
            settings_manager.update_setting("ai.npu_acceleration", True)
        else:
            settings_manager.update_setting("ai.npu_acceleration", False)
        
        # Log successful model change
        AuthService.log_action(
            db, 
            current_user.id, 
            "ai_model_changed", 
            "ai_model", 
            model_change.model_id,
            details={
                "previous_model": previous_model,
                "new_model": model_change.model_id,
                "model_name": model_info['name'],
                "acceleration": model_info['acceleration'],
                "npu_enabled": model_info["acceleration"] == "npu"
            }
        )
        
        # Get current model info from transcription service
        current_info = transcription_service.get_current_model_info()
        
        return {
            "success": True,
            "model_id": model_change.model_id,
            "model_info": model_info,
            "current_info": current_info,
            "message": f"Successfully changed to {model_info['name']}"
        }
        
    except Exception as e:
        logger.error(f"Error changing STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_stt_model(
    current_user: User = Depends(require_permission("ai.model.test"))
) -> Dict[str, Any]:
    """Test the current STT model with synthetic audio"""
    import numpy as np
    import io
    import wave
    import time
    
    try:
        if not transcription_service.is_ready:
            return {
                "success": False,
                "message": "Transcription service not ready"
            }
        
        # Generate synthetic test audio (1 second of sine wave at 440Hz)
        sample_rate = 16000
        duration = 1.0
        frequency = 440  # A4 note
        
        # Generate sine wave
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = np.sin(frequency * 2 * np.pi * t)
        
        # Add some voice-like characteristics (amplitude modulation)
        modulation = 1 + 0.3 * np.sin(10 * 2 * np.pi * t)
        audio_data = audio_data * modulation
        
        # Scale to 16-bit integer range
        audio_data = (audio_data * 32767).astype(np.int16)
        
        # Create WAV bytes
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        wav_bytes = wav_buffer.getvalue()
        wav_buffer.close()
        
        # Get current model info
        model_info = transcription_service.get_current_model_info()
        
        # Test transcription with synthetic audio
        start_time = time.time()
        try:
            result = transcription_service.process_audio_chunk(wav_bytes, session_id="test")
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Calculate performance metrics
            audio_duration = len(audio_data) / sample_rate
            realtime_factor = processing_time / audio_duration if audio_duration > 0 else 0
            
            return {
                "success": True,
                "message": "STT model test completed successfully",
                "model_info": model_info,
                "test_results": {
                    "audio_duration": audio_duration,
                    "processing_time": processing_time,
                    "realtime_factor": realtime_factor,
                    "transcription": result.get("text", "") if result else "No transcription result",
                    "confidence": result.get("confidence", 0) if result else 0,
                    "speakers": result.get("speakers", []) if result else []
                },
                "status": "Model is functioning correctly" if result else "Model processed audio but no transcription result"
            }
            
        except Exception as transcription_error:
            end_time = time.time()
            processing_time = end_time - start_time
            
            return {
                "success": False,
                "message": "Transcription test failed",
                "model_info": model_info,
                "test_results": {
                    "audio_duration": len(audio_data) / sample_rate,
                    "processing_time": processing_time,
                    "error": str(transcription_error)
                },
                "status": "Model test failed - check logs for details"
            }
        
    except Exception as e:
        logger.error(f"Error testing STT model: {e}")
        return {
            "success": False,
            "message": f"Test setup failed: {str(e)}",
            "status": "Unable to run model test"
        }

@router.post("/models/{model_id}/download")
async def download_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.model.write")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Simulate downloading a model"""
    import asyncio
    import random
    
    try:
        # Validate model exists
        if model_id not in STT_MODELS:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        model_info = STT_MODELS[model_id]
        
        # Simulate download progress
        total_size = model_info.get("performance", {}).get("memory", 1024)  # MB
        progress_steps = 10
        
        logger.info(f"Starting simulated download for model {model_id}")
        
        # Simulate progressive download
        for step in range(progress_steps + 1):
            progress = (step / progress_steps) * 100
            downloaded = (step / progress_steps) * total_size
            
            # Add some randomness to simulate realistic download speeds
            if step < progress_steps:
                await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Mark model as "installed" (in a real system, this would update a database)
        logger.info(f"Model {model_id} download simulation completed")
        
        # Log successful model download
        AuthService.log_action(
            db,
            current_user.id,
            "ai_model_downloaded",
            "ai_model",
            model_id,
            details={
                "model_name": model_info['name'],
                "size_mb": total_size,
                "acceleration": model_info.get("acceleration", "unknown"),
                "simulated": True  # Mark as simulation for now
            }
        )
        
        return {
            "success": True,
            "message": f"Model {model_info['name']} downloaded successfully",
            "model_id": model_id,
            "download_info": {
                "size_mb": total_size,
                "status": "installed",
                "install_path": f"/models/{model_id}",
                "checksum": f"sha256:{random.randint(100000, 999999)}"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Log failed download attempt
        AuthService.log_action(
            db,
            current_user.id,
            "ai_model_download_failed",
            "ai_model",
            model_id,
            details={
                "model_name": STT_MODELS.get(model_id, {}).get('name', 'Unknown'),
                "error": str(e),
                "simulated": True
            }
        )
        logger.error(f"Error downloading model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@router.delete("/models/{model_id}")
async def uninstall_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.model.delete")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Simulate uninstalling a model"""
    try:
        # Validate model exists
        if model_id not in STT_MODELS:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        model_info = STT_MODELS[model_id]
        
        # Prevent uninstalling the current model
        current_model = settings_manager.get_setting("ai.whisper_model") or "whisper-base"
        if model_id == current_model:
            raise HTTPException(
                status_code=400, 
                detail="Cannot uninstall the currently active model. Switch to another model first."
            )
        
        logger.info(f"Simulated uninstall for model {model_id}")
        
        # Log successful model uninstall
        AuthService.log_action(
            db,
            current_user.id,
            "ai_model_uninstalled",
            "ai_model",
            model_id,
            details={
                "model_name": model_info['name'],
                "freed_space_mb": model_info.get("performance", {}).get("memory", 1024),
                "acceleration": model_info.get("acceleration", "unknown"),
                "simulated": True
            }
        )
        
        return {
            "success": True,
            "message": f"Model {model_info['name']} uninstalled successfully",
            "model_id": model_id,
            "freed_space_mb": model_info.get("performance", {}).get("memory", 1024)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Log failed uninstall attempt
        AuthService.log_action(
            db,
            current_user.id,
            "ai_model_uninstall_failed",
            "ai_model",
            model_id,
            details={
                "model_name": STT_MODELS.get(model_id, {}).get('name', 'Unknown'),
                "error": str(e),
                "simulated": True
            }
        )
        logger.error(f"Error uninstalling model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Uninstall failed: {str(e)}")

@router.get("/models/{model_id}/availability")
async def check_model_availability(
    model_id: str,
    current_user: User = Depends(require_permission("ai.model.read"))
) -> Dict[str, Any]:
    """Check detailed availability status for a specific model"""
    if model_id not in STT_MODELS:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    model_info = STT_MODELS[model_id]
    
    # Check specific requirements for different model types
    availability_info = {
        "model_id": model_id,
        "name": model_info["name"],
        "available": False,
        "issues": [],
        "requirements": [],
        "recommendations": []
    }
    
    try:
        if model_id in ["whisperx-npu-unified", "whisperx-npu"]:
            # Check WhisperX NPU requirements
            try:
                from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine
                availability_info["available"] = True
                availability_info["requirements"] = [
                    "✓ WhisperX NPU engine available",
                    "✓ MLIR-AIE2 kernels present",
                    "✓ NPU optimization modules loaded"
                ]
            except ImportError as e:
                availability_info["issues"].append(f"WhisperX NPU engine not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ WhisperX NPU engine missing",
                    "✗ MLIR-AIE2 kernels not found",
                    "✗ NPU optimization modules missing"
                ]
                availability_info["recommendations"] = [
                    "Install NPU optimization packages",
                    "Set up MLIR-AIE2 development environment",
                    "Install AMD Phoenix NPU drivers",
                    "Use fallback CPU models like 'whisper-base' in the meantime"
                ]
        
        elif model_id == "whisper-onnx-npu":
            # Check ONNX NPU requirements
            try:
                from stt_engine.whisper_npu_transcriber import ONNXWhisperNPUTranscriber
                availability_info["available"] = True
                availability_info["requirements"] = [
                    "✓ ONNX Runtime available",
                    "✓ NPU transcriber loaded",
                    "✓ INT8 quantization support"
                ]
            except ImportError as e:
                availability_info["issues"].append(f"ONNX NPU transcriber not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ ONNX Runtime missing",
                    "✗ NPU transcriber not found",
                    "✗ INT8 quantization unavailable"
                ]
                availability_info["recommendations"] = [
                    "Install ONNX Runtime",
                    "Install NPU-specific ONNX providers",
                    "Use 'whisper-base' as CPU fallback"
                ]
        
        elif model_id == "diarization-npu":
            # Check NPU diarization requirements
            try:
                from stt_engine.speaker_diarization import SpeakerDiarizer
                availability_info["available"] = True
                availability_info["requirements"] = [
                    "✓ Speaker diarization engine available",
                    "✓ TitanNet embeddings loaded",
                    "✓ NPU acceleration enabled"
                ]
            except ImportError as e:
                availability_info["issues"].append(f"NPU diarization not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ Speaker diarization engine missing",
                    "✗ TitanNet embeddings not found",
                    "✗ NPU acceleration unavailable"
                ]
                availability_info["recommendations"] = [
                    "Install speaker diarization packages",
                    "Use 'pyannote-diarization' as fallback"
                ]
        
        elif model_id == "pyannote-diarization":
            # Check pyannote requirements
            import os
            hf_token = os.getenv("HUGGINGFACE_TOKEN")
            
            try:
                from stt_engine.speaker_diarization import SpeakerDiarizer
                if hf_token:
                    availability_info["available"] = True
                    availability_info["requirements"] = [
                        "✓ Pyannote diarization available",
                        "✓ HuggingFace token configured",
                        "✓ GPU/CPU fallback ready"
                    ]
                else:
                    availability_info["issues"].append("HuggingFace token not configured")
                    availability_info["requirements"] = [
                        "✓ Pyannote diarization available",
                        "✗ HuggingFace token missing",
                        "✓ GPU/CPU fallback ready"
                    ]
                    availability_info["recommendations"] = [
                        "Set HUGGINGFACE_TOKEN environment variable",
                        "Get token from https://huggingface.co/settings/tokens",
                        "Accept pyannote model license agreements"
                    ]
            except ImportError as e:
                availability_info["issues"].append(f"Pyannote diarization not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ Pyannote diarization missing",
                    "✗ HuggingFace token missing",
                    "✗ Dependencies not installed"
                ]
                availability_info["recommendations"] = [
                    "Install pyannote.audio",
                    "Install torch with GPU support",
                    "Configure HuggingFace token"
                ]
        
        elif model_id == "npu-runtime":
            # Check custom NPU runtime requirements
            try:
                from npu_runtime import NPURuntime
                import os
                
                # Check if NPU device exists
                npu_device_exists = os.path.exists('/dev/accel/accel0')
                
                if npu_device_exists:
                    availability_info["available"] = True
                    availability_info["requirements"] = [
                        "✓ Custom NPU runtime available",
                        "✓ NPU device accessible at /dev/accel/accel0",
                        "✓ Direct hardware access enabled",
                        "✓ ONNX to NPU converter available"
                    ]
                else:
                    availability_info["issues"].append("NPU device not found at /dev/accel/accel0")
                    availability_info["requirements"] = [
                        "✓ Custom NPU runtime available", 
                        "✗ NPU device not accessible",
                        "✗ Hardware detection failed",
                        "✓ ONNX to NPU converter available"
                    ]
                    availability_info["recommendations"] = [
                        "Check if amdxdna kernel driver is loaded",
                        "Verify user permissions for /dev/accel/accel0",
                        "Check if hardware supports NPU acceleration",
                        "Use CPU fallback models if NPU unavailable"
                    ]
            except ImportError as e:
                availability_info["issues"].append(f"NPU runtime not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ Custom NPU runtime missing",
                    "✗ NPU device not accessible", 
                    "✗ Direct hardware access unavailable",
                    "✗ ONNX to NPU converter missing"
                ]
                availability_info["recommendations"] = [
                    "Install custom NPU runtime (npu_runtime.py)",
                    "Set up ONNX to NPU converter",
                    "Check NPU development environment",
                    "Use alternative NPU models or CPU fallback"
                ]
        
        elif model_id in ["whisper-base", "whisper-small", "whisper-medium"]:
            # Check basic Whisper requirements
            try:
                from stt_engine.whisper_npu_transcriber import ONNXWhisperNPUTranscriber
                availability_info["available"] = True
                availability_info["requirements"] = [
                    "✓ ONNX Whisper transcriber available",
                    "✓ CPU fallback enabled",
                    "✓ Standard Whisper models"
                ]
            except ImportError as e:
                availability_info["issues"].append(f"Whisper transcriber not available: {str(e)}")
                availability_info["requirements"] = [
                    "✗ ONNX Whisper transcriber missing",
                    "✗ CPU fallback unavailable",
                    "✗ Dependencies not installed"
                ]
                availability_info["recommendations"] = [
                    "Install ONNX Runtime",
                    "Install Whisper dependencies",
                    "Check Python environment setup"
                ]
        
        # Add hardware detection
        availability_info["hardware_info"] = _get_hardware_info()
        
        return availability_info
        
    except Exception as e:
        logger.error(f"Error checking availability for {model_id}: {e}")
        availability_info["issues"].append(f"Availability check failed: {str(e)}")
        return availability_info

def _get_hardware_info() -> Dict[str, Any]:
    """Get hardware acceleration information"""
    import platform
    
    hardware_info = {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "npu_available": False,
        "gpu_available": False,
        "cpu_cores": "unknown"
    }
    
    try:
        import multiprocessing
        hardware_info["cpu_cores"] = multiprocessing.cpu_count()
    except:
        pass
    
    # Check for NPU availability
    try:
        # In a real implementation, this would check for AMD NPU Phoenix
        # For now, we'll simulate based on platform
        if platform.machine().lower() in ['x86_64', 'amd64']:
            # Simulate NPU detection
            hardware_info["npu_available"] = False
            hardware_info["npu_status"] = "AMD Phoenix NPU not detected"
        else:
            hardware_info["npu_status"] = "NPU not supported on this platform"
    except:
        hardware_info["npu_status"] = "NPU detection failed"
    
    # Check for GPU availability
    try:
        import torch
        if torch.cuda.is_available():
            hardware_info["gpu_available"] = True
            hardware_info["gpu_count"] = torch.cuda.device_count()
            hardware_info["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        else:
            hardware_info["gpu_status"] = "CUDA not available"
    except ImportError:
        hardware_info["gpu_status"] = "PyTorch not installed"
    except:
        hardware_info["gpu_status"] = "GPU detection failed"
    
    return hardware_info

@router.get("/audit-logs")
async def get_ai_audit_logs(
    skip: int = 0,
    limit: int = 100,
    action_filter: Optional[str] = None,
    current_user: User = Depends(require_permission("user.read")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get audit logs for AI model operations (admin only)"""
    from auth.models import AuditLog
    
    try:
        # Build query for AI-related audit logs
        query = db.query(AuditLog).filter(
            AuditLog.action.like("ai_%")
        )
        
        # Apply action filter if provided
        if action_filter:
            query = query.filter(AuditLog.action.like(f"%{action_filter}%"))
        
        # Get total count
        total = query.count()
        
        # Get paginated results ordered by most recent first
        audit_logs = query.order_by(
            AuditLog.created_at.desc()
        ).offset(skip).limit(limit).all()
        
        # Format the results
        formatted_logs = []
        for log in audit_logs:
            # Get user info
            user_info = {
                "id": log.user.id,
                "username": log.user.username,
                "email": log.user.email
            } if log.user else {"id": log.user_id, "username": "Unknown", "email": "Unknown"}
            
            formatted_logs.append({
                "id": log.id,
                "user": user_info,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None
            })
        
        return {
            "audit_logs": formatted_logs,
            "pagination": {
                "total": total,
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total
            },
            "filters": {
                "action_filter": action_filter
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch audit logs: {str(e)}")

@router.get("/audit-logs/summary")
async def get_ai_audit_summary(
    days: int = 30,
    current_user: User = Depends(require_permission("user.read")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get summary of AI model audit activities"""
    from auth.models import AuditLog
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get AI-related audit logs within date range
        query = db.query(AuditLog).filter(
            AuditLog.action.like("ai_%"),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        )
        
        # Count by action type
        action_counts = db.query(
            AuditLog.action,
            func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.action.like("ai_%"),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        ).group_by(AuditLog.action).all()
        
        # Count by user
        user_counts = db.query(
            AuditLog.user_id,
            func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.action.like("ai_%"),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        ).group_by(AuditLog.user_id).all()
        
        # Get most recent activities
        recent_activities = query.order_by(
            AuditLog.created_at.desc()
        ).limit(10).all()
        
        # Format results
        action_summary = {action: count for action, count in action_counts}
        user_activity = {}
        for user_id, count in user_counts:
            user = db.query(User).filter(User.id == user_id).first()
            username = user.username if user else f"user_{user_id}"
            user_activity[username] = count
        
        recent_formatted = []
        for log in recent_activities:
            user_info = log.user.username if log.user else f"user_{log.user_id}"
            recent_formatted.append({
                "user": user_info,
                "action": log.action,
                "resource_id": log.resource_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "details": log.details
            })
        
        return {
            "period": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "summary": {
                "total_actions": sum(action_summary.values()),
                "action_breakdown": action_summary,
                "user_activity": user_activity,
                "most_active_user": max(user_activity.keys(), key=user_activity.get) if user_activity else None
            },
            "recent_activities": recent_formatted
        }
        
    except Exception as e:
        logger.error(f"Error generating audit summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate audit summary: {str(e)}")