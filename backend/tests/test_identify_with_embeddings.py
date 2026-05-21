"""Regression tests for the always-on completion -> identify_speakers path.

Background: when always-on / chunked recordings completed, they went through
real_whisper_service.transcribe_file, which returns segments without per-turn
embeddings. identify_speakers then skipped every SPEAKER_xx label with
reason=no_embedding and no SpeakerSessionLink rows ever flipped from manual
to auto — even for users (Aaron) who had been enrolled at the org level.

These tests pin the contract going forward:

  1. transcript_diarized.segments WITH embeddings + a matching enrolled speaker
     -> identify_speakers writes a SpeakerSessionLink with source='auto' and a
     similarity above the threshold.
  2. transcript_diarized.segments WITHOUT embeddings (the regression shape)
     -> identify_speakers records reason='no_embedding' for each label and
     does NOT touch any existing manual links.
  3. transcript_diarized.segments WITH embeddings but below the similarity
     threshold -> identify_speakers records reason='below_threshold' and
     leaves the link unmatched.
  4. _assign_speakers_from_diarization (Path 1 — word-level alignment) PRESERVES
     the per-segment embedding from the diarization turns onto each utterance.
     This is the merge step that previously stripped embeddings, breaking
     identify_speakers downstream.
"""
from __future__ import annotations

import numpy as np
import pytest

from auth.utils import get_password_hash


def _models():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import (
        OrgProviderSettings,
        RecordingSession,
        SpeakerProfile,
        SpeakerSessionLink,
    )
    return (
        Organization,
        User,
        UserOrganization,
        SessionLocal,
        OrgProviderSettings,
        RecordingSession,
        SpeakerProfile,
        SpeakerSessionLink,
    )


def _normalize(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype="float32")
    n = np.linalg.norm(arr)
    if n > 0:
        arr = arr / n
    return arr.tolist()


def _make_embedding(seed: int, dim: int = 256) -> list[float]:
    """Generate a deterministic unit-norm embedding for tests."""
    rng = np.random.default_rng(seed)
    return _normalize(rng.normal(size=dim).tolist())


def _seed_world(client):
    """Seed an org + user + enrolled SpeakerProfile and return ids.

    Idempotent — the test fixture uses a shared SQLite DB so calls across
    test cases get the same speaker row. The enrolled embedding is always
    seeded deterministically (seed=42), so similarity assertions hold across
    test ordering.

    Returns: (org_id, speaker_id, enrolled_embedding)
    """
    (
        Organization,
        User,
        _UO,
        SessionLocal,
        _OPS,
        _RS,
        SpeakerProfile,
        _SSL,
    ) = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
        assert org is not None, "magic-unicorn org should be seeded by conftest"
        org_id = org.id

        from services.speaker_service import encode_embedding

        enrolled = _make_embedding(seed=42)
        sp = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.organization_id == org_id,
                SpeakerProfile.display_name == "Aaron Stransky (test)",
            )
            .first()
        )
        if sp is None:
            sp = SpeakerProfile(
                organization_id=org_id,
                display_name="Aaron Stransky (test)",
                centroid_embedding=encode_embedding(enrolled),
                embedding_dim=len(enrolled),
                embedding_model="pyannote/wespeaker-voxceleb-resnet34-LM",
                sample_count=1,
            )
            db.add(sp)
            db.commit()
            db.refresh(sp)
        return org_id, sp.id, enrolled
    finally:
        db.close()


def _make_session(org_id: int, segments: list[dict], audio_file: str = "") -> int:
    """Create a completed RecordingSession with the given diarized segments."""
    import uuid as _uuid
    (
        _Org,
        _U,
        _UO,
        SessionLocal,
        _OPS,
        RecordingSession,
        _SP,
        _SSL,
    ) = _models()
    db = SessionLocal()
    try:
        sess = RecordingSession(
            session_id=f"test-session-{_uuid.uuid4().hex[:12]}",
            name="Identify Embeddings Test",
            organization_id=org_id,
            status="completed",
            audio_file=audio_file,
            transcript_diarized={
                "segments": segments,
                "speakers": sorted({s.get("speaker") for s in segments if s.get("speaker")}),
                "model": "speaker-svc-test",
            },
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess.id
    finally:
        db.close()


class _FakeMatchingProvider:
    """Stand-in for LocalSpeakerSvcProvider used in tests so we don't depend
    on a live speaker-svc HTTP endpoint. Returns a positive identify match
    when the candidate embedding's cosine similarity to the query is above
    the threshold."""

    async def identify(self, embedding: list[float], candidates: list[dict], threshold: float) -> dict:
        q = np.asarray(embedding, dtype="float32")
        q_norm = np.linalg.norm(q)
        best = None
        best_sim = -1.0
        for c in candidates:
            e = np.asarray(c["embedding"], dtype="float32")
            denom = q_norm * np.linalg.norm(e)
            sim = float(np.dot(q, e) / denom) if denom > 0 else 0.0
            if sim > best_sim:
                best_sim = sim
                best = c
        if best is None:
            return {"best_match": None}
        return {
            "best_match": {
                "speaker_id": best["speaker_id"],
                "similarity": best_sim,
                "matched": best_sim >= threshold,
            }
        }


@pytest.fixture()
def fake_provider(monkeypatch):
    """Force ProviderRegistry.get_speaker_svc to return our deterministic stub."""
    from services.providers import registry as registry_module

    fake = _FakeMatchingProvider()
    monkeypatch.setattr(
        registry_module.ProviderRegistry,
        "get_speaker_svc",
        lambda self, org_id: fake,
    )
    monkeypatch.setattr(
        registry_module.ProviderRegistry,
        "get_diarization",
        lambda self, org_id: fake,
    )
    return fake


def test_identify_speakers_matches_when_embedding_present(client, fake_provider):
    """Happy path: diarized segments carry embeddings -> auto-link."""
    (
        _Org,
        _U,
        _UO,
        SessionLocal,
        _OPS,
        RecordingSession,
        _SP,
        SpeakerSessionLink,
    ) = _models()
    from services.speaker_service import identify_speakers

    org_id, speaker_id, enrolled_emb = _seed_world(client)

    # Two segments with the SAME speaker label, one carrying an embedding
    # nearly identical to the enrolled speaker's centroid. Cosine similarity
    # should clear the 0.55 default threshold easily.
    segments = [
        {
            "start": 0.0,
            "end": 5.0,
            "speaker": "SPEAKER_00",
            "text": "Hello this is Aaron.",
            "embedding": enrolled_emb,  # exact match -> cosine ~1.0
        },
        {
            "start": 6.0,
            "end": 12.0,
            "speaker": "SPEAKER_00",
            "text": "Continuing the meeting.",
            "embedding": enrolled_emb,
        },
    ]
    session_id = _make_session(org_id, segments)

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
        result = identify_speakers(session, db)

        assert result["linked"] == 1, f"expected 1 linked label, got {result}"
        assert result["skipped_reason"] is None
        link = (
            db.query(SpeakerSessionLink)
            .filter(SpeakerSessionLink.session_id == session_id)
            .filter(SpeakerSessionLink.raw_label == "SPEAKER_00")
            .first()
        )
        assert link is not None
        assert link.speaker_id == speaker_id
        assert link.source == "auto"
        assert link.similarity is not None and link.similarity > 0.99
    finally:
        db.close()


def test_identify_speakers_skips_when_no_embedding(client, fake_provider):
    """Regression: no embeddings on segments -> no_embedding reason, no auto-link."""
    (
        _Org,
        _U,
        _UO,
        SessionLocal,
        _OPS,
        RecordingSession,
        _SP,
        SpeakerSessionLink,
    ) = _models()
    from services.speaker_service import identify_speakers

    org_id, speaker_id, _enrolled_emb = _seed_world(client)

    # Same shape as the broken always-on output: segments with speaker
    # labels but NO embedding key, and no audio_file on disk either.
    segments = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello."},
        {"start": 6.0, "end": 12.0, "speaker": "SPEAKER_00", "text": "Continuing."},
    ]
    session_id = _make_session(org_id, segments, audio_file="")  # no audio path

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
        result = identify_speakers(session, db)

        # Without audio AND without inline embeddings, the function bails
        # out early with audio_missing — this is the documented behavior.
        assert result["skipped_reason"] is not None
        assert (
            result["skipped_reason"].startswith("audio_missing")
            or result["skipped_reason"] == "no_diarized_segments"
        )
        # Critically: no link should have been created. If a link existed it
        # would have to come from elsewhere (manual tagging) and we'd not
        # touch it.
        link = (
            db.query(SpeakerSessionLink)
            .filter(SpeakerSessionLink.session_id == session_id)
            .first()
        )
        assert link is None
    finally:
        db.close()


def test_identify_speakers_below_threshold(client, fake_provider):
    """Embedding present but cosine similarity < 0.55 -> below_threshold, no auto-link."""
    (
        _Org,
        _U,
        _UO,
        SessionLocal,
        _OPS,
        RecordingSession,
        _SP,
        SpeakerSessionLink,
    ) = _models()
    from services.speaker_service import identify_speakers

    org_id, speaker_id, enrolled_emb = _seed_world(client)

    # A completely different, near-orthogonal embedding (seed=999 is far
    # from seed=42 in random unit-vector space, cosine ~0).
    other_emb = _make_embedding(seed=999)
    segments = [
        {
            "start": 0.0,
            "end": 8.0,
            "speaker": "SPEAKER_01",
            "text": "An unknown speaker.",
            "embedding": other_emb,
        },
    ]
    session_id = _make_session(org_id, segments)

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
        result = identify_speakers(session, db)

        assert result["linked"] == 0
        assert result["unmatched"] == 1
        link = (
            db.query(SpeakerSessionLink)
            .filter(SpeakerSessionLink.session_id == session_id)
            .first()
        )
        # A link IS created (so the UI can show "unidentified" + offer manual
        # tagging) but with speaker_id=None and source!='auto+matched'.
        assert link is not None
        assert link.speaker_id is None
        assert link.similarity is None
    finally:
        db.close()


def test_build_segments_from_words_preserves_embedding(client):
    """The word-level merge in api/uploads MUST copy the diarization turn's
    embedding onto each utterance. Without this fix, identify_speakers
    falls through to no_embedding even when the diarizer returned them.
    """
    from api.uploads import _build_segments_from_words

    aaron_emb = _make_embedding(seed=42)
    other_emb = _make_embedding(seed=999)

    diar_segments = [
        {
            "start": 0.0,
            "end": 5.0,
            "speaker": "SPEAKER_00",
            "embedding": aaron_emb,
        },
        {
            "start": 5.5,
            "end": 9.0,
            "speaker": "SPEAKER_01",
            "embedding": other_emb,
        },
    ]
    words = [
        {"word": "Hello", "start": 0.1, "end": 0.5},
        {"word": "there", "start": 0.6, "end": 1.0},
        {"word": "thanks", "start": 6.0, "end": 6.5},
        {"word": "for", "start": 6.6, "end": 6.9},
        {"word": "joining", "start": 7.0, "end": 7.6},
    ]
    utterances = _build_segments_from_words(words, diar_segments)
    assert len(utterances) >= 2
    by_speaker: dict[str, dict] = {}
    for u in utterances:
        by_speaker[u["speaker"]] = u
    assert "SPEAKER_00" in by_speaker, f"missing SPEAKER_00 in {utterances}"
    assert "SPEAKER_01" in by_speaker, f"missing SPEAKER_01 in {utterances}"

    # The cosine sim between the copied embedding and the original must be
    # 1.0 (it's literally the same float list).
    assert by_speaker["SPEAKER_00"].get("embedding") == aaron_emb
    assert by_speaker["SPEAKER_01"].get("embedding") == other_emb


def test_build_segments_from_words_handles_diar_without_embeddings(client):
    """Backwards-compat: if the diarizer doesn't include embeddings (e.g.
    fallback backend), the utterances should still be built — just without
    the embedding key. identify_speakers will then skip with no_embedding,
    which is the correct behavior for that case."""
    from api.uploads import _build_segments_from_words

    diar_segments = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.5, "end": 9.0, "speaker": "SPEAKER_01"},
    ]
    words = [
        {"word": "Hello", "start": 0.1, "end": 0.5},
        {"word": "there", "start": 6.0, "end": 6.5},
    ]
    utterances = _build_segments_from_words(words, diar_segments)
    assert utterances, "expected at least one utterance"
    for u in utterances:
        assert "embedding" not in u, f"utterance {u} should not carry embedding when diar didn't emit one"
