"""Picker contact ids must resolve inside the session's workspace.

S1: a speaker editor must not attach a Contact-Ops person id that
Contact-Ops cannot resolve as canonical or redirected for the meeting's
workspace. Unreachable Contact-Ops fails closed (no link written).
"""
from __future__ import annotations

import uuid

from auth.utils import get_password_hash

FOREIGN = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CANONICAL = "11111111-2222-4333-8444-555555555555"


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession, SpeakerProfile, SpeakerSessionLink

    return Organization, User, UserOrganization, SessionLocal, RecordingSession, SpeakerProfile, SpeakerSessionLink


def _seed(*, workspace_id: str | None = "set"):
    Organization, User, UserOrganization, SessionLocal, RecordingSession, _, SpeakerSessionLink = _models()
    suffix = uuid.uuid4().hex[:8]
    ws = f"ws-{suffix}" if workspace_id == "set" else workspace_id
    db = SessionLocal()
    try:
        org = Organization(
            name=f"Picker guard {suffix}", slug=f"picker-guard-{suffix}",
            is_active=True, plan="pro", workspace_id=ws,
        )
        db.add(org)
        db.flush()
        user = User(
            email=f"guard_{suffix}@meeting-ops.local", username=f"guard_{suffix}",
            hashed_password=get_password_hash("admin123"), is_active=True, is_verified=True, tier="pro",
        )
        db.add(user)
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=org.id, role="member"))
        session = RecordingSession(
            session_id=str(uuid.uuid4()), name="Guard", title="Guard", status="completed",
            user_id=user.id, organization_id=org.id,
            participants=[{"id": "p1", "name": "Jules Whitman", "email": None, "role": "attendee"}],
            transcript_diarized={
                "segments": [{
                    "idx": 0, "speaker": "SPEAKER_00", "raw_label": "SPEAKER_00",
                    "start": 0.0, "end": 6.0, "text": "I'll send the contract.",
                }],
                "speakers": ["SPEAKER_00"],
            },
        )
        db.add(session)
        db.flush()
        link = SpeakerSessionLink(session_id=session.id, organization_id=org.id, raw_label="SPEAKER_00")
        db.add(link)
        db.commit()
        return {
            "slug": org.slug, "org_id": org.id, "username": user.username,
            "session_pk": session.id, "link_id": link.id, "workspace_id": org.workspace_id,
        }
    finally:
        db.close()


def _headers(client, username, slug):
    resp = client.post("/api/auth/login", data={"username": username, "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}", "X-MeetingOps-Org": slug}


def _add_speaker(org_id, name, contact_id=None, confirmed=False):
    *_, SessionLocal, _, SpeakerProfile, _ = _models()
    db = SessionLocal()
    try:
        sp = SpeakerProfile(
            organization_id=org_id, display_name=name,
            contact_id=contact_id, contact_link_confirmed=confirmed,
        )
        db.add(sp)
        db.commit()
        return sp.id
    finally:
        db.close()


def _mock_resolver(monkeypatch, *, status="canonical", canonical=None, unavailable=False, configured=True):
    from api import speakers as speakers_api

    seen = {"calls": 0, "workspace_id": None, "person_id": None}
    monkeypatch.setattr(speakers_api.contact_ops_resolver, "is_configured", lambda: configured)

    async def resolve(person_id, workspace_id):
        seen["calls"] += 1
        seen["person_id"] = person_id
        seen["workspace_id"] = workspace_id
        if unavailable:
            return None
        chosen = person_id if canonical is None else canonical
        return {
            "requested_person_id": person_id,
            "canonical_person_id": chosen,
            "alias_ids": [],
            "status": status,
        }

    monkeypatch.setattr(speakers_api.contact_ops_resolver, "resolve_person_id", resolve)
    return seen


def _speaker_contact(speaker_id):
    *_, SessionLocal, _, SpeakerProfile, _ = _models()
    db = SessionLocal()
    try:
        sp = db.query(SpeakerProfile).filter(SpeakerProfile.id == speaker_id).one()
        return sp.contact_id, sp.contact_link_confirmed
    finally:
        db.close()


def _link_speaker(link_id):
    *_, SessionLocal, _, _, SpeakerSessionLink = _models()
    db = SessionLocal()
    try:
        return db.query(SpeakerSessionLink).filter(SpeakerSessionLink.id == link_id).one().speaker_id
    finally:
        db.close()


def _profiles(org_id):
    *_, SessionLocal, _, SpeakerProfile, _ = _models()
    db = SessionLocal()
    try:
        rows = db.query(SpeakerProfile).filter(SpeakerProfile.organization_id == org_id).all()
        return [(r.display_name, r.contact_id, r.contact_link_confirmed) for r in rows]
    finally:
        db.close()


def test_assign_rejects_contact_outside_the_session_workspace(client, monkeypatch, tmp_path):
    """PATCH, create-speaker, and enroll all refuse an unresolved id and write nothing."""
    seeded = _seed()
    speaker_id = _add_speaker(seeded["org_id"], "Jules Whitman")
    seen = _mock_resolver(monkeypatch, status="not_found", canonical=None)
    headers = _headers(client, seeded["username"], seeded["slug"])

    patched = client.patch(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}",
        headers=headers,
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": FOREIGN},
    )
    assert patched.status_code == 422, patched.text
    assert "not linkable" in patched.json()["detail"]
    assert _speaker_contact(speaker_id) == (None, False)
    assert _link_speaker(seeded["link_id"]) is None
    assert seen["workspace_id"] == seeded["workspace_id"]
    assert seen["person_id"] == FOREIGN

    created = client.post(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}/create-speaker",
        headers=headers,
        json={"display_name": "New Person", "contact_id": FOREIGN},
    )
    assert created.status_code == 422, created.text
    assert _profiles(seeded["org_id"]) == [("Jules Whitman", None, False)]
    assert _link_speaker(seeded["link_id"]) is None

    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFFfake")
    *_, SessionLocal, RecordingSession, _, _ = _models()
    db = SessionLocal()
    try:
        row = db.query(RecordingSession).filter(RecordingSession.id == seeded["session_pk"]).one()
        row.audio_file = str(audio)
        db.commit()
    finally:
        db.close()

    def _fake_ffmpeg(args, **_kwargs):
        with open(args[-1], "wb") as fh:
            fh.write(b"RIFFfake")

        class Proc:
            returncode = 0
            stderr = b""

        return Proc()

    monkeypatch.setattr("subprocess.run", _fake_ffmpeg)
    enrolled = client.post(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}/enroll",
        headers=headers,
        json={"display_name": "Enrolled Foreign", "contact_id": FOREIGN},
    )
    assert enrolled.status_code == 422, enrolled.text
    assert _link_speaker(seeded["link_id"]) is None
    assert all(name != "Enrolled Foreign" for name, _cid, _ok in _profiles(seeded["org_id"]))
    assert all(cid != FOREIGN for _name, cid, _ok in _profiles(seeded["org_id"]))


def test_assign_fails_closed_when_contact_ops_is_unreachable(client, monkeypatch):
    seeded = _seed()
    speaker_id = _add_speaker(seeded["org_id"], "Jules Whitman")
    seen = _mock_resolver(monkeypatch, unavailable=True)
    resp = client.patch(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}",
        headers=_headers(client, seeded["username"], seeded["slug"]),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": FOREIGN},
    )
    assert resp.status_code == 503, resp.text
    assert "unavailable" in resp.json()["detail"]
    assert seen["calls"] == 1
    assert _speaker_contact(speaker_id) == (None, False)
    assert _link_speaker(seeded["link_id"]) is None


def test_assign_fails_closed_when_contact_ops_is_not_configured(client, monkeypatch):
    seeded = _seed()
    speaker_id = _add_speaker(seeded["org_id"], "Jules Whitman")
    seen = _mock_resolver(monkeypatch, configured=False)
    resp = client.patch(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}",
        headers=_headers(client, seeded["username"], seeded["slug"]),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": FOREIGN},
    )
    assert resp.status_code == 503, resp.text
    assert "not configured" in resp.json()["detail"]
    assert seen["calls"] == 0
    assert _speaker_contact(speaker_id) == (None, False)
    assert _link_speaker(seeded["link_id"]) is None


def test_assign_rejects_when_session_workspace_is_unmapped(client, monkeypatch):
    seeded = _seed(workspace_id=None)
    speaker_id = _add_speaker(seeded["org_id"], "Jules Whitman")
    seen = _mock_resolver(monkeypatch)
    resp = client.patch(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}",
        headers=_headers(client, seeded["username"], seeded["slug"]),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": FOREIGN},
    )
    assert resp.status_code == 409, resp.text
    assert "not mapped" in resp.json()["detail"]
    assert seen["calls"] == 0
    assert _speaker_contact(speaker_id) == (None, False)


def test_assign_stores_redirected_canonical_id(client, monkeypatch):
    seeded = _seed()
    speaker_id = _add_speaker(seeded["org_id"], "Jules Whitman")
    seen = _mock_resolver(monkeypatch, status="redirected", canonical=CANONICAL)
    resp = client.patch(
        f"/api/sessions/{seeded['session_pk']}/speaker-links/{seeded['link_id']}",
        headers=_headers(client, seeded["username"], seeded["slug"]),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": FOREIGN},
    )
    assert resp.status_code == 200, resp.text
    assert seen["workspace_id"] == seeded["workspace_id"]
    assert _speaker_contact(speaker_id) == (CANONICAL, True)
    assert _link_speaker(seeded["link_id"]) == speaker_id

    *_, SessionLocal, RecordingSession, _, _ = _models()
    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == seeded["session_pk"]).one()
        assert [p.get("contact_id") for p in session.participants] == [CANONICAL]
    finally:
        db.close()
