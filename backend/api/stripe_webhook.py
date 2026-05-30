"""Stripe webhook handler.

Single endpoint: POST /api/stripe/webhook

Mandatory signature verification against STRIPE_WEBHOOK_SECRET. We do
NOT have a "skip in dev" branch: the local dev workflow uses
`stripe listen --forward-to ...` which sends real signatures, so a
skip-flag would only be a footgun that lets unsigned attacker payloads
through if the env var is misset.

Idempotency: every Stripe event has a unique `event.id`. We stash it in
Redis with a 24h TTL the first time we process it; duplicate deliveries
(Stripe retries on 5xx, on timeouts, and sometimes spontaneously) return
200 without re-processing. Without idempotency, a duplicate
`subscription.deleted` event would briefly flip a user to free while a
subscription is being renewed — fix tier state vs. fix Stripe state is
a one-way operation, so we lock it down here.

Events handled:
  - customer.subscription.created  → set User.tier from price_id
  - customer.subscription.updated  → re-resolve tier from current price_id
                                      + cancel_at_period_end flag
  - customer.subscription.deleted  → set User.tier = "free"
  - customer.created               → store stripe_customer_id if not set

Anything else is logged + 200'd. We DON'T 5xx on unhandled events: that
would tell Stripe to retry, and the retry would keep failing for the
same reason. 200 = "received, intentionally ignored."

Logging: webhook bodies contain customer PII (email, name, last4 of
card). They go to DEBUG only. INFO logs the event type + ID + the local
user we matched, never the raw body.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.models import User
from database.database import get_db
from services.stripe_client import _stripe, price_id_to_tier

# Default cohort label for Meeting-Ops v1 Founding 100. Aaron's design
# intent: future cohorts (e.g. crisis_ops_v1) get distinct labels rather
# than overflowing the same 100.
_FOUNDING_DEFAULT_COHORT = "meeting_ops_v1"
_FOUNDING_COHORT_CLOSED_FLAG = "FOUNDING_COHORT_CLOSED"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["billing"])


# Redis is best-effort. If it's unreachable, we fall back to processing
# every event (with a logged warning) rather than 5xx'ing. Stripe will
# still retry on a real error.
def _redis_client():
    try:
        import redis  # type: ignore
    except ImportError:
        return None
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        return redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stripe webhook: Redis unavailable for idempotency: %s", exc)
        return None


_IDEMPOTENCY_KEY_PREFIX = "stripe:event:processed:"
_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24  # 24h — Stripe retries window is ~3 days but the bulk happens in <1h.


def _already_processed(event_id: str) -> bool:
    """Atomic test-and-set on Redis. Returns True if we've already
    processed this event (caller should 200 immediately)."""
    client = _redis_client()
    if client is None:
        return False
    try:
        # SET key value NX EX 86400 — atomic, the only safe primitive here.
        # Returns True if the key was created (i.e. not seen before).
        set_ok = client.set(
            f"{_IDEMPOTENCY_KEY_PREFIX}{event_id}",
            "1",
            nx=True,
            ex=_IDEMPOTENCY_TTL_SECONDS,
        )
        return not bool(set_ok)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Stripe webhook: Redis SET failed for event %s: %s. "
            "Falling through to process (no idempotency on this delivery).",
            event_id, exc,
        )
        return False


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _find_user_by_customer(db: Session, customer_id: Optional[str]) -> Optional[User]:
    if not customer_id:
        return None
    return db.query(User).filter(User.stripe_customer_id == customer_id).first()


def _find_user_by_metadata(db: Session, sub: dict) -> Optional[User]:
    """Fallback: find a user via the `meeting_ops_user_id` we stamp into
    subscription metadata at Checkout time. Useful when the customer
    arrives before `customer.created` (race during Checkout)."""
    md = sub.get("metadata") or {}
    user_id_raw = md.get("meeting_ops_user_id")
    if not user_id_raw:
        return None
    try:
        return db.query(User).filter(User.id == int(user_id_raw)).first()
    except (ValueError, TypeError):
        return None


def _extract_price_id(sub: dict) -> Optional[str]:
    """Pull the first line item's price ID out of a subscription object."""
    try:
        return sub["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return None


def _handle_subscription_created(db: Session, sub: dict) -> None:
    customer_id = sub.get("customer")
    user = _find_user_by_customer(db, customer_id) or _find_user_by_metadata(db, sub)
    if user is None:
        logger.warning(
            "subscription.created: no local user for customer=%s sub=%s; ignoring",
            customer_id, sub.get("id"),
        )
        return
    # Stamp the customer ID if we got here via metadata fallback.
    if not user.stripe_customer_id and customer_id:
        user.stripe_customer_id = customer_id
    price_id = _extract_price_id(sub)
    new_tier = price_id_to_tier(price_id)
    if sub.get("status") in ("incomplete", "incomplete_expired", "canceled", "unpaid"):
        # Sub created but not yet paid — don't upgrade yet. Stripe will
        # send subscription.updated when it activates.
        logger.info(
            "subscription.created status=%s user_id=%s — not flipping tier yet",
            sub.get("status"), user.id,
        )
        db.add(user)
        db.commit()
        return
    logger.info(
        "subscription.created: user_id=%s tier %s→%s price=%s",
        user.id, user.tier, new_tier, price_id,
    )
    user.tier = new_tier
    db.add(user)
    db.commit()
    # Founding 100: annual-upfront subscribers get the cohort flag at
    # checkout-completion time. Other intervals (monthly) never qualify
    # by design — Aaron's spec.
    if _is_annual_upfront(sub):
        try:
            _maybe_grant_founding_member(db, user)
        except Exception:
            logger.exception(
                "founding 100 grant failed for user_id=%s on sub=%s",
                user.id, sub.get("id"),
            )


def _handle_subscription_updated(db: Session, sub: dict) -> None:
    customer_id = sub.get("customer")
    user = _find_user_by_customer(db, customer_id) or _find_user_by_metadata(db, sub)
    if user is None:
        logger.warning(
            "subscription.updated: no local user for customer=%s sub=%s; ignoring",
            customer_id, sub.get("id"),
        )
        return
    status_str = sub.get("status")
    price_id = _extract_price_id(sub)
    if status_str in ("active", "trialing"):
        new_tier = price_id_to_tier(price_id)
    elif status_str in ("past_due",):
        # Grace period — keep paid tier active while Stripe retries the card.
        new_tier = price_id_to_tier(price_id)
    elif status_str in ("canceled", "unpaid", "incomplete_expired"):
        new_tier = "free"
    else:
        # incomplete / paused / something new — leave tier alone.
        logger.info(
            "subscription.updated: status=%s user_id=%s — leaving tier=%s",
            status_str, user.id, user.tier,
        )
        return
    if user.tier != new_tier:
        logger.info(
            "subscription.updated: user_id=%s tier %s→%s status=%s price=%s",
            user.id, user.tier, new_tier, status_str, price_id,
        )
        user.tier = new_tier
        db.add(user)
        db.commit()


def _handle_subscription_deleted(db: Session, sub: dict) -> None:
    customer_id = sub.get("customer")
    user = _find_user_by_customer(db, customer_id) or _find_user_by_metadata(db, sub)
    if user is None:
        logger.warning(
            "subscription.deleted: no local user for customer=%s; ignoring",
            customer_id,
        )
        return
    if user.tier != "free":
        logger.info(
            "subscription.deleted: user_id=%s tier %s→free",
            user.id, user.tier,
        )
        user.tier = "free"
        db.add(user)
        db.commit()


def _handle_customer_created(db: Session, customer: dict) -> None:
    customer_id = customer.get("id")
    email = (customer.get("email") or "").strip().lower()
    if not (customer_id and email):
        return
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger.info(
            "customer.created: no local user for email=%s customer=%s",
            email, customer_id,
        )
        return
    if user.stripe_customer_id and user.stripe_customer_id != customer_id:
        logger.warning(
            "customer.created: user_id=%s already linked to %s, got %s; ignoring",
            user.id, user.stripe_customer_id, customer_id,
        )
        return
    if user.stripe_customer_id == customer_id:
        return
    user.stripe_customer_id = customer_id
    db.add(user)
    db.commit()
    logger.info(
        "customer.created: linked user_id=%s ↔ customer=%s", user.id, customer_id,
    )


# ---------------------------------------------------------------------------
# Founding 100 (renamed from "Founders 100" in v3.21.0)
# ---------------------------------------------------------------------------


def _founding_cap() -> int:
    """Cohort capacity. Defaults to 100. Reads FOUNDING_100_LIMIT first;
    falls back to the legacy FOUNDERS_100_LIMIT name so an old env file
    keeps working through the v3.21.0 transition."""
    raw = os.getenv("FOUNDING_100_LIMIT") or os.getenv("FOUNDERS_100_LIMIT") or "100"
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 100


def _founding_active() -> bool:
    """True iff the Founding 100 mechanic is allowed to grant new seats.
    Env-gated (FOUNDING_100_ACTIVE / legacy FOUNDERS_100_ACTIVE) AND
    not admin-closed. See POST /api/admin/founding/close + api.founding."""
    if os.getenv(_FOUNDING_COHORT_CLOSED_FLAG, "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        return False
    raw = (
        os.getenv("FOUNDING_100_ACTIVE")
        or os.getenv("FOUNDERS_100_ACTIVE")
        or "true"
    ).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _is_annual_upfront(sub: dict) -> bool:
    """Detect the annual-upfront Founding 100 trigger.

    Annual-upfront either comes through with
        items.data[0].price.recurring.interval == "year"
    or, on Checkout-session metadata, with
        metadata.annual_upfront == "true"
    (the Checkout client sets the latter when it kicks off the year
    plan because Stripe doesn't echo recurring on every event shape).
    """
    md = sub.get("metadata") or {}
    if str(md.get("annual_upfront", "")).strip().lower() in ("1", "true", "yes"):
        return True
    try:
        recurring = sub["items"]["data"][0]["price"].get("recurring") or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        recurring = {}
    return str(recurring.get("interval", "")).lower() == "year"


def _maybe_grant_founding_member(
    db: Session,
    user: User,
    *,
    cohort: str = _FOUNDING_DEFAULT_COHORT,
) -> bool:
    """Atomically grant the user the Founding 100 flag if the cohort is
    open and below capacity. Idempotent: re-grants for an already-flagged
    user are a no-op.

    Concurrency: uses `SELECT ... FOR UPDATE` on the existing-cohort row
    set so two parallel Stripe webhooks can't both award seat 100. On
    SQLite (tests) the SAVEPOINT acts as the same lock since there's no
    concurrent writer.

    Returns True if the flag was newly granted, False otherwise (already
    flagged, cohort closed, or capacity hit). Logs a `founding_member_granted`
    structured event on grant.
    """
    if not user:
        return False
    if getattr(user, "is_founding_member", False):
        return False
    if not _founding_active():
        return False
    # Admin-closed cohorts (POST /api/admin/founding/close) stop granting
    # even when nominally below capacity. Imported lazily so api.founding
    # stays an independent optional router.
    try:
        from api.founding import _is_cohort_closed  # type: ignore
        if _is_cohort_closed(cohort):
            logger.info(
                "Founding 100: cohort %s admin-closed; not granting user_id=%s",
                cohort, user.id,
            )
            return False
    except Exception:  # pragma: no cover - founding router optional
        pass

    limit = _founding_cap()
    is_postgres = db.bind is not None and db.bind.dialect.name == "postgresql"

    # PostgreSQL: SELECT FOR UPDATE in a transaction so concurrent webhook
    # workers serialize on the cohort row set. SQLite has no FOR UPDATE
    # but tests are single-process so the plain SELECT is fine.
    try:
        if is_postgres:
            # Lock the cohort rows. We don't need to lock the whole table —
            # locking the rows that contribute to the count is enough,
            # because INSERT-into-this-set is what we serialize against.
            locked_count = (
                db.query(User)
                .filter(User.is_founding_member.is_(True))
                .filter(User.founding_cohort == cohort)
                .with_for_update()
                .count()
            )
        else:
            locked_count = (
                db.query(User)
                .filter(User.is_founding_member.is_(True))
                .filter(User.founding_cohort == cohort)
                .count()
            )

        if locked_count >= limit:
            logger.info(
                "Founding 100: cohort %s at capacity (%s/%s); not granting user_id=%s",
                cohort, locked_count, limit, user.id,
            )
            db.commit()
            return False

        user.is_founding_member = True
        user.founding_cohort = cohort
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    seat_num = locked_count + 1
    logger.info(
        "founding_member_granted user_id=%s cohort=%s seat_num=%s capacity=%s",
        user.id, cohort, seat_num, limit,
    )
    return True


# Backward-compat alias: older call sites + tests still import
# `_maybe_grant_founder`. Keep until v3.22.0 cleanup.
def _maybe_grant_founder(db: Session, user: User) -> None:  # pragma: no cover - thin shim
    _maybe_grant_founding_member(db, user)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


def _handle_checkout_session_completed(db: Session, session_obj: dict) -> None:
    """Checkout-session.completed: alternative trigger for Founding 100 grant.

    Stripe always sends customer.subscription.created for new subs, but the
    Founding 100 spec wants the grant tied specifically to annual-upfront
    Checkout completions (and the metadata.annual_upfront marker is set on
    the Checkout Session, not always echoed onto the Subscription). We
    consult session.metadata + session.mode and fire `_maybe_grant_founding_member`
    when the conditions match.
    """
    if session_obj.get("mode") != "subscription":
        return
    customer_id = session_obj.get("customer")
    md = session_obj.get("metadata") or {}
    # Look up the user via the customer ID (preferred) or
    # client_reference_id which we stamp with the local user id.
    user = _find_user_by_customer(db, customer_id)
    if user is None:
        ref = session_obj.get("client_reference_id")
        if ref:
            try:
                user = db.query(User).filter(User.id == int(ref)).first()
            except (ValueError, TypeError):
                user = None
    if user is None:
        logger.info(
            "checkout.session.completed: no local user for customer=%s session=%s",
            customer_id, session_obj.get("id"),
        )
        return

    annual_marker = str(md.get("annual_upfront", "")).strip().lower() in (
        "1", "true", "yes",
    )
    if not annual_marker:
        # Not flagged as annual-upfront; the subscription.created handler
        # will pick up the recurring=year case via _is_annual_upfront.
        return

    try:
        _maybe_grant_founding_member(db, user)
    except Exception:
        logger.exception(
            "founding 100 grant failed for user_id=%s on checkout=%s",
            user.id, session_obj.get("id"),
        )


_DISPATCH = {
    "customer.subscription.created": _handle_subscription_created,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "customer.created": _handle_customer_created,
    "checkout.session.completed": _handle_checkout_session_completed,
}


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="stripe-signature"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Stripe webhook. Verifies signature, idempotency-locks the event,
    dispatches to the typed handler. Returns 200 on success (including
    duplicates and intentionally-ignored event types). 400 on bad
    signature. 500 on processing failure (Stripe will retry)."""

    body = await request.body()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        # We treat a missing secret as a hard failure: silently accepting
        # unsigned events would let an attacker upgrade tiers by POSTing
        # JSON. 503 makes the misconfiguration loud.
        logger.error("STRIPE_WEBHOOK_SECRET unset; rejecting webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook not configured",
        )
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )
    try:
        stripe = _stripe()
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=secret,
        )
    except RuntimeError as exc:
        # _stripe() raised — lib missing / no api key. Same reasoning as
        # missing secret: 503 + loud log.
        logger.error("Stripe webhook: SDK not ready: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe SDK not configured",
        )
    except Exception as exc:  # noqa: BLE001
        # Signature verification failure or malformed payload.
        logger.warning("Stripe webhook: signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )

    event_id = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    if not event_id or not event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed event",
        )

    # Idempotency — short-circuit duplicates.
    if _already_processed(event_id):
        logger.info("Stripe webhook: duplicate event %s (%s); 200", event_id, event_type)
        return {"received": True, "duplicate": True}

    logger.info("Stripe webhook: processing event %s type=%s", event_id, event_type)
    # Body at DEBUG only — contains customer PII.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Stripe webhook body: %s", json.dumps(_event_to_dict(event))[:2000])

    handler = _DISPATCH.get(event_type)
    if handler is None:
        logger.info("Stripe webhook: no handler for %s; ignoring", event_type)
        return {"received": True, "handled": False}

    data_object = _data_object(event)
    try:
        handler(db, data_object)
    except Exception as exc:  # noqa: BLE001
        # Re-raise as 500 so Stripe retries. Don't silently swallow —
        # the whole point of idempotency keys is to make retries safe.
        logger.exception("Stripe webhook: handler %s failed: %s", event_type, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed",
        )

    return {"received": True, "handled": True}


def _event_to_dict(event: Any) -> dict:
    if isinstance(event, dict):
        return event
    # stripe.Event has a .to_dict() / .to_dict_recursive() in newer versions
    for attr in ("to_dict_recursive", "to_dict"):
        fn = getattr(event, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return {}


def _data_object(event: Any) -> dict:
    """Pull the `data.object` payload from either a dict or a stripe.Event."""
    if isinstance(event, dict):
        return (event.get("data") or {}).get("object") or {}
    data = getattr(event, "data", None)
    if data is None:
        return {}
    obj = getattr(data, "object", None)
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}
    # stripe.Resource has to_dict_recursive
    for attr in ("to_dict_recursive", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return {}
