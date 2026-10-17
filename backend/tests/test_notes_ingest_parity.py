"""Focused parity tests for Notes-ingest title handling."""

from __future__ import annotations

from types import SimpleNamespace


def _session(*, original_title, current_title="Summary title", status="completed", title_user_set=False):
    return SimpleNamespace(
        id=1,
        title=current_title,
        status=status,
        title_user_set=title_user_set,
        updated_at=None,
        processing_metadata={"ingest": {"title": original_title}},
    )


def test_ingest_person_title_skips_when_original_title_is_not_a_call(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky")
    session = _session(original_title="Project planning")

    assert uploads._apply_ingest_person_title(session) is None
    assert session.title == "Summary title"


def test_ingest_person_title_skips_configured_self_name(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky, Meeting Minutes")
    session = _session(original_title="Call with meeting minutes")

    assert uploads._apply_ingest_person_title(session) is None
    assert session.title == "Summary title"


def test_ingest_person_title_skips_user_title(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky")
    session = _session(original_title="Call with Diesal", title_user_set=True)

    assert uploads._apply_ingest_person_title(session) is None
    assert session.title == "Summary title"


def test_ingest_person_title_skips_unfinished_session(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky")
    session = _session(original_title="Call with Diesal", status="processing")

    assert uploads._apply_ingest_person_title(session) is None
    assert session.title == "Summary title"


def test_ingest_person_title_skips_when_person_is_already_present(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky")
    session = _session(original_title="Call with Diesal", current_title="Diesal · Summary title")

    assert uploads._apply_ingest_person_title(session) is None
    assert session.title == "Diesal · Summary title"


def test_ingest_person_title_preserves_original_title_after_summary_retitle(monkeypatch):
    from api import uploads

    monkeypatch.setenv("NOTES_SYNC_SELF_NAMES", "Aaron Stransky")
    session = _session(original_title="  CALL WITH Diesal  ", current_title="Summary retitle")

    change = uploads._apply_ingest_person_title(session)

    assert change == {
        "id": "1",
        "before": "Summary retitle",
        "after": "Diesal · Summary retitle",
    }
    assert session.title == "Diesal · Summary retitle"
    assert session.processing_metadata["ingest"]["title"] == "  CALL WITH Diesal  "
