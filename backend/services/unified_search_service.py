"""
Unified Search Service

Combines semantic search, full-text search, and graph-based search
to provide comprehensive meeting intelligence capabilities.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Set
from datetime import datetime
from collections import defaultdict
import re

from database.database import get_db
from database.models import RecordingSession, Transcription
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text
from services.embedding_service import embedding_service
from services.knowledge_graph_service import knowledge_graph
from auth.models import User

logger = logging.getLogger(__name__)

class UnifiedSearchService:
    """Unified search service combining multiple search strategies"""
    
    def __init__(self):
        self.search_weights = {
            'semantic': 0.4,
            'keyword': 0.3,
            'graph': 0.3
        }
        
        # Initialize full-text search
        self._ensure_fts_table()
    
    def _ensure_fts_table(self):
        """Ensure FTS table exists for full-text search"""
        try:
            db = next(get_db())
            
            # Create FTS table for transcriptions
            db.execute(text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS transcriptions_fts USING fts5(
                    session_id, text, speaker_id, start_time, end_time
                )
            """))
            
            # Create trigger to keep FTS in sync
            db.execute(text("""
                CREATE TRIGGER IF NOT EXISTS transcriptions_fts_insert 
                AFTER INSERT ON transcriptions BEGIN
                    INSERT INTO transcriptions_fts(
                        session_id, text, speaker_id, start_time, end_time
                    ) VALUES (
                        new.session_id, new.text, new.speaker_id, 
                        new.start_time, new.end_time
                    );
                END
            """))
            
            db.execute(text("""
                CREATE TRIGGER IF NOT EXISTS transcriptions_fts_update 
                AFTER UPDATE ON transcriptions BEGIN
                    UPDATE transcriptions_fts SET
                        text = new.text,
                        speaker_id = new.speaker_id,
                        start_time = new.start_time,
                        end_time = new.end_time
                    WHERE rowid = new.id;
                END
            """))
            
            db.execute(text("""
                CREATE TRIGGER IF NOT EXISTS transcriptions_fts_delete 
                AFTER DELETE ON transcriptions BEGIN
                    DELETE FROM transcriptions_fts WHERE rowid = old.id;
                END
            """))
            
            db.commit()
            logger.info("FTS table and triggers initialized")
            
        except Exception as e:
            logger.error(f"Error initializing FTS table: {e}")
        finally:
            if 'db' in locals():
                db.close()
    
    async def get_user_accessible_sessions(self, user: User) -> List[str]:
        """Get list of session IDs accessible to the user"""
        try:
            # For now, implement basic access control
            # In production, this would check user permissions, team membership, etc.
            
            db = next(get_db())
            
            if user.role in ['admin', 'superuser']:
                # Admins can access all sessions
                sessions = db.query(RecordingSession.session_id).all()
                return [s[0] for s in sessions]
            
            else:
                # Regular users can access sessions they participated in
                # This is a simplified implementation
                sessions = db.query(RecordingSession.session_id).filter(
                    RecordingSession.settings.like(f'%{user.username}%')
                ).all()
                
                # Also add sessions created by them (if we track creator)
                return [s[0] for s in sessions]
            
        except Exception as e:
            logger.error(f"Error getting accessible sessions for user {user.username}: {e}")
            return []
        finally:
            if 'db' in locals():
                db.close()
    
    async def hybrid_search(self, query: str, user: User, 
                           search_type: str = 'hybrid',
                           date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None,
                           speakers: Optional[List[str]] = None,
                           limit: int = 20) -> Dict[str, Any]:
        """Perform hybrid search combining multiple strategies"""
        
        # Get user's accessible sessions
        user_sessions = await self.get_user_accessible_sessions(user)
        if not user_sessions:
            return {
                'results': [],
                'query': query,
                'search_type': search_type,
                'message': 'No accessible sessions found'
            }
        
        # Apply filters
        filtered_sessions = await self._apply_filters(
            user_sessions, date_from, date_to, speakers
        )
        
        results = {}
        
        try:
            # Run different search strategies based on type
            if search_type in ['hybrid', 'semantic']:
                results['semantic'] = await self._semantic_search(
                    query, filtered_sessions, limit
                )
            
            if search_type in ['hybrid', 'keyword']:
                results['keyword'] = await self._keyword_search(
                    query, filtered_sessions, limit
                )
            
            if search_type in ['hybrid', 'graph']:
                results['graph'] = await self._graph_search(
                    query, filtered_sessions, limit
                )
            
            # Combine results if hybrid search
            if search_type == 'hybrid' and len(results) > 1:
                results['combined'] = await self._combine_results(results, query, limit)
            
            # Add metadata
            results['query'] = query
            results['search_type'] = search_type
            results['accessible_sessions'] = len(filtered_sessions)
            results['total_sessions'] = len(user_sessions)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            return {
                'error': f'Search failed: {e}',
                'query': query,
                'search_type': search_type
            }
    
    async def _apply_filters(self, sessions: List[str], 
                           date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None,
                           speakers: Optional[List[str]] = None) -> List[str]:
        """Apply date and speaker filters to sessions"""
        if not any([date_from, date_to, speakers]):
            return sessions
        
        try:
            db = next(get_db())
            
            # Build filter conditions
            conditions = ["session_id IN ({})".format(','.join(['?' for _ in sessions]))]
            params = sessions.copy()
            
            if date_from:
                conditions.append("start_time >= ?")
                params.append(date_from)
            
            if date_to:
                conditions.append("start_time <= ?")
                params.append(date_to)
            
            query = f"SELECT DISTINCT session_id FROM recording_sessions WHERE {' AND '.join(conditions)}"
            
            cursor = db.execute(query, params)
            filtered_sessions = [row[0] for row in cursor.fetchall()]
            
            # Apply speaker filter if specified
            if speakers and filtered_sessions:
                speaker_conditions = ["session_id IN ({})".format(','.join(['?' for _ in filtered_sessions]))]
                speaker_params = filtered_sessions.copy()
                
                speaker_filter = " OR ".join([f"speaker_id LIKE ?" for _ in speakers])
                speaker_conditions.append(f"({speaker_filter})")
                speaker_params.extend([f"%{speaker}%" for speaker in speakers])
                
                speaker_query = f"SELECT DISTINCT session_id FROM transcriptions WHERE {' AND '.join(speaker_conditions)}"
                cursor = db.execute(speaker_query, speaker_params)
                filtered_sessions = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"Filtered {len(sessions)} sessions to {len(filtered_sessions)}")
            return filtered_sessions
            
        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            return sessions
        finally:
            if 'db' in locals():
                db.close()
    
    async def _semantic_search(self, query: str, sessions: List[str], 
                              limit: int) -> List[Dict]:
        """Perform semantic search using embeddings"""
        try:
            results = await embedding_service.semantic_search(
                query=query,
                user_sessions=sessions,
                limit=limit
            )
            
            # Enhance results with session metadata
            enhanced_results = []
            for result in results:
                enhanced_result = result.copy()
                enhanced_result['search_method'] = 'semantic'
                enhanced_result['score'] = result['similarity']
                enhanced_results.append(enhanced_result)
            
            logger.info(f"Semantic search returned {len(enhanced_results)} results")
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    async def _keyword_search(self, query: str, sessions: List[str], 
                             limit: int) -> List[Dict]:
        """Perform full-text keyword search"""
        try:
            db = next(get_db())
            
            # Prepare FTS query
            # Clean and format query for FTS
            clean_query = re.sub(r'[^\w\s]', ' ', query)
            fts_query = ' OR '.join([f'"{word}"' for word in clean_query.split() if len(word) > 2])
            
            if not fts_query:
                return []
            
            # Build session filter
            session_filter = ""
            params = [fts_query]
            
            if sessions:
                placeholders = ','.join(['?' for _ in sessions])
                session_filter = f" AND session_id IN ({placeholders})"
                params.extend(sessions)
            
            # Execute FTS search
            cursor = db.execute(f"""
                SELECT session_id, text, speaker_id, start_time, end_time,
                       rank, snippet(transcriptions_fts, 1, '<mark>', '</mark>', '...', 32) as snippet
                FROM transcriptions_fts
                WHERE transcriptions_fts MATCH ?
                {session_filter}
                ORDER BY rank
                LIMIT ?
            """, params + [limit])
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'session_id': row[0],
                    'text': row[1],
                    'speaker_id': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'rank': row[5],
                    'snippet': row[6],
                    'search_method': 'keyword',
                    'score': 1.0 / (row[5] + 1) if row[5] else 1.0  # Convert rank to score
                })
            
            logger.info(f"Keyword search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in keyword search: {e}")
            return []
        finally:
            if 'db' in locals():
                db.close()
    
    async def _graph_search(self, query: str, sessions: List[str], 
                           limit: int) -> Dict[str, Any]:
        """Perform graph-based search"""
        try:
            graph_results = await knowledge_graph.graph_search(
                query=query,
                user_sessions=sessions,
                k=limit
            )
            
            # Convert graph results to standard format
            results = []
            for node in graph_results.get('nodes', []):
                results.append({
                    'node_id': node['node_id'],
                    'node_type': node['node_type'],
                    'name': node['name'],
                    'properties': node['properties'],
                    'similarity': node['similarity'],
                    'search_method': 'graph',
                    'score': node['similarity']
                })
            
            graph_results['results'] = results
            logger.info(f"Graph search returned {len(results)} node results")
            return graph_results
            
        except Exception as e:
            logger.error(f"Error in graph search: {e}")
            return {'results': [], 'context': f'Graph search error: {e}'}
    
    async def _combine_results(self, all_results: Dict[str, Any], 
                              query: str, limit: int) -> List[Dict]:
        """Combine and rank results from different search methods"""
        try:
            combined = []
            
            # Collect all results with method-specific scoring
            for method, method_results in all_results.items():
                if method in ['semantic', 'keyword']:
                    for result in method_results:
                        result_copy = result.copy()
                        result_copy['weighted_score'] = result['score'] * self.search_weights.get(method, 1.0)
                        combined.append(result_copy)
                
                elif method == 'graph':
                    for result in method_results.get('results', []):
                        result_copy = result.copy()
                        result_copy['weighted_score'] = result['score'] * self.search_weights.get(method, 1.0)
                        combined.append(result_copy)
            
            # Remove duplicates and merge scores
            unique_results = {}
            
            for result in combined:
                # Create a unique key based on content
                if 'session_id' in result and 'text' in result:
                    key = f"{result['session_id']}_{hash(result['text']) % 10000}"
                elif 'node_id' in result:
                    key = result['node_id']
                else:
                    key = str(hash(str(result)) % 10000)
                
                if key in unique_results:
                    # Merge scores (take maximum)
                    unique_results[key]['weighted_score'] = max(
                        unique_results[key]['weighted_score'],
                        result['weighted_score']
                    )
                    # Combine search methods
                    methods = unique_results[key].get('search_methods', [unique_results[key].get('search_method')])
                    if result.get('search_method') not in methods:
                        methods.append(result.get('search_method'))
                    unique_results[key]['search_methods'] = methods
                else:
                    unique_results[key] = result
                    unique_results[key]['search_methods'] = [result.get('search_method')]
            
            # Sort by weighted score and limit
            final_results = sorted(
                unique_results.values(),
                key=lambda x: x['weighted_score'],
                reverse=True
            )[:limit]
            
            logger.info(f"Combined search returned {len(final_results)} unique results")
            return final_results
            
        except Exception as e:
            logger.error(f"Error combining results: {e}")
            return []
    
    async def index_session(self, session_id: str) -> bool:
        """Index a session for search (embeddings + FTS + graph)"""
        try:
            # Index embeddings
            embedding_success = await embedding_service.index_session(session_id)
            
            # Build knowledge graph
            graph_success = await knowledge_graph.build_session_graph(session_id)
            
            # FTS is automatically updated via triggers
            
            success = embedding_success and graph_success
            logger.info(f"Session {session_id} indexing: embeddings={embedding_success}, graph={graph_success}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error indexing session {session_id}: {e}")
            return False
    
    async def search_suggestions(self, partial_query: str, user: User, 
                               limit: int = 5) -> List[str]:
        """Get search suggestions based on partial query"""
        try:
            suggestions = []
            
            # Get common terms from transcriptions
            user_sessions = await self.get_user_accessible_sessions(user)
            if not user_sessions:
                return suggestions
            
            db = next(get_db())
            
            # Find words that start with the partial query
            cursor = db.execute("""
                SELECT DISTINCT LOWER(word) as word, COUNT(*) as frequency
                FROM (
                    SELECT unnest(string_to_array(LOWER(text), ' ')) as word
                    FROM transcriptions
                    WHERE session_id = ANY(?)
                ) words
                WHERE word LIKE ? AND LENGTH(word) > 3
                GROUP BY LOWER(word)
                ORDER BY frequency DESC
                LIMIT ?
            """, (user_sessions, f"{partial_query.lower()}%", limit))
            
            suggestions = [row[0] for row in cursor.fetchall()]
            
            # Add topic-based suggestions
            for category, keywords in knowledge_graph.topic_keywords.items():
                for keyword in keywords:
                    if keyword.startswith(partial_query.lower()) and keyword not in suggestions:
                        suggestions.append(keyword)
                        if len(suggestions) >= limit:
                            break
                if len(suggestions) >= limit:
                    break
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return []
        finally:
            if 'db' in locals():
                db.close()
    
    async def get_search_stats(self, user: User) -> Dict[str, Any]:
        """Get search statistics for the user"""
        try:
            user_sessions = await self.get_user_accessible_sessions(user)
            
            db = next(get_db())
            
            stats = {
                'accessible_sessions': len(user_sessions),
                'indexed_sessions': 0,
                'total_chunks': 0,
                'graph_nodes': 0,
                'graph_edges': 0
            }
            
            if user_sessions:
                # Count indexed sessions
                placeholders = ','.join(['?' for _ in user_sessions])
                
                cursor = db.execute(f"""
                    SELECT COUNT(DISTINCT session_id) 
                    FROM meeting_embeddings 
                    WHERE session_id IN ({placeholders})
                """, user_sessions)
                stats['indexed_sessions'] = cursor.fetchone()[0]
                
                # Count chunks
                cursor = db.execute(f"""
                    SELECT COUNT(*) 
                    FROM meeting_embeddings 
                    WHERE session_id IN ({placeholders})
                """, user_sessions)
                stats['total_chunks'] = cursor.fetchone()[0]
                
                # Count graph nodes and edges
                session_nodes = [f"session_{sid}" for sid in user_sessions]
                node_placeholders = ','.join(['?' for _ in session_nodes])
                
                cursor = db.execute(f"""
                    SELECT COUNT(*) FROM graph_nodes 
                    WHERE node_id IN ({node_placeholders})
                    OR node_id IN (
                        SELECT source_id FROM graph_edges 
                        WHERE target_id IN ({node_placeholders})
                    )
                """, session_nodes * 2)
                stats['graph_nodes'] = cursor.fetchone()[0]
                
                cursor = db.execute(f"""
                    SELECT COUNT(*) FROM graph_edges 
                    WHERE source_id IN ({node_placeholders})
                    OR target_id IN ({node_placeholders})
                """, session_nodes * 2)
                stats['graph_edges'] = cursor.fetchone()[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting search stats: {e}")
            return {'error': f'Failed to get stats: {e}'}
        finally:
            if 'db' in locals():
                db.close()


# Global instance
search_service = UnifiedSearchService()