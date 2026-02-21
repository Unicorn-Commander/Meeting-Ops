"""
AI Backend Configuration
Single Granite 3.3 2B on llama.cpp Vulkan via OpenAI-compatible API
"""
import os
import logging

logger = logging.getLogger(__name__)

# Default to GPU-accelerated backend
AI_BACKEND = os.getenv("AI_BACKEND", "llamacpp")

# Backend configurations - Single Granite 3.3 2B model
AI_BACKENDS = {
    "llamacpp": {
        "url": os.getenv("LLAMACPP_URL", "http://localhost:11437"),
        "endpoint": "/v1/chat/completions",
        "type": "llamacpp",
        "name": "Granite 3.3 2B (llama.cpp Vulkan)",
        "model": "granite-3.3-2b-instruct",
        "timeout": 30,
        "health_check": "/health"
    }
}

def get_ai_backend(backend_name: str = None):
    """Get AI backend configuration"""
    backend_name = backend_name or AI_BACKEND

    if backend_name not in AI_BACKENDS:
        logger.warning(f"Unknown backend {backend_name}, falling back to llamacpp")
        backend_name = "llamacpp"

    backend = AI_BACKENDS[backend_name].copy()
    logger.info(f"Using AI backend: {backend['name']} at {backend['url']}")
    return backend

def check_backend_health(backend_config: dict) -> bool:
    """Check if backend is available"""
    import requests
    try:
        url = f"{backend_config['url']}{backend_config['health_check']}"
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Backend health check failed: {e}")
        return False

def get_available_backend():
    """Get the Granite 3.3 2B backend"""
    backend_name = "llamacpp"
    backend = AI_BACKENDS[backend_name]

    if check_backend_health(backend):
        logger.info(f"{backend['name']} is available")
        return backend_name, backend

    # If GPU backend not available, warn but return config anyway
    logger.warning("GPU backend not responding - ensure llama.cpp is running on port 11437")
    logger.warning("   Start with: docker compose -f docker-compose-full-stack.yml up -d")
    return backend_name, backend
