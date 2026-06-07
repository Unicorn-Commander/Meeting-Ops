"""Guard against worker/backend env drift in the bigboy compose.

The Arq reprocess worker (`meet-bulk-import-worker`) runs the SAME STT ->
diarize -> summarize -> index pipeline as the `backend`, so it needs the same
model-service endpoints. When it silently lacked them, every server-side
reprocess failed ("Temporary failure in name resolution / no segments") and
recordings never produced a summary. This test fails if the worker is missing
any model-service env var the backend declares, so the drift can't recur.
"""
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "bigboy"
    / "docker-compose.bigboy.yml"
)

# Names whose absence on the worker breaks the reprocess pipeline.
SERVICE_VAR_RE = re.compile(
    r"^(PARAKEET|SORTFORMER|SPEAKER|EMBEDDING|INFINITY|RERANKER|LLM_MODEL|"
    r"MEETING_OPS_LLM|MEETING_OPS_SUMMARIZER|OPENAI|LLAMA|QDRANT|GARAGE)"
)


def _env_names(service: dict) -> set[str]:
    env = service.get("environment", [])
    names: set[str] = set()
    if isinstance(env, list):
        for item in env:
            names.add(str(item).split("=", 1)[0].strip())
    elif isinstance(env, dict):
        names.update(str(k) for k in env)
    return names


def test_worker_has_backend_model_service_env():
    if not COMPOSE.exists():
        pytest.skip(f"compose not found at {COMPOSE}")
    data = yaml.safe_load(COMPOSE.read_text())
    services = data.get("services", {})
    backend = services.get("backend")
    worker = services.get("meet-bulk-import-worker")
    assert backend and worker, "backend / meet-bulk-import-worker services missing"

    backend_service_vars = {v for v in _env_names(backend) if SERVICE_VAR_RE.match(v)}
    worker_vars = _env_names(worker)
    missing = sorted(backend_service_vars - worker_vars)
    assert not missing, (
        "meet-bulk-import-worker is missing model-service env the backend "
        "declares; the reprocess pipeline will fail (Parakeet/LLM unreachable). "
        "Add these to the worker service env: " + ", ".join(missing)
    )
