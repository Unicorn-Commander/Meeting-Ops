"""
Meeting Embeddings Service — chunk, embed, and index meeting transcripts into Qdrant.
Triggered when a meeting ends (status changes to 'completed').
"""
import logging
import os
from typing import Optional
from sqlalchemy.orm import Session

from services.providers.registry import get_provider_registry
from database.models import RecordingSession, MeetingChunkEmbedding
from services.semantic_search_service import semantic_search, CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

QDRANT_COLLECTION_CHUNKS = f"{os.getenv('QDRANT_COLLECTION_PREFIX', 'meet_')}chunks"
QDRANT_COLLECTION_SUMMARIES = f"{os.getenv('QDRANT_COLLECTION_PREFIX', 'meet_')}summaries"


def _qdrant_client():
    from qdrant_client import QdrantClient

    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        return QdrantClient(url=qdrant_url)
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "unicorn-qdrant"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _chunk_transcript(text: str, chunk_size: int = 500) -> list[dict]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_text = " ".join(words[start:end])
        chunks.append({"text": chunk_text, "start_word": start, "end_word": end})
        start = end - (chunk_size // 10)
        if start >= len(words):
            break
        if start <= 0:
            start = 1
    if not chunks:
        chunks = [{"text": text, "start_word": 0, "end_word": len(words)}]
    return chunks


def ensure_collections():
    from qdrant_client.models import VectorParams, Distance
    client = _qdrant_client()

    collections = {c.name for c in client.get_collections().collections}

    for coll_name, dim in [(QDRANT_COLLECTION_CHUNKS, 1024), (QDRANT_COLLECTION_SUMMARIES, 1024)]:
        if coll_name not in collections:
            client.create_collection(
                collection_name=coll_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {coll_name}")


def _extract_speakers(session: RecordingSession) -> list[str]:
    speakers = []
    if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
        for seg in session.transcript_diarized.get("segments", []):
            speaker = seg.get("speaker", "")
            if speaker and speaker not in speakers:
                speakers.append(speaker)
    return speakers


def _extract_transcript_text(session: RecordingSession) -> str:
    if session.transcript_simple:
        return session.transcript_simple
    if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
        segments = session.transcript_diarized.get("segments", [])
        if segments:
            lines = []
            for seg in segments:
                speaker = seg.get("speaker", "Speaker")
                text = seg.get("text", "")
                if text:
                    lines.append(f"{speaker}: {text}")
            return "\n".join(lines)
    if session.transcript:
        try:
            import json
            data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
            if isinstance(data, dict):
                if "text" in data:
                    return data["text"]
                if "segments" in data:
                    return " ".join(s.get("text", "") for s in data["segments"] if s.get("text"))
            return str(data)
        except (json.JSONDecodeError, TypeError):
            return str(session.transcript)
    return ""


def embed_meeting(session: RecordingSession, db: Session):
    ensure_collections()

    import uuid as _uuid

    org_id = session.organization_id
    meeting_id = session.id
    session_slug = session.session_id or str(meeting_id)
    project_id = session.project_id
    project_app = session.project_app
    project_slug = session.project_slug
    session_kind = session.meeting_type

    speakers = _extract_speakers(session)
    transcript = _extract_transcript_text(session)

    registry = get_provider_registry(db)
    embedder = registry.get_embeddings(org_id)

    client = _qdrant_client()

    # Delete existing points for this meeting
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    for coll in [QDRANT_COLLECTION_CHUNKS, QDRANT_COLLECTION_SUMMARIES]:
        try:
            client.delete(
                collection_name=coll,
                points_selector=Filter(
                    must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
                ),
            )
        except Exception:
            pass

    # Clear existing chunk tracking
    db.query(MeetingChunkEmbedding).filter(
        MeetingChunkEmbedding.meeting_id == meeting_id
    ).delete()

    total_points = 0

    # Chunk and embed transcript
    if transcript:
        chunks = _chunk_transcript(transcript)
        for i, chunk_data in enumerate(chunks):
            chunk_text = chunk_data["text"]
            point_id = str(_uuid.uuid4())
            snippet = chunk_text[:200] if len(chunk_text) > 200 else chunk_text

            try:
                embeddings = embedder.embed_sync([chunk_text])
                if embeddings:
                    from qdrant_client.models import PointStruct
                    client.upsert(
                        collection_name=QDRANT_COLLECTION_CHUNKS,
                        points=[PointStruct(
                            id=point_id,
                            vector=embeddings[0],
                            payload={
                                "org_id": org_id,
                                "meeting_id": meeting_id,
                                "project_id": project_id,
                                "project_app": project_app,
                                "project_slug": project_slug,
                                "chunk_idx": i,
                                "start_word": chunk_data["start_word"],
                                "end_word": chunk_data["end_word"],
                                "speakers": speakers,
                                "session_kind": session_kind,
                                "text": chunk_text[:4000],
                            },
                        )],
                    )

                    db.add(MeetingChunkEmbedding(
                        meeting_id=meeting_id,
                        chunk_idx=i,
                        qdrant_point_id=point_id,
                        text_snippet=snippet,
                    ))
                    total_points += 1
            except Exception as e:
                logger.error(f"Chunk embedding failed for meeting {meeting_id} chunk {i}: {e}")

    # Embed summary as separate point
    summary = session.summary or ""
    if summary:
        try:
            embeddings = embedder.embed_sync([summary])
            if embeddings:
                point_id = str(_uuid.uuid4())
                from qdrant_client.models import PointStruct
                client.upsert(
                    collection_name=QDRANT_COLLECTION_SUMMARIES,
                    points=[PointStruct(
                        id=point_id,
                        vector=embeddings[0],
                        payload={
                            "org_id": org_id,
                            "meeting_id": meeting_id,
                            "project_id": project_id,
                            "project_app": project_app,
                            "text": summary[:4000],
                        },
                    )],
                )
                total_points += 1
        except Exception as e:
            logger.error(f"Summary embedding failed for meeting {meeting_id}: {e}")

    db.commit()
    logger.info(f"Embedded meeting {meeting_id}: {total_points} points in Qdrant")
    return total_points
