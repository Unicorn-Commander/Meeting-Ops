"""Tests for the read-only graph-augmented meeting retriever."""

from __future__ import annotations

import asyncio
import sys
import types
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pytest


if "prometheus_client" not in sys.modules:
    prometheus_client = types.ModuleType("prometheus_client")

    def _make_asgi_app(*args, **kwargs):
        async def _app(scope, receive, send):
            return None

        return _app

    prometheus_client.make_asgi_app = _make_asgi_app
    sys.modules["prometheus_client"] = prometheus_client


def _models():
    from auth.models import Organization
    from database.database import SessionLocal, engine
    from database.models import RecordingSession

    return Organization, SessionLocal, RecordingSession, engine


def _seed_org_with_sessions():
    Organization, SessionLocal, RecordingSession, engine = _models()
    from database.models import Base
    from database.models_rooms import (  # noqa: F401
        ConferenceRoom,
        RoomAcl,
        RoomAudioSource,
        RoomPairingCode,
    )

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    seed_session_id = f"seed-session-{uuid.uuid4().hex}"
    linked_session_id = f"linked-session-{uuid.uuid4().hex}"

    org = Organization(
        name=f"Graph Augment Org {suffix}",
        slug=f"graph-augment-org-{suffix}",
        is_active=True,
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    now = datetime.now(timezone.utc)
    seed = RecordingSession(
        session_id=seed_session_id,
        name="Seed meeting",
        title="Seed meeting",
        status="completed",
        duration=60.0,
        created_at=now,
        started_at=now,
        ended_at=now,
        transcript_simple="Shafen mentioned loan timing and follow-ups.",
        summary="Seed discussion with Shafen.",
        final_summary={
            "executive": "Seed discussion with Shafen.",
            "bullets": ["Loan timing"],
            "decisions": [],
            "action_items": [],
        },
        participants=[],
        tags=[],
        organization_id=org.id,
    )
    linked = RecordingSession(
        session_id=linked_session_id,
        name="Linked meeting",
        title="Harborline loans restructure",
        status="completed",
        duration=75.0,
        created_at=now,
        started_at=now,
        ended_at=now,
        transcript_simple="We reviewed loan restructuring options with Shafen.",
        summary="Harborline loans restructure with Shafen.",
        final_summary={
            "executive": "Harborline loans restructure with Shafen.",
            "bullets": ["Loan restructuring"],
            "decisions": ["Proceed with loan analysis"],
            "action_items": [],
        },
        participants=[],
        tags=[],
        organization_id=org.id,
    )
    db.add_all([seed, linked])
    db.commit()
    db.refresh(seed)
    db.refresh(linked)

    return db, org, seed, linked


@pytest.fixture()
def graph_aug_ctx():
    db, org, seed, linked = _seed_org_with_sessions()
    yield {
        "db": db,
        "org": org,
        "seed": seed,
        "linked": linked,
        "seed_session_id": seed.session_id,
        "linked_session_id": linked.session_id,
    }
    db.close()


def _make_fake_semantic_search(seed_session_id: str):
    class _FakeSemanticSearch:
        def search(self, query: str, limit: int = 5, organization_id: Optional[int] = None):
            return [
                {
                    "session_id": seed_session_id,
                    "title": "Seed meeting",
                    "score": 0.4,
                    "snippet": "Shafen mentioned loan timing and follow-ups.",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "match_type": "semantic",
                }
            ]

        def search_chunks(self, query: str, limit: int = 8, organization_id: Optional[int] = None):
            return [
                {
                    "session_id": seed_session_id,
                    "title": "Seed meeting",
                    "content_type": "transcript",
                    "chunk_index": 0,
                    "text": "Shafen mentioned loan timing and follow-ups.",
                    "speakers": ["Shafen"],
                    "score": 0.91,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

    return _FakeSemanticSearch


def _make_fake_brigade_client(seed_id: int, linked_id: int):
    class _FakeBrigadeClient:
        is_live = True

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def fetch_entity_context(self, *, entity_name: str, **kwargs) -> Optional[dict[str, Any]]:
            seed_node = f"meeting_ops_meeting_{seed_id}"
            linked_node = f"meeting_ops_meeting_{linked_id}"
            speaker_node = "meeting_ops_speaker_7"

            if entity_name == seed_node:
                return {
                    "entity": {
                        "name": seed_node,
                        "type": "Meeting",
                        "properties": {
                            "id": seed_id,
                            "title": "Seed meeting",
                            "org_id": 1,
                        },
                    },
                    "relationships": [
                        {
                            "from": {"name": seed_node, "type": "Meeting"},
                            "to": {"name": speaker_node, "type": "Speaker"},
                            "relationship": "HAS_SPEAKER",
                        }
                    ],
                    "related_entities": [
                        {
                            "name": speaker_node,
                            "type": "Speaker",
                            "distance": 1,
                            "properties": {
                                "display_name": "Shafen",
                                "org_id": 1,
                            },
                        },
                        {
                            "name": f"meeting_ops_topic_{seed_id}_0",
                            "type": "Topic",
                            "distance": 1,
                            "properties": {
                                "text": "Loan timing and follow-ups",
                                "org_id": 1,
                            },
                        },
                    ],
                }

            if entity_name == speaker_node:
                return {
                    "entity": {
                        "name": speaker_node,
                        "type": "Speaker",
                        "properties": {
                            "display_name": "Shafen",
                            "org_id": 1,
                        },
                    },
                    "relationships": [
                        {
                            "from": {"name": speaker_node, "type": "Speaker"},
                            "to": {"name": linked_node, "type": "Meeting"},
                            "relationship": "HAS_SPEAKER",
                        }
                    ],
                    "related_entities": [
                        {
                            "name": linked_node,
                            "type": "Meeting",
                            "distance": 1,
                            "properties": {
                                "id": linked_id,
                                "title": "Harborline loans restructure",
                                "org_id": 1,
                            },
                        }
                    ],
                }

            return None

        async def aclose(self) -> None:
            return None

    return _FakeBrigadeClient


def test_search_meetings_graph_flag_off_is_base_only(monkeypatch, graph_aug_ctx):
    from services import agent_tools

    FakeSemanticSearch = _make_fake_semantic_search(graph_aug_ctx["seed_session_id"])
    monkeypatch.setattr("services.semantic_search_service.SemanticSearchService", FakeSemanticSearch)

    def _fail(*args, **kwargs):
        raise AssertionError("graph augmentation should be disabled")

    monkeypatch.setattr(agent_tools, "augment_meeting_search", _fail)

    result = asyncio.run(
        agent_tools.search_meetings_impl(
            graph_aug_ctx["db"],
            graph_aug_ctx["org"].id,
            query="Shafen loans",
            limit=5,
            graph_augment=False,
        )
    )

    assert result["match_type"] == "semantic"
    assert result["results"][0]["session_id"] == graph_aug_ctx["seed_session_id"]
    assert "graph" not in result


def test_augment_meeting_search_expands_linked_meeting(monkeypatch, graph_aug_ctx):
    from services.graph_augmented_retrieval import augment_meeting_search

    FakeSemanticSearch = _make_fake_semantic_search(graph_aug_ctx["seed_session_id"])
    FakeBrigadeClient = _make_fake_brigade_client(graph_aug_ctx["seed"].id, graph_aug_ctx["linked"].id)
    monkeypatch.setattr("services.graph_augmented_retrieval.SemanticSearchService", FakeSemanticSearch)
    monkeypatch.setattr("services.graph_augmented_retrieval.BrigadeClient", FakeBrigadeClient)

    base_results = [
        {
            "session_id": graph_aug_ctx["seed_session_id"],
            "title": "Seed meeting",
            "score": -1.0,
            "snippet": "Shafen mentioned loan timing and follow-ups.",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "match_type": "semantic",
        }
    ]

    result = asyncio.run(
        augment_meeting_search(
            graph_aug_ctx["db"],
            graph_aug_ctx["org"].id,
            query="what did Shafen and I discuss about loans across meetings?",
            base_results=base_results,
            limit=5,
            enabled=True,
        )
    )

    assert result["enabled"] is True
    assert result["results"][0]["session_id"] == graph_aug_ctx["linked_session_id"]
    assert result["results"][0]["title"] == "Harborline loans restructure"
    assert result["results"][0]["graph_bonus"] > 0
    assert "graph_evidence" in result["results"][0]
    assert "Linked meetings" in result["results"][0]["graph_evidence"]["graph_block"]


def test_ask_about_meetings_includes_graph_block(monkeypatch, graph_aug_ctx):
    from services import agent_tools

    FakeSemanticSearch = _make_fake_semantic_search(graph_aug_ctx["seed_session_id"])
    FakeBrigadeClient = _make_fake_brigade_client(graph_aug_ctx["seed"].id, graph_aug_ctx["linked"].id)
    monkeypatch.setattr("services.graph_augmented_retrieval.SemanticSearchService", FakeSemanticSearch)
    monkeypatch.setattr("services.graph_augmented_retrieval.BrigadeClient", FakeBrigadeClient)
    monkeypatch.setattr("services.semantic_search_service.SemanticSearchService", FakeSemanticSearch)

    captured: dict[str, Any] = {}

    class _FakeLLM:
        def chat_sync(self, system_prompt, user_prompt, **kwargs):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return "Canned answer"

    result = asyncio.run(
        agent_tools.ask_about_meetings_impl(
            graph_aug_ctx["db"],
            graph_aug_ctx["org"].id,
            _FakeLLM(),
            query="what did Shafen and I discuss about loans across meetings?",
            limit=5,
            graph_augment=True,
        )
    )

    assert result["answer"] == "Canned answer"
    assert "Graph context for" in captured["system_prompt"]
    assert "Harborline loans restructure" in captured["system_prompt"]
