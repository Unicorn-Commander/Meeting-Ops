"""
Meeting-Ops Backend - Production main.py
Clean router loading with status tracking and real timestamps.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
import os
from typing import List

# Phase B.5: Prometheus /metrics ASGI app. Imported here so it's always
# available, even if api.streaming fails to load (degraded mode).
from prometheus_client import make_asgi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router loading status tracking
loaded_routers: List[str] = []
failed_routers: List[dict] = []

audio_monitor_task = None


def _load_router(app: FastAPI, name: str, module_path: str, router_attr: str = "router",
                 prefix: str = "", required: bool = False):
    """Load a router with status tracking. Required routers raise on failure."""
    try:
        module = __import__(module_path, fromlist=[router_attr])
        router = getattr(module, router_attr)
        app.include_router(router, prefix=prefix if prefix else "")
        loaded_routers.append(name)
        logger.info(f"Loaded router: {name}")
    except Exception as e:
        entry = {"name": name, "error": str(e)}
        failed_routers.append(entry)
        if required:
            logger.error(f"REQUIRED router failed: {name} - {e}")
            raise RuntimeError(f"Required router '{name}' failed to load: {e}")
        else:
            logger.warning(f"Optional router skipped: {name} - {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global audio_monitor_task

    logger.info("Starting Meeting-Ops Backend...")

    # Initialize database
    try:
        from database.database import init_database
        init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

    # Clean up stale sessions (created but never started)
    try:
        from database.database import SessionLocal
        from database.models import RecordingSession
        from datetime import timedelta
        cleanup_db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = cleanup_db.query(RecordingSession).filter(
            RecordingSession.status == "active",
            RecordingSession.started_at.is_(None),
            RecordingSession.created_at < cutoff
        ).all()
        if stale:
            for s in stale:
                s.status = "abandoned"
            cleanup_db.commit()
            logger.info(f"Cleaned up {len(stale)} stale sessions")
        cleanup_db.close()
    except Exception as e:
        logger.warning(f"Stale session cleanup failed: {e}")

    # Check transcription service. The legacy local NPU path stays inert when
    # DISABLE_LOCAL_AUDIO is set (cloud build); STT then routes through
    # ProviderRegistry.get_stt() instead, which is verified at upload time.
    try:
        import os as _os
        from services.transcription_service import transcription_service
        if transcription_service.is_ready:
            logger.info(f"Local transcription service ready: {transcription_service.current_model_id}")
        elif _os.getenv("DISABLE_LOCAL_AUDIO", "").strip().lower() in ("1", "true", "yes", "on"):
            logger.info("Local transcription service inert (DISABLE_LOCAL_AUDIO); STT via ProviderRegistry")
        else:
            logger.warning("Local transcription service not ready")
    except Exception as e:
        logger.warning(f"Transcription service check failed: {e}")

    try:
        from api.uploads import cleanup_stale_uploads, start_upload_pipeline_queue
        await start_upload_pipeline_queue()
        await cleanup_stale_uploads()
        logger.info("Upload pipeline initialized")
    except Exception as e:
        logger.warning(f"Upload pipeline initialization failed: {e}")

    try:
        from services.tts_jobs import tts_queue
        await tts_queue.start()
        logger.info("TTS render queue initialized")
    except Exception as e:
        logger.warning(f"TTS render queue initialization failed: {e}")

    try:
        from workers.bulk_import_worker import start_arq_worker
        await start_arq_worker()
        logger.info("Bulk import queue initialized")
    except Exception as e:
        logger.warning(f"Bulk import queue initialization failed: {e}")

    logger.info(f"Routers loaded: {len(loaded_routers)}, failed: {len(failed_routers)}")

    yield

    logger.info("Shutting down...")

    # Phase B.5 streaming-drain: send a server_shutdown JSON frame + 1001
    # close to every active WS session on /ws/sessions/{id}/live so the
    # frontend can reconnect cleanly after the deploy lands. The
    # useReconnectingWebSocket hook treats 1001 as a clean close and
    # does NOT auto-reconnect; the explicit shutdown frame lets the
    # client implement its own "reconnect_after_ms" hint. We give each
    # close a short timeout so a wedged socket doesn't block teardown.
    try:
        from api.streaming import active_sessions as _active_streaming_sessions

        # Snapshot the dict so iteration is safe even if a handler
        # finishes mid-iteration and tries to pop itself.
        snapshot = list(_active_streaming_sessions.items())
        if snapshot:
            logger.info(
                "Streaming drain: closing %d active WS session(s) with "
                "server_shutdown + close 1001",
                len(snapshot),
            )

            async def _drain_one(sid, ws):
                try:
                    await asyncio.wait_for(
                        ws.send_json({
                            "type": "server_shutdown",
                            "reason": "deployment",
                            "reconnect_after_ms": 3000,
                        }),
                        timeout=1.0,
                    )
                except Exception as exc:
                    logger.debug("drain send_json failed sid=%s err=%s", sid, exc)
                try:
                    await asyncio.wait_for(
                        ws.close(code=1001, reason="going_away"),
                        timeout=1.0,
                    )
                except Exception as exc:
                    logger.debug("drain close failed sid=%s err=%s", sid, exc)

            # Run all drains in parallel and cap the overall wait at 5 s.
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(_drain_one(sid, ws) for sid, ws in snapshot),
                        return_exceptions=True,
                    ),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Streaming drain hit 5s timeout; proceeding with shutdown")
    except Exception as e:
        # api.streaming may have failed to import (optional router); log
        # and continue without blocking the rest of shutdown.
        logger.debug(f"Streaming drain skipped: {e}")

    try:
        from api.uploads import stop_upload_pipeline_queue
        await stop_upload_pipeline_queue()
    except Exception as e:
        logger.warning(f"Upload pipeline shutdown failed: {e}")
    try:
        from services.tts_jobs import tts_queue
        await tts_queue.stop()
    except Exception as e:
        logger.warning(f"TTS render queue shutdown failed: {e}")
    try:
        from workers.bulk_import_worker import stop_arq_worker
        await stop_arq_worker()
    except Exception as e:
        logger.warning(f"Bulk import queue shutdown failed: {e}")
    if audio_monitor_task and not audio_monitor_task.done():
        audio_monitor_task.cancel()
        try:
            await audio_monitor_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Meeting-Ops API",
    description="AI-powered meeting recording and transcription system",
    version="0.5.0",
    lifespan=lifespan
)

_cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

app.add_middleware(
    CORSMiddleware,
    # In production: set CORS_ORIGINS env var. For LAN appliance: allow frontend port.
    allow_origins=_cors_origins or [],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$" if not _cors_origins else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Phase B.5: Prometheus /metrics endpoint ===
# Mounted as an ASGI sub-app so prometheus_client owns the text-format
# response + Content-Type header. Exposed unauthenticated by design:
# scraped by the centerdeep Prometheus on the internal Tailscale net.
# If you ever expose meeting-ops directly to the public internet, gate
# this behind oauth2-proxy via the ingress config (we run behind it on
# meetingops.magicunicorn.dev, so /metrics is already gated there).
app.mount("/metrics", make_asgi_app())

# === REQUIRED ROUTERS (fail fast if missing) ===
_load_router(app, "auth", "auth.routes", required=True)
# session_tags must precede recording so /recording-sessions/tags wins
# routing over /recording-sessions/{session_id} (the wildcard would swallow it).
_load_router(app, "session_tags", "api.sessions_tags")
_load_router(app, "recording", "api.simple_recording_db", required=True)
_load_router(app, "always_on_recordings", "api.recording", required=True)
# Brigade Phase 2 read endpoint — lives in api.recording but as a
# second router (no prefix) so the URL is /api/sessions/{id}/brigade-graph.
_load_router(
    app,
    "brigade_graph",
    "api.recording",
    router_attr="brigade_graph_router",
)
_load_router(app, "sessions", "api.sessions", prefix="/api", required=True)
# Per-meeting permissions (collaborators + magic-link share). Two
# routers in one module: `router` carries the auth'd per-session
# endpoints, `public_router` exposes the anonymous token-resolve.
_load_router(app, "session_permissions", "api.session_permissions")
_load_router(
    app,
    "session_permissions_public",
    "api.session_permissions",
    router_attr="public_router",
)
_load_router(app, "session_emails", "api.session_emails")
_load_router(app, "session_participants", "api.sessions_participants")
_load_router(app, "action_items", "api.action_items")
# Per-session file attachments: Granola notes, external transcripts,
# slide decks, photos, etc. `router` is the CRUD; `counts_router` is the
# cheap per-session paperclip-icon lookup for the Sessions list page.
_load_router(app, "session_attachments", "api.session_attachments")
_load_router(
    app,
    "session_attachment_counts",
    "api.session_attachments",
    router_attr="counts_router",
)
# Move-session-between-orgs: org reassignment with cascade + Qdrant re-tag.
_load_router(app, "session_move_org", "api.session_move_org")

# === CORE ROUTERS (optional but expected) ===
_load_router(app, "meeting_management", "api.meeting_management")
# v3.18.3: pass prefix="" explicitly to honor the routers' internal absolute
# paths (e.g. APIRouter(prefix="/api"). The 4 admin routers below previously
# had documentation drift suggesting a double-mount; passing prefix=""
# explicitly closes that ambiguity and makes the mount behavior obvious.
_load_router(app, "ai_settings", "api.ai_settings", prefix="")
# === PHASE 3 ROUTERS ===
_load_router(app, "agents", "api.agents")

_load_router(app, "agent_management", "api.agent_management_api", prefix="")
_load_router(app, "websocket_transcription", "api.websocket_transcription")
_load_router(app, "websocket_auto_summary", "api.websocket_auto_summary")
_load_router(app, "unified_agent", "api.unified_agent_api", prefix="")
_load_router(app, "live_transcription", "api.live_transcription")
_load_router(app, "analytics", "api.analytics_simple")
_load_router(app, "ai_insights", "api.ai_insights")
_load_router(app, "ai_chat", "api.ai_chat")
_load_router(app, "vocabulary", "api.vocabulary")
_load_router(app, "batch_export", "api.batch_export")
_load_router(app, "simple_settings", "api.simple_settings", prefix="")

# === SATELLITE DEVICE ROUTERS (optional) ===
_load_router(app, "satellite_api", "api.satellite_api")
_load_router(app, "websocket_satellite", "api.websocket_satellite")

# === CONFERENCE ROOM ROUTERS (optional) ===
# `router` carries /api/rooms/* (CRUD + sources + pairing + recordings + ACL).
# `system_router` carries /api/system/audio-devices for the setup wizard.
_load_router(app, "rooms", "api.rooms")
_load_router(app, "rooms_system", "api.rooms", router_attr="system_router")

# === COMPANION APP ROUTERS (optional) ===
_load_router(app, "websocket_remote_audio", "api.websocket_remote_audio")

# === PHASE 2 ROUTERS ===
_load_router(app, "provider_settings", "api.provider_settings")
_load_router(app, "integrations", "api.integrations")
# v3.19.0: per-org integration toggles + secrets (Brigade / Project-Ops /
# Contact-Ops / Accounting-Ops / Stable). See api/integrations_org.py.
_load_router(app, "integrations_org", "api.integrations_org")
_load_router(app, "digests", "api.digests")
_load_router(app, "agent_actions", "api.agent_actions")
_load_router(app, "personal_access_tokens", "api.personal_access_tokens")

# === PUBLIC LANDING PAGE (invite-only beta) ===
# Single endpoint /api/landing/invite-request, no auth, rate-limited per-IP.
# Powers the v3.19 public landing at meeting-ops.unicorncommander.ai/.
# Inert in dev if VITE_LANDING_PAGE_ENABLED=false on the frontend; the
# backend endpoint still loads either way so direct curl smoke works.
_load_router(app, "landing", "api.landing")

# === BILLING (Stripe Subscriptions) ===
# Webhook + checkout/portal/subscription endpoints. Inert until
# STRIPE_API_KEY + STRIPE_WEBHOOK_SECRET + STRIPE_PRO_PRICE_ID are set —
# routes return 503 in that case. See backend/api/billing.py for the
# request shapes and backend/api/stripe_webhook.py for the event
# dispatch table.
_load_router(app, "stripe_webhook", "api.stripe_webhook")
_load_router(app, "billing", "api.billing")

# === PHASE 3 ROUTERS ===
_load_router(app, "speakers", "api.speakers")

# === PHASE 4A ROUTERS ===
_load_router(app, "uploads", "api.uploads")
_load_router(app, "upload_websocket", "api.uploads", router_attr="ws_router")

# === BULK AUDIO IMPORT (B-import.1) ===
# Powers the /import page that ingests Aaron 526-file audio archive (and
# any other bulk import workflow). Per-file pipeline runs in the
# BulkImportPipelineQueue worker pool started by the lifespan hook above.
_load_router(app, "bulk_import", "api.imports")
_load_router(app, "bulk_import_admin", "api.admin_imports")



# === PHASE 4C-2 ROUTERS ===
_load_router(app, "tts", "api.tts")
_load_router(app, "tts_websocket", "api.tts", router_attr="ws_router")
_load_router(app, "system_caps", "api.system_caps")
# v3.18.3 background-jobs: generic poll endpoint for arq job status.
_load_router(app, "jobs", "api.jobs")

# === PHASE B.1 ROUTERS (server-live streaming scaffolding) ===
# /ws/sessions/{session_id}/live — auth via oauth2-proxy forward headers,
# logs binary frames per the 19-byte header protocol in
# docs/phase-b-server-live-streaming.md and acks them. Real Parakeet
# forwarding is Phase B.2.
_load_router(app, "streaming", "api.streaming")



# === CORE API ENDPOINTS ===

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Meeting-Ops API",
        "version": "0.5.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check with router status"""
    has_failures = len(failed_routers) > 0

    # v3.18.3: report streaming-degraded state when neither stdlib audioop
    # nor the audioop-lts back-port is available (py3.13+ moat).
    streaming_audioop_ok = True
    try:
        from api import streaming as _streaming
        streaming_audioop_ok = _streaming.audioop is not None
    except Exception:  # pragma: no cover - streaming router not loaded
        streaming_audioop_ok = True

    degraded = has_failures or not streaming_audioop_ok
    return {
        "status": "degraded" if degraded else "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routers_loaded": len(loaded_routers),
        "routers_failed": failed_routers if has_failures else [],
        "streaming_audioop": "ok" if streaming_audioop_ok else "missing",
    }


@app.get("/api/status")
async def get_status():
    """Get system status"""
    try:
        npu_available = os.path.exists("/dev/accel/accel0")

        from services.transcription_service import transcription_service
        transcription_ready = transcription_service and transcription_service.is_ready
        model_loaded = transcription_service.current_model_id if transcription_service else "none"

        audio_devices = []
        try:
            from services.working_audio_service import WorkingAudioService
            audio_service = WorkingAudioService()
            audio_devices = audio_service.get_audio_devices()
        except Exception as e:
            logger.error(f"Failed to get audio devices: {e}")

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcription": {
                "ready": transcription_ready,
                "model": model_loaded,
                "engine": "whisperx-npu" if transcription_ready else "none"
            },
            "npu": {
                "available": npu_available,
                "device": "/dev/accel/accel0" if npu_available else None,
                "status": "active" if npu_available and transcription_ready else "idle"
            },
            "audio": {
                "devices_count": len(audio_devices),
                "server_mic_available": any("usb" in d.get("name", "").lower() or
                                           "m-305" in d.get("name", "").lower()
                                           for d in audio_devices)
            },
            "services": {
                "recording": True,
                "transcription": transcription_ready,
                "ai_notes": True,
                "websockets": True
            },
            "routers": {
                "loaded": len(loaded_routers),
                "failed": len(failed_routers),
            }
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/audio-devices")
async def get_audio_devices():
    """Get list of available audio input devices"""
    try:
        from services.working_audio_service import WorkingAudioService
        audio_service = WorkingAudioService()
        devices = audio_service.get_audio_devices()
        return {"devices": devices, "status": "success"}
    except Exception as e:
        logger.error(f"Failed to get audio devices: {e}")
        return {"devices": [], "status": "error", "message": str(e)}


@app.get("/api/system-info")
async def get_system_info():
    """Get detailed system information"""
    import platform
    import psutil

    try:
        npu_available = os.path.exists("/dev/accel/accel0")

        from services.transcription_service import transcription_service
        transcription_ready = transcription_service and transcription_service.is_ready
        model_loaded = transcription_service.current_model_id if transcription_service else "none"

        return {
            "system": {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "memory_available": psutil.virtual_memory().available
            },
            "npu": {
                "available": npu_available,
                "device_path": "/dev/accel/accel0" if npu_available else None,
                "status": "active" if npu_available and transcription_ready else "idle",
                "driver": "MLIR-AIE2" if npu_available else None
            },
            "transcription": {
                "service_ready": transcription_ready,
                "current_model": model_loaded,
                "engine_type": "whisperx-npu" if transcription_ready else "none",
                "performance_factor": "220x speedup" if npu_available else "CPU-only"
            },
            "version": "0.5.0",
            "build": "production"
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9050)
