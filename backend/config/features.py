"""Deployment feature flags.

These flags toggle whole subsystems on / off per deploy target. They are
read once at import time so they're cheap to check in hot endpoint paths.

Flags
-----
ROOM_MODE_ENABLED:
    Conference Room mode (Meeting-Ops appliance running on dedicated room
    hardware with a USB mic). On VPS / cloud deploys there is no physical
    mic and rooms cannot record, so we ship the endpoints disabled by
    default in cloud compose. Bigboy + on-prem appliance compose keep it
    on (default True). Endpoints return HTTP 503 when disabled.

Add new flags here, then pass them through the per-deploy compose
``environment:`` block (see ``deploy/*/docker-compose.*.yml``).
"""
from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Conference Room mode — defaults ON (preserves bigboy appliance behavior).
# Cloud / VPS compose should set ROOM_MODE_ENABLED=false explicitly.
ROOM_MODE_ENABLED: bool = _bool("ROOM_MODE_ENABLED", True)
