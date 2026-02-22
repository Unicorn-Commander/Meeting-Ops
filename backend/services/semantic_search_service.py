"""
Semantic Search Service
Vector-based meeting search using Qdrant + fastembed.

Indexes meeting transcripts and summaries as vector embeddings,
enabling natural language queries like "find meetings about budget planning"
instead of exact keyword matches.

Uses fastembed (CPU) for embedding generation — fast enough for our scale
(tens to hundreds of meetings, not millions of documents).
"""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Qdrant connection
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6335"))
COLLECTION_NAME = "meeting_transcripts"

# Embedding model (384-dim, fast on CPU)
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# Chunk settings for long transcripts
CHUNK_SIZE = 400  # words per chunk
CHUNK_OVERLAP = 50  # overlapping words between chunks

# Speaker label patterns for speaker-aware chunking
import re
SPEAKER_PATTERN = re.compile(
    r'^(?:'
    r'(?:Speaker\s*\d+|[A-Z][a-zA-Z\s]*?):\s'  # "Speaker 1: ..." or "John: ..."
    r'|'
    r'\[(?:Speaker\s*\d+|[A-Z][a-zA-Z\s]*?)\]\s'  # "[Speaker 1] ..." or "[John] ..."
    r')',
    re.MULTILINE
)


class SemanticSearchService:
    """Manages vector indexing and semantic search for meeting transcripts."""

    def __init__(self):
        self._client = None
        self._embedder = None
        self._initialized = False

    def _get_client(self):
        """Lazy-init Qdrant client."""
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                check_compatibility=False,
            )
        return self._client

    def _get_embedder(self):
        """Lazy-init embedding model."""
        if self._embedder is None:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(EMBEDDING_MODEL)
            logger.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        return self._embedder

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        embedder = self._get_embedder()
        return [e.tolist() for e in embedder.embed(texts)]

    def ensure_collection(self):
        """Create the Qdrant collection if it doesn't exist.

        TODO: Hybrid search (dense + sparse BM25) - fastembed has SparseTextEmbedding
        with model "Qdrant/bm25", but adding sparse_vectors_config to an existing
        Qdrant collection requires recreation (would destroy existing 25+ points).
        When it's acceptable to recreate (e.g. after a full reindex), add:
          sparse_vectors_config={"bm25": SparseVectorParams(index=SparseIndexParams())}
        to create_collection, generate sparse embeddings at index time, and use
        Qdrant prefetch + RRF fusion at query time. See:
        https://qdrant.tech/documentation/concepts/hybrid-queries/
        """
        client = self._get_client()
        collections = [c.name for c in client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            from qdrant_client.models import VectorParams, Distance
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")
        self._initialized = True

    def _chunk_text(self, text: str) -> List[Dict]:
        """
        Split text into overlapping chunks. Returns list of dicts with
        'text' and 'speakers' keys.

        Speaker-aware: if the text has speaker labels (e.g. "Speaker 1: ..."
        or "[Speaker 1] ..."), splits on speaker turn boundaries first, then
        merges turns into ~CHUNK_SIZE-word chunks with overlap.

        Falls back to plain word-count splitting for unlabelled text.
        """
        # Detect speaker-labelled transcript
        has_speakers = bool(SPEAKER_PATTERN.search(text))

        if has_speakers:
            return self._chunk_speaker_text(text)
        else:
            return self._chunk_plain_text(text)

    def _chunk_plain_text(self, text: str) -> List[Dict]:
        """Plain word-count chunking (no speaker labels)."""
        words = text.split()
        if len(words) <= CHUNK_SIZE:
            return [{"text": text, "speakers": []}]
        chunks = []
        start = 0
        while start < len(words):
            end = start + CHUNK_SIZE
            chunk = " ".join(words[start:end])
            chunks.append({"text": chunk, "speakers": []})
            start = end - CHUNK_OVERLAP
        return chunks

    def _chunk_speaker_text(self, text: str) -> List[Dict]:
        """
        Speaker-aware chunking. Splits on speaker turn boundaries,
        then groups turns into ~CHUNK_SIZE-word chunks with CHUNK_OVERLAP
        word overlap. Keeps speaker labels in the chunk text.
        """
        # Split into speaker turns. Each turn starts with a speaker label.
        lines = text.split("\n")
        turns = []  # list of (speaker_name, turn_text)
        current_speaker = ""
        current_lines = []

        for line in lines:
            # Check for speaker label at start of line
            m = re.match(
                r'^(?:(\[?(?:Speaker\s*\d+|[A-Z][a-zA-Z\s]*?)\]?):\s*(.*))',
                line
            )
            if not m:
                # Also try bracket format: [Speaker 1] text
                m = re.match(
                    r'^\[(Speaker\s*\d+|[A-Z][a-zA-Z\s]*?)\]\s*(.*)',
                    line
                )
                if m:
                    # Reformat to have bracket speaker
                    speaker = m.group(1)
                    rest = m.group(2)
                else:
                    speaker = None
                    rest = None
            else:
                speaker = m.group(1).strip("[]")
                rest = m.group(2)

            if speaker:
                # Save previous turn
                if current_lines:
                    turns.append((current_speaker, "\n".join(current_lines)))
                current_speaker = speaker
                current_lines = [line]  # keep original line with label
            else:
                # Continuation of current speaker's turn
                if line.strip():
                    current_lines.append(line)

        # Don't forget the last turn
        if current_lines:
            turns.append((current_speaker, "\n".join(current_lines)))

        if not turns:
            return self._chunk_plain_text(text)

        # Now merge turns into chunks of ~CHUNK_SIZE words
        chunks = []
        current_chunk_turns = []
        current_word_count = 0
        current_speakers = set()

        for speaker, turn_text in turns:
            turn_words = len(turn_text.split())

            # If adding this turn exceeds the limit and we already have content,
            # finalize the current chunk
            if current_word_count + turn_words > CHUNK_SIZE and current_chunk_turns:
                chunk_text = "\n".join(current_chunk_turns)
                chunks.append({
                    "text": chunk_text,
                    "speakers": sorted(current_speakers),
                })

                # Overlap: keep the last few turns that fit within CHUNK_OVERLAP words
                overlap_turns = []
                overlap_words = 0
                overlap_speakers = set()
                for ot_speaker, ot_text in reversed(list(zip(
                    [s for s, _ in zip([speaker for speaker, _ in turns], turns)],
                    current_chunk_turns
                ))):
                    ot_words = len(ot_text.split())
                    if overlap_words + ot_words > CHUNK_OVERLAP:
                        break
                    overlap_turns.insert(0, ot_text)
                    overlap_words += ot_words

                current_chunk_turns = overlap_turns
                current_word_count = overlap_words
                # Re-extract speakers from overlap turns
                current_speakers = set()
                for ot in overlap_turns:
                    m2 = re.match(r'^(?:(\[?(?:Speaker\s*\d+|[A-Z][a-zA-Z\s]*?)\]?):\s)', ot)
                    if m2:
                        current_speakers.add(m2.group(1).strip("[]"))

            current_chunk_turns.append(turn_text)
            current_word_count += turn_words
            if speaker:
                current_speakers.add(speaker)

        # Finalize the last chunk
        if current_chunk_turns:
            chunk_text = "\n".join(current_chunk_turns)
            chunks.append({
                "text": chunk_text,
                "speakers": sorted(current_speakers),
            })

        return chunks if chunks else [{"text": text, "speakers": []}]

    def index_session(self, session_id: str, title: str,
                      transcript: Optional[str], summary: Optional[str],
                      created_at: Optional[str] = None):
        """
        Index a meeting session into Qdrant.
        Chunks long transcripts and indexes each chunk as a separate point.
        Also indexes the summary as its own point.
        """
        self.ensure_collection()
        client = self._get_client()

        # First, delete any existing points for this session (re-index)
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id),
                )]
            ),
        )

        points_to_upsert = []
        texts_to_embed = []
        payloads = []

        # Index transcript chunks
        if transcript and len(transcript.strip()) > 10:
            chunks = self._chunk_text(transcript)
            for i, chunk_data in enumerate(chunks):
                chunk_text = chunk_data["text"]
                chunk_speakers = chunk_data.get("speakers", [])
                texts_to_embed.append(chunk_text)
                payloads.append({
                    "session_id": session_id,
                    "title": title or "",
                    "content_type": "transcript",
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "text": chunk_text,  # Store full chunk text for RAG retrieval
                    "speakers": chunk_speakers,
                    "created_at": created_at or "",
                })

        # Index summary as a single point
        if summary and len(summary.strip()) > 10:
            texts_to_embed.append(summary)
            payloads.append({
                "session_id": session_id,
                "title": title or "",
                "content_type": "summary",
                "chunk_index": 0,
                "total_chunks": 1,
                "text": summary,  # Store full summary text for RAG retrieval
                "speakers": [],
                "created_at": created_at or "",
            })

        # Index title
        if title and len(title.strip()) > 3:
            texts_to_embed.append(title)
            payloads.append({
                "session_id": session_id,
                "title": title,
                "content_type": "title",
                "chunk_index": 0,
                "total_chunks": 1,
                "text": title,
                "speakers": [],
                "created_at": created_at or "",
            })

        if not texts_to_embed:
            logger.debug(f"No content to index for session {session_id}")
            return 0

        # Generate embeddings
        embeddings = self._embed(texts_to_embed)

        # Build points
        from qdrant_client.models import PointStruct
        import uuid

        points = []
        for emb, payload in zip(embeddings, payloads):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload=payload,
            ))

        # Upsert to Qdrant
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"Indexed session {session_id}: {len(points)} points "
                     f"({len([p for p in payloads if p['content_type'] == 'transcript'])} transcript, "
                     f"{len([p for p in payloads if p['content_type'] == 'summary'])} summary, "
                     f"{len([p for p in payloads if p['content_type'] == 'title'])} title)")
        return len(points)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Semantic search across all indexed meetings.
        Returns matching sessions with relevance scores and snippets.
        """
        self.ensure_collection()
        client = self._get_client()

        # Check if collection has points
        info = client.get_collection(COLLECTION_NAME)
        if info.points_count == 0:
            return []

        # Embed the query
        query_embedding = self._embed([query])[0]

        # Search Qdrant (v1.17+ API: query_points instead of search)
        from qdrant_client.models import models
        query_result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=limit * 3,  # Over-fetch to deduplicate by session
        )
        results = query_result.points

        # Deduplicate by session_id, keeping the best score
        seen_sessions = {}
        for hit in results:
            sid = hit.payload.get("session_id")
            if sid not in seen_sessions or hit.score > seen_sessions[sid]["score"]:
                seen_sessions[sid] = {
                    "session_id": sid,
                    "title": hit.payload.get("title", ""),
                    "score": round(float(hit.score), 4),
                    "match_type": hit.payload.get("content_type", ""),
                    "snippet": hit.payload.get("text", ""),
                    "created_at": hit.payload.get("created_at", ""),
                }

        # Sort by score descending, limit
        results_list = sorted(
            seen_sessions.values(),
            key=lambda x: x["score"],
            reverse=True,
        )[:limit]

        return results_list

    def search_chunks(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Semantic search returning individual chunks (not deduplicated by session).
        Used by RAG pipeline to retrieve relevant context across all meetings.
        Returns chunks with full text, session metadata, and relevance scores.
        """
        self.ensure_collection()
        client = self._get_client()

        info = client.get_collection(COLLECTION_NAME)
        if info.points_count == 0:
            return []

        query_embedding = self._embed([query])[0]

        from qdrant_client.models import models
        query_result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=limit,
        )

        chunks = []
        for hit in query_result.points:
            chunks.append({
                "session_id": hit.payload.get("session_id", ""),
                "title": hit.payload.get("title", ""),
                "content_type": hit.payload.get("content_type", ""),
                "chunk_index": hit.payload.get("chunk_index", 0),
                "text": hit.payload.get("text", ""),
                "speakers": hit.payload.get("speakers", []),
                "score": round(float(hit.score), 4),
                "created_at": hit.payload.get("created_at", ""),
            })

        return chunks

    def delete_session(self, session_id: str):
        """Remove all indexed points for a session."""
        self.ensure_collection()
        client = self._get_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id),
                )]
            ),
        )
        logger.info(f"Deleted vectors for session {session_id}")

    def get_stats(self) -> Dict:
        """Get collection statistics."""
        try:
            client = self._get_client()
            collections = [c.name for c in client.get_collections().collections]
            if COLLECTION_NAME not in collections:
                return {
                    "initialized": False,
                    "collection": COLLECTION_NAME,
                    "points_count": 0,
                }
            info = client.get_collection(COLLECTION_NAME)
            return {
                "initialized": True,
                "collection": COLLECTION_NAME,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": str(info.status),
            }
        except Exception as e:
            return {
                "initialized": False,
                "error": str(e),
            }

    def reindex_all(self, db_session) -> Dict:
        """Reindex all completed sessions from the database."""
        from database.models import RecordingSession
        sessions = db_session.query(RecordingSession).filter(
            RecordingSession.status.in_(["completed", "failed"])
        ).all()

        total_points = 0
        indexed = 0
        skipped = 0

        for session in sessions:
            # Gather text content
            transcript = session.transcript_simple or ""
            if not transcript and session.transcript:
                # Try to extract text from JSON transcript
                import json
                try:
                    t = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
                    if isinstance(t, dict) and "text" in t:
                        transcript = t["text"]
                    elif isinstance(t, dict) and "segments" in t:
                        transcript = " ".join(seg.get("text", "") for seg in t["segments"])
                except Exception:
                    transcript = str(session.transcript) if session.transcript else ""

            summary = session.summary or ""
            title = session.title or session.name or ""
            created = session.created_at.isoformat() if session.created_at else ""

            if not transcript and not summary and not title:
                skipped += 1
                continue

            points = self.index_session(
                session_id=session.session_id or str(session.id),
                title=title,
                transcript=transcript,
                summary=summary,
                created_at=created,
            )
            total_points += points
            indexed += 1

        return {
            "sessions_indexed": indexed,
            "sessions_skipped": skipped,
            "total_points": total_points,
        }


# Global singleton
semantic_search = SemanticSearchService()
