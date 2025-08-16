# Ollama - DEPRECATED

## Status: NOT IN USE

This folder contains the deprecated Ollama setup. The Meeting-Ops system now uses GPU-accelerated llama.cpp on port 11437 for all AI operations.

## Why Deprecated?

- **Performance**: Ollama was causing 100% CPU usage during AI operations
- **Speed**: GPU llama.cpp is 55% faster (0.8s vs 1.8s per summary)
- **Consistency**: Single AI backend simplifies the system

## Current AI Backend

The system now uses:
- **Service**: GPU-accelerated llama.cpp
- **Port**: 11437
- **Model**: granite3.3:8b
- **Location**: Main docker-compose.yml

## DO NOT START THIS SERVICE

This Ollama setup is kept only for:
1. Historical reference
2. Emergency fallback (not recommended)
3. Testing comparisons

## If You Must Use Ollama

**Warning**: This will degrade performance significantly!

```bash
# Start Ollama (not recommended)
cd /home/ucadmin/Meeting-Ops/extensions/ollama
docker-compose up -d

# Stop Ollama
docker-compose down
```

## Migration Notes

- All backend services updated to use GPU llama.cpp
- Configuration: `/backend/config/ai_backends.py`
- Default backend: `llamacpp` on port 11437
- Ollama references removed from main codebase

## Performance Comparison

| Metric | Ollama (CPU) | llama.cpp (GPU) |
|--------|--------------|-----------------|
| Port | 11434 | 11437 |
| Inference Time | ~1.8s | ~0.8s |
| CPU Usage | 100% | ~5% |
| GPU Usage | 0% | 99% |
| Tokens/sec | ~10 | ~15.5 |

## Recommendation

**DO NOT USE OLLAMA**. Keep using the GPU-accelerated llama.cpp for all AI operations.