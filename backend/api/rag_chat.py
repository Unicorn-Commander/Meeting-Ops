"""
RAG Chat API — cross-meeting RAG with SSE streaming, reranking, and citations.
Replaces the simpler /api/ai-chat/rag/query with a full pipeline.

The core pipeline lives in `rag_chat_pipeline()` so the multi-agent
dispatcher (api/agents.py) can reuse it without code duplication.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, AsyncIterator
from pydantic import BaseModel, Field
from datetime import datetime
import json
import logging
import os
import time

from database.database import get_db
from database.models import ChatHistory
from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.models import User
from services.providers.registry import get_provider_registry

router = APIRouter(prefix="/api/rag", tags=["RAG Chat"])
logger = logging.getLogger(__name__)

RAG_SESSION_KEY = "__rag_v2__"


class RAGChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    scope: Optional[dict] = Field(default_factory=dict)
    history: Optional[list[dict]] = Field(default_factory=list)


def _load_history(db: Session, org_id: int, limit: int = 10) -> list[dict]:
    rows = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_key == RAG_SESSION_KEY,
            ChatHistory.organization_id == org_id,
        )
        .order_by(ChatHistory.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def _save_message(db: Session, org_id: int, role: str, content: str):
    msg = ChatHistory(
        session_key=RAG_SESSION_KEY,
        role=role,
        content=content,
        organization_id=org_id,
    )
    db.add(msg)
    db.commit()


async def rag_chat_pipeline(
    *,
    question: str,
    scope: Optional[dict],
    history: Optional[list[dict]],
    db: Session,
    org_id: int,
) -> StreamingResponse:
    """Run the full RAG pipeline and return an SSE StreamingResponse.

    Exposed as a function so api/agents.py can dispatch to the same logic
    when an agent_id of 'meeting-rag' is selected.
    """
    scope = scope or {}
    history = history or _load_history(db, org_id)

    registry = get_provider_registry(db)
    embeddings = registry.get_embeddings(org_id)
    llm = registry.get_llm(org_id, task="chat")
    reranker = registry.get_reranking(org_id)

    # 1. Embed question
    question_embedding = embeddings.embed_sync([question])
    if not question_embedding:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    query_vector = question_embedding[0]

    # 2. Search Qdrant with org filter + scope
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qdrant = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6335")),
        check_compatibility=False,
    )

    must_filters = [
        FieldCondition(key="organization_id", match=MatchValue(value=org_id)),
    ]

    project_id = scope.get("project_id")
    if project_id:
        must_filters.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))

    meeting_ids = scope.get("meeting_ids")
    if meeting_ids:
        from qdrant_client.models import MatchAny
        must_filters.append(FieldCondition(key="meeting_id", match=MatchAny(any=[str(mid) for mid in meeting_ids])))

    time_window = scope.get("time_window")
    if time_window:
        try:
            start_ts = datetime.fromisoformat(time_window[0]).timestamp() if time_window[0] else 0
            end_ts = datetime.fromisoformat(time_window[1]).timestamp() if time_window[1] else float("inf")
            from qdrant_client.models import Range
            must_filters.append(FieldCondition(key="end_ts", range=Range(gte=start_ts, lte=end_ts)))
        except Exception:
            pass

    qdrant_filter = Filter(must=must_filters)

    search_result = qdrant.query_points(
        collection_name=f"{os.getenv('QDRANT_COLLECTION_PREFIX', 'meet_')}chunks",
        query=query_vector,
        limit=50,
        query_filter=qdrant_filter,
    )

    if not search_result.points:
        async def empty_stream():
            yield f"data: {json.dumps({'token': 'No relevant meeting content found for your question.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': [], 'metadata': {'chunks_searched': 0}})}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    # 3. Rerank top-50 to top-5
    documents = []
    point_map = {}
    for point in search_result.points:
        payload = point.payload or {}
        text = payload.get("text", "")
        if text:
            documents.append(text)
            point_map[len(documents) - 1] = point

    reranked = await reranker.rerank(question, documents, top_n=5)
    if reranked:
        top_points = [point_map[r.get("index", i)] for i, r in enumerate(reranked[:5])]
    else:
        top_points = search_result.points[:5]

    # 4. Build prompt with citations
    context_parts = []
    citations = []
    for i, point in enumerate(top_points):
        payload = point.payload or {}
        meeting_id = payload.get("meeting_id", "unknown")
        chunk_idx = payload.get("chunk_idx", 0)
        text = payload.get("text", "")
        citation = f"[{meeting_id}:{chunk_idx}]"
        context_parts.append(f"Source {citation}:\n{text}")
        citations.append({
            "meeting_id": meeting_id,
            "chunk_idx": chunk_idx,
            "snippet": text[:200],
        })

    context_text = "\n\n".join(context_parts)

    system_prompt = (
        "You are a meeting analyst for Meeting-Ops. Answer the user's question "
        "using ONLY the meeting excerpts provided below. Cite which source each "
        "fact comes from using the citation markers like [meeting_id:chunk_idx]. "
        "If the excerpts do not contain enough information, say so honestly.\n\n"
        f"Meeting Excerpts:\n{context_text}"
    )

    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "\n".join([
            f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content'][:300]}"
            for h in recent
        ])

    user_prompt = question
    if history_text:
        user_prompt = f"Previous conversation:\n{history_text}\n\nUser: {question}"

    chunks_searched = len(search_result.points)

    async def event_stream():
        full_answer = ""
        chunk_count = 0
        t0 = time.time()
        try:
            async for token in llm.chat_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=800,
                temperature=0.3,
            ):
                if token:
                    full_answer += token
                    chunk_count += 1
                    yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            logger.error(f"RAG stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        inference_ms = int((time.time() - t0) * 1000)
        yield f"data: {json.dumps({'done': True, 'sources': citations, 'metadata': {'response_time_ms': inference_ms, 'chunks_searched': chunks_searched, 'chunks_streamed': chunk_count}})}\n\n"

        try:
            _save_message(db, org_id, "user", question)
            _save_message(db, org_id, "assistant", full_answer)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to persist RAG history: {e}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat")
async def rag_chat(
    request: RAGChatRequest,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    return await rag_chat_pipeline(
        question=request.question,
        scope=request.scope,
        history=request.history,
        db=db,
        org_id=active_org.organization.id,
    )


@router.get("/chat/history")
async def get_rag_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    history = _load_history(db, active_org.organization.id, limit=50)
    return [{"role": h["role"], "content": h["content"]} for h in history]


@router.delete("/chat/history")
async def clear_rag_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    db.query(ChatHistory).filter(
        ChatHistory.session_key == RAG_SESSION_KEY,
        ChatHistory.organization_id == active_org.organization.id,
    ).delete()
    db.commit()
    return {"message": "RAG chat history cleared"}
