"""System capabilities endpoint.

Lets the frontend ask the backend "is this the cloud build or the UC-1
appliance build?" so it can hide irrelevant settings tabs (recording
devices, NPU, network config, etc.) on hosts that don't have that
hardware. The signal is the same DISABLE_LOCAL_AUDIO env var that already
gates the legacy NPU services on the backend.
"""
import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["System"])


def _local_audio_disabled() -> bool:
    val = os.getenv("DISABLE_LOCAL_AUDIO", "").strip().lower()
    return val in ("1", "true", "yes", "on")


@router.get("/capabilities")
async def get_capabilities() -> dict:
    """Return host capability flags.

    Public endpoint (no auth) — answers tell the frontend which UI surfaces
    to render and don't reveal secrets. Currently:
    - local_audio: True when a local mic / sound card path is expected
      (UC-1 appliance build). False on the cloud SaaS build.
    - npu: True when the AMD XDNA NPU is present. Implies local_audio.
    """
    local_audio = not _local_audio_disabled()
    return {
        "local_audio": local_audio,
        "npu": local_audio and os.path.exists("/dev/accel/accel0"),
        "build": "appliance" if local_audio else "cloud",
    }
