"""Safe rendering of configured service URLs.

Configured service URLs are used with their original value by callers.  This
module is only for values that cross a response or logging boundary.
"""

from __future__ import annotations

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit


URL_REDACTION_PLACEHOLDER = "<invalid URL>"
_MASK = "***"

# Match both the exact names and common qualified forms such as
# ``client_secret`` and ``x-api-key``.  Deliberately do not match arbitrary
# substrings such as ``monkey`` just because it contains ``key``.
_SECRET_QUERY_NAMES = {
    "token",
    "key",
    "secret",
    "password",
    "pass",
    "sig",
    "signature",
    "auth",
    "apikey",
    "api_key",
    "access_token",
}
_SECRET_QUERY_PARTS = _SECRET_QUERY_NAMES | {
    "accesstoken",
    "apikey",
}
_QUERY_NAME_PART_RE = re.compile(r"[a-z0-9]+")


def _is_secret_query_name(raw_name: str) -> bool:
    """Return whether a query parameter name identifies a secret value."""
    try:
        name = unquote_plus(raw_name).strip().lower()
    except Exception:  # pragma: no cover - urllib is intentionally defensive
        return True

    normalized = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    if normalized in _SECRET_QUERY_NAMES:
        return True

    parts = set(_QUERY_NAME_PART_RE.findall(name))
    if parts & _SECRET_QUERY_PARTS:
        return True

    # Also cover compact names such as ``clientsecret`` without treating
    # unrelated words containing the short markers ``key`` or ``pass`` as
    # credentials.
    return any(
        marker in normalized
        for marker in ("token", "secret", "password", "signature", "apikey")
    )


def _redact_query(query: str) -> str:
    """Mask secret query values without normalizing unrelated query text."""
    if not query:
        return ""

    # Keep separators and non-secret values byte-for-byte.  ``parse_qsl``
    # would otherwise normalize encoding and could throw away unusual but
    # valid query formatting.
    pieces = re.split(r"([&;])", query)
    for index in range(0, len(pieces), 2):
        piece = pieces[index]
        name, separator, _value = piece.partition("=")
        if not separator or not _is_secret_query_name(name):
            continue
        pieces[index] = f"{name}={_MASK}"
    return "".join(pieces)


def redact_url(url: str) -> str:
    """Return a display-safe form of *url*.

    The scheme, host, port, path, and non-secret query values are retained.
    URL userinfo is replaced with ``***`` and secret-looking query values are
    replaced with the same marker.  Invalid or non-string values never escape
    into a response or log: a fixed placeholder is returned instead.
    """
    if not isinstance(url, str) or not url:
        return URL_REDACTION_PLACEHOLDER if url else ""

    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc or not parsed.hostname:
            return URL_REDACTION_PLACEHOLDER

        # Access these properties so malformed ports/bracketed IPv6 values
        # are rejected instead of being copied into a supposedly safe output.
        _ = parsed.port

        authority = parsed.netloc.rsplit("@", 1)[-1]
        if "@" in parsed.netloc:
            authority = f"{_MASK}@{authority}"

        return urlunsplit(
            (
                parsed.scheme,
                authority,
                parsed.path,
                _redact_query(parsed.query),
                "",
            )
        )
    except Exception:  # noqa: BLE001 - redaction must never break the caller
        return URL_REDACTION_PLACEHOLDER
