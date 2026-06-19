"""POST /api/simple/recording-sessions/{id}/email-attendees

Send a meeting summary/transcript/link to selected attendees via
Postmark. When the link is included, each recipient gets (or reuses) a
session_collaborators row so their token grants read access.
"""
from __future__ import annotations

import html
import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.tier import gate_feature_for_caller
from database.database import get_db
from auth.models import User
from database.models import (
    RecordingSession,
    SessionCollaborator,
    SpeakerProfile,
    SpeakerSessionLink,
)
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simple/recording-sessions", tags=["session-emails"])


class EmailAttendeesRequest(BaseModel):
    # When speaker_ids is provided, send to those SpeakerProfile emails (existing
    # behavior). When omitted/empty AND additional_recipients is also empty,
    # fall back to session.participants[*].email.
    speaker_ids: Optional[List[int]] = Field(default=None, max_length=64)
    # Arbitrary external email addresses — people who were NOT identified
    # as speakers in this meeting. Each one gets a fresh (or reused)
    # SessionCollaborator row + magic-link token granting read access to
    # ONLY this session.
    additional_recipients: List[EmailStr] = Field(
        default_factory=list,
        max_length=64,
        description="Free-form external email addresses to also send to",
    )
    include: List[str] = Field(
        default_factory=lambda: ["link"],
        description="Which artifacts to include: link, summary_pdf, transcript_pdf",
    )
    message: Optional[str] = Field(default=None, max_length=4000)


class EmailAttendeesResponse(BaseModel):
    sent: int
    skipped: int
    failures: List[dict] = Field(default_factory=list)


def _get_session_or_404(db: Session, org_id: int, session_id: str) -> RecordingSession:
    query = db.query(RecordingSession).filter(RecordingSession.organization_id == org_id)
    sess = query.filter(RecordingSession.session_id == session_id).first()
    if sess:
        return sess
    try:
        sess = query.filter(RecordingSession.id == int(session_id)).first()
    except (TypeError, ValueError):
        sess = None
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


def _resolve_link_for_email(
    db: Session,
    session: RecordingSession,
    inviter: User,
    email: str,
) -> str:
    """Find or create a session_collaborators row for this email with
    read access, then return the magic-link URL. Idempotent — reuses
    any existing un-revoked row."""
    existing = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.session_id == session.id,
            SessionCollaborator.email == email,
            SessionCollaborator.revoked_at.is_(None),
        )
        .first()
    )
    if not existing:
        existing = SessionCollaborator(
            session_id=session.id,
            email=email,
            access_level="read",
            invited_by_user_id=inviter.id,
            token=uuid.uuid4(),
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
    base = (
        os.getenv("MEETING_OPS_PUBLIC_URL", "").strip().rstrip("/")
        or "https://meetingops.magicunicorn.dev"
    )
    return f"{base}/shared/sessions?token={existing.token}"


def _build_html(
    session: RecordingSession,
    inviter: User,
    recipient_name: str,
    link: Optional[str],
    message: Optional[str],
) -> str:
    title = html.escape(session.title or session.name or "Meeting recording")
    sender_name = html.escape(inviter.full_name or inviter.username or inviter.email)
    body_parts = [
        '<div style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; max-width: 600px; margin: 0 auto; color: #1f2937; padding: 24px;">',
        f'<h2 style="color: #1f2937; margin: 0 0 12px;">{title}</h2>',
        f'<p style="color: #4b5563;">Hi {html.escape(recipient_name)},</p>',
        f'<p style="color: #4b5563;">{sender_name} shared a meeting recording with you.</p>',
    ]
    if message:
        body_parts.append(
            f'<div style="border-left: 3px solid #9333ea; padding: 12px 16px; background: #faf5ff; margin: 16px 0; color: #1f2937; white-space: pre-wrap;">{html.escape(message)}</div>'
        )
    if link:
        body_parts.append(
            f'<p style="margin: 24px 0;"><a href="{link}" style="background: #7c3aed; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 500;">Open the meeting</a></p>'
        )
        body_parts.append(
            f'<p style="color: #6b7280; font-size: 13px;">Or paste this link into your browser: <a href="{link}" style="color: #7c3aed;">{link}</a></p>'
        )
    body_parts.append(
        '<hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />'
    )
    body_parts.append(
        '<p style="color: #9ca3af; font-size: 12px;">Sent by Meeting-Ops on behalf of '
        + sender_name
        + '. Reply to this email to talk to '
        + sender_name
        + ' directly.</p>'
    )
    body_parts.append("</div>")
    return "".join(body_parts)


def _build_attachments(
    db: Session, session: RecordingSession, include: List[str]
) -> List[dict]:
    """Generate base64-encoded attachments for any requested PDFs."""
    import base64
    from api.batch_export import ExportOptions, export_to_pdf

    out: List[dict] = []
    safe_title = (session.title or session.name or "meeting").replace(" ", "_")[:80]
    if "summary_pdf" in include or "transcript_pdf" in include:
        opts_summary = ExportOptions(includeTranscript=False)
        opts_transcript = ExportOptions(includeTranscript=True)
        if "summary_pdf" in include:
            try:
                pdf_bytes = export_to_pdf(session, opts_summary)
                out.append({
                    "Name": f"{safe_title}_summary.pdf",
                    "Content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "ContentType": "application/pdf",
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("Summary PDF generation failed: %s", exc)
        if "transcript_pdf" in include:
            try:
                pdf_bytes = export_to_pdf(session, opts_transcript)
                out.append({
                    "Name": f"{safe_title}_transcript.pdf",
                    "Content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "ContentType": "application/pdf",
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("Transcript PDF generation failed: %s", exc)
    return out


def _postmark_send(
    *,
    to_email: str,
    to_name: Optional[str],
    subject: str,
    html_body: str,
    reply_to: Optional[str] = None,
    attachments: Optional[List[dict]] = None,
) -> dict:
    import httpx

    token = os.getenv("POSTMARK_SERVER_TOKEN", "").strip()
    sender = os.getenv("POSTMARK_FROM", "").strip()
    stream = os.getenv("POSTMARK_MESSAGE_STREAM", "outbound").strip() or "outbound"
    if not token or not sender:
        return {"ok": False, "error": "POSTMARK_SERVER_TOKEN/POSTMARK_FROM not configured"}

    to_field = f"{to_name} <{to_email}>" if to_name else to_email
    payload = {
        "From": sender,
        "To": to_field,
        "Subject": subject,
        "HtmlBody": html_body,
        "MessageStream": stream,
    }
    if reply_to:
        payload["ReplyTo"] = reply_to
    if attachments:
        payload["Attachments"] = attachments

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": token,
                },
                json=payload,
            )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200:
            return {"ok": True, "message_id": data.get("MessageID")}
        return {"ok": False, "error": data.get("Message") or f"HTTP {resp.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@router.post(
    "/{session_id}/email-attendees",
    response_model=EmailAttendeesResponse,
)
async def email_attendees(
    session_id: str,
    payload: EmailAttendeesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Send the meeting link / summary / transcript to selected speakers."""
    # v3.18.3: defense-in-depth tier gate. Free users have no server-side
    # summaries / canonical transcript to email out (browser-only tier), so
    # this endpoint should never be reachable for them. Explicit gate
    # prevents a future regression silently re-opening the surface.
    gate_feature_for_caller(current_user, "canonical_reprocess")
    session = _get_session_or_404(db, active_org.organization.id, session_id)

    # Auth: org admin/manager or session creator
    is_admin = active_org.role_name in {"owner", "admin", "manager"}
    is_creator = bool(session.user_id) and session.user_id == current_user.id
    if not (is_admin or is_creator or getattr(current_user, "is_superuser", False)):
        raise HTTPException(status_code=403, detail="Not permitted to email attendees for this session")

    # Build the recipient list. The handler supports three input modes,
    # which can combine in a single send:
    #   1. speaker_ids — named speakers identified in the meeting (existing
    #      EmailAttendeesModal flow). Looks up SpeakerProfile.email.
    #   2. additional_recipients — free-form external email addresses for
    #      people NOT identified as attendees. Each gets a session-scoped
    #      magic link.
    #   3. Neither provided — fall back to session.participants[*].email,
    #      preserving the "send to the people who were here" button on
    #      SessionDetails.
    recipients: List[dict] = []
    if payload.speaker_ids:
        speakers = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.id.in_(payload.speaker_ids),
                SpeakerProfile.organization_id == active_org.organization.id,
            )
            .all()
        )
        if not speakers:
            # Only 404 here if neither input source produced anything; the
            # caller may still have valid additional_recipients.
            if not payload.additional_recipients:
                raise HTTPException(status_code=404, detail="No matching speakers")
        for sp in speakers:
            recipients.append({
                "ref": f"speaker:{sp.id}",
                "speaker_id": sp.id,
                "name": sp.display_name,
                "email": (sp.email or "").strip(),
            })

    if payload.additional_recipients:
        # Dedupe against already-collected speaker emails so we don't double-send
        # to someone who's both a named speaker and was re-typed into the
        # external-recipients box.
        existing_emails = {(r.get("email") or "").lower() for r in recipients if r.get("email")}
        for raw_email in payload.additional_recipients:
            email = str(raw_email).strip()
            if not email or email.lower() in existing_emails:
                continue
            existing_emails.add(email.lower())
            recipients.append({
                "ref": f"external:{email.lower()}",
                "name": None,
                "email": email,
            })

    if not recipients and not payload.speaker_ids:
        # Neither speaker_ids nor additional_recipients supplied — try the
        # participants fallback.
        raw = session.participants if isinstance(session.participants, list) else []
        for p in raw:
            if not isinstance(p, dict):
                continue
            recipients.append({
                "ref": f"participant:{p.get('id')}",
                "participant_id": p.get("id"),
                "name": (p.get("name") or "").strip() or None,
                "email": (p.get("email") or "").strip(),
            })
        if not recipients:
            raise HTTPException(
                status_code=400,
                detail="No recipients: session has no participants and no speaker_ids or additional_recipients passed",
            )

    if not recipients:
        # speaker_ids was passed but resolved to zero usable rows AND no
        # additional_recipients — refuse explicitly so the UI shows a useful
        # error rather than a silent 200 with sent=0.
        raise HTTPException(
            status_code=400,
            detail="No recipients to send to",
        )

    include = [s.lower() for s in (payload.include or ["link"])]
    attachments = _build_attachments(db, session, include) or None

    sent = 0
    skipped = 0
    failures: List[dict] = []

    subject_title = session.title or session.name or "Meeting recording"
    subject = f"Meeting: {subject_title}"

    for r in recipients:
        email = (r.get("email") or "").strip()
        name = r.get("name")
        if not email:
            skipped += 1
            failure: dict = {"name": name, "reason": "no email on file"}
            if "speaker_id" in r:
                failure["speaker_id"] = r["speaker_id"]
            elif "participant_id" in r:
                failure["participant_id"] = r["participant_id"]
            elif r.get("ref", "").startswith("external:"):
                failure["external"] = True
            failures.append(failure)
            continue
        link = _resolve_link_for_email(db, session, current_user, email) if "link" in include else None
        html_body = _build_html(session, current_user, name or email, link, payload.message)
        result = _postmark_send(
            to_email=email,
            to_name=name,
            subject=subject,
            html_body=html_body,
            reply_to=current_user.email,
            attachments=attachments,
        )
        if result.get("ok"):
            sent += 1
        else:
            failure = {"name": name, "email": email, "reason": result.get("error") or "send failed"}
            if "speaker_id" in r:
                failure["speaker_id"] = r["speaker_id"]
            elif "participant_id" in r:
                failure["participant_id"] = r["participant_id"]
            elif r.get("ref", "").startswith("external:"):
                failure["external"] = True
            failures.append(failure)

    sources = []
    if payload.speaker_ids:
        sources.append("speakers")
    if payload.additional_recipients:
        sources.append("external")
    if not sources:
        sources.append("participants")
    logger.info(
        "email-attendees: session=%s sent=%d skipped=%d failed=%d (source=%s)",
        session.id, sent, skipped, len(failures),
        "+".join(sources),
    )
    return EmailAttendeesResponse(sent=sent, skipped=skipped, failures=failures)
