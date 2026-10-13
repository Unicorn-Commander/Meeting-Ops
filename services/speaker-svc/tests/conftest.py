"""Pytest fixtures for speaker-svc unit tests.

We don't want the tests to actually load pyannote / wespeaker models — they
are gigabytes and need a HuggingFace token. The /healthz/synthetic tests
mock out _run_diarization_on_wav at the boundary instead.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# Make `import main` work when pytest is run from anywhere.
SVC_ROOT = Path(__file__).resolve().parent.parent
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

# The backend test venv intentionally does not carry the multi-gigabyte GPU
# stack used by the container image.  Keep the HTTP health tests runnable in
# that venv by providing only the import-time torch/torchaudio surface they
# need; tests that exercise model inference still belong in the service image.
try:
    import torch  # noqa: F401
except ModuleNotFoundError:
    torch_stub = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

        @staticmethod
        def get_device_name(_index: int) -> str:
            return "stub"

        @staticmethod
        def empty_cache() -> None:
            return None

    torch_stub.cuda = _Cuda()
    torch_stub.device = lambda name: name
    torch_stub.from_numpy = lambda value: value
    torch_stub.inference_mode = types.SimpleNamespace
    torch_stub.no_grad = types.SimpleNamespace
    sys.modules["torch"] = torch_stub

try:
    import torchaudio  # noqa: F401
except ModuleNotFoundError:
    torchaudio_stub = types.ModuleType("torchaudio")
    torchaudio_stub.functional = types.SimpleNamespace(resample=lambda value, *_args: value)
    sys.modules["torchaudio"] = torchaudio_stub
