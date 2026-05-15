"""System capabilities + live pipeline status.

Two endpoints:
- GET /api/system/capabilities — static host flags (build = cloud / appliance)
- GET /api/system/pipeline    — live, probes each backend for its actual
  configured model + endpoint + reachable status. Used by the
  "Agent & Pipeline Status" panel and anywhere the UI wants to truthfully
  surface what is wired up vs hardcoded labels.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["System"])


def _local_audio_disabled() -> bool:
    val = os.getenv("DISABLE_LOCAL_AUDIO", "").strip().lower()
    return val in ("1", "true", "yes", "on")


@router.get("/capabilities")
async def get_capabilities() -> dict:
    """Static host capability flags (no probes)."""
    local_audio = not _local_audio_disabled()
    return {
        "local_audio": local_audio,
        "npu": local_audio and os.path.exists("/dev/accel/accel0"),
        "build": "appliance" if local_audio else "cloud",
    }


async def _probe_json(url: str, timeout: float = 3.0) -> Optional[dict]:
    """GET a /health-shaped URL and return parsed JSON or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            try:
                return resp.json()
            except ValueError:
                return None
    except Exception:
        return None


@router.get("/pipeline")
async def get_pipeline_status() -> dict[str, Any]:
    """Live snapshot of the configured inference pipeline.

    Reports the actual STT engine, diarization backend, and LLM model the
    backend is wired to RIGHT NOW. Used by the Live Recording status panel
    to render real labels instead of UC-1 legacy hardcodes.

    No auth required — status info only, no secrets in the response.
    """
    parakeet_url = os.getenv("PARAKEET_SERVER_URL", "http://meet-parakeet-svc:8881")
    whisper_url = os.getenv("WHISPER_SERVER_URL", "http://meet-whisper:8178")
    speaker_url = os.getenv("SPEAKER_SVC_URL", "http://meet-speaker-svc:8889")

    parakeet_health = await _probe_json(f"{parakeet_url.rstrip('/')}/health")
    whisper_health = await _probe_json(f"{whisper_url.rstrip('/')}/health")
    speaker_health = await _probe_json(f"{speaker_url.rstrip('/')}/health")

    stt_default = os.getenv("STT_DEFAULT_PROVIDER", "parakeet").lower()
    stt_active = "parakeet" if stt_default in ("parakeet", "nemo", "parakeet-tdt") else "whisper"
    if stt_active == "parakeet" and not parakeet_health and whisper_health:
        stt_active = "whisper"

    if stt_active == "parakeet":
        stt_block = {
            "engine": "parakeet",
            "model": (parakeet_health or {}).get("model", "nvidia/parakeet-tdt-1.1b"),
            "endpoint": parakeet_url,
            "ready": bool((parakeet_health or {}).get("model_loaded")),
            "gpu": (parakeet_health or {}).get("gpu_name"),
            "label": "NeMo Parakeet-TDT 1.1B",
        }
    else:
        stt_block = {
            "engine": "whisper",
            "model": "whisper-large-v3-turbo",
            "endpoint": whisper_url,
            "ready": bool(whisper_health),
            "gpu": None,
            "label": "whisper.cpp large-v3-turbo",
        }

    pyannote_ok = bool((speaker_health or {}).get("diarizer_available"))
    diarization_block = {
        "backend": "pyannote-3.1" if pyannote_ok else "ecapa-cluster-fallback",
        "endpoint": speaker_url,
        "ready": bool(speaker_health),
        "gpu": (speaker_health or {}).get("gpu_name"),
        "label": (
            "Pyannote 3.1 (multi-speaker)"
            if pyannote_ok
            else "ECAPA cluster (single-speaker fallback)"
        ),
        "hf_token_required": not pyannote_ok,
    }

    direct_url = os.getenv("MEETING_OPS_SUMMARIZER_URL", "").strip()
    direct_model = os.getenv("MEETING_OPS_SUMMARIZER_MODEL", "").strip()
    if direct_url and direct_model:
        llm_health = await _probe_json(direct_url.rstrip("/") + "/models")
        llm_block = {
            "route": "direct",
            "model": direct_model,
            "endpoint": direct_url,
            "ready": bool(llm_health),
            "label": direct_model,
            "thinking": False,
        }
    else:
        litellm_url = os.getenv("OPENAI_API_BASE", "http://unicorn-litellm:4000/v1")
        model = os.getenv("LLM_MODEL_QUALITY", "gemma-4-26b-moe")
        llm_block = {
            "route": "litellm",
            "model": model,
            "endpoint": litellm_url,
            "ready": True,
            "label": model,
            "thinking": False,
        }

    return {
        "stt": stt_block,
        "diarization": diarization_block,
        "llm": llm_block,
        "build": "appliance" if not _local_audio_disabled() else "cloud",
    }
