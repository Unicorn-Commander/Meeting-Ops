"""
Vector search API endpoints for semantic search capabilities
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from database.database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from services.vector_search import get_vector_search_service, VectorSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    session_id: Optional[str] = Field(None, description="Filter by session ID")
    speaker: Optional[str] = Field(None, description="Filter by speaker name/ID")
    start_date: Optional[datetime] = Field(None, description="Filter by date range start")
    end_date: Optional[datetime] = Field(None, description="Filter by date range end")
    score_threshold: float = Field(0.0, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchResult(BaseModel):
    score: float
    segment_id: str
    session_id: str
    text: str
    speaker: str
    timestamp: datetime
    start_time: Optional[float]
    end_time: Optional[float]
    confidence: Optional[float]


class SimilarSegmentsRequest(BaseModel):
    text: str = Field(..., description="Text to find similar segments for")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of results")
    exclude_session: Optional[str] = Field(None, description="Session ID to exclude from results")


class CollectionInfo(BaseModel):
    name: str
    vector_count: int
    indexed_vectors: int
    points_count: int
    segments_count: int
    status: str
    vector_size: int
    distance: str


@router.post("/semantic", response_model=List[SearchResult])
async def semantic_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Perform semantic search across all transcriptions
    """
    try:
        # Convert date range to timestamps if provided
        time_range = None
        if request.start_date or request.end_date:
            start_ts = int(request.start_date.timestamp()) if request.start_date else 0
            end_ts = int(request.end_date.timestamp()) if request.end_date else int(datetime.now().timestamp())
            time_range = (start_ts, end_ts)
        
        # Perform search
        results = vector_service.search(
            query=request.query,
            limit=request.limit,
            session_id=request.session_id,
            speaker=request.speaker,
            time_range=time_range,
            score_threshold=request.score_threshold
        )
        
        # Convert results to response model
        search_results = []
        for result in results:
            search_results.append(SearchResult(
                score=result["score"],
                segment_id=result["segment_id"],
                session_id=result["session_id"],
                text=result["text"],
                speaker=result.get("speaker", "unknown"),
                timestamp=datetime.fromisoformat(result["indexed_at"]),
                start_time=result.get("start_time"),
                end_time=result.get("end_time"),
                confidence=result.get("confidence")
            ))
        
        logger.info(f"User {current_user.username} performed search: '{request.query[:50]}...' - {len(search_results)} results")
        return search_results
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/similar", response_model=List[SearchResult])
async def find_similar_segments(
    request: SimilarSegmentsRequest,
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Find segments similar to the provided text
    """
    try:
        results = vector_service.find_similar_segments(
            segment_text=request.text,
            limit=request.limit,
            exclude_session=request.exclude_session
        )
        
        # Convert results to response model
        search_results = []
        for result in results:
            search_results.append(SearchResult(
                score=result["score"],
                segment_id=result["segment_id"],
                session_id=result["session_id"],
                text=result["text"],
                speaker=result.get("speaker", "unknown"),
                timestamp=datetime.fromisoformat(result["indexed_at"]),
                start_time=result.get("start_time"),
                end_time=result.get("end_time"),
                confidence=result.get("confidence")
            ))
        
        return search_results
        
    except Exception as e:
        logger.error(f"Similar segments search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/index/session/{session_id}")
async def index_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Index or re-index all transcriptions for a session
    """
    try:
        # Get session from database
        from database.models import RecordingSession, Transcription
        
        session = db.query(RecordingSession).filter(RecordingSession.session_id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get all transcriptions for the session
        transcriptions = db.query(Transcription).filter(Transcription.session_id == session.id).all()
        
        if not transcriptions:
            return {"message": "No transcriptions found for session", "indexed": 0}
        
        # Prepare segments for indexing
        segments = []
        for trans in transcriptions:
            segment = {
                "text": trans.text,
                "speaker": trans.speaker_id or "unknown",
                "timestamp": int(trans.timestamp.timestamp()) if trans.timestamp else None,
                "start_time": trans.start_time_seconds,
                "end_time": trans.end_time_seconds,
                "confidence": trans.confidence
            }
            segments.append(segment)
        
        # Index the segments
        vector_service.index_full_transcript(
            session_id=session_id,
            segments=segments
        )
        
        logger.info(f"Indexed {len(segments)} segments for session {session_id}")
        return {
            "message": "Session indexed successfully",
            "indexed": len(segments),
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session indexing error: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.delete("/index/session/{session_id}")
async def delete_session_index(
    session_id: str,
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Delete all indexed data for a session
    """
    try:
        vector_service.delete_session(session_id)
        logger.info(f"Deleted index for session {session_id}")
        return {"message": "Session index deleted successfully", "session_id": session_id}
        
    except Exception as e:
        logger.error(f"Session index deletion error: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@router.get("/collection/info", response_model=CollectionInfo)
async def get_collection_info(
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Get information about the vector search collection
    """
    try:
        info = vector_service.get_collection_info()
        
        return CollectionInfo(
            name=info.get("name", "unknown"),
            vector_count=info.get("vector_count", 0),
            indexed_vectors=info.get("indexed_vectors", 0),
            points_count=info.get("points_count", 0),
            segments_count=info.get("segments_count", 0),
            status=info.get("status", "unknown"),
            vector_size=info.get("config", {}).get("vector_size", 0),
            distance=info.get("config", {}).get("distance", "unknown")
        )
        
    except Exception as e:
        logger.error(f"Collection info error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get collection info: {str(e)}")


@router.post("/reindex-all")
async def reindex_all_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    vector_service: VectorSearchService = Depends(get_vector_search_service)
):
    """
    Reindex all sessions (admin only)
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from database.models import RecordingSession, Transcription
        
        # Get all sessions with transcriptions
        sessions = db.query(RecordingSession).all()
        indexed_count = 0
        
        for session in sessions:
            transcriptions = db.query(Transcription).filter(Transcription.session_id == session.id).all()
            
            if transcriptions:
                segments = []
                for trans in transcriptions:
                    segment = {
                        "text": trans.text,
                        "speaker": trans.speaker_id or "unknown",
                        "timestamp": int(trans.timestamp.timestamp()) if trans.timestamp else None,
                        "start_time": trans.start_time_seconds,
                        "end_time": trans.end_time_seconds,
                        "confidence": trans.confidence
                    }
                    segments.append(segment)
                
                vector_service.index_full_transcript(
                    session_id=session.session_id,
                    segments=segments
                )
                indexed_count += 1
        
        logger.info(f"Reindexed {indexed_count} sessions")
        return {
            "message": "Reindexing completed",
            "sessions_indexed": indexed_count
        }
        
    except Exception as e:
        logger.error(f"Reindexing error: {e}")
        raise HTTPException(status_code=500, detail=f"Reindexing failed: {str(e)}")