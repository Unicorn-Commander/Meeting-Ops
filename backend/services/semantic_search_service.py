"""
Semantic Search Service — Hybrid (Dense + Sparse BM25)
Vector-based meeting search using Qdrant + fastembed.

Indexes meeting transcripts and summaries as both dense (BAAI/bge-small-en-v1.5)
and sparse (Qdrant/bm25) vector embeddings. Queries use Reciprocal Rank Fusion
(RRF) to combine semantic similarity with keyword relevance.

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

# Embedding models
DENSE_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, fast on CPU
DENSE_DIM = 384
SPARSE_MODEL = "Qdrant/bm25"             # BM25 sparse via fastembed

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
    """Manages hybrid vector indexing and search for meeting transcripts.

    Uses dense (semantic) + sparse (BM25 keyword) vectors with Reciprocal
    Rank Fusion for better recall than either method alone.
    """

    def __init__(self):
        self._client = None
        self._dense_embedder = None
        self._sparse_embedder = None
        self._hybrid_enabled = False  # Set True after successful collection setup
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

    def _get_dense_embedder(self):
        """Lazy-init dense embedding model (BAAI/bge-small-en-v1.5, 384-dim)."""
        if self._dense_embedder is None:
            from fastembed import TextEmbedding
            self._dense_embedder = TextEmbedding(DENSE_MODEL)
            logger.info(f"Loaded dense embedding model: {DENSE_MODEL}")
        return self._dense_embedder

    def _get_sparse_embedder(self):
        """Lazy-init sparse BM25 embedding model (Qdrant/bm25)."""
        if self._sparse_embedder is None:
            try:
                from fastembed import SparseTextEmbedding
                self._sparse_embedder = SparseTextEmbedding(SPARSE_MODEL)
                logger.info(f"Loaded sparse embedding model: {SPARSE_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to load sparse embedder: {e}")
                self._sparse_embedder = None
        return self._sparse_embedder

    # Backward-compatible aliases
    def _get_embedder(self):
        return self._get_dense_embedder()

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Generate dense embeddings for a list of texts."""
        embedder = self._get_dense_embedder()
        return [e.tolist() for e in embedder.embed(texts)]

    def _sparse_embed(self, texts: List[str]) -> list:
        """Generate sparse BM25 embeddings for a list of texts.

        Returns list of sparse embedding objects (with .indices and .values),
        or None if sparse embedder is unavailable.
        """
        embedder = self._get_sparse_embedder()
        if embedder is None:
            return None
        try:
            return list(embedder.embed(texts))
        except Exception as e:
            logger.warning(f"Sparse embedding failed: {e}")
            return None

    def ensure_collection(self):
        """Create or recreate the Qdrant collection with hybrid vector support.

        The collection uses named vectors:
        - "dense": 384-dim COSINE (BAAI/bge-small-en-v1.5 semantic embeddings)
        - "sparse": BM25 sparse vectors (keyword matching via fastembed)

        If the collection exists but lacks sparse vector config, it is
        deleted and recreated. All data is reindexed afterward.
        """
        client = self._get_client()
        collections = [c.name for c in client.get_collections().collections]

        needs_creation = False

        if COLLECTION_NAME in collections:
            # Check if the existing collection already has hybrid config
            info = client.get_collection(COLLECTION_NAME)
            vectors_config = info.config.params.vectors

            # Named vectors will be a dict; unnamed will be a VectorParams
            has_named_dense = (
                isinstance(vectors_config, dict) and "dense" in vectors_config
            )
            has_sparse = bool(
                info.config.params.sparse_vectors
                and "sparse" in info.config.params.sparse_vectors
            )

            if has_named_dense and has_sparse:
                # Already hybrid — nothing to do
                self._hybrid_enabled = True
                self._initialized = True
                logger.info("Qdrant collection already has hybrid config")
                return

            # Old collection (dense-only or wrong config) — delete and recreate
            logger.info(
                "Deleting old Qdrant collection to recreate with hybrid vectors "
                f"(had named_dense={has_named_dense}, sparse={has_sparse})"
            )
            client.delete_collection(COLLECTION_NAME)
            needs_creation = True
        else:
            needs_creation = True

        if needs_creation:
            from qdrant_client.models import (
                VectorParams, Distance,
                SparseVectorParams, SparseIndexParams,
            )
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(
                        size=DENSE_DIM,
                        distance=Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(),
                    ),
                },
            )
            self._hybrid_enabled = True
            logger.info(
                f"Created Qdrant collection '{COLLECTION_NAME}' with hybrid "
                f"vectors (dense {DENSE_DIM}-dim COSINE + sparse BM25)"
            )

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
        Index a meeting session into Qdrant with hybrid (dense + sparse) vectors.
        Chunks long transcripts and indexes each chunk as a separate point.
        Also indexes the summary and title as their own points.
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

        # Generate dense embeddings
        dense_embeddings = self._embed(texts_to_embed)

        # Generate sparse (BM25) embeddings
        sparse_embeddings = self._sparse_embed(texts_to_embed)

        # Build points with named vectors
        from qdrant_client.models import PointStruct, SparseVector
        import uuid

        points = []
        for i, (dense_emb, payload) in enumerate(zip(dense_embeddings, payloads)):
            vector_dict = {
                "dense": dense_emb,
            }

            # Add sparse vector if available
            if sparse_embeddings is not None and i < len(sparse_embeddings):
                sparse = sparse_embeddings[i]
                vector_dict["sparse"] = SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist(),
                )

            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector_dict,
                payload=payload,
            ))

        # Upsert to Qdrant
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        has_sparse = sparse_embeddings is not None
        logger.info(
            f"Indexed session {session_id}: {len(points)} points "
            f"({len([p for p in payloads if p['content_type'] == 'transcript'])} transcript, "
            f"{len([p for p in payloads if p['content_type'] == 'summary'])} summary, "
            f"{len([p for p in payloads if p['content_type'] == 'title'])} title) "
            f"[hybrid={'yes' if has_sparse else 'no'}]"
        )
        return len(points)

    def _hybrid_query(self, query: str, limit: int):
        """Execute a hybrid (dense + sparse) query using Qdrant prefetch + RRF fusion.

        Falls back to dense-only if sparse embedder is unavailable or the
        collection doesn't have sparse vectors configured.

        Returns (points_list, search_mode_str).
        """
        client = self._get_client()

        # Dense embedding (always available)
        query_dense = self._embed([query])[0]

        # Try sparse embedding
        sparse_result = self._sparse_embed([query])
        use_hybrid = (
            self._hybrid_enabled
            and sparse_result is not None
            and len(sparse_result) > 0
        )

        if use_hybrid:
            try:
                from qdrant_client.models import (
                    Prefetch, FusionQuery, Fusion, SparseVector,
                )

                sparse = sparse_result[0]
                query_sparse = SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist(),
                )

                query_result = client.query_points(
                    collection_name=COLLECTION_NAME,
                    prefetch=[
                        Prefetch(
                            query=query_dense,
                            using="dense",
                            limit=limit * 3,
                        ),
                        Prefetch(
                            query=query_sparse,
                            using="sparse",
                            limit=limit * 3,
                        ),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                )
                return query_result.points, "hybrid"

            except Exception as e:
                logger.warning(
                    f"Hybrid query failed, falling back to dense-only: {e}"
                )

        # Fallback: dense-only search
        query_result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_dense,
            using="dense",
            limit=limit,
        )
        return query_result.points, "dense"

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Hybrid semantic search across all indexed meetings.
        Uses dense + sparse BM25 with RRF fusion for best recall.
        Returns matching sessions with relevance scores and snippets.
        """
        self.ensure_collection()
        client = self._get_client()

        # Check if collection has points
        info = client.get_collection(COLLECTION_NAME)
        if info.points_count == 0:
            return []

        # Hybrid query: dense + sparse with RRF fusion
        results, search_mode = self._hybrid_query(query, limit=limit * 3)

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
        Hybrid semantic search returning individual chunks (not deduplicated by session).
        Used by RAG pipeline to retrieve relevant context across all meetings.
        Returns chunks with full text, session metadata, and relevance scores.
        """
        self.ensure_collection()
        client = self._get_client()

        info = client.get_collection(COLLECTION_NAME)
        if info.points_count == 0:
            return []

        # Hybrid query: dense + sparse with RRF fusion
        results, search_mode = self._hybrid_query(query, limit=limit)

        chunks = []
        for hit in results:
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
        """Get collection statistics including hybrid search status."""
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

            # Detect vector configuration
            vectors_config = info.config.params.vectors
            has_named_dense = (
                isinstance(vectors_config, dict) and "dense" in vectors_config
            )
            has_sparse = bool(
                info.config.params.sparse_vectors
                and "sparse" in info.config.params.sparse_vectors
            )
            search_mode = "hybrid" if (has_named_dense and has_sparse) else "dense-only"

            return {
                "initialized": True,
                "collection": COLLECTION_NAME,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": str(info.status),
                "search_mode": search_mode,
                "dense_model": DENSE_MODEL,
                "sparse_model": SPARSE_MODEL if has_sparse else None,
            }
        except Exception as e:
            return {
                "initialized": False,
                "error": str(e),
            }

    def reindex_all(self, db_session) -> Dict:
        """Reindex all completed sessions from the database.

        Recreates the collection with hybrid vectors if needed, then
        indexes all sessions with both dense and sparse embeddings.
        """
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
            "search_mode": "hybrid" if self._hybrid_enabled else "dense-only",
        }


# Global singleton
semantic_search = SemanticSearchService()
