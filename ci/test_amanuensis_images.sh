#!/usr/bin/env bash
set -euo pipefail
# CI only: use the exact published digests. No GPU, mounts, host network or model credentials.
image() { python3 -c 'import json,sys; print(json.load(open("deploy/amanuensis/images.lock.json"))["images"][sys.argv[1]])' "$1"; }
for svc in parakeet-svc parakeet-stream-svc speaker-svc parakeet-openai-shim; do
  docker pull "$(image "$svc")"
done
docker run --rm --network none --entrypoint python "$(image parakeet-svc)" -m compileall -q /app/main.py
docker run --rm --entrypoint sh "$(image speaker-svc)" -c 'python -m pip install pytest==8.3.5 httpx==0.28.1 && SPEAKER_EAGER_LOAD_EMBEDDER=false SPEAKER_EAGER_LOAD_DIARIZER=false python -m pytest tests/test_healthz_synthetic.py -q'
docker run --rm --entrypoint sh "$(image parakeet-stream-svc)" -c 'python -m pip install pytest==8.3.5 && python -m pytest tests/test_opus_decoder.py -q'
docker run --rm --network none --entrypoint python "$(image parakeet-openai-shim)" -c 'from main import app; assert any(r.path == "/v1/audio/transcriptions" for r in app.routes)'
