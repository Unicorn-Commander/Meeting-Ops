# Backend Dockerfile - Python 3.12 + NPU Support
FROM python:3.12-slim

# Install system dependencies for NPU and audio
RUN apt-get update && apt-get install -y \
    build-essential \
    portaudio19-dev \
    ffmpeg \
    git \
    curl \
    cmake \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements-docker.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copy application code
COPY . .

# Create directories for data and NPU kernels
RUN mkdir -p /app/data /app/recordings /app/whisper_onnx_cache /app/npu_kernels

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:////app/data/meeting_sessions.db
ENV PYTHON_VERSION=3.13
ENV NPU_KERNEL_CACHE_DIR=/app/npu_kernels

# NPU/XRT environment (when available)
ENV XRT_INI_PATH=/opt/xilinx/xrt/xrt.ini
ENV XILINX_XRT=/opt/xilinx/xrt

# Expose port
EXPOSE 9050

# Run the application (simplified for Docker)
CMD ["python", "-m", "uvicorn", "main_docker:app", "--host", "0.0.0.0", "--port", "9050"]