"""
Unified Memory Service for Meeting Intelligence

Implements a dual-memory system that combines:
1. Meeting Knowledge System - Extract and organize knowledge from meetings
2. Personal Assistant Memory - Remember user preferences and conversation context
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from collections import defaultdict
import pickle
from pathlib import Path

from database.database import get_db
from database.models import RecordingSession, Transcription
from sqlalchemy.orm import Session as DBSession
from auth.models import User
from services.knowledge_graph_service import knowledge_graph
from services.unified_search_service import search_service

logger = logging.getLogger(__name__)

class PersonalMemory:
    """User-specific memory for preferences and context"""
    
    def __init__(self):
        self.memory_dir = Path("storage/user_memory")
        self.memory_dir.mkdir(exist_ok=True)
        
        # Default preferences structure
        self.default_preferences = {
            'summary_style': 'concise',  # concise, detailed, bullet-points
            'focus_areas': [],  # Topics of special interest
            'formatting': {
                'timestamps': True,
                'speaker_names': True,
                'confidence_scores': False
            },
            'notification_settings': {
                'email_summaries': False,
                'action_items': True,
                'decisions': True
            },
            'search_preferences': {
                'default_type': 'hybrid',
                'results_per_page': 20,
                'highlight_keywords': True
            }
        }
        
        # Context retention settings
        self.context_retention_days = 30
        self.max_conversation_history = 100
    
    async def get_user_memory(self, user_id: int) -> Dict[str, Any]:
        """Get all memory data for a user"""
        memory_file = self.memory_dir / f"user_{user_id}.json"
        
        if memory_file.exists():
            try:
                with open(memory_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading user memory for {user_id}: {e}")
        
        # Return default structure
        return {
            'preferences': self.default_preferences.copy(),
            'conversation_history': [],
            'project_context': {},
            'learned_patterns': {},
            'last_updated': datetime.utcnow().isoformat()
        }
    
    async def update_preferences(self, user_id: int, preferences: Dict[str, Any]) -> bool:
        """Update user preferences"""
        try:
            memory = await self.get_user_memory(user_id)
            
            # Deep merge preferences
            memory['preferences'] = self._deep_merge(
                memory['preferences'], preferences
            )
            memory['last_updated'] = datetime.utcnow().isoformat()
            
            # Save to file
            memory_file = self.memory_dir / f"user_{user_id}.json"
            with open(memory_file, 'w') as f:
                json.dump(memory, f, indent=2)
            
            logger.info(f"Updated preferences for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating preferences for user {user_id}: {e}")
            return False
    
    async def add_conversation(self, user_id: int, query: str, 
                             response: str, context: Dict[str, Any]) -> bool:
        """Add a conversation to user's history"""
        try:
            memory = await self.get_user_memory(user_id)
            
            # Add new conversation
            conversation = {
                'timestamp': datetime.utcnow().isoformat(),
                'query': query,
                'response': response[:500],  # Truncate long responses
                'context': context,
                'session_ids': context.get('session_ids', [])
            }
            
            memory['conversation_history'].insert(0, conversation)
            
            # Limit history size
            memory['conversation_history'] = memory['conversation_history'][:self.max_conversation_history]
            
            # Clean old conversations
            cutoff_date = datetime.utcnow() - timedelta(days=self.context_retention_days)
            memory['conversation_history'] = [
                conv for conv in memory['conversation_history']
                if datetime.fromisoformat(conv['timestamp']) > cutoff_date
            ]
            
            # Update patterns
            await self._update_learned_patterns(memory, query, context)
            
            memory['last_updated'] = datetime.utcnow().isoformat()
            
            # Save to file
            memory_file = self.memory_dir / f"user_{user_id}.json"
            with open(memory_file, 'w') as f:
                json.dump(memory, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding conversation for user {user_id}: {e}")
            return False
    
    async def update_project_context(self, user_id: int, project: str, 
                                   context: Dict[str, Any]) -> bool:
        """Update project-specific context for a user"""
        try:
            memory = await self.get_user_memory(user_id)
            
            if 'project_context' not in memory:
                memory['project_context'] = {}
            
            if project not in memory['project_context']:
                memory['project_context'][project] = {
                    'created': datetime.utcnow().isoformat(),
                    'data': {}
                }
            
            memory['project_context'][project]['data'].update(context)
            memory['project_context'][project]['last_accessed'] = datetime.utcnow().isoformat()
            memory['last_updated'] = datetime.utcnow().isoformat()
            
            # Save to file
            memory_file = self.memory_dir / f"user_{user_id}.json"
            with open(memory_file, 'w') as f:
                json.dump(memory, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating project context for user {user_id}: {e}")
            return False
    
    async def _update_learned_patterns(self, memory: Dict[str, Any], 
                                     query: str, context: Dict[str, Any]):
        """Update learned patterns from user interactions"""
        if 'learned_patterns' not in memory:
            memory['learned_patterns'] = {}
        
        patterns = memory['learned_patterns']
        
        # Track query types
        if 'query_types' not in patterns:
            patterns['query_types'] = defaultdict(int)
        
        # Simple query classification
        query_lower = query.lower()
        if any(word in query_lower for word in ['decision', 'decide', 'agreed']):
            patterns['query_types']['decisions'] += 1
        elif any(word in query_lower for word in ['action', 'todo', 'task']):
            patterns['query_types']['action_items'] += 1
        elif any(word in query_lower for word in ['who', 'person', 'speaker']):
            patterns['query_types']['people'] += 1
        elif any(word in query_lower for word in ['when', 'date', 'time']):
            patterns['query_types']['temporal'] += 1
        else:
            patterns['query_types']['general'] += 1
        
        # Track frequently accessed sessions
        if 'frequent_sessions' not in patterns:
            patterns['frequent_sessions'] = defaultdict(int)
        
        for session_id in context.get('session_ids', []):
            patterns['frequent_sessions'][session_id] += 1
        
        # Track topic interests
        if 'topic_interests' not in patterns:
            patterns['topic_interests'] = defaultdict(int)
        
        # Extract topics from query
        topics = context.get('topics', [])
        for topic in topics:
            patterns['topic_interests'][topic] += 1
    
    def _deep_merge(self, base: Dict, updates: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result


class MeetingIntelligenceSystem:
    """Unified system combining organizational knowledge with personal memory"""
    
    def __init__(self):
        self.personal_memory = PersonalMemory()
        self.cache_dir = Path("storage/intelligence_cache")
        self.cache_dir.mkdir(exist_ok=True)
    
    async def handle_user_query(self, user: User, query: str, 
                              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle user query with both organizational knowledge and personal memory
        
        Returns a response that combines:
        - Meeting knowledge (filtered by permissions)
        - Personal context and preferences
        - Intelligent formatting based on user preferences
        """
        try:
            # Get user's personal memory
            user_memory = await self.personal_memory.get_user_memory(user.id)
            user_preferences = user_memory.get('preferences', {})
            
            # Get accessible sessions
            accessible_sessions = await search_service.get_user_accessible_sessions(user)
            
            # Determine search type based on user preferences and query
            search_type = await self._determine_search_type(query, user_preferences)
            
            # Perform search with user context
            search_results = await search_service.hybrid_search(
                query=query,
                user=user,
                search_type=search_type,
                limit=user_preferences.get('search_preferences', {}).get('results_per_page', 20)
            )
            
            # Build context-aware response
            response = await self._build_intelligent_response(
                query=query,
                search_results=search_results,
                user_memory=user_memory,
                user=user
            )
            
            # Update conversation history
            await self.personal_memory.add_conversation(
                user_id=user.id,
                query=query,
                response=response['summary'],
                context={
                    'search_type': search_type,
                    'result_count': len(search_results.get('results', [])),
                    'session_ids': list(set([
                        r.get('session_id') for r in search_results.get('results', [])
                        if r.get('session_id')
                    ])),
                    'topics': response.get('identified_topics', [])
                }
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling user query: {e}")
            return {
                'error': f'Failed to process query: {e}',
                'query': query
            }
    
    async def _determine_search_type(self, query: str, preferences: Dict) -> str:
        """Intelligently determine the best search type for the query"""
        query_lower = query.lower()
        
        # Check for explicit search type indicators
        if any(word in query_lower for word in ['similar', 'like', 'related']):
            return 'semantic'
        elif any(word in query_lower for word in ['exact', 'quote', 'said']):
            return 'keyword'
        elif any(word in query_lower for word in ['connected', 'relationship', 'who knows']):
            return 'graph'
        
        # Use user's default preference
        return preferences.get('search_preferences', {}).get('default_type', 'hybrid')
    
    async def _build_intelligent_response(self, query: str, search_results: Dict,
                                        user_memory: Dict, user: User) -> Dict[str, Any]:
        """Build an intelligent response based on user preferences and context"""
        preferences = user_memory.get('preferences', {})
        conversation_history = user_memory.get('conversation_history', [])
        
        # Extract key information
        results = search_results.get('combined') or search_results.get('results', [])
        
        # Build response structure
        response = {
            'query': query,
            'timestamp': datetime.utcnow().isoformat(),
            'user': user.username,
            'result_count': len(results),
            'search_type': search_results.get('search_type'),
            'accessible_sessions': search_results.get('accessible_sessions', 0)
        }
        
        # Generate summary based on style preference
        summary_style = preferences.get('summary_style', 'concise')
        
        if not results:
            response['summary'] = self._generate_no_results_message(query, conversation_history)
        else:
            response['summary'] = await self._generate_summary(
                results, query, summary_style, preferences
            )
        
        # Extract key insights
        response['key_insights'] = await self._extract_key_insights(results, query)
        
        # Identify topics
        response['identified_topics'] = await self._identify_topics(results)
        
        # Extract action items if user prefers
        if preferences.get('notification_settings', {}).get('action_items', True):
            response['action_items'] = await self._extract_action_items(results)
        
        # Extract decisions if user prefers
        if preferences.get('notification_settings', {}).get('decisions', True):
            response['decisions'] = await self._extract_decisions(results)
        
        # Add personalized recommendations
        response['recommendations'] = await self._generate_recommendations(
            query, results, user_memory
        )
        
        # Format response based on user preferences
        response['formatted_response'] = self._format_response(response, preferences)
        
        return response
    
    def _generate_no_results_message(self, query: str, history: List[Dict]) -> str:
        """Generate helpful message when no results found"""
        message = f"I couldn't find any results for '{query}' in your accessible meetings."
        
        # Check if user has searched similar queries before
        similar_queries = [
            h['query'] for h in history[-10:]  # Last 10 queries
            if any(word in h['query'].lower() for word in query.lower().split())
        ]
        
        if similar_queries:
            message += f"\n\nYou previously searched for: {', '.join(similar_queries[:3])}"
        
        message += "\n\nTry:\n- Using different keywords\n- Checking the date range\n- Using semantic search for conceptual matches"
        
        return message
    
    async def _generate_summary(self, results: List[Dict], query: str, 
                              style: str, preferences: Dict) -> str:
        """Generate summary based on user's preferred style"""
        if style == 'bullet-points':
            summary_parts = [f"Found {len(results)} results for '{query}':\n"]
            
            for i, result in enumerate(results[:5]):  # Top 5 results
                if result.get('text'):
                    text = result['text'][:100] + '...' if len(result['text']) > 100 else result['text']
                    speaker = f" ({result.get('speaker_id', 'Unknown')})" if preferences.get('formatting', {}).get('speaker_names') else ""
                    summary_parts.append(f"• {text}{speaker}")
                elif result.get('name'):
                    summary_parts.append(f"• {result['node_type']}: {result['name']}")
            
            return '\n'.join(summary_parts)
        
        elif style == 'detailed':
            summary_parts = [f"Comprehensive results for '{query}':\n"]
            
            # Group by session
            by_session = defaultdict(list)
            for result in results:
                session_id = result.get('session_id', 'unknown')
                by_session[session_id].append(result)
            
            for session_id, session_results in list(by_session.items())[:3]:
                summary_parts.append(f"\nSession {session_id[-8:]}:")
                for result in session_results[:3]:
                    if result.get('text'):
                        summary_parts.append(f"  - {result['text'][:150]}...")
            
            return '\n'.join(summary_parts)
        
        else:  # concise
            if results:
                top_result = results[0]
                text = top_result.get('text', top_result.get('name', 'No content'))
                return f"Found {len(results)} matches. Top result: '{text[:200]}...'"
            return "No results found."
    
    async def _extract_key_insights(self, results: List[Dict], query: str) -> List[str]:
        """Extract key insights from search results"""
        insights = []
        
        # Analyze result distribution
        result_types = defaultdict(int)
        speakers = defaultdict(int)
        
        for result in results:
            if result.get('node_type'):
                result_types[result['node_type']] += 1
            if result.get('speaker_id'):
                speakers[result['speaker_id']] += 1
        
        # Generate insights
        if result_types:
            most_common_type = max(result_types.items(), key=lambda x: x[1])
            insights.append(f"Most results are {most_common_type[0].replace('_', ' ')}s ({most_common_type[1]} occurrences)")
        
        if len(speakers) > 1:
            top_speaker = max(speakers.items(), key=lambda x: x[1])
            insights.append(f"{top_speaker[0]} mentioned this topic most frequently ({top_speaker[1]} times)")
        
        # Time-based insights
        if any(r.get('start_time') for r in results):
            time_spans = [r.get('start_time', 0) for r in results if r.get('start_time')]
            if time_spans:
                insights.append(f"Discussions span {len(set(r.get('session_id') for r in results))} different meetings")
        
        return insights
    
    async def _identify_topics(self, results: List[Dict]) -> List[str]:
        """Identify main topics from results"""
        topics = set()
        
        for result in results:
            # Extract from node properties
            if result.get('properties', {}).get('category'):
                topics.add(result['properties']['category'])
            
            # Extract from text using simple keyword matching
            if result.get('text'):
                text_lower = result['text'].lower()
                for category, keywords in knowledge_graph.topic_keywords.items():
                    if any(keyword in text_lower for keyword in keywords):
                        topics.add(category)
        
        return list(topics)[:5]  # Top 5 topics
    
    async def _extract_action_items(self, results: List[Dict]) -> List[Dict]:
        """Extract action items from results"""
        action_items = []
        
        for result in results:
            if result.get('node_type') == 'action_item':
                action_items.append({
                    'description': result.get('name', ''),
                    'session_id': result.get('session_id'),
                    'assigned_to': result.get('properties', {}).get('speaker'),
                    'status': result.get('properties', {}).get('status', 'pending')
                })
        
        return action_items
    
    async def _extract_decisions(self, results: List[Dict]) -> List[Dict]:
        """Extract decisions from results"""
        decisions = []
        
        for result in results:
            if result.get('node_type') == 'decision':
                decisions.append({
                    'description': result.get('name', ''),
                    'session_id': result.get('session_id'),
                    'made_by': result.get('properties', {}).get('speaker'),
                    'timestamp': result.get('properties', {}).get('timestamp')
                })
        
        return decisions
    
    async def _generate_recommendations(self, query: str, results: List[Dict], 
                                      user_memory: Dict) -> List[str]:
        """Generate personalized recommendations"""
        recommendations = []
        
        # Based on query patterns
        patterns = user_memory.get('learned_patterns', {})
        query_types = patterns.get('query_types', {})
        
        if query_types.get('decisions', 0) > query_types.get('action_items', 0):
            recommendations.append("You frequently search for decisions. Consider setting up decision tracking.")
        
        # Based on frequent sessions
        frequent_sessions = patterns.get('frequent_sessions', {})
        if frequent_sessions:
            top_session = max(frequent_sessions.items(), key=lambda x: x[1])[0]
            recommendations.append(f"You often reference session {top_session[-8:]}. Would you like to bookmark it?")
        
        # Based on result quality
        if results and all(r.get('score', 0) < 0.5 for r in results[:5]):
            recommendations.append("Results have low confidence. Try rephrasing your query or using different keywords.")
        
        return recommendations[:3]  # Limit recommendations
    
    def _format_response(self, response: Dict, preferences: Dict) -> str:
        """Format the complete response based on user preferences"""
        formatted_parts = []
        
        # Summary is always included
        formatted_parts.append(response['summary'])
        
        # Add insights if available
        if response.get('key_insights'):
            formatted_parts.append("\n📊 Key Insights:")
            for insight in response['key_insights']:
                formatted_parts.append(f"  • {insight}")
        
        # Add action items if requested and available
        if response.get('action_items'):
            formatted_parts.append("\n📋 Action Items:")
            for item in response['action_items'][:5]:
                assignee = f" → {item['assigned_to']}" if item.get('assigned_to') else ""
                formatted_parts.append(f"  • {item['description']}{assignee}")
        
        # Add decisions if requested and available
        if response.get('decisions'):
            formatted_parts.append("\n✅ Decisions:")
            for decision in response['decisions'][:5]:
                formatted_parts.append(f"  • {decision['description']}")
        
        # Add recommendations
        if response.get('recommendations'):
            formatted_parts.append("\n💡 Recommendations:")
            for rec in response['recommendations']:
                formatted_parts.append(f"  • {rec}")
        
        return '\n'.join(formatted_parts)


# Global instance
meeting_intelligence = MeetingIntelligenceSystem()