"""Tests for the SSO forward-auth proxy-trust boundary (security-1).

``auth/proxy_trust.forward_auth_trusted`` gates whether the
``X-Auth-Request-*`` identity headers may be honoured. Those headers are
forgeable by any co-tenant container on the shared docker network, so trusting
them unconditionally is an auth bypass + superuser escalation (the groups
header drives ``is_superuser`` at auto-provision time).

The gate is FAIL-CLOSED:

  * No secret configured → forward-auth headers are IGNORED (correct for
    native-OIDC / cookie deploys that don't use forward-auth at all).
  * Secret set → a request must carry a matching ``X-Proxy-Auth`` (injected
    only by the trusted proxy) or its identity headers are ignored and the
    caller falls through to token auth.

Trusted ⟺ (secret configured) AND (matching ``X-Proxy-Auth``).

Comparison is constant-time (``secrets.compare_digest``), mirroring
``auth/internal.py``.
"""
from __future__ import annotations

import os
import pathlib
from unittest.mock import patch

import pytest
from starlette.datastructures import Headers

import auth.proxy_trust as proxy_trust_mod
from auth.proxy_trust import (
    PROXY_AUTH_HEADER,
    PROXY_AUTH_SECRET_ENV,
    PROXY_AUTH_SECRET_FILE_ENV,
    configured_secret_source,
    forward_auth_trusted,
    proxy_trust_enforced,
)


SECRET = "test-proxy-secret-aaaa-bbbb-cccc-dddd-eeee-ffff-0011-2233"
WRONG = "test-proxy-secret-not-the-right-value-0123456789abcdef"


@pytest.fixture()
def with_secret():
    """Secret configured → fail-closed mode active."""
    with patch.dict(os.environ, {"PROXY_AUTH_SHARED_SECRET": SECRET}):
        yield


@pytest.fixture()
def without_secret():
    """Secret cleared → fail-closed (forward-auth headers ignored)."""
    with patch.dict(os.environ, {"PROXY_AUTH_SHARED_SECRET": ""}):
        yield


# ---------------------------------------------------------------------------
# Unit: the gate function
# ---------------------------------------------------------------------------
def test_fail_closed_when_secret_unset(without_secret):
    # No secret configured → forward-auth headers are IGNORED (fail-closed).
    # proxy_trust_enforced() still reports "no secret provisioned".
    assert proxy_trust_enforced() is False
    assert forward_auth_trusted(Headers({"X-Auth-Request-Email": "u@x.com"})) is False
    # And of course with no X-Proxy-Auth header at all.
    assert forward_auth_trusted(Headers({})) is False


def test_fail_closed_missing_proxy_header(with_secret):
    # Secret configured but request carries no X-Proxy-Auth → not trusted.
    assert proxy_trust_enforced() is True
    assert forward_auth_trusted(Headers({"X-Auth-Request-Email": "u@x.com"})) is False


def test_fail_closed_matching_secret(with_secret):
    # Correct secret (the Traefik-injected path) → trusted.
    assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is True


def test_fail_closed_wrong_secret(with_secret):
    assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: WRONG})) is False


def test_header_match_is_case_insensitive(with_secret):
    # Starlette headers are case-insensitive; a lower-cased injection still matches.
    assert forward_auth_trusted(Headers({"x-proxy-auth": SECRET})) is True


def test_empty_presented_value_rejected(with_secret):
    assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: ""})) is False


# ---------------------------------------------------------------------------
# Integration: forged identity header is ignored once enforced
# ---------------------------------------------------------------------------
def test_forged_sso_header_ignored_when_enforced(client, with_secret):
    # Secret is set but we present NO X-Proxy-Auth (simulating a direct-to-
    # container forge). The X-Auth-Request-Email must be ignored, so /api/auth/me
    # — which requires a real authenticated user — must NOT return a profile.
    resp = client.get(
        "/api/auth/me",
        headers={
            "X-Auth-Request-Email": "attacker@evil.com",
            "X-Auth-Request-Groups": "uc-admins",  # would escalate to superuser
        },
    )
    assert resp.status_code != 200, (
        f"Forged forward-auth header authenticated /api/auth/me without a valid "
        f"X-Proxy-Auth secret: {resp.status_code} {resp.text}"
    )


# ---------------------------------------------------------------------------
# security-3 follow-up: the secret may come from a mounted FILE, so the value
# need not sit in the container environment where `docker inspect` reads it.
#
# The sequencing requirement these tests encode: a file source must be
# adoptable WITHOUT a flag day, and a broken mount must NOT silently stop
# honouring forward-auth identity headers -- that would log every SSO user out
# of a working deploy. So: file wins when usable, env is the fallback, and only
# "neither source" is fail-closed.
# ---------------------------------------------------------------------------
FILE_SECRET = "file-sourced-proxy-secret-9988-7766-5544-3322-1100-aabb"


@pytest.fixture(autouse=True)
def _clear_file_cache():
    """The module memoizes file reads on (mtime_ns, size); clear between tests."""
    proxy_trust_mod._FILE_CACHE.clear()
    proxy_trust_mod._FILE_WARNED.clear()
    yield
    proxy_trust_mod._FILE_CACHE.clear()
    proxy_trust_mod._FILE_WARNED.clear()


def _write(tmp_path, value, name="proxy_auth_secret"):
    f = tmp_path / name
    f.write_text(value)
    return str(f)


def test_secret_from_file_is_accepted(tmp_path):
    """File source alone (no env var) → the file's value is trusted."""
    path = _write(tmp_path, FILE_SECRET)
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: path, PROXY_AUTH_SECRET_ENV: ""}):
        assert configured_secret_source() == "file"
        assert proxy_trust_enforced() is True
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: FILE_SECRET})) is True
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: WRONG})) is False


def test_trailing_whitespace_in_file_is_stripped(tmp_path):
    """`openssl rand -hex 32 > file` leaves a newline; it must not break the match."""
    path = _write(tmp_path, FILE_SECRET + "\n")
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: path, PROXY_AUTH_SECRET_ENV: ""}):
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: FILE_SECRET})) is True


def test_file_wins_over_env_when_both_set(tmp_path):
    """Both sources present → the FILE value is authoritative."""
    path = _write(tmp_path, FILE_SECRET)
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: path, PROXY_AUTH_SECRET_ENV: SECRET}):
        assert configured_secret_source() == "file"
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: FILE_SECRET})) is True
        # The env value is no longer accepted once a usable file is mounted.
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is False


def test_env_var_still_works_with_no_file_configured():
    """Regression: the pre-existing env-only deploy is unchanged."""
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_ENV: SECRET}, clear=False):
        os.environ.pop(PROXY_AUTH_SECRET_FILE_ENV, None)
        assert configured_secret_source() == "env"
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is True


def test_missing_file_falls_back_to_env_and_does_not_lock_out(tmp_path):
    """A typo'd / unmounted path must NOT stop honouring forward-auth while a
    valid env var is still present. This is the no-lockout guarantee."""
    bogus = str(tmp_path / "does-not-exist")
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: bogus, PROXY_AUTH_SECRET_ENV: SECRET}):
        assert configured_secret_source() == "env"
        assert proxy_trust_enforced() is True
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is True


def test_empty_file_falls_back_to_env(tmp_path):
    path = _write(tmp_path, "   \n")
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: path, PROXY_AUTH_SECRET_ENV: SECRET}):
        assert configured_secret_source() == "env"
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is True


def test_neither_source_is_fail_closed(tmp_path):
    """No usable file AND no env var → headers ignored (fail-closed)."""
    bogus = str(tmp_path / "nope")
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: bogus, PROXY_AUTH_SECRET_ENV: ""}):
        assert configured_secret_source() == "none"
        assert proxy_trust_enforced() is False
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: SECRET})) is False
        assert forward_auth_trusted(Headers({"X-Auth-Request-Email": "u@x.com"})) is False


def test_file_rotation_is_picked_up_without_a_restart(tmp_path):
    """The cache keys on (mtime_ns, size), so rewriting the file rotates the
    secret in place -- the old value stops being accepted."""
    path = _write(tmp_path, FILE_SECRET)
    with patch.dict(os.environ, {PROXY_AUTH_SECRET_FILE_ENV: path, PROXY_AUTH_SECRET_ENV: ""}):
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: FILE_SECRET})) is True
        rotated = "rotated-" + FILE_SECRET
        pathlib.Path(path).write_text(rotated)
        os.utime(path, ns=(0, 0))  # force a distinct mtime so the cache invalidates
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: rotated})) is True
        assert forward_auth_trusted(Headers({PROXY_AUTH_HEADER: FILE_SECRET})) is False
