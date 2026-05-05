# parakeet-svc — NVIDIA NeMo Parakeet-TDT ASR microservice
# Targets: bigboy GPU 1 (Quadro RTX 6000), CUDA 12.x, joined to meet-internal network
#
# Build:  docker build -t meet-parakeet-svc:local .
# Run:    docker run -d --gpus '"device=1"' -p 8881:8881 \
#           -e HUGGINGFACE_TOKEN=... -v /opt/parakeet-models:/models \
#           --name meet-parakeet-svc meet-parakeet-svc:local
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf \
    NEMO_CACHE_DIR=/models/nemo \
    TORCH_HOME=/models/torch \
    HYDRA_FULL_ERROR=1

# Use the Ubuntu 22.04 default Python 3.10 — Jammy's python3.11 package is
# 3.11.0rc1 and segfaults loading some NeMo ASR modules.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip python3-dev \
        ffmpeg libsndfile1 libsox-fmt-all sox \
        ca-certificates curl git \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3 1

WORKDIR /app

COPY requirements.txt .

# torch/torchaudio first (CUDA 12.4 wheels), then NeMo on top.
# NeMo's pip resolver fights torch/torchaudio versions if installed together.
RUN python -m pip install --upgrade pip wheel setuptools \
    && python -m pip install --extra-index-url https://download.pytorch.org/whl/cu124 \
        torch==2.4.1 torchaudio==2.4.1 \
    && python -m pip install -r requirements.txt

COPY . .

EXPOSE 8881

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=240s \
    CMD curl -fsS http://localhost:8881/health || exit 1

# Single worker — the model is loaded once at startup and kept warm.
# Adding workers would multiply the VRAM cost and serialize on the GPU anyway.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8881", "--workers", "1"]
