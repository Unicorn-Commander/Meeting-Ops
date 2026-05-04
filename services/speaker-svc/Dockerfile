# speaker-svc — SpeechBrain ECAPA + optional Pyannote 3.1 diarization
# Targets: bigboy GPU 1 (Quadro RTX 6000), CUDA 12.x, joined to meet-internal network
#
# Build:  docker build -t meet-speaker-svc:local .
# Run:    docker run -d --gpus '"device=1"' -p 8889:8889 \
#           -e HUGGINGFACE_TOKEN=... -v /opt/speaker-models:/models \
#           --name meet-speaker-svc meet-speaker-svc:local
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf \
    SPEECHBRAIN_FETCH_LOCAL=true \
    TORCH_HOME=/models/torch

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg libsndfile1 libsox-fmt-all sox \
        ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip wheel \
    && python -m pip install --extra-index-url https://download.pytorch.org/whl/cu124 \
        torch==2.4.1 torchaudio==2.4.1 \
    && python -m pip install -r requirements.txt

# Pre-fetch SpeechBrain ECAPA at build time so first request isn't a 200 MB cold start.
# Pyannote 3.1 is gated; we do NOT pre-fetch it here. It is downloaded on first /diarize
# call when HUGGINGFACE_TOKEN is set and the user has accepted the model terms.
RUN python -c "from speechbrain.inference.speaker import EncoderClassifier; \
EncoderClassifier.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb', \
savedir='/models/ecapa', run_opts={'device':'cpu'})"

COPY . .

EXPOSE 8889

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=60s \
    CMD curl -fsS http://localhost:8889/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8889", "--workers", "1"]
