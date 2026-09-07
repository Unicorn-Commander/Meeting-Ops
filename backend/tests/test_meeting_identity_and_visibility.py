"""One meeting is one session, readable by the people who were in it.

Two behaviours are pinned here.

**Meeting identity.** Unicorn Stable exports a call once per participant
browser, and the payload each browser hashes into ``export_id`` contains that
browser's own clock, so an N-person call produces N different export_ids —
reliably, not as a race. Before ``meeting_key`` that meant N sessions and N
summaries. These tests prove the exports coalesce onto one session, that a
genuinely different call in the same room still gets its own, and that the
pre-existing replay/conflict contract is unchanged.

**Who may read it.** The default is unchanged: every member of the owning
organization reads every session in it. An organization may narrow that to
``participants``, and then a member who was not in the meeting is refused —
including through the list and search side doors. Identity comes from a
verified email or a server-stamped user_id, never from an unverified claim.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api import stable_ingest
from api.session_permissions import has_session_access, resolve_session_for_user
from auth.models import Organization, User, UserOrganization
from database.database import SessionLocal, engine
from database.models import Base, RecordingSession
from database import models_rooms  # noqa: F401 - registers FK targets
from services.session_visibility import (
    SESSION_VISIBILITY_KEY,
    VISIBILITY_ORGANIZATION,
    VISIBILITY_PARTICIPANTS,
    user_is_participant,
    visible_session_clause,
)

BASE = datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _org(db, slug: str, visibility: str | None = None) -> Organization:
    org = Organization(
        name=f"Org {slug}",
        slug=slug,
        is_active=True,
        settings=({SESSION_VISIBILITY_KEY: visibility} if visibility else {}),
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _user(
    db,
    email: str,
    *,
    username: str | None = None,
    verified: bool = True,
    active: bool = True,
    superuser: bool = False,
) -> User:
    user = User(
        email=email,
        username=username or email.split("@")[0] + uuid.uuid4().hex[:6],
        hashed_password="x",
        is_active=active,
        is_verified=verified,
        is_superuser=superuser,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _member(db, user: User, org: Organization, role: str = "member") -> None:
    db.add(
        UserOrganization(user_id=user.id, organization_id=org.id, role=role)
    )
    db.commit()


def _session(
    db,
    org: Organization,
    *,
    owner: User | None = None,
    participants: list[dict] | None = None,
) -> RecordingSession:
    row = RecordingSession(
        session_id=str(uuid.uuid4()),
        name="A meeting",
        status="completed",
        organization_id=org.id,
        user_id=owner.id if owner else None,
        participants=participants or [],
        started_at=BASE.replace(tzinfo=None),
        ended_at=(BASE + timedelta(minutes=30)).replace(tzinfo=None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _set_visibility(db, org: Organization, visibility: str) -> None:
    org.settings = {SESSION_VISIBILITY_KEY: visibility}
    db.add(org)
    db.commit()
    db.refresh(org)


# ---------------------------------------------------------------------
# Meeting identity — the Stable ingest coalescing
# ---------------------------------------------------------------------


def _ingest_body(
    *,
    room_id: str,
    export_id: str,
    started: datetime,
    ended: datetime,
    lines: list[tuple[str, str, datetime]],
    exporter: dict | None = None,
    meeting_ops_session_id: str | None = None,
) -> stable_ingest.StableTranscriptIngest:
    payload_lines = [
        {
            "participant_id": pid,
            "name": name,
            "text": f"{name} said something",
            "ts": int(ts.timestamp() * 1000),
        }
        for pid, name, ts in lines
    ]
    return stable_ingest.StableTranscriptIngest(
        source="unicorn-stable",
        export_id=export_id,
        exported_at=ended,
        room_id=room_id,
        room_name="Design review",
        call_started_at=started,
        call_ended_at=ended,
        exporter=exporter or {},
        meeting_ops_session_id=meeting_ops_session_id,
        line_count=len(payload_lines),
        lines=payload_lines,
        metadata={},
    )


class _Principal:
    def __init__(self, user, org):
        self.user = user
        self.token = type("T", (), {"id": 1, "scope": "stable.transcript.ingest",
                                    "organization_id": org.id})()
        self.active_org = type("A", (), {"organization": org})()


async def _ingest(db, principal, body):
    return await stable_ingest.ingest_stable_transcript(
        body=body, idempotency_key=None, db=db, principal=principal
    )


@pytest.mark.asyncio
async def test_two_participants_exporting_one_call_make_one_session(db):
    """The headline case: two browsers, two export_ids, one meeting."""
    org = _org(db, f"coalesce-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    # Alice joined at 15:00 and hung up at 15:30.
    first = await _ingest(db, principal, _ingest_body(
        room_id="room-1",
        export_id="export-alice",
        started=BASE,
        ended=BASE + timedelta(minutes=30),
        lines=[("p-alice", "Alice", BASE + timedelta(minutes=1))],
    ))
    assert first.created is True

    # Bob joined late and hung up 12 seconds later than Alice: a different
    # window and a different line set, therefore a different export_id.
    second = await _ingest(db, principal, _ingest_body(
        room_id="room-1",
        export_id="export-bob",
        started=BASE + timedelta(minutes=5),
        ended=BASE + timedelta(minutes=30, seconds=12),
        lines=[
            ("p-alice", "Alice", BASE + timedelta(minutes=1)),
            ("p-bob", "Bob", BASE + timedelta(minutes=6)),
        ],
    ))

    assert second.created is False
    assert second.session_id == first.session_id
    rows = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).all()
    assert len(rows) == 1, "one call must not become two sessions"


@pytest.mark.asyncio
async def test_second_export_adds_its_participants_to_the_one_session(db):
    org = _org(db, f"roster-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-2", export_id="e1", started=BASE,
        ended=BASE + timedelta(minutes=20),
        lines=[("p-alice", "Alice", BASE + timedelta(minutes=1))],
    ))
    await _ingest(db, principal, _ingest_body(
        room_id="room-2", export_id="e2", started=BASE + timedelta(minutes=2),
        ended=BASE + timedelta(minutes=21),
        lines=[
            ("p-alice", "Alice", BASE + timedelta(minutes=1)),
            ("p-bob", "Bob", BASE + timedelta(minutes=3)),
        ],
    ))

    row = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).one()
    ids = {p["id"] for p in row.participants}
    assert {"p-alice", "p-bob"} <= ids
    exports = row.processing_metadata["federation"]["exports"]
    assert [e["export_id"] for e in exports] == ["e2"], (
        "the extra export must be recorded as provenance"
    )


@pytest.mark.asyncio
async def test_exporter_is_linked_to_their_meeting_ops_account(db):
    """The exporter's Stable username resolves to an in-org account, which is
    what turns 'was in the meeting' into 'can read the meeting'."""
    org = _org(db, f"exporter-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    bob = _user(db, "bob@example.com", username="bob")
    _member(db, bob, org, "member")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-3", export_id="e1", started=BASE,
        ended=BASE + timedelta(minutes=10),
        lines=[("p-alice", "Alice", BASE + timedelta(minutes=1))],
        exporter={"participant_id": "p-bob", "username": "bob",
                  "display_name": "Bob B"},
    ))

    row = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).one()
    entry = next(p for p in row.participants if p["id"] == "p-bob")
    assert entry["user_id"] == bob.id
    assert entry["email"] == "bob@example.com"
    assert user_is_participant(row, bob) is True


@pytest.mark.asyncio
async def test_exporter_outside_the_org_is_recorded_but_not_linked(db):
    """A username that resolves to an account in another tenant must never
    become an identity on this tenant's meeting."""
    org = _org(db, f"crossorg-{uuid.uuid4().hex[:8]}")
    other = _org(db, f"other-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    outsider = _user(db, "outsider@example.com", username="outsider")
    _member(db, outsider, other, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-4", export_id="e1", started=BASE,
        ended=BASE + timedelta(minutes=10),
        lines=[("p-alice", "Alice", BASE + timedelta(minutes=1))],
        exporter={"participant_id": "p-out", "username": "outsider"},
    ))

    row = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).one()
    entry = next(p for p in row.participants if p["id"] == "p-out")
    assert "user_id" not in entry
    assert "email" not in entry
    assert user_is_participant(row, outsider) is False


@pytest.mark.asyncio
async def test_a_later_call_in_the_same_room_is_a_different_meeting(db):
    org = _org(db, f"twocalls-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-5", export_id="morning", started=BASE,
        ended=BASE + timedelta(minutes=30),
        lines=[("p-a", "A", BASE + timedelta(minutes=1))],
    ))
    later = BASE + timedelta(hours=4)
    second = await _ingest(db, principal, _ingest_body(
        room_id="room-5", export_id="afternoon", started=later,
        ended=later + timedelta(minutes=30),
        lines=[("p-a", "A", later + timedelta(minutes=1))],
    ))

    assert second.created is True
    assert db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).count() == 2


@pytest.mark.asyncio
async def test_explicit_meeting_ops_session_id_coalesces_across_any_gap(db):
    """When upstream states the meeting identity, it wins over the window."""
    org = _org(db, f"explicit-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-6", export_id="x1", started=BASE,
        ended=BASE + timedelta(minutes=5),
        lines=[("p-a", "A", BASE)], meeting_ops_session_id="call-77",
    ))
    far_later = BASE + timedelta(days=1)
    second = await _ingest(db, principal, _ingest_body(
        room_id="room-6", export_id="x2", started=far_later,
        ended=far_later + timedelta(minutes=5),
        lines=[("p-b", "B", far_later)], meeting_ops_session_id="call-77",
    ))

    assert second.created is False
    assert db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).count() == 1


@pytest.mark.asyncio
async def test_identical_export_replayed_is_idempotent(db):
    org = _org(db, f"replay-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    body = _ingest_body(
        room_id="room-7", export_id="same", started=BASE,
        ended=BASE + timedelta(minutes=5),
        lines=[("p-a", "A", BASE)],
    )
    first = await _ingest(db, principal, body)
    second = await _ingest(db, principal, body)

    assert first.created is True and second.created is False
    assert first.session_id == second.session_id
    assert db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).count() == 1


@pytest.mark.asyncio
async def test_reusing_an_export_id_for_different_content_still_conflicts(db):
    """Pre-existing contract: an export_id is a promise about content."""
    org = _org(db, f"conflict-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-8", export_id="dup", started=BASE,
        ended=BASE + timedelta(minutes=5), lines=[("p-a", "A", BASE)],
    ))
    with pytest.raises(HTTPException) as exc:
        await _ingest(db, principal, _ingest_body(
            room_id="room-8", export_id="dup", started=BASE,
            ended=BASE + timedelta(minutes=5),
            lines=[("p-a", "A", BASE), ("p-b", "B", BASE)],
        ))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_richer_transcript_upgrades_an_unsummarised_meeting(db):
    org = _org(db, f"upgrade-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-9", export_id="short", started=BASE,
        ended=BASE + timedelta(minutes=10), lines=[("p-a", "A", BASE)],
    ))
    await _ingest(db, principal, _ingest_body(
        room_id="room-9", export_id="long", started=BASE,
        ended=BASE + timedelta(minutes=11),
        lines=[
            ("p-a", "A", BASE),
            ("p-b", "B", BASE + timedelta(minutes=1)),
            ("p-c", "C", BASE + timedelta(minutes=2)),
        ],
    ))

    row = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).one()
    assert len(row.transcript_diarized["segments"]) == 3


@pytest.mark.asyncio
async def test_an_existing_summary_is_never_silently_re_based(db):
    org = _org(db, f"nosummaryclobber-{uuid.uuid4().hex[:8]}")
    svc = _user(db, f"svc-{uuid.uuid4().hex[:6]}@example.com")
    _member(db, svc, org, "admin")
    principal = _Principal(svc, org)

    await _ingest(db, principal, _ingest_body(
        room_id="room-10", export_id="short", started=BASE,
        ended=BASE + timedelta(minutes=10), lines=[("p-a", "A", BASE)],
    ))
    row = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org.id
    ).one()
    row.summary = "Already summarised."
    db.add(row)
    db.commit()

    await _ingest(db, principal, _ingest_body(
        room_id="room-10", export_id="long", started=BASE,
        ended=BASE + timedelta(minutes=11),
        lines=[("p-a", "A", BASE), ("p-b", "B", BASE + timedelta(minutes=1))],
    ))

    db.refresh(row)
    assert row.summary == "Already summarised."
    assert len(row.transcript_diarized["segments"]) == 1
    # The participant still gains access even though the text is frozen.
    assert {p["id"] for p in row.participants} >= {"p-a", "p-b"}


# ---------------------------------------------------------------------
# Who may read it
# ---------------------------------------------------------------------


def test_default_visibility_is_unchanged_org_wide_access(db):
    org = _org(db, f"default-{uuid.uuid4().hex[:8]}")
    owner = _user(db, "owner@example.com")
    bystander = _user(db, "bystander@example.com")
    _member(db, owner, org, "member")
    _member(db, bystander, org, "member")
    row = _session(db, org, owner=owner)

    assert has_session_access(row.id, bystander, db) == "edit"
    assert visible_session_clause(db, org.id, bystander, "member") is None


def test_participant_reads_the_meeting_they_were_in(db):
    org = _org(db, f"grant-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner2@example.com")
    attendee = _user(db, "attendee@example.com")
    _member(db, owner, org, "member")
    _member(db, attendee, org, "member")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "name": "Attendee",
                       "email": "Attendee@Example.com"}],
    )

    assert has_session_access(row.id, attendee, db) == "view"
    assert resolve_session_for_user(db, org.id, row.session_id, attendee) is not None


def test_non_participant_org_member_is_refused_when_tightened(db):
    """The negative case that makes the setting mean anything."""
    org = _org(db, f"deny-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner3@example.com")
    bystander = _user(db, "bystander3@example.com")
    _member(db, owner, org, "member")
    _member(db, bystander, org, "member")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "email": "someone-else@example.com"}],
    )

    assert has_session_access(row.id, bystander, db) == "denied"
    assert resolve_session_for_user(db, org.id, row.session_id, bystander) is None


def test_unverified_email_does_not_become_an_identity(db):
    """Anyone who can edit a session can type any address into the roster, so
    an address only counts once the account has proven it owns it."""
    org = _org(db, f"unverified-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner4@example.com")
    impostor = _user(db, "claimed@example.com", verified=False)
    _member(db, owner, org, "member")
    _member(db, impostor, org, "member")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "email": "claimed@example.com"}],
    )

    assert user_is_participant(row, impostor) is False
    assert has_session_access(row.id, impostor, db) == "denied"


def test_a_roster_entry_cannot_reach_across_tenants(db):
    """A participant email widens access inside a tenant, never across one."""
    org = _org(db, f"tenant-a-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    other = _org(db, f"tenant-b-{uuid.uuid4().hex[:8]}")
    owner = _user(db, "owner5@example.com")
    stranger = _user(db, "stranger@example.com")
    _member(db, owner, org, "member")
    _member(db, stranger, other, "admin")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "email": "stranger@example.com"}],
    )

    # The roster names them and their email is verified, but they are not in
    # this organization, so the answer is still no.
    assert user_is_participant(row, stranger) is True
    assert has_session_access(row.id, stranger, db) == "denied"


def test_creator_and_org_admin_keep_access_when_tightened(db):
    org = _org(db, f"admins-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    creator = _user(db, "creator@example.com")
    admin = _user(db, "admin@example.com")
    _member(db, creator, org, "member")
    _member(db, admin, org, "admin")
    row = _session(db, org, owner=creator)

    assert has_session_access(row.id, creator, db) == "edit"
    assert has_session_access(row.id, admin, db) == "edit"
    assert visible_session_clause(db, org.id, admin, "admin") is None


def test_stamped_user_id_grants_access_without_any_email(db):
    org = _org(db, f"stamped-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner6@example.com")
    attendee = _user(db, "stamped@example.com")
    _member(db, owner, org, "member")
    _member(db, attendee, org, "member")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "user_id": attendee.id}],
    )

    assert has_session_access(row.id, attendee, db) == "view"


def test_inactive_account_is_refused_even_when_named(db):
    org = _org(db, f"inactive-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner7@example.com")
    disabled = _user(db, "disabled@example.com", active=False)
    _member(db, owner, org, "member")
    _member(db, disabled, org, "member")
    row = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "email": "disabled@example.com"}],
    )

    assert user_is_participant(row, disabled) is False


def test_list_query_hides_meetings_you_were_not_in(db):
    """The detail check is worthless if the list leaks the same rows."""
    org = _org(db, f"list-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    owner = _user(db, "owner8@example.com")
    attendee = _user(db, "attendee8@example.com")
    _member(db, owner, org, "member")
    _member(db, attendee, org, "member")

    mine = _session(
        db, org, owner=owner,
        participants=[{"id": "p1", "email": "attendee8@example.com"}],
    )
    _session(db, org, owner=owner, participants=[{"id": "p2",
                                                  "email": "nope@example.com"}])
    owned = _session(db, org, owner=attendee)

    clause = visible_session_clause(db, org.id, attendee, "member")
    assert clause is not None
    visible = (
        db.query(RecordingSession)
        .filter(RecordingSession.organization_id == org.id)
        .filter(clause)
        .all()
    )
    assert {r.id for r in visible} == {mine.id, owned.id}


def test_the_list_and_the_detail_view_agree_about_email_casing(db):
    """Rosters store whatever address someone typed. If the detail check folds
    case but the list does not, a participant opens their meeting fine and
    then cannot find it again — the meeting silently vanishes from the list.
    """
    org = _org(db, f"casing-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    attendee = _user(db, "mixed@example.com")
    _member(db, attendee, org, "member")
    row = _session(
        db, org,
        participants=[{"id": "p1", "email": "MiXeD@Example.COM"}],
    )

    assert user_is_participant(row, attendee) is True
    assert has_session_access(row.id, attendee, db) == "view"

    clause = visible_session_clause(db, org.id, attendee, "member")
    visible = (
        db.query(RecordingSession)
        .filter(RecordingSession.organization_id == org.id)
        .filter(clause)
        .all()
    )
    assert [r.id for r in visible] == [row.id], (
        "the list must show the same meeting the detail view opens"
    )


def test_a_user_with_no_identity_sees_nothing_rather_than_everything(db):
    org = _org(db, f"noident-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    ghost = User(email="", username=f"ghost{uuid.uuid4().hex[:6]}",
                 hashed_password="x", is_active=True, is_verified=False)
    db.add(ghost)
    db.commit()
    db.refresh(ghost)
    _member(db, ghost, org, "member")
    _session(db, org, participants=[{"id": "p1", "email": "someone@example.com"}])

    clause = visible_session_clause(db, org.id, ghost, "member")
    visible = (
        db.query(RecordingSession)
        .filter(RecordingSession.organization_id == org.id)
        .filter(clause)
        .all()
    )
    assert visible == []


def test_unrecognised_setting_falls_back_to_the_open_default(db):
    """An unreadable setting must never be why someone loses their data."""
    org = _org(db, f"garbage-{uuid.uuid4().hex[:8]}")
    org.settings = {SESSION_VISIBILITY_KEY: "somethingelse"}
    db.add(org)
    db.commit()
    member = _user(db, "member9@example.com")
    _member(db, member, org, "member")
    row = _session(db, org)

    assert has_session_access(row.id, member, db) == "edit"


def test_switching_the_setting_back_restores_access(db):
    org = _org(db, f"toggle-{uuid.uuid4().hex[:8]}", VISIBILITY_PARTICIPANTS)
    bystander = _user(db, "bystander10@example.com")
    _member(db, bystander, org, "member")
    row = _session(db, org)

    assert has_session_access(row.id, bystander, db) == "denied"
    _set_visibility(db, org, VISIBILITY_ORGANIZATION)
    assert has_session_access(row.id, bystander, db) == "edit"
