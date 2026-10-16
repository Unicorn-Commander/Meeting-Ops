"""Scheduled in-app digests; delivery requires account opt-in AND org permission.

The arq cron invokes these hooks hourly because arq cron has no timezone. Each
hook acts during 09:00–09:59 in ``America/New_York`` (daily) or on that hour
Monday (weekly), so the delivery wall-clock time remains stable across DST.
Generation is independent of email settings. Existing WEEKLY_DIGEST_* paid/cap
controls apply to both periods; DAILY_DIGEST_ENABLED controls the daily pass.
See docs/in-app-digests.md for precedence, retries, and rollout.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.time import business_date_from_utc, business_today, utc_to_business

logger = logging.getLogger(__name__)

SCHEDULED_LOCAL_HOUR = 9


# ----------------------------- env knobs ---------------------------------- #

def _enabled() -> bool:
    return os.getenv("WEEKLY_DIGEST_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _default_on() -> bool:
    """Fallback org permission only; personal opt-ins are always required."""
    return os.getenv("WEEKLY_DIGEST_DEFAULT_ON", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_paid() -> bool:
    return os.getenv("WEEKLY_DIGEST_REQUIRE_PAID", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _max_orgs_per_pass() -> int:
    try:
        return max(1, int(os.getenv("WEEKLY_DIGEST_MAX_ORGS_PER_PASS", "500")))
    except ValueError:
        return 500


def _public_base_url() -> str:
    return (
        os.getenv("MEETING_OPS_PUBLIC_URL", "").strip().rstrip("/")
        or os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
        or os.getenv("APP_BASE_URL", "").strip().rstrip("/")
        or "https://meetingops.magicunicorn.dev"
    )


# --------------------------- date resolution ------------------------------ #

def _last_week_date_str(now: datetime | None = None) -> str:
    """The `date` argument `_generate_digest(\"week\", date)` should receive to
    summarize the PREVIOUS completed Mon-Sun week.

    `api.digests._get_date_range(\"week\", date)` snaps `date` to Monday of its
    ISO week and spans 7 days. Passing any day inside last week yields last
    week's window. We pass last Monday explicitly so the cached digest's
    `date` is stable + human-meaningful (always a Monday)."""
    now = utc_to_business(now or datetime.now(timezone.utc))
    this_monday = now.date() - timedelta(days=now.weekday())
    last_monday = this_monday - timedelta(days=7)
    return last_monday.strftime("%Y-%m-%d")


def _cron_should_run(period: str, now: datetime | None = None) -> bool:
    """Guard an hourly arq tick with the intended New York wall-clock hour."""
    local_now = utc_to_business(now or datetime.now(timezone.utc))
    if local_now.hour != SCHEDULED_LOCAL_HOUR:
        return False
    return period == "day" or (period == "week" and local_now.weekday() == 0)


# ----------------------------- recipients --------------------------------- #

def _resolve_recipients(db, org, period="week"):
    """Only active, verified members who personally opted in; no legacy list fallback."""
    from auth.models import User, UserOrganization
    preference = User.email_daily_digest if period == "day" else User.email_weekly_digest
    return db.query(User).join(UserOrganization, UserOrganization.user_id == User.id).filter(
        UserOrganization.organization_id == org.id,
        User.is_active.is_(True), User.is_verified.is_(True), preference.is_(True),
    ).order_by(User.id).all()


def _org_is_paid(db, org) -> bool:
    """True if the org's plan is paid OR any member is on a non-free tier."""
    if (org.plan or "free").strip().lower() not in ("free", "", "none"):
        return True
    from auth.models import User, UserOrganization

    paid_member = (
        db.query(User.id)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(
            UserOrganization.organization_id == org.id,
            User.tier.isnot(None),
            User.tier != "free",
        )
        .first()
    )
    return paid_member is not None


def _org_opted_in(org) -> bool:
    settings = org.settings if isinstance(org.settings, dict) else {}
    cfg = settings.get("weekly_digest") if isinstance(settings.get("weekly_digest"), dict) else None
    if cfg is None or "enabled" not in cfg:
        return _default_on()
    return bool(cfg.get("enabled"))


# ------------------------------- email ------------------------------------ #

def _render_email_html(org_name: str, period_label: str, content: str, dashboard_url: str) -> str:
    import html as _html

    safe_org = _html.escape(org_name or "your organization")
    safe_period = _html.escape(period_label)
    # `content` is LLM-generated plain text (paragraphs). Escape + preserve
    # newlines; never inject as raw HTML.
    safe_content = _html.escape(content or "No completed meetings this week.").replace("\n", "<br>")
    return f"""\
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#1f2937;background:#f5f5f5;padding:24px">
  <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden">
    <div style="background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;padding:28px 32px">
      <div style="font-size:20px;font-weight:700">Meeting-Ops</div>
      <div style="font-size:13px;opacity:.9;margin-top:4px">Meeting digest for {safe_org}</div>
    </div>
    <div style="padding:28px 32px">
      <h2 style="margin:0 0 6px;font-size:18px">Your meetings</h2>
      <p style="margin:0 0 18px;font-size:13px;color:#6b7280">{safe_period}</p>
      <div style="font-size:14px;line-height:1.7;color:#374151">{safe_content}</div>
      <p style="margin:28px 0 0">
        <a href="{dashboard_url}" style="display:inline-block;background:#7c3aed;color:#fff;text-decoration:none;
           padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600">Open Meeting-Ops</a>
      </p>
    </div>
    <div style="padding:18px 32px;border-top:1px solid #eee;color:#9ca3af;font-size:12px">
      You're receiving this because you opted into digest email.
      Change your preferences on the Digests page or in Settings → Notifications.
    </div>
  </div>
</body></html>"""


def _send_digest_email(*, recipient: str, org_name: str, period: str,
                       period_label: str, content: str, dashboard_url: str) -> bool:
    from auth.email import _send
    cadence = "daily" if period == "day" else "weekly"
    return _send(
        recipient, f"Your {cadence} Meeting-Ops digest — {period_label}",
        _render_email_html(org_name, period_label, content, dashboard_url),
        f"{cadence.title()} Meeting-Ops digest for {org_name} ({period_label}).\n\n"
        f"{content}\n\nOpen Meeting-Ops: {dashboard_url}",
        raise_on_transport_error=True,
    )


def deliver_digest(db, org, digest) -> int:
    """Separate delivery step. Claim each recipient/window before contacting Postmark.

    A definitive False releases the claim. An exception or crash may mean the
    provider accepted mail, so leave the claim unresolved to prevent duplicates.
    """
    from database.models import DigestDelivery
    from sqlalchemy.exc import IntegrityError
    if not _org_opted_in(org):
        return 0
    sent = 0
    for user in _resolve_recipients(db, org, digest.period):
        delivery = DigestDelivery(
            digest_id=digest.id, organization_id=org.id, user_id=user.id,
            period=digest.period, date=digest.date,
        )
        db.add(delivery)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        try:
            success = _send_digest_email(
                recipient=user.email, org_name=org.name, period=digest.period,
                period_label=digest.date, content=digest.content,
                dashboard_url=f"{_public_base_url()}/digests",
            )
        except Exception:
            logger.exception("digest delivery unresolved claim_id=%s", delivery.id)
            continue
        if success:
            sent_at = datetime.now(timezone.utc)
            delivery.sent_at = sent_at
            # Keep the legacy row-level receipt meaningful: NULL means that
            # this scheduled digest has not been emailed to anyone.
            digest.emailed_at = sent_at
            sent += 1
        else:
            db.delete(delivery)
        db.commit()
    return sent


async def store_scheduled_digests(
    period: str, *, date_str: str | None = None, dry_run: bool = False,
) -> dict[str, Any]:
    """Store eligible org digests first, then independently attempt opted-in delivery.

    Candidate selection excludes empty windows before applying the cap. Sort
    ungenerated windows first so previously cached orgs cannot starve later orgs.
    """
    if period not in ("day", "week"):
        raise ValueError("Scheduled period must be day or week")
    enabled = _enabled() if period == "week" else os.getenv("DAILY_DIGEST_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    if not enabled:
        return {"enabled": False}
    from database.database import SessionLocal
    from auth.models import Organization
    from database.models import MeetingDigest, RecordingSession
    from api.digests import _get_date_range, _generate_digest
    from sqlalchemy import exists, case, func, or_
    date_str = date_str or (
        _last_week_date_str()
        if period == "week"
        else (business_today() - timedelta(days=1)).strftime("%Y-%m-%d")
    )
    start_dt, end_dt = _get_date_range(period, date_str)
    date_str = business_date_from_utc(start_dt).strftime("%Y-%m-%d")
    summary = {"enabled": True, "period": period, "date": date_str,
               "orgs_considered": 0, "orgs_processed": 0, "generated": 0,
               "skipped_free": 0, "emails_sent": 0, "errors": 0, "dry_run": dry_run}
    with SessionLocal() as db:
        has_meetings = exists().where(
            RecordingSession.organization_id == Organization.id,
            RecordingSession.status == "completed",
            RecordingSession.created_at >= start_dt, RecordingSession.created_at < end_dt,
        )
        has_digest = exists().where(
            MeetingDigest.organization_id == Organization.id,
            MeetingDigest.period == period, MeetingDigest.date == date_str,
            MeetingDigest.project_id.is_(None),
        )
        # Filter paid candidates BEFORE the cap too, including legacy member grants.
        query = db.query(Organization).filter(Organization.is_active.is_(True), has_meetings)
        if _require_paid():
            from auth.models import User, UserOrganization
            paid_member = exists().where(
                UserOrganization.organization_id == Organization.id,
                UserOrganization.user_id == User.id, User.tier.isnot(None), User.tier != "free",
            )
            query = query.filter(or_(
                func.lower(func.trim(func.coalesce(Organization.plan, "free"))).notin_(("free", "", "none")),
                paid_member,
            ))
        org_ids = [org.id for org in query.order_by(
            case((has_digest, 1), else_=0), Organization.id,
        ).limit(_max_orgs_per_pass()).all()]
    summary["orgs_considered"] = len(org_ids)
    for org_id in org_ids:
        with SessionLocal() as db:
            try:
                org = db.query(Organization).filter(Organization.id == org_id).first()
                if org is None or not org.is_active:
                    continue
                if _require_paid() and not _org_is_paid(db, org):
                    summary["skipped_free"] += 1
                    continue
                if dry_run:
                    summary["orgs_processed"] += 1
                    continue
                digest = db.query(MeetingDigest).filter(
                    MeetingDigest.organization_id == org_id, MeetingDigest.period == period,
                    MeetingDigest.date == date_str, MeetingDigest.project_id.is_(None),
                ).order_by(MeetingDigest.id.desc()).first()
                if digest is None:
                    result = await _generate_digest(db, org_id, period, date_str, None)
                    if result.id is None:
                        continue
                    digest = db.get(MeetingDigest, result.id)
                    summary["generated"] += 1
                summary["orgs_processed"] += 1
                summary["emails_sent"] += deliver_digest(db, org, digest)
            except asyncio.CancelledError:
                raise
            except Exception:
                summary["errors"] += 1
                logger.exception("digest pass failed org_id=%s period=%s", org_id, period)
                db.rollback()
    logger.info("digest pass: %s", summary)
    return summary


async def send_weekly_digests_for_all_orgs(*, date_str=None, dry_run=False):
    """Compatibility entrypoint for existing operators/scripts."""
    return await store_scheduled_digests("week", date_str=date_str, dry_run=dry_run)


async def weekly_digest_cron(ctx: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not _cron_should_run("week", now):
        return {"enabled": False, "period": "week", "reason": "outside business schedule"}
    return await send_weekly_digests_for_all_orgs(
        date_str=_last_week_date_str(now),
    )


async def daily_digest_cron(ctx: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not _cron_should_run("day", now):
        return {"enabled": False, "period": "day", "reason": "outside business schedule"}
    return await store_scheduled_digests(
        "day",
        date_str=(business_today(now) - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
