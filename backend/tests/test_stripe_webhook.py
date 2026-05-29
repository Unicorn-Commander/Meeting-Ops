"""Stripe webhook handler tests.

Covers the three things that must be true for the webhook to be safe:
  1. Bodies without a valid signature are rejected with 400.
  2. Duplicate event IDs are short-circuited (idempotency).
  3. Subscription created / updated / deleted map to the right
     User.tier transitions.

We don't go through the real Stripe SDK signature path (that requires
a real secret + a HMAC the SDK accepts). Instead we monkeypatch
`services.stripe_client._stripe` to return a stub whose
`Webhook.construct_event` returns the dict we feed it, and we exercise
both happy paths and the "no signature" error path explicitly.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

def _models():
    """Import inside fn so conftest's app fixture has reloaded modules first."""
    from auth.models import User
    from database.database import SessionLocal
    return User, SessionLocal


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stripe_env(monkeypatch):
    """Provide the minimum env vars so the webhook doesn't 503 on config."""
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_000000000000000000000000")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_test")
    monkeypatch.setenv("STRIPE_ENTERPRISE_PRICE_ID", "price_ent_test")
    monkeypatch.setenv("FOUNDERS_100_ACTIVE", "true")
    monkeypatch.setenv("FOUNDERS_100_LIMIT", "100")
    # Make absolutely sure no test bleeds real Redis state — leave REDIS_URL
    # alone; _redis_client returns None on import failure / unset URL,
    # which falls through to "always process".
    monkeypatch.delenv("REDIS_URL", raising=False)
    yield


class _StubStripeWebhook:
    """Stand-in for `stripe.Webhook` that hands us back the event dict."""

    def __init__(self, event):
        self._event = event

    def construct_event(self, payload, sig_header, secret):
        if sig_header == "BAD":
            raise ValueError("Invalid signature")
        return self._event


class _StubStripeModule:
    def __init__(self, event):
        self.Webhook = _StubStripeWebhook(event)
        self.api_key = None


def _patch_stripe(monkeypatch, event):
    """Patch the `_stripe()` helper to return a stub module that yields
    the given event from `construct_event`."""
    stub = _StubStripeModule(event)
    monkeypatch.setattr(
        "services.stripe_client._stripe",
        lambda: stub,
    )
    monkeypatch.setattr(
        "api.stripe_webhook._stripe",
        lambda: stub,
    )
    return stub


def _make_user(email=None, *, customer_id=None, tier="free"):
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        uname = "wh" + uuid.uuid4().hex[:8]
        user = User(
            email=email or f"{uname}@example.com",
            username=uname,
            hashed_password="x",
            is_active=True,
            is_verified=True,
            tier=tier,
            stripe_customer_id=customer_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _refresh(user):
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user.id).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Signature verification
# ---------------------------------------------------------------------------


def test_webhook_rejects_missing_signature(client, monkeypatch):
    _patch_stripe(monkeypatch, {"id": "evt_x", "type": "customer.created"})
    r = client.post("/api/stripe/webhook", content=b"{}")
    assert r.status_code == 400
    assert "stripe-signature" in r.json()["detail"].lower()


def test_webhook_rejects_invalid_signature(client, monkeypatch):
    _patch_stripe(monkeypatch, {"id": "evt_x", "type": "customer.created"})
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "BAD"},
    )
    assert r.status_code == 400


def test_webhook_503s_when_secret_missing(client, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    _patch_stripe(monkeypatch, {"id": "evt_x", "type": "customer.created"})
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


def test_webhook_idempotency_short_circuits_duplicate(client, monkeypatch, app):
    """Two deliveries of the same event ID. First processes, second is
    short-circuited.

    Redis is not available in tests, so this exercises the "no Redis"
    fallback path: both calls return 200, and there is no double-write
    visible side-effect since both handlers are idempotent themselves.
    To exercise the *real* Redis short-circuit we patch _redis_client to
    return an in-memory dict-backed stub.
    """
    user = _make_user(customer_id="cus_idem")

    # Replace the redis client with a tiny in-memory stub so we can prove
    # the second call really did skip processing.
    seen: dict[str, str] = {}

    class _Fake:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in seen:
                return False
            seen[key] = value
            return True

    monkeypatch.setattr("api.stripe_webhook._redis_client", lambda: _Fake())

    event = {
        "id": "evt_dup_1",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_1",
                "status": "active",
                "customer": "cus_idem",
                "items": {
                    "data": [{"price": {"id": "price_pro_test"}}]
                },
            }
        },
    }
    _patch_stripe(monkeypatch, event)

    r1 = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    r2 = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r1.status_code == 200
    assert r1.json().get("handled") is True
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True

    # User was upgraded exactly once.
    refreshed = _refresh(user)
    assert refreshed.tier == "pro"


# ---------------------------------------------------------------------------
# 3. Event → tier mapping
# ---------------------------------------------------------------------------


def test_subscription_created_pro_price_flips_to_pro(client, monkeypatch):
    user = _make_user(customer_id="cus_created_pro", tier="free")
    event = {
        "id": "evt_created_pro_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_pro_1",
                "status": "active",
                "customer": "cus_created_pro",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert _refresh(user).tier == "pro"


def test_subscription_created_incomplete_does_not_upgrade(client, monkeypatch):
    user = _make_user(customer_id="cus_incomplete", tier="free")
    event = {
        "id": "evt_incomplete_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_inc_1",
                "status": "incomplete",
                "customer": "cus_incomplete",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert _refresh(user).tier == "free"


def test_subscription_updated_canceled_flips_to_free(client, monkeypatch):
    user = _make_user(customer_id="cus_cancelled", tier="pro")
    event = {
        "id": "evt_cancel_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "status": "canceled",
                "customer": "cus_cancelled",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert _refresh(user).tier == "free"


def test_subscription_updated_past_due_keeps_paid_tier(client, monkeypatch):
    user = _make_user(customer_id="cus_past_due", tier="pro")
    event = {
        "id": "evt_past_due_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_2",
                "status": "past_due",
                "customer": "cus_past_due",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    # Grace period — keep them on pro while Stripe retries the card.
    assert _refresh(user).tier == "pro"


def test_subscription_deleted_flips_to_free(client, monkeypatch):
    user = _make_user(customer_id="cus_deleted", tier="pro")
    event = {
        "id": "evt_del_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_3",
                "status": "canceled",
                "customer": "cus_deleted",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert _refresh(user).tier == "free"


def test_customer_created_links_customer_id(client, monkeypatch):
    user = _make_user(email="cust@example.com", customer_id=None)
    event = {
        "id": "evt_cust_" + uuid.uuid4().hex[:6],
        "type": "customer.created",
        "data": {
            "object": {
                "id": "cus_link_test",
                "email": "cust@example.com",
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert _refresh(user).stripe_customer_id == "cus_link_test"


def test_unhandled_event_type_is_200_not_500(client, monkeypatch):
    event = {
        "id": "evt_unknown_" + uuid.uuid4().hex[:6],
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {}},
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    assert r.json().get("handled") is False


def test_subscription_unknown_price_id_does_not_upgrade(client, monkeypatch):
    user = _make_user(customer_id="cus_weird_price", tier="free")
    event = {
        "id": "evt_weird_" + uuid.uuid4().hex[:6],
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_weird",
                "status": "active",
                "customer": "cus_weird_price",
                "items": {"data": [{"price": {"id": "price_unknown"}}]},
            }
        },
    }
    _patch_stripe(monkeypatch, event)
    r = client.post(
        "/api/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "ok"},
    )
    assert r.status_code == 200
    # Unknown price defaults to "free" — no silent upgrade.
    assert _refresh(user).tier == "free"
