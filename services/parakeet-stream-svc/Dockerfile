# parakeet-stream-svc — Phase B.1 scaffolding for server-live streaming
# Targets: midboy2 GPU 0 (RTX 3060), reachable over Tailscale + meet-internal docker network
#
# This image is intentionally CPU-only and dependency-light. It exposes a stub
# /transcribe-stream endpoint that returns dummy partial transcripts so the
# end-to-end WS seam (Cloudflare -> oauth2-proxy -> Traefik -> meet-backend
# -> meet-parakeet-stream-svc) can be proven before we wire in the actual
# Parakeet 0.6B v3 streaming model. The real CUDA + NeMo build lands in
# Phase B.2 per docs/phase-b-server-live-streaming.md sections 5-7.
#
# Build:  docker build -t meet-parakeet-stream-svc:local .
# Run:    docker run -d --name meet-parakeet-stream-svc -p 8895:8895 \
#           meet-parakeet-stream-svc:local

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip wheel \
    && python -m pip install -r requirements.txt

COPY . .

EXPOSE 8895

# Cheap healthcheck — the scaffolding image has no model to probe, so /healthz
# is HTTP-up only. The B.2 image will replace this with a synthetic-WAV probe
# in the same style as speaker-svc /healthz/synthetic.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -fsS http://localhost:8895/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8895", "--workers", "1"]
