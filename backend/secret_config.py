"""Mounted-file support for deployment secrets, without changing env fallback.

A nonempty NAME_FILE (UTF-8, surrounding whitespace removed) wins. Missing,
unreadable, invalid-text or empty files fall back to NAME, preserving its value
exactly. Callers retain their existing validation, alternate-key precedence,
and configuration lifetime: this helper does not hot-reload cached clients.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
_warned: set[tuple[str, str]] = set()


def _warn(name: str, reason: str) -> None:
    marker = (name, reason)
    if marker not in _warned:
        _warned.add(marker)
        # Source names/reasons only: no value, file contents or filesystem path.
        logger.warning("%s_FILE unavailable (%s); falling back to %s env", name, reason, name)


def _resolve(name: str) -> tuple[Optional[str], str]:
    path = (os.getenv(f"{name}_FILE") or "").strip()
    if path:
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError, ValueError) as exc:
            _warn(name, type(exc).__name__)
        else:
            if value:
                return value, "file"
            _warn(name, "empty")
    value = os.getenv(name)
    return value, "env" if value else "none"


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Like getenv, with a preferred file; preserve empty env versus unset."""
    value, _ = _resolve(name)
    return default if value is None else value


def configured_secret_source(name: str) -> str:
    """Return only file/env/none for this named key, not fallback aliases.

    This reports current resolver inputs, not a previously initialized client.
    Import-time consumers must be recreated before same-value relocation can
    be considered verified in the running application.
    """
    return _resolve(name)[1]
