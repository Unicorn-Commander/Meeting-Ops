# meet-parakeet-stream-svc

Streaming-ASR microservice for the Phase B server-live path, deployed on
midboy2 alongside the existing batch `parakeet-svc` (which keeps handling
completed-audio reprocess).

## Status: Phase B.1 scaffolding only

This commit ships the **container + endpoint surface** but does **not**
load the actual Parakeet 0.6B v3 streaming model. The real model
integration is Phase B.2 (~2-3 days of work) per
[`docs/phase-b-server-live-streaming.md`](../../docs/phase-b-server-live-streaming.md)
sections 5-7.

What's here today:

- `GET /healthz` — HTTP-up liveness probe (`model_loaded: false`).
- `POST /transcribe-stream` — accepts any payload, returns a fixed
  `"[B.1 scaffold] stub transcript"` so the meet-backend WS endpoint
  can later forward frames here without changing call shape.
- Python 3.11-slim base, FastAPI + uvicorn + pydantic only — no
  CUDA, no NeMo, no PyTorch in B.1.

What's coming in B.2:

- Switch base image to `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`
  to match `parakeet-svc`.
- Load Parakeet 0.6B v3 (the streaming variant; the existing batch
  service runs the 1.1B FastConformer model).
- Accept the 19-byte binary frame header from the meet-backend
  (sequence + ts_us + format + sr/100 + flags), decode the PCM16
  payload, push through the FastConformer streaming chunker, emit
  partial + final transcript events back.
- Replace the HTTP-up healthcheck with a synthetic-WAV probe in the
  same shape as `speaker-svc /healthz/synthetic`.

## Why a separate streaming container

The existing `parakeet-svc` runs Parakeet-TDT 1.1B against whole audio
files at session completion. That's optimised for accuracy and batch
throughput. The streaming path needs a different model + chunker:

- **0.6B v3 streaming variant** for sub-300ms partials per design doc
  section 6.
- **Per-stream model state** (chunker buffers, attention cache) that's
  awkward to retrofit into the batch container without poisoning batch
  latency.
- **Independent scaling** — streaming load is concurrent-meeting-bound,
  batch load is queue-depth-bound. Splitting the containers lets each
  scale on its own knob.

Both containers share GPU 0 on midboy2; combined VRAM headroom is fine
with the 12 GB RTX 3060 once the 0.6B v3 weights land (estimated ~2-3
GB resident on top of the 4.3 GB the batch 1.1B currently holds).

## Build + run on midboy2

The midboy2 runtime compose lives **on the midboy2 host** (not in this
repo) at `/home/muut/uc-meeting-ops-deploy/midboy2/docker-compose.midboy2.yml`.
See `project_midboy2_service_map.md` in user memory for the deploy
convention.

```bash
# from the bigboy worktree:
rsync -av services/parakeet-stream-svc/ \
  midboy2:/home/muut/uc-meeting-ops-deploy/midboy2/meet-parakeet-stream-svc/

ssh midboy2 'cd /home/muut/uc-meeting-ops-deploy/midboy2 \
  && docker compose -f docker-compose.midboy2.yml build meet-parakeet-stream-svc \
  && docker compose -f docker-compose.midboy2.yml up -d meet-parakeet-stream-svc'
```

Verify:

```bash
ssh midboy2 'docker ps --format "{{.Names}} {{.Status}}" | grep parakeet-stream'
ssh midboy2 'curl -sS http://localhost:8895/healthz'
```

Expected:

```json
{"status":"ok","version":"0.1.0-scaffold","model_loaded":false,"phase":"B.1"}
```

## Networking

- Port: **8895** on midboy2 host (picked to sit alongside `parakeet-svc:8881`
  and `speaker-svc:8889` in the 88xx band).
- The meet-backend on bigboy reaches it over Tailscale at
  `http://100.66.42.57:8895` in B.2 (same Tailscale address as the
  other midboy2 services).
- No public ingress. The only client is meet-backend.

## API contract (B.1 stub)

```bash
curl -sS http://localhost:8895/healthz
# -> {"status":"ok","version":"0.1.0-scaffold","model_loaded":false,"phase":"B.1"}

# B.2 will replace this body with PCM16 audio frames; in B.1 any bytes work:
curl -sS -X POST http://localhost:8895/transcribe-stream \
  --data-binary 'whatever-bytes'
# -> {"partial":"[B.1 scaffold] stub transcript","is_final":false, ... }
```

## References

- Design doc: `docs/phase-b-server-live-streaming.md`
- Sibling service (batch): `services/parakeet-svc/`
- Sibling service (diarization): `services/speaker-svc/`
- Frontend test page (B.1): `frontend/src/pages/StreamingTest.tsx`
- meet-backend WS endpoint (B.1): `backend/api/streaming.py`
