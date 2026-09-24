"""Speaker picker -> Contact-Ops link (2026-09-24, P-00055 task 7b39b094).

Picking a Contact-Ops person for a voice in the meeting's speaker picker
must: land on the profile already linked to that person (never mint a
duplicate), fill an EMPTY contact link only (a different existing link is a
409, not a silent re-point), carry the name onto action-item owners
instantly, and stamp the contact onto the meeting's participants so
Customer-Ops (which finds meetings by participant contact_id) sees it.
"""
from __future__ import annotations

import uuid

from auth.utils import get_password_hash

CONTACT_A = "3f6c2a8e-1d4b-4c1e-9a52-6b0f1e7d2c01"
CONTACT_B = "9b1d7e44-5a0c-4f3e-8e21-2c6a9d0b4f02"


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import ActionItem, RecordingSession, SpeakerProfile, SpeakerSessionLink

    return Organization, User, UserOrganization, SessionLocal, RecordingSession, SpeakerProfile, SpeakerSessionLink, ActionItem


def _seed(role: str = "admin"):
    Organization, User, UserOrganization, SessionLocal, RecordingSession, _, SpeakerSessionLink, ActionItem = _models()
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        org = Organization(name=f"Picker {suffix}", slug=f"picker-{suffix}", is_active=True, plan="pro")
        db.add(org)
        db.flush()
        user = User(
            email=f"picker_{suffix}@meeting-ops.local", username=f"picker_{suffix}",
            hashed_password=get_password_hash("admin123"), is_active=True, is_verified=True, tier="pro",
        )
        db.add(user)
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=org.id, role=role))
        session = RecordingSession(
            session_id=str(uuid.uuid4()), name="Picker test", title="Picker test", status="completed",
            user_id=user.id, organization_id=org.id,
            participants=[{"id": "p1", "name": "Jules Whitman", "email": None, "role": "attendee"}],
            transcript_diarized={
                "segments": [{"idx": 0, "speaker": "Speaker 7C21", "raw_label": "SPEAKER_00",
                              "start": 0.0, "end": 6.0, "text": "I'll send the contract."}],
                "speakers": ["Speaker 7C21"],
            },
            final_summary={"executive": "Speaker 7C21 will send the contract.",
                           "actions": [{"action": "Send the contract", "owner": "Speaker 7C21"}]},
        )
        db.add(session)
        db.flush()
        link = SpeakerSessionLink(session_id=session.id, organization_id=org.id, raw_label="SPEAKER_00")
        db.add(link)
        db.add(ActionItem(session_id=session.id, organization_id=org.id,
                          text="Speaker 7C21 sends the contract", owner="Speaker 7C21"))
        db.commit()
        return org.slug, org.id, user.username, session.id, link.id
    finally:
        db.close()


def _headers(client, username, slug):
    resp = client.post("/api/auth/login", data={"username": username, "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}", "X-MeetingOps-Org": slug}


def _add_speaker(org_id, name, contact_id=None, confirmed=False):
    *_, SessionLocal, _, SpeakerProfile, _, _ = _models()
    db = SessionLocal()
    try:
        sp = SpeakerProfile(organization_id=org_id, display_name=name,
                            contact_id=contact_id, contact_link_confirmed=confirmed)
        db.add(sp)
        db.commit()
        return sp.id
    finally:
        db.close()


def test_assign_with_contact_fills_link_relabels_items_and_stamps_participant(client):
    slug, org_id, username, session_pk, link_id = _seed(role="member")
    speaker_id = _add_speaker(org_id, "Jules Whitman")

    resp = client.patch(
        f"/api/sessions/{session_pk}/speaker-links/{link_id}",
        headers=_headers(client, username, slug),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": CONTACT_A},
    )
    assert resp.status_code == 200, resp.text

    *_, SessionLocal, RecordingSession, SpeakerProfile, _, ActionItem = _models()
    db = SessionLocal()
    try:
        sp = db.query(SpeakerProfile).filter(SpeakerProfile.id == speaker_id).one()
        assert (sp.contact_id, sp.contact_link_confirmed) == (CONTACT_A, True)
        item = db.query(ActionItem).filter(ActionItem.session_id == session_pk).one()
        assert (item.owner, item.text) == ("Jules Whitman", "Jules Whitman sends the contract")
        session = db.query(RecordingSession).filter(RecordingSession.id == session_pk).one()
        assert session.final_summary["actions"][0]["owner"] == "Jules Whitman"
        # Existing same-name participant got the contact; no duplicate entry.
        assert [(p["id"], p.get("contact_id")) for p in session.participants] == [("p1", CONTACT_A)]
    finally:
        db.close()


def test_picker_never_repoints_a_profile_linked_to_another_contact(client):
    slug, org_id, username, session_pk, link_id = _seed(role="member")
    speaker_id = _add_speaker(org_id, "Jules Whitman", contact_id=CONTACT_B, confirmed=True)

    resp = client.patch(
        f"/api/sessions/{session_pk}/speaker-links/{link_id}",
        headers=_headers(client, username, slug),
        json={"speaker_id": speaker_id, "confirmed": True, "contact_id": CONTACT_A},
    )
    assert resp.status_code == 409, resp.text

    *_, SessionLocal, _, SpeakerProfile, SpeakerSessionLink, _ = _models()
    db = SessionLocal()
    try:
        assert db.query(SpeakerProfile).filter(SpeakerProfile.id == speaker_id).one().contact_id == CONTACT_B
        assert db.query(SpeakerSessionLink).filter(SpeakerSessionLink.id == link_id).one().speaker_id is None
    finally:
        db.close()


def test_create_with_contact_reuses_the_profile_already_linked_to_it(client):
    slug, org_id, username, session_pk, link_id = _seed(role="member")
    existing = _add_speaker(org_id, "Dana W.", contact_id=CONTACT_A, confirmed=True)

    resp = client.post(
        f"/api/sessions/{session_pk}/speaker-links/{link_id}/create-speaker",
        headers=_headers(client, username, slug),
        json={"display_name": "Jules Whitman", "contact_id": CONTACT_A},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["speaker_id"] == existing

    *_, SessionLocal, _, SpeakerProfile, _, _ = _models()
    db = SessionLocal()
    try:
        names = [s.display_name for s in db.query(SpeakerProfile).filter(SpeakerProfile.organization_id == org_id)]
        assert names == ["Dana W."]
    finally:
        db.close()


def test_library_contact_link_backfills_past_meeting_participants(client):
    slug, org_id, username, session_pk, link_id = _seed(role="admin")
    speaker_id = _add_speaker(org_id, "Jules Whitman")
    h = _headers(client, username, slug)
    assert client.patch(
        f"/api/sessions/{session_pk}/speaker-links/{link_id}", headers=h,
        json={"speaker_id": speaker_id, "confirmed": True},
    ).status_code == 200

    resp = client.patch(f"/api/speakers/{speaker_id}/contact-link", headers=h,
                        json={"contact_id": CONTACT_A, "confirmed": True})
    assert resp.status_code == 200, resp.text

    *_, SessionLocal, RecordingSession, _, _, _ = _models()
    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_pk).one()
        assert [p.get("contact_id") for p in session.participants] == [CONTACT_A]
    finally:
        db.close()
