"""
Meeting Intelligence API endpoints

Provides intelligent query handling with personal memory and preferences
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime

from auth.dependencies import get_current_user
from auth.models import User
from services.memory_service import meeting_intelligence
from services.unified_search_service import search_service

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

class IntelligentQueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None

class PreferencesUpdateRequest(BaseModel):
    preferences: Dict[str, Any]

class ProjectContextRequest(BaseModel):
    project: str
    context: Dict[str, Any]

class ConversationResponse(BaseModel):
    query: str
    summary: str
    key_insights: List[str]
    action_items: Optional[List[Dict]]
    decisions: Optional[List[Dict]]
    recommendations: List[str]
    formatted_response: str
    metadata: Dict[str, Any]

@router.post("/query", response_model=ConversationResponse)
async def intelligent_query(
    request: IntelligentQueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Process an intelligent query with personal memory and context
    
    This endpoint:
    - Uses the user's preferences for response formatting
    - Considers conversation history for context
    - Provides personalized recommendations
    - Extracts insights, action items, and decisions
    """
    try:
        response = await meeting_intelligence.handle_user_query(
            user=current_user,
            query=request.query,
            context=request.context
        )
        
        if 'error' in response:
            raise HTTPException(status_code=500, detail=response['error'])
        
        # Structure response for API
        return ConversationResponse(
            query=response['query'],
            summary=response['summary'],
            key_insights=response.get('key_insights', []),
            action_items=response.get('action_items'),
            decisions=response.get('decisions'),
            recommendations=response.get('recommendations', []),
            formatted_response=response['formatted_response'],
            metadata={
                'timestamp': response['timestamp'],
                'search_type': response['search_type'],
                'result_count': response['result_count'],
                'accessible_sessions': response.get('accessible_sessions', 0)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")

@router.get("/memory")
async def get_user_memory(
    current_user: User = Depends(get_current_user)
):
    """Get user's complete memory including preferences and conversation history"""
    try:
        memory = await meeting_intelligence.personal_memory.get_user_memory(current_user.id)
        
        # Remove sensitive data if needed
        return {
            'preferences': memory.get('preferences', {}),
            'conversation_history': memory.get('conversation_history', [])[:20],  # Last 20
            'project_context': list(memory.get('project_context', {}).keys()),  # Just project names
            'learned_patterns': {
                'query_types': dict(memory.get('learned_patterns', {}).get('query_types', {})),
                'topic_interests': dict(memory.get('learned_patterns', {}).get('topic_interests', {}))
            },
            'last_updated': memory.get('last_updated')
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve memory: {e}")

@router.put("/preferences")
async def update_preferences(
    request: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update user preferences"""
    try:
        success = await meeting_intelligence.personal_memory.update_preferences(
            user_id=current_user.id,
            preferences=request.preferences
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update preferences")
        
        return {"message": "Preferences updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {e}")

@router.post("/project-context")
async def update_project_context(
    request: ProjectContextRequest,
    current_user: User = Depends(get_current_user)
):
    """Update project-specific context"""
    try:
        success = await meeting_intelligence.personal_memory.update_project_context(
            user_id=current_user.id,
            project=request.project,
            context=request.context
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update project context")
        
        return {"message": f"Project context updated for {request.project}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update project context: {e}")

@router.get("/conversation-history")
async def get_conversation_history(
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get user's conversation history"""
    try:
        memory = await meeting_intelligence.personal_memory.get_user_memory(current_user.id)
        history = memory.get('conversation_history', [])[:limit]
        
        return {
            'conversations': history,
            'total': len(memory.get('conversation_history', [])),
            'limit': limit
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve history: {e}")

@router.delete("/conversation-history")
async def clear_conversation_history(
    current_user: User = Depends(get_current_user)
):
    """Clear user's conversation history"""
    try:
        memory = await meeting_intelligence.personal_memory.get_user_memory(current_user.id)
        memory['conversation_history'] = []
        memory['last_updated'] = datetime.utcnow().isoformat()
        
        # Save updated memory
        from pathlib import Path
        import json
        
        memory_file = Path("storage/user_memory") / f"user_{current_user.id}.json"
        with open(memory_file, 'w') as f:
            json.dump(memory, f, indent=2)
        
        return {"message": "Conversation history cleared"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {e}")

@router.get("/insights")
async def get_user_insights(
    current_user: User = Depends(get_current_user)
):
    """Get insights about user's interaction patterns"""
    try:
        memory = await meeting_intelligence.personal_memory.get_user_memory(current_user.id)
        patterns = memory.get('learned_patterns', {})
        
        # Generate insights
        insights = []
        
        # Query type insights
        query_types = patterns.get('query_types', {})
        if query_types:
            most_common = max(query_types.items(), key=lambda x: x[1])
            insights.append({
                'type': 'query_pattern',
                'insight': f"You most frequently search for {most_common[0]}",
                'count': most_common[1]
            })
        
        # Session access insights
        frequent_sessions = patterns.get('frequent_sessions', {})
        if frequent_sessions:
            top_sessions = sorted(frequent_sessions.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append({
                'type': 'session_access',
                'insight': f"Your most accessed sessions",
                'sessions': [{'id': s[0], 'count': s[1]} for s in top_sessions]
            })
        
        # Topic interest insights
        topic_interests = patterns.get('topic_interests', {})
        if topic_interests:
            top_topics = sorted(topic_interests.items(), key=lambda x: x[1], reverse=True)[:5]
            insights.append({
                'type': 'topic_interests',
                'insight': "Your primary areas of interest",
                'topics': [{'name': t[0], 'score': t[1]} for t in top_topics]
            })
        
        return {
            'insights': insights,
            'total_conversations': len(memory.get('conversation_history', [])),
            'preferences_set': bool(memory.get('preferences'))
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {e}")

@router.post("/feedback")
async def provide_feedback(
    query_id: str = Query(..., description="ID of the query to provide feedback for"),
    helpful: bool = Query(..., description="Was the response helpful?"),
    feedback: Optional[str] = Query(None, description="Additional feedback"),
    current_user: User = Depends(get_current_user)
):
    """Provide feedback on a query response"""
    try:
        # In a production system, this would update the response quality metrics
        # For now, we'll just log it
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"User {current_user.username} provided feedback for query {query_id}: "
                   f"helpful={helpful}, feedback={feedback}")
        
        return {"message": "Thank you for your feedback"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {e}")

# Quick actions based on learned patterns
@router.get("/quick-actions")
async def get_quick_actions(
    current_user: User = Depends(get_current_user)
):
    """Get suggested quick actions based on user patterns"""
    try:
        memory = await meeting_intelligence.personal_memory.get_user_memory(current_user.id)
        patterns = memory.get('learned_patterns', {})
        
        quick_actions = []
        
        # Based on query types
        query_types = patterns.get('query_types', {})
        if query_types.get('decisions', 0) > 5:
            quick_actions.append({
                'action': 'View recent decisions',
                'query': 'Show me all decisions from the last week',
                'icon': '✅'
            })
        
        if query_types.get('action_items', 0) > 5:
            quick_actions.append({
                'action': 'Check action items',
                'query': 'What are my pending action items?',
                'icon': '📋'
            })
        
        # Based on frequent sessions
        frequent_sessions = patterns.get('frequent_sessions', {})
        if frequent_sessions:
            top_session = max(frequent_sessions.items(), key=lambda x: x[1])[0]
            quick_actions.append({
                'action': f'Review session {top_session[-8:]}',
                'query': f'Show me the summary of session {top_session}',
                'icon': '📄'
            })
        
        # Always include search actions
        quick_actions.extend([
            {
                'action': "Today's meetings",
                'query': "What was discussed in today's meetings?",
                'icon': '📅'
            },
            {
                'action': 'Search by speaker',
                'query': 'Show me what [speaker] said about [topic]',
                'icon': '👤'
            }
        ])
        
        return {'quick_actions': quick_actions[:5]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate quick actions: {e}")