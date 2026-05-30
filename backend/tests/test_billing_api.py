"""Tests for /api/billing endpoints.

We stub the entire `services.stripe_client` surface so the tests run
without touching real Stripe — the production behavior is exercised via
unit-tests + manual `stripe listen` smoke against the dev instance.

Covers:
  - All three endpoints require auth (401 without token).
  - /checkout returns the Stripe URL when the SDK is configured.
  - /checkout 400s for unknown plans.
  - /checkout 400s with a helpful message for "enterprise".
  - /portal returns the Portal URL.
  - /subscription returns the user's tier + founder flag even when
    Stripe isn't configured (free users with no billing history).
  - /subscription returns subscription data when the customer + Stripe
    config exist.
  - All three endpoints 503 when Stripe isn't configured.
"""

from __future__ import annotations

import uuid

import pytest

def _models():
    from auth.models import User
    from database.database import SessionLocal
    return User, SessionLocal


def _login(client) -> str:
    r = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    return r.json()["access_token"]


def _auth(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client)}"}


@pytest.fixture
def stripe_configured(monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_000000000000000000000000")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_test")
    monkeypatch.setenv("STRIPE_ENTERPRISE_PRICE_ID", "")
    yield


@pytest.fixture
def stripe_unconfigured(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRO_PRICE_ID", raising=False)
    yield


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_checkout_requires_auth(client, stripe_configured):
    r = client.post("/api/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 401


def test_portal_requires_auth(client, stripe_configured):
    r = client.post("/api/billing/portal")
    assert r.status_code == 401


def test_subscription_requires_auth(client, stripe_configured):
    r = client.get("/api/billing/subscription")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Unconfigured Stripe → 503 on mutating, 200 on subscription
# ---------------------------------------------------------------------------


def test_checkout_503_when_stripe_unconfigured(client, stripe_unconfigured):
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "pro"},
        headers=_auth(client),
    )
    assert r.status_code == 503


def test_portal_503_when_stripe_unconfigured(client, stripe_unconfigured):
    r = client.post("/api/billing/portal", headers=_auth(client))
    assert r.status_code == 503


def test_subscription_returns_local_state_when_stripe_unconfigured(client, stripe_unconfigured):
    r = client.get("/api/billing/subscription", headers=_auth(client))
    assert r.status_code == 200
    body = r.json()
    assert body["has_subscription"] is False
    # Admin user is superuser, which TIER_FEATURES resolves to enterprise;
    # but the user's column tier is whatever the seed left. The endpoint
    # reports the column-level tier (not the superuser override) so a
    # superuser without a subscription still sees the right "no sub" state.
    assert "tier" in body
    assert body["is_founding_member"] is False


# ---------------------------------------------------------------------------
# Checkout — happy path + bad plans
# ---------------------------------------------------------------------------


def test_checkout_returns_url(client, stripe_configured, monkeypatch):
    captured = {}

    def _fake_create(db, user, price_id, success_url, cancel_url):
        captured["price_id"] = price_id
        captured["user_id"] = user.id
        return "https://checkout.stripe.com/test/cs_123"

    monkeypatch.setattr(
        "services.stripe_client.create_checkout_session", _fake_create
    )
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "pro"},
        headers=_auth(client),
    )
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://checkout.stripe.com/")
    assert captured["price_id"] == "price_pro_test"


def test_checkout_400_for_unknown_plan(client, stripe_configured):
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "ultra-mega"},
        headers=_auth(client),
    )
    assert r.status_code == 400


def test_checkout_enterprise_routes_to_sales(client, stripe_configured):
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "enterprise"},
        headers=_auth(client),
    )
    assert r.status_code == 400
    assert "sales" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Portal
# ---------------------------------------------------------------------------


def test_portal_returns_url(client, stripe_configured, monkeypatch):
    monkeypatch.setattr(
        "services.stripe_client.get_or_create_stripe_customer",
        lambda db, user: "cus_test",
    )
    monkeypatch.setattr(
        "services.stripe_client.create_billing_portal_session",
        lambda user, return_url: "https://billing.stripe.com/p/test_xyz",
    )
    r = client.post("/api/billing/portal", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://billing.stripe.com/")


# ---------------------------------------------------------------------------
# Subscription read with linked customer
# ---------------------------------------------------------------------------


def test_subscription_returns_active_sub_data(client, stripe_configured, monkeypatch):
    # Link admin to a fake stripe customer so the path through to
    # get_active_subscription runs.
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        admin.stripe_customer_id = "cus_admin_test"
        db.add(admin)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "services.stripe_client.get_active_subscription",
        lambda user: {
            "subscription_id": "sub_1",
            "status": "active",
            "price_id": "price_pro_test",
            "tier": "pro",
            "current_period_end": 1735689600,  # 2026-01-01 UTC
            "cancel_at_period_end": False,
        },
    )
    r = client.get("/api/billing/subscription", headers=_auth(client))
    assert r.status_code == 200
    body = r.json()
    assert body["has_subscription"] is True
    assert body["subscription_id"] == "sub_1"
    assert body["status"] == "active"
    assert body["tier"] == "pro"
    assert body["cancel_at_period_end"] is False
    assert body["current_period_end"] is not None
