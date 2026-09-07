"""Combined meetings (docs/COMBINED-MEETINGS-CONTRACT.md).

A combined meeting is a summary-only session linked to its parts in time
order; the parts are never modified. Covers:

  - POST /api/sessions/combine: ordering by started_at, default name, the
    combined row's timeline fields, link rows, job enqueue + drift stamp,
    validation (>= 2 distinct, unknown id, no nesting, same org).
  - POST /api/sessions/{id}/combine/rerun.
  - list + detail serializers: is_combined / parts_count / part_of / parts.
  - combine_sessions_job: transcript assembly (markers in order, generic
    speaker labels suffixed per part, named speakers kept, timeline offset),
    summary + insights calls (LLM mocked), drift skip, failure recording.
  - delete semantics: either side survives the other.
  - build_attributed_transcript renders marker segments as bare lines.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, time as dt_time, timedelta

import pytest

ADMIN_ORG = "magic-unicorn"


def _admin_headers(client):
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _org_id(slug: str) -> int:
    from auth.models import Organization
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if org is None:
            org = Organization(name=slug, slug=slug, is_active=True)
            db.add(org)
            db.commit()
            db.refresh(org)
        return org.id
    finally:
        db.close()


def _seed(
    name: str,
    started: datetime,
    duration: float,
    segments: list[dict] | None = None,
    *,
    org_slug: str = ADMIN_ORG,
    status: str = "completed",
    is_combined: bool = False,
) -> int:
    """Seed a session in `org_slug`; return its integer pk."""
    from auth.models import User
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        diarized = None
        if segments is not None:
            speakers = []
            for seg in segments:
                if seg.get("speaker") and seg["speaker"] not in speakers:
                    speakers.append(seg["speaker"])
            diarized = {"segments": segments, "speakers": speakers}
        row = RecordingSession(
            session_id=str(uuid.uuid4()),
            name=name,
            title=name,
            status=status,
            organization_id=_org_id(org_slug),
            user_id=admin.id,
            created_at=started,
            started_at=started,
            ended_at=started + timedelta(seconds=duration),
            duration=duration,
            meeting_date=started.date(),
            meeting_time=started.time(),
            transcript_diarized=diarized,
            transcript_simple=" ".join(s["text"] for s in (segments or [])) or None,
            is_combined=is_combined,
            participants=[],
            tags=[],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _load(pk: int):
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        row = db.query(RecordingSession).filter(RecordingSession.id == pk).first()
        if row is not None:
            db.refresh(row)
            db.expunge(row)
        return row
    finally:
        db.close()


def _links(combined_pk: int):
    from database.database import SessionLocal
    from database.models import SessionGroupMember

    db = SessionLocal()
    try:
        return [
            (m.member_session_id, m.position)
            for m in db.query(SessionGroupMember)
            .filter(SessionGroupMember.combined_session_id == combined_pk)
            .order_by(SessionGroupMember.position)
            .all()
        ]
    finally:
        db.close()


T0 = datetime(2026, 8, 13, 21, 5, 49)
T1 = datetime(2026, 8, 13, 21, 30, 42)

PART_A_SEGS = [
    {"speaker": "Aaron Stransky", "text": "Hey Tom, long time.", "start": 0.0, "end": 2.0},
    {"speaker": "SPEAKER_00", "text": "I was in Korea, forgot to call back.", "start": 2.0, "end": 6.0},
    {"speaker": "Aaron Stransky", "text": "Let me call you right back in two minutes.", "start": 6.0, "end": 9.0},
]
PART_B_SEGS = [
    {"speaker": "SPEAKER_00", "text": "So the music thing, we expanded out.", "start": 0.0, "end": 3.0},
    {"speaker": "Aaron Stransky", "text": "Might be down in Dallas soon.", "start": 3.0, "end": 5.0},
]


@pytest.fixture
def fake_enqueue(monkeypatch):
    """Capture arq enqueues instead of touching Redis."""
    calls: list[tuple] = []

    async def _enqueue(function_name, *args, **kwargs):
        calls.append((function_name, args, kwargs))
        return f"job-{len(calls)}"

    import services.job_runner as job_runner

    monkeypatch.setattr(job_runner, "enqueue_job", _enqueue)
    return calls


@pytest.fixture
def fake_llm(monkeypatch):
    """Stand in for the finalize summary + insights calls (no LLM)."""
    seen: dict = {"summaries": [], "insights": []}

    async def _summarize(db, session, *, template="standard", force=False, **_):
        seen["summaries"].append({"session": session.id, "force": force, "template": template})
        session.summary = '{"executive": "Two-part call about music and Dallas.", "bullets": [], "actions": [], "decisions": []}'
        session.final_summary = {"executive": "Two-part call about music and Dallas."}
        db.commit()

    class _Insights:
        def model_dump(self):
            return {"summary": "insights", "keyTopics": ["music"]}

    async def _insights(transcript, transcriptions, session, db, org_id):
        seen["insights"].append({
            "session": session.id,
            "rows": len(transcriptions),
            "speakers": sorted({t.speaker for t in transcriptions if t.speaker}),
            "transcript_has_marker": "=== Part 1 of" in transcript,
        })
        return _Insights()

    import api.ai_insights as ai_insights
    import api.uploads as uploads

    monkeypatch.setattr(uploads, "_summarize_session", _summarize)
    monkeypatch.setattr(ai_insights, "_generate_ai_insights", _insights)
    return seen


# ---------------------------------------------------------------------------
# Endpoint: combine
# ---------------------------------------------------------------------------


def test_combine_orders_parts_by_start_and_enqueues(client, fake_enqueue):
    headers = _admin_headers(client)
    later = _seed("Call with Tom Kim2", T1, 1193.5, PART_B_SEGS)
    earlier = _seed("Call with Tom Kim1", T0, 1228.1, PART_A_SEGS)
    later_wire = _load(later).session_id

    # Later part listed first, by UUID; earlier part by numeric pk string.
    res = client.post(
        "/api/sessions/combine",
        json={"session_ids": [later_wire, str(earlier)]},
        headers=headers,
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["is_combined"] is True
    assert body["status"] == "processing"
    assert body["name"] == "Call with Tom Kim1 (combined, 2 parts)"
    assert body["job_id"] == "job-1"
    assert [p["pk"] for p in body["parts"]] == [earlier, later]
    assert body["parts"][0]["id"] == _load(earlier).session_id  # wire id, not pk
    assert body["parts"][0]["started_at"] == T0.isoformat()
    assert body["parts"][0]["meeting_date"] == T0.date().isoformat()
    assert body["parts"][1]["duration"] == 1193.5

    combined = _load(body["pk"])
    assert combined.is_combined is True
    assert combined.processing_job_id == "job-1"
    assert combined.started_at == T0
    assert combined.created_at == T0
    assert combined.ended_at == T1 + timedelta(seconds=1193.5)
    assert combined.duration == pytest.approx(1228.1 + 1193.5)
    assert combined.meeting_date == T0.date()
    assert combined.organization_id == _org_id(ADMIN_ORG)
    assert _links(combined.id) == [(earlier, 0), (later, 1)]

    fn, args, kwargs = fake_enqueue[0]
    assert fn == "combine_sessions_job"
    assert args == (combined.id,)
    assert kwargs["force"] is False
    assert kwargs["owner_org_id"] == combined.organization_id

    # Parts are untouched.
    assert _load(earlier).status == "completed"
    assert _load(earlier).is_combined is False


def test_combine_custom_name_is_final(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("A", T0, 10.0, PART_A_SEGS)
    b = _seed("B", T1, 10.0, PART_B_SEGS)
    res = client.post(
        "/api/sessions/combine",
        json={"session_ids": [a, b], "name": "  Tom Reyes, both halves  "},
        headers=headers,
    )
    assert res.status_code == 202, res.text
    combined = _load(res.json()["pk"])
    assert combined.name == "Tom Reyes, both halves"
    assert combined.title_user_set is True


def test_combine_validation(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("A", T0, 10.0, PART_A_SEGS)
    b = _seed("B", T1, 10.0, PART_B_SEGS)

    # fewer than two distinct ids
    assert client.post("/api/sessions/combine", json={"session_ids": [a]}, headers=headers).status_code == 400
    assert client.post("/api/sessions/combine", json={"session_ids": [a, a]}, headers=headers).status_code == 400
    assert client.post("/api/sessions/combine", json={"session_ids": []}, headers=headers).status_code == 400
    # the same session by UUID and by pk is still one session
    res = client.post(
        "/api/sessions/combine",
        json={"session_ids": [a, _load(a).session_id]},
        headers=headers,
    )
    assert res.status_code == 400
    # unknown id -> 404, nothing created
    assert client.post("/api/sessions/combine", json={"session_ids": [a, 999999]}, headers=headers).status_code == 404
    assert fake_enqueue == []

    # no nesting: a combined session cannot be a part
    res = client.post("/api/sessions/combine", json={"session_ids": [a, b]}, headers=headers)
    assert res.status_code == 202
    combined_pk = res.json()["pk"]
    res = client.post("/api/sessions/combine", json={"session_ids": [combined_pk, a]}, headers=headers)
    assert res.status_code == 400
    assert "combined" in res.json()["detail"].lower()


def test_combine_rejects_parts_from_different_orgs(client, fake_enqueue):
    headers = _admin_headers(client)
    mine = _seed("Mine", T0, 10.0, PART_A_SEGS)
    # The conftest admin is a superuser, so a foreign-org session RESOLVES
    # (cross-org fallback) — the same-org rule must still refuse it.
    theirs = _seed("Theirs", T1, 10.0, PART_B_SEGS, org_slug="other-org-combined")
    res = client.post(
        "/api/sessions/combine",
        json={"session_ids": [mine, _load(theirs).session_id]},
        headers=headers,
    )
    assert res.status_code == 400
    assert "organization" in res.json()["detail"].lower()
    assert fake_enqueue == []


def test_combine_falls_back_inline_when_arq_is_unavailable(client, monkeypatch, fake_llm):
    headers = _admin_headers(client)
    a = _seed("A", T0, 9.0, PART_A_SEGS)
    b = _seed("B", T1, 5.0, PART_B_SEGS)

    async def _boom(*_a, **_k):
        raise RuntimeError("redis down")

    import services.job_runner as job_runner

    monkeypatch.setattr(job_runner, "enqueue_job", _boom)
    res = client.post("/api/sessions/combine", json={"session_ids": [a, b]}, headers=headers)
    assert res.status_code == 202, res.text
    assert res.json()["job_id"].startswith("inline-")
    # TestClient runs background tasks before returning: the inline job ran.
    combined = _load(res.json()["pk"])
    assert combined.status == "completed"
    assert combined.processing_job_id == res.json()["job_id"]
    assert fake_llm["summaries"] and fake_llm["summaries"][0]["session"] == combined.id


# ---------------------------------------------------------------------------
# Endpoint: rerun
# ---------------------------------------------------------------------------


def test_rerun_reenqueues_with_force(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("A", T0, 10.0, PART_A_SEGS)
    b = _seed("B", T1, 10.0, PART_B_SEGS)
    res = client.post("/api/sessions/combine", json={"session_ids": [a, b]}, headers=headers)
    wire = res.json()["id"]

    res = client.post(f"/api/sessions/{wire}/combine/rerun", headers=headers)
    assert res.status_code == 202, res.text
    assert res.json()["job_id"] == "job-2"
    assert fake_enqueue[-1][2]["force"] is True
    assert _load(res.json()["pk"]).processing_job_id == "job-2"

    # not a combined meeting
    res = client.post(f"/api/sessions/{a}/combine/rerun", headers=headers)
    assert res.status_code == 400
    # unknown
    res = client.post("/api/sessions/999999/combine/rerun", headers=headers)
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _list_items(client, headers, wanted: set[str]) -> dict:
    """Walk the paginated list until every wanted wire id is seen (the shared
    test DB accumulates sessions from other test files)."""
    found: dict = {}
    cursor = None
    for _ in range(50):
        url = "/api/simple/recording-sessions?limit=200"
        if cursor:
            url += f"&cursor={cursor}"
        res = client.get(url, headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        for item in body["items"]:
            if item["id"] in wanted:
                found[item["id"]] = item
        if wanted <= set(found) or not body.get("has_more"):
            break
        cursor = body["next_cursor"]
    assert wanted <= set(found), f"missing from list: {wanted - set(found)}"
    return found


def test_detail_and_list_expose_combined_fields(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("Detail A", T0, 10.0, PART_A_SEGS)
    b = _seed("Detail B", T1, 10.0, PART_B_SEGS)
    res = client.post("/api/sessions/combine", json={"session_ids": [b, a]}, headers=headers)
    combined_wire = res.json()["id"]
    combined_pk = res.json()["pk"]

    detail = client.get(f"/api/simple/recording-sessions/{combined_wire}", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["is_combined"] is True
    assert payload["part_of"] == []
    assert [p["pk"] for p in payload["parts"]] == [a, b]
    part = payload["parts"][0]
    assert part["id"] == _load(a).session_id
    assert part["name"] == "Detail A"
    assert part["started_at"] == T0.isoformat()
    assert part["duration"] == 10.0
    assert part["status"] == "completed"
    assert part["meeting_date"] == T0.date().isoformat()
    assert part["meeting_time"] == T0.time().isoformat()

    part_detail = client.get(f"/api/simple/recording-sessions/{a}", headers=headers).json()
    assert part_detail["is_combined"] is False
    assert "parts" not in part_detail
    assert part_detail["part_of"] == [
        {"id": combined_wire, "pk": combined_pk, "name": res.json()["name"]}
    ]

    by_id = _list_items(client, headers, {combined_wire, _load(a).session_id})
    assert by_id[combined_wire]["is_combined"] is True
    assert by_id[combined_wire]["parts_count"] == 2
    assert by_id[combined_wire]["part_of"] == []
    member = by_id[_load(a).session_id]
    assert member["is_combined"] is False
    assert member["parts_count"] == 0
    assert member["part_of"][0]["id"] == combined_wire


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _combine_via_api(client, headers, ids):
    res = client.post("/api/sessions/combine", json={"session_ids": ids}, headers=headers)
    assert res.status_code == 202, res.text
    return res.json()


def test_job_assembles_transcript_and_summarizes(client, fake_enqueue, fake_llm):
    from workers.combine_workers import combine_sessions_job

    headers = _admin_headers(client)
    a = _seed("Call with Tom Kim1", T0, 9.0, PART_A_SEGS)
    b = _seed("Call with Tom Kim2", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [b, a])
    combined_pk = body["pk"]

    result = asyncio.run(combine_sessions_job({"job_id": "job-1"}, combined_pk))
    assert result["status"] == "completed", result
    assert result["parts"] == [a, b]

    combined = _load(combined_pk)
    assert combined.status == "completed"
    text = combined.transcript_simple
    assert text is not None
    marker_1 = "=== Part 1 of 2: Call with Tom Kim1 — 2026-08-13 21:05 UTC (00:09) ==="
    marker_2 = "=== Part 2 of 2: Call with Tom Kim2 — 2026-08-13 21:30 UTC (00:05) ==="
    assert text.index(marker_1) < text.index(marker_2)
    lines = text.splitlines()
    assert lines[0] == marker_1  # bare line, no speaker prefix
    # named speakers kept; raw diarizer codes normalized AND tagged per part
    assert "Aaron Stransky: Hey Tom, long time." in text
    assert "Speaker 1 (part 1): I was in Korea, forgot to call back." in text
    assert "Speaker 1 (part 2): So the music thing, we expanded out." in text
    assert "SPEAKER_00" not in text

    doc = combined.transcript_diarized
    assert doc["source"] == "combined"
    assert doc["speakers"] == ["Aaron Stransky", "Speaker 1 (part 1)", "Speaker 1 (part 2)"]
    markers = [s for s in doc["segments"] if s.get("kind") == "marker"]
    assert [m["part"] for m in markers] == [1, 2]
    # part 2 sits after part 1 on one continuous timeline (offset = 9.0s)
    first_b = next(s for s in doc["segments"] if s.get("part") == 2 and s.get("kind") != "marker")
    assert first_b["start"] == pytest.approx(9.0)
    assert first_b["end"] == pytest.approx(12.0)
    assert combined.speaker_count == 3

    assert fake_llm["summaries"] == [{"session": combined_pk, "force": False, "template": "standard"}]
    ins = fake_llm["insights"][0]
    assert ins["session"] == combined_pk
    assert ins["rows"] == 5  # 3 + 2 speaker turns, markers excluded
    assert ins["transcript_has_marker"] is True
    assert combined.ai_insights == {"summary": "insights", "keyTopics": ["music"]}
    assert combined.processing_metadata["completion"]["mode"] == "combined"
    assert combined.processing_metadata["combined"]["parts"] == [a, b]
    assert "summary_error" not in combined.processing_metadata

    # Parts are untouched: no transcriptions rows written, own docs intact.
    from database.database import SessionLocal
    from database.models import Transcription

    db = SessionLocal()
    try:
        assert db.query(Transcription).filter(Transcription.session_id == combined_pk).count() == 0
    finally:
        db.close()
    assert _load(a).transcript_diarized["segments"][1]["speaker"] == "SPEAKER_00"


def test_job_uses_transcription_rows_when_part_has_no_diarized_doc(client, fake_enqueue, fake_llm):
    from database.database import SessionLocal
    from database.models import Transcription
    from workers.combine_workers import combine_sessions_job

    headers = _admin_headers(client)
    a = _seed("Rows only", T0, 4.0, None)
    b = _seed("Flat only", T1, 3.0, None)
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        db.add(Transcription(session_id=a, text="second line", speaker="Shafen Khan", start_time=2.0, end_time=4.0))
        db.add(Transcription(session_id=a, text="first line", speaker="Shafen Khan", start_time=0.0, end_time=2.0))
        flat = db.query(RecordingSession).filter(RecordingSession.id == b).first()
        flat.transcript_simple = "just a flat transcript"
        db.commit()
    finally:
        db.close()
    body = _combine_via_api(client, headers, [a, b])
    result = asyncio.run(combine_sessions_job({"job_id": "job-1"}, body["pk"]))
    assert result["status"] == "completed", result
    text = _load(body["pk"]).transcript_simple
    assert "Shafen Khan: first line second line" in text
    assert text.index("first line") < text.index("second line")
    assert "just a flat transcript" in text


def test_job_rerun_passes_force(client, fake_enqueue, fake_llm):
    from workers.combine_workers import combine_sessions_job

    headers = _admin_headers(client)
    a = _seed("A", T0, 9.0, PART_A_SEGS)
    b = _seed("B", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [a, b])
    result = asyncio.run(combine_sessions_job({"job_id": "job-1"}, body["pk"], force=True))
    assert result["status"] == "completed"
    assert fake_llm["summaries"][-1]["force"] is True


def test_job_drift_skips_without_touching_the_row(client, fake_enqueue, fake_llm):
    from workers.combine_workers import combine_sessions_job

    headers = _admin_headers(client)
    a = _seed("A", T0, 9.0, PART_A_SEGS)
    b = _seed("B", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [a, b])  # stamped job-1
    result = asyncio.run(combine_sessions_job({"job_id": "stale-job"}, body["pk"]))
    assert result["status"] == "skipped" and result["reason"] == "drift"
    combined = _load(body["pk"])
    assert combined.status == "processing"
    assert combined.transcript_simple is None
    assert fake_llm["summaries"] == []


def test_job_skips_non_combined_and_missing_sessions(client, fake_llm):
    from workers.combine_workers import combine_sessions_job

    plain = _seed("Plain", T0, 9.0, PART_A_SEGS)
    assert asyncio.run(combine_sessions_job({"job_id": "j"}, plain))["reason"] == "not_combined"
    assert asyncio.run(combine_sessions_job({"job_id": "j"}, 987654321))["reason"] == "session_missing"
    assert fake_llm["summaries"] == []


def test_job_records_summary_failure(client, fake_enqueue, monkeypatch):
    from workers.combine_workers import combine_sessions_job

    headers = _admin_headers(client)
    a = _seed("A", T0, 9.0, PART_A_SEGS)
    b = _seed("B", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [a, b])

    async def _fail(db, session, **_):
        raise RuntimeError("summarizer exploded")

    import api.uploads as uploads

    monkeypatch.setattr(uploads, "_summarize_session", _fail)
    result = asyncio.run(combine_sessions_job({"job_id": "job-1"}, body["pk"]))
    assert result["status"] == "failed"
    combined = _load(body["pk"])
    assert combined.status == "failed"
    assert "summarizer exploded" in combined.processing_metadata["summary_error"]
    assert combined.processing_metadata["completion"]["summary_error"].startswith("summary:")
    # never handed to the finalize re-drive
    assert not combined.processing_metadata.get("needs_summary")


# ---------------------------------------------------------------------------
# Delete semantics
# ---------------------------------------------------------------------------


def test_delete_combined_keeps_parts(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("Keep A", T0, 9.0, PART_A_SEGS)
    b = _seed("Keep B", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [a, b])
    res = client.delete(f"/api/simple/recording-sessions/{body['id']}", headers=headers)
    assert res.status_code == 200, res.text
    assert _load(body["pk"]) is None
    assert _load(a) is not None and _load(b) is not None
    assert _links(body["pk"]) == []
    assert client.get(f"/api/simple/recording-sessions/{a}", headers=headers).json()["part_of"] == []


def test_delete_part_keeps_combined_with_fewer_parts(client, fake_enqueue):
    headers = _admin_headers(client)
    a = _seed("Gone A", T0, 9.0, PART_A_SEGS)
    b = _seed("Stay B", T1, 5.0, PART_B_SEGS)
    body = _combine_via_api(client, headers, [a, b])
    res = client.delete(f"/api/simple/recording-sessions/{a}", headers=headers)
    assert res.status_code == 200, res.text
    assert _load(a) is None
    assert _load(body["pk"]) is not None
    assert _links(body["pk"]) == [(b, 1)]
    detail = client.get(f"/api/simple/recording-sessions/{body['id']}", headers=headers).json()
    assert [p["pk"] for p in detail["parts"]] == [b]


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def test_build_attributed_transcript_renders_markers_as_bare_lines():
    from services.speaker_labels import build_attributed_transcript

    text, speakers = build_attributed_transcript([
        {"kind": "marker", "speaker": "", "text": "=== Part 1 of 2 ==="},
        {"speaker": "SPEAKER_00", "text": "hello"},
        {"speaker": "SPEAKER_00", "text": "again"},
        {"kind": "marker", "speaker": "", "text": "=== Part 2 of 2 ==="},
        {"speaker": "SPEAKER_00", "text": "back"},
    ])
    assert text.splitlines() == [
        "=== Part 1 of 2 ===",
        "Speaker 1: hello again",
        "=== Part 2 of 2 ===",
        "Speaker 1: back",
    ]
    assert speakers == ["Speaker 1"]


def test_order_parts_and_default_name():
    from types import SimpleNamespace

    from services.session_combine import default_name, order_parts

    x = SimpleNamespace(id=2, name="Second", title=None, started_at=T1, created_at=None)
    y = SimpleNamespace(id=1, name=None, title="First", started_at=T0, created_at=None)
    z = SimpleNamespace(id=3, name="No start", title=None, started_at=None, created_at=None)
    ordered = order_parts([x, z, y])
    assert [p.id for p in ordered] == [1, 2, 3]
    assert default_name(ordered) == "First (combined, 3 parts)"
