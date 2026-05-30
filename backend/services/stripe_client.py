"""Thin wrapper around the Stripe Python SDK.

Centralizes:
  - API key loading (TEST keys only in dev; live keys gated behind an
    explicit deploy step — see deploy/bigboy/.env.bigboy.example).
  - Customer get-or-create (one Stripe customer per local user, link
    stored on `User.stripe_customer_id`).
  - Checkout Session creation (the link the Pricing page redirects to).
  - Billing Portal Session creation (so existing customers can update
    cards / cancel without us building those screens).

Why a thin wrapper instead of calling `stripe` directly in routes:
  - Single place that imports `stripe` (the lib is optional in tests
    via the stub fallback below; webhook tests exercise signature
    verification through this module too).
  - Single place that sets `stripe.api_key` (avoids a per-route assign).
  - Customer dedup logic lives here so /billing/checkout, /billing/portal,
    and the `customer.created` webhook all stay consistent.

The module is import-safe even when the `stripe` package isn't installed
or `STRIPE_API_KEY` is unset — every public function raises a clear
RuntimeError instead of an ImportError or AttributeError. That keeps the
billing router optional in environments that don't have Stripe wired yet
(test sandboxes, offline appliance builds).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from auth.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import + config — keep billing optional when the lib isn't installed.
# ---------------------------------------------------------------------------

_stripe_module: Optional[Any] = None
_api_key_set = False


def _stripe():
    """Import the `stripe` lib lazily, set api_key on first use.

    Raises RuntimeError with a clear message if the lib is missing or
    STRIPE_API_KEY is unset — callers (routes/webhook) translate this
    into a 503 so the API doesn't 500 in environments without billing.
    """
    global _stripe_module, _api_key_set
    if _stripe_module is None:
        try:
            import stripe  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in CI w/o lib
            raise RuntimeError(
                "stripe package not installed. Add `stripe` to requirements.txt "
                "and rebuild the container."
            ) from exc
        _stripe_module = stripe
    if not _api_key_set:
        api_key = os.getenv("STRIPE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "STRIPE_API_KEY is unset. Billing endpoints are inert until "
                "configured (use sk_test_... in dev)."
            )
        if not api_key.startswith("sk_test_") and os.getenv("STRIPE_ALLOW_LIVE") != "1":
            # Belt-and-suspenders: refuse to use a live key unless an
            # explicit env flag is set. Aaron's hard constraint: live keys
            # are gated behind an explicit deploy step.
            raise RuntimeError(
                "Refusing to use a non-test Stripe key without STRIPE_ALLOW_LIVE=1. "
                "Live keys must be enabled by an explicit deploy step."
            )
        _stripe_module.api_key = api_key
        _api_key_set = True
    return _stripe_module


def is_configured() -> bool:
    """True iff STRIPE_API_KEY is set. Used by frontend feature gates / health
    checks. Does not actually load the SDK."""
    return bool(os.getenv("STRIPE_API_KEY", "").strip())


# ---------------------------------------------------------------------------
# Price ID → tier mapping (env-driven).
# ---------------------------------------------------------------------------


def price_id_to_tier(price_id: Optional[str]) -> str:
    """Map a Stripe price ID to a local tier name. Unknown / missing
    price IDs default to 'free' so a misconfigured webhook can't silently
    upgrade someone.

    Aaron's pricing decisions (locked 2026-05-29):
      Free        = $0,  browser-only
      Pro         = $12, individual — Meeting-Ops only
      Suite       = $25, individual — Meeting-Ops + Project-Ops + Contact-Ops
      Enterprise  = custom, on-prem

    The Suite tier carries the same effective TIER_FEATURES as Pro
    (canonical_reprocess, brigade_integration, cross_device_sync, etc.) — the
    difference is access to the sister apps (Project-Ops + Contact-Ops),
    which is enforced at those apps' auth layers, not here. Within Meeting-Ops
    a Suite subscriber and a Pro subscriber experience the same product.
    """
    if not price_id:
        return "free"
    pro = os.getenv("STRIPE_PRO_PRICE_ID", "").strip()
    suite = os.getenv("STRIPE_SUITE_PRICE_ID", "").strip()
    ent = os.getenv("STRIPE_ENTERPRISE_PRICE_ID", "").strip()
    if pro and price_id == pro:
        return "pro"
    if suite and price_id == suite:
        # Suite subscribers map to "pro" inside Meeting-Ops — same tier features.
        # The Suite-vs-Pro distinction lives on the User.is_suite_subscriber
        # flag (used by Project-Ops / Contact-Ops to gate cross-app access)
        # so a single Meeting-Ops tier lookup stays simple.
        return "pro"
    if ent and price_id == ent:
        return "enterprise"
    logger.warning(
        "Unknown Stripe price_id=%s; defaulting to 'free'. "
        "Set STRIPE_PRO_PRICE_ID / STRIPE_SUITE_PRICE_ID / STRIPE_ENTERPRISE_PRICE_ID.",
        price_id,
    )
    return "free"


def price_id_is_suite(price_id: str) -> bool:
    """True iff the price ID matches the configured Suite tier price.

    Used by the webhook handler to set User.is_suite_subscriber alongside
    User.tier — needed for the Project-Ops / Contact-Ops cross-app gates."""
    if not price_id:
        return False
    suite = os.getenv("STRIPE_SUITE_PRICE_ID", "").strip()
    return bool(suite) and price_id == suite


def tier_to_price_id(tier: str) -> Optional[str]:
    """Reverse of price_id_to_tier — used by /billing/checkout to translate
    the plan name from the request body into the Stripe price ID. Accepts
    "pro" (Meeting-Ops only), "suite" (UC Suite), and "enterprise"."""
    tier = (tier or "").lower()
    if tier == "pro":
        return os.getenv("STRIPE_PRO_PRICE_ID", "").strip() or None
    if tier == "suite":
        return os.getenv("STRIPE_SUITE_PRICE_ID", "").strip() or None
    if tier == "enterprise":
        return os.getenv("STRIPE_ENTERPRISE_PRICE_ID", "").strip() or None
    return None


# ---------------------------------------------------------------------------
# Customer get-or-create
# ---------------------------------------------------------------------------


def get_or_create_stripe_customer(db: Session, user: User) -> str:
    """Ensure the user has a Stripe customer record + populated
    `stripe_customer_id`. Idempotent: re-using returns the existing ID.

    Returns the Stripe customer ID (cus_...).
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id
    s = _stripe()
    customer = s.Customer.create(
        email=user.email,
        name=user.full_name or user.username,
        metadata={"meeting_ops_user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created Stripe customer %s for user_id=%s", customer.id, user.id)
    return customer.id


# ---------------------------------------------------------------------------
# Checkout + Billing Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    db: Session,
    user: User,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session for a Subscription. Returns the
    hosted Checkout URL the frontend redirects to.

    `subscription_data.cancel_at_period_end` is NOT set here — that's a
    user-initiated action on the Billing Portal. Aaron's call: at-cancel
    we let the user finish the period rather than immediate prorate.
    The actual cancel-at-period-end UX lives in the Billing Portal.
    """
    s = _stripe()
    customer_id = get_or_create_stripe_customer(db, user)
    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=False,
        client_reference_id=str(user.id),
        # Subscription metadata travels through to the
        # customer.subscription.created webhook so we can audit the
        # provenance of every upgrade.
        subscription_data={
            "metadata": {
                "meeting_ops_user_id": str(user.id),
                "source": "pricing_page",
            },
        },
    )
    return session.url


def create_billing_portal_session(user: User, return_url: str) -> str:
    """Create a Billing Portal session for an existing customer. Returns
    the hosted portal URL. The user must already have a Stripe customer
    record (raises ValueError otherwise — caller surfaces as 400)."""
    if not user.stripe_customer_id:
        raise ValueError("User has no Stripe customer record yet")
    s = _stripe()
    session = s.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    return session.url


# ---------------------------------------------------------------------------
# Subscription lookup (for GET /api/billing/subscription)
# ---------------------------------------------------------------------------


def get_active_subscription(user: User) -> Optional[dict]:
    """Return the user's current active subscription as a small dict,
    or None if they don't have one. Used by /api/billing/subscription.
    """
    if not user.stripe_customer_id:
        return None
    s = _stripe()
    subs = s.Subscription.list(
        customer=user.stripe_customer_id,
        status="all",
        limit=10,
    )
    # Pick the first non-canceled subscription. Prefer active over
    # trialing/past_due so a renewed-after-cancel user shows the right
    # state.
    pick = None
    for sub in subs.auto_paging_iter() if hasattr(subs, "auto_paging_iter") else subs.data:
        if sub.status in ("active", "trialing", "past_due"):
            pick = sub
            break
        if sub.status in ("incomplete", "incomplete_expired") and pick is None:
            pick = sub
    if pick is None:
        return None
    price_id = None
    try:
        price_id = pick["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        pass
    return {
        "subscription_id": pick.id,
        "status": pick.status,
        "price_id": price_id,
        "tier": price_id_to_tier(price_id),
        "current_period_end": getattr(pick, "current_period_end", None),
        "cancel_at_period_end": bool(getattr(pick, "cancel_at_period_end", False)),
    }
