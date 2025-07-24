"""
Search API endpoints for meeting intelligence

Provides unified search capabilities across meetings with semantic,
keyword, and graph-based search strategies.
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks, WebSocket
from pydantic import BaseModel

from auth.dependencies import get_current_user, require_permission
from auth.models import User
from services.unified_search_service import search_service
from services.knowledge_graph_service import knowledge_graph
from services.embedding_service import embedding_service

router = APIRouter(prefix="/api/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    search_type: str = "hybrid"
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    speakers: Optional[List[str]] = None
    limit: int = 20

class IndexRequest(BaseModel):
    session_ids: List[str]

@router.get("/")
async def unified_search(
    q: str = Query(..., description="Search query"),
    search_type: str = Query("hybrid", regex="^(hybrid|semantic|keyword|graph)$"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    speakers: Optional[List[str]] = Query(None),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    Unified search across all meeting data
    
    Search types:
    - hybrid: Combines semantic, keyword, and graph search
    - semantic: AI-powered semantic similarity search
    - keyword: Traditional full-text search
    - graph: Knowledge graph relationship search
    """
    try:
        results = await search_service.hybrid_search(
            query=q,
            user=current_user,
            search_type=search_type,
            date_from=date_from,
            date_to=date_to,
            speakers=speakers,
            limit=limit
        )
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

@router.post("/")
async def advanced_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    """Advanced search with full parameter control"""
    try:
        results = await search_service.hybrid_search(
            query=request.query,
            user=current_user,
            search_type=request.search_type,
            date_from=request.date_from,
            date_to=request.date_to,
            speakers=request.speakers,
            limit=request.limit
        )
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

@router.get("/suggestions")
async def search_suggestions(
    q: str = Query(..., description="Partial query for suggestions"),
    limit: int = Query(5, le=20),
    current_user: User = Depends(get_current_user)
):
    """Get search suggestions based on partial query"""
    try:
        suggestions = await search_service.search_suggestions(
            partial_query=q,
            user=current_user,
            limit=limit
        )
        
        return {"suggestions": suggestions}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {e}")

@router.get("/stats")
async def search_stats(
    current_user: User = Depends(get_current_user)
):
    """Get search statistics for the current user"""
    try:
        stats = await search_service.get_search_stats(current_user)
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {e}")

@router.get("/graph/explore/{node_id}")
async def explore_graph_node(
    node_id: str,
    depth: int = Query(2, le=5, description="Exploration depth"),
    current_user: User = Depends(get_current_user)
):
    """
    Explore knowledge graph from a specific node
    
    Returns the node context including connected nodes and relationships
    up to the specified depth.
    """
    try:
        # Get user's accessible sessions for permission checking
        user_sessions = await search_service.get_user_accessible_sessions(current_user)
        
        subgraph = await knowledge_graph.get_node_context(
            node_id=node_id,
            depth=depth,
            user_sessions=user_sessions
        )
        
        if 'error' in subgraph:
            raise HTTPException(status_code=404, detail=subgraph['error'])
        
        return subgraph
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph exploration failed: {e}")

@router.get("/graph/query")
async def graph_query(
    q: str = Query(..., description="Graph search query"),
    k: int = Query(10, le=50, description="Number of top nodes to return"),
    current_user: User = Depends(get_current_user)
):
    """Perform a direct knowledge graph query"""
    try:
        user_sessions = await search_service.get_user_accessible_sessions(current_user)
        
        results = await knowledge_graph.graph_search(
            query=q,
            user_sessions=user_sessions,
            k=k
        )
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {e}")

@router.post("/index/session/{session_id}")
async def index_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("session.read"))
):
    """
    Trigger indexing for a specific session
    
    Creates embeddings and builds knowledge graph for the session.
    This is required before the session can be searched.
    """
    try:
        # Verify user has access to this session
        user_sessions = await search_service.get_user_accessible_sessions(current_user)
        if session_id not in user_sessions:
            raise HTTPException(status_code=403, detail="Access denied to this session")
        
        # Run indexing in background
        background_tasks.add_task(
            search_service.index_session,
            session_id=session_id
        )
        
        return {
            "message": "Indexing started",
            "session_id": session_id,
            "status": "queued"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start indexing: {e}")

@router.post("/index/bulk")
async def bulk_index_sessions(
    request: IndexRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("session.read"))
):
    """Trigger bulk indexing for multiple sessions"""
    try:
        # Verify user has access to all sessions
        user_sessions = await search_service.get_user_accessible_sessions(current_user)
        
        accessible_sessions = []
        denied_sessions = []
        
        for session_id in request.session_ids:
            if session_id in user_sessions:
                accessible_sessions.append(session_id)
            else:
                denied_sessions.append(session_id)
        
        if not accessible_sessions:
            raise HTTPException(status_code=403, detail="No accessible sessions to index")
        
        # Run bulk indexing in background
        for session_id in accessible_sessions:
            background_tasks.add_task(
                search_service.index_session,
                session_id=session_id
            )
        
        return {
            "message": f"Bulk indexing started for {len(accessible_sessions)} sessions",
            "indexed_sessions": accessible_sessions,
            "denied_sessions": denied_sessions,
            "status": "queued"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start bulk indexing: {e}")

@router.get("/index/status")
async def indexing_status(
    current_user: User = Depends(get_current_user)
):
    """Get indexing status for user's accessible sessions"""
    try:
        stats = await search_service.get_search_stats(current_user)
        
        indexing_percentage = 0
        if stats['accessible_sessions'] > 0:
            indexing_percentage = (stats['indexed_sessions'] / stats['accessible_sessions']) * 100
        
        return {
            "total_sessions": stats['accessible_sessions'],
            "indexed_sessions": stats['indexed_sessions'],
            "indexing_percentage": round(indexing_percentage, 1),
            "total_chunks": stats['total_chunks'],
            "graph_nodes": stats['graph_nodes'],
            "graph_edges": stats['graph_edges'],
            "status": "complete" if indexing_percentage == 100 else "partial"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get indexing status: {e}")

@router.delete("/index/session/{session_id}")
async def remove_session_index(
    session_id: str,
    current_user: User = Depends(require_permission("session.delete"))
):
    """Remove search index data for a specific session"""
    try:
        # Verify user has access to this session
        user_sessions = await search_service.get_user_accessible_sessions(current_user)
        if session_id not in user_sessions:
            raise HTTPException(status_code=403, detail="Access denied to this session")
        
        # Remove from database
        from database.database import get_db
        db = next(get_db())
        
        try:
            # Remove embeddings
            db.execute("DELETE FROM meeting_embeddings WHERE session_id = ?", (session_id,))
            
            # Remove graph nodes and edges
            session_node = f"session_{session_id}"
            
            # Get all related nodes
            cursor = db.execute("""
                SELECT DISTINCT node_id FROM graph_nodes 
                WHERE node_id = ? 
                OR node_id IN (
                    SELECT source_id FROM graph_edges WHERE target_id = ?
                ) OR node_id IN (
                    SELECT target_id FROM graph_edges WHERE source_id = ?
                )
            """, (session_node, session_node, session_node))
            
            related_nodes = [row[0] for row in cursor.fetchall()]
            
            # Remove edges
            db.execute("""
                DELETE FROM graph_edges 
                WHERE source_id = ? OR target_id = ?
            """, (session_node, session_node))
            
            # Remove session-specific nodes
            session_specific_nodes = [n for n in related_nodes if session_id in n]
            if session_specific_nodes:
                placeholders = ','.join(['?' for _ in session_specific_nodes])
                db.execute(f"""
                    DELETE FROM graph_nodes 
                    WHERE node_id IN ({placeholders})
                """, session_specific_nodes)
            
            db.commit()
            
            return {
                "message": f"Search index removed for session {session_id}",
                "session_id": session_id,
                "removed_nodes": len(session_specific_nodes)
            }
            
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove index: {e}")

# WebSocket endpoint for real-time search (optional)
@router.websocket("/ws")
async def search_websocket(websocket):
    """WebSocket endpoint for real-time search updates"""
    # Note: WebSocket authentication should be handled differently
    # For now, accept the connection
    await websocket.accept()
    
    # In production, verify JWT token from query params or headers
    # token = websocket.query_params.get("token")
    # user = verify_token(token)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get('type') == 'search':
                # Perform search (without user context for now)
                # In production, get user from token verification
                # results = await search_service.hybrid_search(
                #     query=data['query'],
                #     user=current_user,
                #     search_type=data.get('search_type', 'hybrid'),
                #     limit=data.get('limit', 20)
                # )
                
                # For now, return a placeholder
                results = {
                    'message': 'WebSocket search endpoint needs authentication implementation',
                    'query': data['query']
                }
                
                await websocket.send_json({
                    'type': 'search_results',
                    'results': results
                })
            
            elif data.get('type') == 'graph_explore':
                # Graph exploration (without user context for now)
                # In production, get user_sessions from authenticated user
                # user_sessions = await search_service.get_user_accessible_sessions(current_user)
                
                # For now, return a placeholder
                subgraph = {
                    'message': 'WebSocket graph exploration needs authentication implementation',
                    'node_id': data.get('node_id')
                }
                
                await websocket.send_json({
                    'type': 'graph_data',
                    'data': subgraph
                })
            
    except Exception as e:
        await websocket.send_json({
            'type': 'error',
            'message': f'WebSocket error: {e}'
        })
    finally:
        await websocket.close()