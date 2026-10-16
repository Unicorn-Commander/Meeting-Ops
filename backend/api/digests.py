"""
Time-Window Digests API — map-reduce meeting summaries over time periods.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging

from database.database import get_db
from database.models import RecordingSession, MeetingDigest, DigestDelivery
from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.models import User
from auth.tier import gate_feature_for_caller
from services.providers.registry import get_provider_registry
from utils.time import business_today, business_window_utc

router = APIRouter(prefix="/api/digests", tags=["Digests"])
logger = logging.getLogger(__name__)


class DigestResponse(BaseModel):
    id: Optional[int] = None
    period: str
    date: str
    project_id: Optional[int] = None
    content: str
    meeting_count: int
    cached: bool = False


class DigestJobResponse(BaseModel):
    """202 response: digest generation is queued; poll /api/jobs/{job_id}."""
    job_id: str
    status_url: str
    period: str
    date: str
    cached: bool = False


def _get_date_range(period: str, date_str: str) -> tuple[datetime, datetime]:
    """Return a half-open UTC window for a business-calendar date.

    The selected date is a New York calendar date; only the resulting query
    instants are UTC. This keeps a late-evening Eastern meeting in its named
    day and lets the UTC window change length at DST boundaries.
    """
    selected = datetime.strptime(date_str, "%Y-%m-%d").date()
    if period == "day":
        start_date, end_date = selected, selected + timedelta(days=1)
    elif period == "week":
        start_date = selected - timedelta(days=selected.weekday())
        end_date = start_date + timedelta(days=7)
    elif period == "month":
        start_date = selected.replace(day=1)
        if selected.month == 12:
            end_date = selected.replace(year=selected.year + 1, month=1, day=1)
        else:
            end_date = selected.replace(month=selected.month + 1, day=1)
    elif period == "quarter":
        quarter_start_month = ((selected.month - 1) // 3) * 3 + 1
        start_date = selected.replace(month=quarter_start_month, day=1)
        if quarter_start_month + 3 > 12:
            end_date = selected.replace(year=selected.year + 1, month=1, day=1)
        else:
            end_date = selected.replace(month=quarter_start_month + 3, day=1)
    elif period == "year":
        start_date = selected.replace(month=1, day=1)
        end_date = selected.replace(year=selected.year + 1, month=1, day=1)
    else:
        raise ValueError(f"Invalid period: {period}")
    return business_window_utc(start_date, end_date)


def _week_range_label(date_str: str) -> str:
    selected = datetime.strptime(date_str, "%Y-%m-%d").date()
    start = selected - timedelta(days=selected.weekday())
    last_day = start + timedelta(days=6)
    return f"{start.strftime('%b %-d')}–{last_day.strftime('%b %-d, %Y')}"


async def _generate_digest(
    db: Session,
    org_id: int,
    period: str,
    date_str: str,
    project_id: Optional[int],
) -> DigestResponse:
    start_dt, end_dt = _get_date_range(period, date_str)
    query = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org_id,
        RecordingSession.created_at >= start_dt,
        RecordingSession.created_at < end_dt,
        RecordingSession.status.in_(["completed"]),
    )
    if project_id is not None:
        query = query.filter(RecordingSession.project_id == project_id)

    sessions = query.order_by(RecordingSession.created_at.asc()).all()

    if not sessions:
        return DigestResponse(
            period=period,
            date=date_str,
            project_id=project_id,
            content=f"No completed meetings found for {period} {date_str}.",
            meeting_count=0,
            cached=True,
        )

    meeting_texts = []
    for s in sessions:
        title = s.title or s.name or "Untitled"
        summary = s.summary or "No summary available."
        meeting_texts.append(f"Meeting: {title}\nSummary: {summary}")

    combined = "\n\n---\n\n".join(meeting_texts)

    registry = get_provider_registry(db)
    llm = registry.get_llm(org_id, task="quality")

    chunks = []
    chunk_size = 4000
    for i in range(0, len(combined), chunk_size):
        chunks.append(combined[i:i + chunk_size])

    mini_summaries = []
    for chunk in chunks[:10]:
        prompt = f"Summarize these meeting notes in 2-3 sentences:\n\n{chunk}"
        result = await llm.chat(
            system_prompt="You are a meeting analyst. Summarize concisely.",
            user_prompt=prompt,
            max_tokens=200,
            temperature=0.3,
        )
        if result:
            mini_summaries.append(result)

    if len(mini_summaries) > 1:
        synthesis = await llm.chat(
            system_prompt="You synthesize multiple meeting summaries into a cohesive digest.",
            user_prompt=f"Synthesize these meeting summaries into a unified {period} digest:\n\n" + "\n".join(mini_summaries),
            max_tokens=800,
            temperature=0.3,
        )
        content = synthesis or "\n".join(mini_summaries)
    elif mini_summaries:
        content = mini_summaries[0]
    else:
        content = f"Could not generate digest for {period} {date_str}."

    existing = (
        db.query(MeetingDigest)
        .filter(
            MeetingDigest.organization_id == org_id,
            MeetingDigest.period == period,
            MeetingDigest.date == date_str,
            MeetingDigest.project_id == (str(project_id) if project_id is not None else None),
        )
        .first()
    )

    if existing:
        existing.content = content
        existing.meeting_count = len(sessions)
        existing.source_meeting_ids = [s.id for s in sessions]
        existing.generated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return DigestResponse(
            id=existing.id,
            period=period,
            date=date_str,
            project_id=project_id,
            content=content,
            meeting_count=len(sessions),
            cached=True,
        )

    digest = MeetingDigest(
        organization_id=org_id,
        period=period,
        date=date_str,
        project_id=project_id,
        content=content,
        meeting_count=len(sessions),
        source_meeting_ids=[s.id for s in sessions],
        generated_at=datetime.now(timezone.utc),
    )
    db.add(digest)
    db.commit()
    db.refresh(digest)
    return DigestResponse(
        id=digest.id,
        period=period,
        date=date_str,
        project_id=project_id,
        content=content,
        meeting_count=len(sessions),
        cached=True,
    )


@router.get("")
async def get_digest(
    response: Response,
    period: str = Query(..., description="day, week, month, quarter, year"),
    date: str = Query(None, description="YYYY-MM-DD (defaults to today)"),
    project_id: Optional[int] = Query(None),
    force: bool = Query(False, description="Force regeneration"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Fetch a time-window digest.

    Behavior:
      - Cached digest exists AND `force=false`: return 200 with the cached
        content (any tier).
      - No cache OR `force=true`: tier-gate, then enqueue an arq job and
        return 202 with `{job_id, status_url}`. The frontend polls
        `GET /api/jobs/{job_id}` until the worker finishes.

    v3.18.3 background-jobification: the inline path used to do up to 11
    LLM calls (10 mini-summaries + 1 synthesis), routinely exceeding
    Cloudflare's edge timeout. Heavy work now runs out-of-band.
    """
    if period not in ("day", "week", "month", "quarter", "year"):
        raise HTTPException(status_code=400, detail="Invalid period")
    # Default date to today if not provided
    if not date:
        date = business_today().isoformat()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    if not force:
        existing = (
            db.query(MeetingDigest)
            .filter(
                MeetingDigest.organization_id == active_org.organization.id,
                MeetingDigest.period == period,
                MeetingDigest.date == date,
            )
            .first()
        )
        if existing:
            return DigestResponse(
                id=existing.id,
                period=period,
                date=date,
                project_id=project_id,
                content=existing.content,
                meeting_count=existing.meeting_count,
                cached=True,
            )

    # v3.18.2 tier gate: digest generation runs the server LLM (multiple
    # chat calls to mini-summarize + synthesize). Cached digests above
    # are free for any tier to read; new generation is paid-tier.
    gate_feature_for_caller(current_user, "canonical_reprocess", active_org)

    # v3.18.3: enqueue + 202 + poll. Fall back to inline if arq is
    # unavailable so dev/test envs without Redis keep working.
    try:
        from services.job_runner import enqueue_job
        job_id = await enqueue_job(
            "generate_digest_job",
            active_org.organization.id,
            period,
            date,
            project_id=str(project_id) if project_id is not None else None,
            owner_user_id=current_user.id,
            owner_org_id=active_org.organization.id,
        )
        # Stamp the digest row if one already exists so future workers
        # can drift-check.
        existing_row = (
            db.query(MeetingDigest)
            .filter(
                MeetingDigest.organization_id == active_org.organization.id,
                MeetingDigest.period == period,
                MeetingDigest.date == date,
            )
            .first()
        )
        if existing_row is not None:
            existing_row.generation_job_id = job_id
            db.commit()
        response.status_code = 202
        return DigestJobResponse(
            job_id=job_id,
            status_url=f"/api/jobs/{job_id}",
            period=period,
            date=date,
            cached=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "get_digest: arq enqueue failed period=%s date=%s: %s — running inline",
            period, date, exc,
        )

    return await _generate_digest(db, active_org.organization.id, period, date, project_id)


class DigestPreferences(BaseModel):
    email_daily_digest: bool
    email_weekly_digest: bool


class DigestPreferencesPatch(BaseModel):
    email_daily_digest: Optional[bool] = None
    email_weekly_digest: Optional[bool] = None
    weekly_digest_email: Optional[bool] = None


@router.get("/preferences")
def get_digest_preferences(
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    from workers.weekly_digest_workers import _org_opted_in
    return {
        "email_daily_digest": bool(current_user.email_daily_digest),
        "email_weekly_digest": bool(current_user.email_weekly_digest),
        "weekly_digest_email": bool(current_user.email_weekly_digest),
        "organization_email_enabled": _org_opted_in(active_org.organization),
    }


@router.patch("/preferences")
def update_digest_preferences(
    preferences: DigestPreferencesPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    values = preferences.model_dump(exclude_unset=True)
    if "weekly_digest_email" in values:
        values["email_weekly_digest"] = values.pop("weekly_digest_email")
    for field, value in values.items():
        if value is None:
            raise HTTPException(status_code=422, detail="Preferences must be booleans")
        setattr(current_user, field, value)
    db.commit()
    return get_digest_preferences(current_user, active_org)


def _history_item(db, digest, user_id):
    delivery = db.query(DigestDelivery.sent_at).filter(
        DigestDelivery.organization_id == digest.organization_id,
        DigestDelivery.period == digest.period,
        DigestDelivery.date == digest.date,
        DigestDelivery.user_id == user_id,
        DigestDelivery.sent_at.isnot(None),
    ).first()
    item = {
        "id": digest.id, "period": digest.period, "date": digest.date,
        "meeting_count": digest.meeting_count,
        "generated_at": digest.generated_at or digest.created_at,
        "emailed_to_you": delivery is not None,
        "delivery_status": "emailed" if delivery is not None else "in-app only",
    }
    if digest.period == "week":
        item["week_range"] = _week_range_label(digest.date)
        item["title"] = f"Weekly digest · {_week_range_label(digest.date)}"
    else:
        item["title"] = f"Daily digest · {digest.date}"
    return item


@router.get("/history")
def get_digest_history(
    period: str = Query("day", pattern="^(day|week)$"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Stored digests are readable on all tiers, like the existing cache hit.

    Cursor is date|id, ordered newest window first with an id tie-breaker.
    Project-specific digests are excluded from the organization history.
    """
    from sqlalchemy import and_, or_
    query = db.query(MeetingDigest).filter(
        MeetingDigest.organization_id == active_org.organization.id,
        MeetingDigest.period == period,
        MeetingDigest.project_id.is_(None),
    )
    try:
        for value in (from_date, to_date):
            if value:
                if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
                    raise ValueError()
        if from_date and to_date and from_date > to_date:
            raise ValueError()
        if cursor:
            cursor_date, cursor_id = cursor.split("|")
            if datetime.strptime(cursor_date, "%Y-%m-%d").strftime("%Y-%m-%d") != cursor_date:
                raise ValueError()
            query = query.filter(or_(
                MeetingDigest.date < cursor_date,
                and_(MeetingDigest.date == cursor_date, MeetingDigest.id < int(cursor_id)),
            ))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date range or cursor")
    if from_date:
        query = query.filter(MeetingDigest.date >= from_date)
    if to_date:
        query = query.filter(MeetingDigest.date <= to_date)
    rows = query.order_by(MeetingDigest.date.desc(), MeetingDigest.id.desc()).limit(limit + 1).all()
    page = rows[:limit]
    return {
        "items": [_history_item(db, row, current_user.id) for row in page],
        "next_cursor": f"{page[-1].date}|{page[-1].id}" if len(rows) > limit else None,
    }


@router.get("/history/{digest_id}")
def get_digest_detail(
    digest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    digest = db.query(MeetingDigest).filter(
        MeetingDigest.id == digest_id,
        MeetingDigest.organization_id == active_org.organization.id,
        MeetingDigest.project_id.is_(None),
    ).first()
    if digest is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    # Re-check scope and existence: meetings can be deleted or moved later.
    sources = db.query(RecordingSession).filter(
        RecordingSession.organization_id == active_org.organization.id,
        RecordingSession.id.in_(digest.source_meeting_ids or []),
    ).order_by(RecordingSession.created_at, RecordingSession.id).all()
    return {
        **_history_item(db, digest, current_user.id), "content": digest.content,
        "sources_recorded": digest.source_meeting_ids is not None,
        "source_meetings": [{"id": s.id, "title": s.title or s.name or "Untitled"} for s in sources],
    }
