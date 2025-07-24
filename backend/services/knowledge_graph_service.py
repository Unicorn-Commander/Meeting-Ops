"""
Knowledge Graph Service for Meeting Intelligence

Builds and manages knowledge graphs from meeting transcriptions,
extracting entities like people, topics, decisions, and their relationships.
"""

import asyncio
import json
import logging
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path
import networkx as nx
import numpy as np
import pickle
import re
from collections import defaultdict, Counter

from database.database import get_db
from database.models import Session as RecordingSession, Transcription
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

class MeetingKnowledgeGraph:
    """Knowledge graph for meeting intelligence"""
    
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.cache_dir = Path("storage/graph")
        self.cache_dir.mkdir(exist_ok=True)
        
        # Entity extraction patterns
        self.decision_patterns = [
            r'we decided to\s+(.+?)(?:\.|$)',
            r'decision was\s+(.+?)(?:\.|$)',
            r'agreed to\s+(.+?)(?:\.|$)',
            r'conclusion is\s+(.+?)(?:\.|$)',
            r'we will\s+(.+?)(?:\.|$)',
            r'going to\s+(.+?)(?:\.|$)'
        ]
        
        self.action_patterns = [
            r'action item\s*:?\s*(.+?)(?:\.|$)',
            r'todo\s*:?\s*(.+?)(?:\.|$)', 
            r'need to\s+(.+?)(?:\.|$)',
            r'should\s+(.+?)(?:\.|$)',
            r'must\s+(.+?)(?:\.|$)',
            r'will follow up\s+(.+?)(?:\.|$)'
        ]
        
        self.topic_keywords = {
            'technical': ['api', 'database', 'server', 'code', 'bug', 'feature', 'system', 'architecture', 'performance'],
            'business': ['revenue', 'customer', 'market', 'sales', 'strategy', 'budget', 'profit', 'growth'],
            'project': ['deadline', 'milestone', 'sprint', 'release', 'timeline', 'scope', 'deliverable'],
            'team': ['hiring', 'training', 'performance', 'feedback', 'team', 'role', 'responsibility'],
            'product': ['feature', 'requirement', 'user', 'feedback', 'design', 'testing', 'launch'],
            'meeting': ['agenda', 'meeting', 'discussion', 'presentation', 'review', 'sync', 'standup']
        }
    
    async def build_session_graph(self, session_id: str) -> bool:
        """Extract entities and build graph from session"""
        try:
            db = next(get_db())
            
            # Get session data
            session = db.query(RecordingSession).filter_by(session_id=session_id).first()
            if not session:
                logger.error(f"Session {session_id} not found")
                return False
            
            # Add session node
            session_node = f"session_{session_id}"
            self.graph.add_node(
                session_node,
                type='session',
                title=session.title,
                date=session.start_time.isoformat() if session.start_time else None,
                session_id=session_id,
                properties={
                    'duration': (session.end_time - session.start_time).total_seconds() 
                               if session.end_time and session.start_time else 0,
                    'status': session.status
                }
            )
            
            # Get transcript segments
            segments = db.query(Transcription).filter_by(
                session_id=session_id
            ).order_by(Transcription.start_time).all()
            
            if not segments:
                logger.warning(f"No transcripts found for session {session_id}")
                return False
            
            # Extract and add entities
            await self._extract_speakers(session_node, segments)
            await self._extract_topics(session_node, segments)
            await self._extract_decisions(session_node, segments)
            await self._extract_action_items(session_node, segments)
            
            # Save graph to cache
            await self._cache_session_graph(session_id)
            
            # Update database
            await self._persist_graph_to_db(session_id, db)
            
            logger.info(f"Built knowledge graph for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error building graph for session {session_id}: {e}")
            return False
        finally:
            if 'db' in locals():
                db.close()
    
    async def _extract_speakers(self, session_node: str, segments: List[Transcription]):
        """Extract speaker entities and relationships"""
        speakers = {}
        
        for segment in segments:
            speaker_id = segment.speaker_id or "unknown"
            
            if speaker_id not in speakers:
                speakers[speaker_id] = {
                    'segments': [],
                    'total_time': 0,
                    'word_count': 0
                }
            
            speakers[speaker_id]['segments'].append(segment)
            speakers[speaker_id]['word_count'] += len(segment.text.split())
            
            if segment.end_time and segment.start_time:
                speakers[speaker_id]['total_time'] += segment.end_time - segment.start_time
        
        # Add speaker nodes
        for speaker_id, data in speakers.items():
            person_node = f"person_{speaker_id}"
            
            self.graph.add_node(
                person_node,
                type='person',
                name=speaker_id,
                properties={
                    'total_speaking_time': data['total_time'],
                    'word_count': data['word_count'],
                    'segment_count': len(data['segments'])
                }
            )
            
            # Connect person to session
            self.graph.add_edge(
                person_node, session_node,
                type='attended',
                weight=data['total_time'],
                properties={
                    'speaking_time': data['total_time'],
                    'contribution': data['word_count']
                }
            )
    
    async def _extract_topics(self, session_node: str, segments: List[Transcription]):
        """Extract topic entities using keyword analysis"""
        # Combine all text
        full_text = ' '.join([s.text.lower() for s in segments])
        words = full_text.split()
        
        # Count topic keywords
        topic_scores = defaultdict(int)
        topic_contexts = defaultdict(list)
        
        for category, keywords in self.topic_keywords.items():
            for keyword in keywords:
                count = full_text.count(keyword)
                if count > 0:
                    topic_scores[category] += count
                    
                    # Find context around keyword
                    for segment in segments:
                        if keyword in segment.text.lower():
                            topic_contexts[category].append({
                                'text': segment.text,
                                'speaker': segment.speaker_id,
                                'time': segment.start_time
                            })
        
        # Add significant topics as nodes
        for topic, score in topic_scores.items():
            if score >= 2:  # Minimum threshold
                topic_node = f"topic_{topic}"
                
                if not self.graph.has_node(topic_node):
                    self.graph.add_node(
                        topic_node,
                        type='topic',
                        name=topic,
                        properties={
                            'category': topic,
                            'total_mentions': score
                        }
                    )
                
                # Connect topic to session
                self.graph.add_edge(
                    session_node, topic_node,
                    type='discussed',
                    weight=score,
                    properties={
                        'mention_count': score,
                        'contexts': topic_contexts[topic][:5]  # Top 5 contexts
                    }
                )
    
    async def _extract_decisions(self, session_node: str, segments: List[Transcription]):
        """Extract decision entities"""
        decisions = []
        
        for segment in segments:
            text = segment.text.lower()
            
            for pattern in self.decision_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    decisions.append({
                        'text': match.strip(),
                        'context': segment.text,
                        'speaker': segment.speaker_id,
                        'timestamp': segment.start_time,
                        'segment_id': segment.id
                    })
        
        # Add decision nodes
        for i, decision in enumerate(decisions):
            decision_node = f"decision_{session_node}_{i}"
            
            self.graph.add_node(
                decision_node,
                type='decision',
                description=decision['text'],
                properties={
                    'full_context': decision['context'],
                    'speaker': decision['speaker'],
                    'timestamp': decision['timestamp'],
                    'confidence': 0.8  # Simple confidence score
                }
            )
            
            # Connect decision to session
            self.graph.add_edge(
                session_node, decision_node,
                type='decided',
                weight=1.0
            )
            
            # Connect decision to speaker if known
            if decision['speaker']:
                speaker_node = f"person_{decision['speaker']}"
                if self.graph.has_node(speaker_node):
                    self.graph.add_edge(
                        speaker_node, decision_node,
                        type='proposed',
                        weight=1.0
                    )
    
    async def _extract_action_items(self, session_node: str, segments: List[Transcription]):
        """Extract action item entities"""
        action_items = []
        
        for segment in segments:
            text = segment.text.lower()
            
            for pattern in self.action_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    action_items.append({
                        'text': match.strip(),
                        'context': segment.text,
                        'speaker': segment.speaker_id,
                        'timestamp': segment.start_time,
                        'segment_id': segment.id
                    })
        
        # Add action item nodes
        for i, action in enumerate(action_items):
            action_node = f"action_{session_node}_{i}"
            
            self.graph.add_node(
                action_node,
                type='action_item',
                description=action['text'],
                properties={
                    'full_context': action['context'],
                    'speaker': action['speaker'],
                    'timestamp': action['timestamp'],
                    'status': 'pending'
                }
            )
            
            # Connect action to session
            self.graph.add_edge(
                session_node, action_node,
                type='generated_action',
                weight=1.0
            )
            
            # Connect action to speaker if known
            if action['speaker']:
                speaker_node = f"person_{action['speaker']}"
                if self.graph.has_node(speaker_node):
                    self.graph.add_edge(
                        action_node, speaker_node,
                        type='assigned_to',
                        weight=1.0
                    )
    
    async def _cache_session_graph(self, session_id: str):
        """Cache session graph to disk"""
        try:
            cache_file = self.cache_dir / f"session_{session_id}.json"
            
            # Extract session subgraph
            session_node = f"session_{session_id}"
            subgraph_nodes = {session_node}
            
            # Add all connected nodes
            for node in self.graph.neighbors(session_node):
                subgraph_nodes.add(node)
            for node in self.graph.predecessors(session_node):
                subgraph_nodes.add(node)
            
            subgraph = self.graph.subgraph(subgraph_nodes)
            
            # Convert to JSON-serializable format
            graph_data = nx.node_link_data(subgraph)
            
            with open(cache_file, 'w') as f:
                json.dump(graph_data, f, indent=2, default=str)
                
            logger.debug(f"Cached graph for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error caching graph for session {session_id}: {e}")
    
    async def _persist_graph_to_db(self, session_id: str, db: DBSession):
        """Persist graph nodes and edges to database"""
        try:
            # Create tables if not exist
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_type TEXT NOT NULL,
                    node_id TEXT UNIQUE NOT NULL,
                    name TEXT,
                    properties TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    session_id TEXT,
                    properties TEXT,
                    weight REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Get session subgraph
            session_node = f"session_{session_id}"
            subgraph_nodes = {session_node}
            
            for node in self.graph.neighbors(session_node):
                subgraph_nodes.add(node)
            for node in self.graph.predecessors(session_node):
                subgraph_nodes.add(node)
            
            # Insert nodes
            for node_id in subgraph_nodes:
                if self.graph.has_node(node_id):
                    node_data = self.graph.nodes[node_id]
                    
                    # Generate embedding for node
                    node_text = f"{node_data.get('name', '')} {node_data.get('description', '')}"
                    if node_text.strip():
                        embeddings = await embedding_service.generate_embeddings([node_text])
                        embedding_blob = pickle.dumps(embeddings[0]) if len(embeddings) > 0 else None
                    else:
                        embedding_blob = None
                    
                    db.execute("""
                        INSERT OR REPLACE INTO graph_nodes 
                        (node_type, node_id, name, properties, embedding)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        node_data.get('type', 'unknown'),
                        node_id,
                        node_data.get('name', node_data.get('description', '')),
                        json.dumps(node_data.get('properties', {})),
                        embedding_blob
                    ))
            
            # Insert edges
            for source, target, edge_data in self.graph.edges(data=True):
                if source in subgraph_nodes and target in subgraph_nodes:
                    db.execute("""
                        INSERT INTO graph_edges 
                        (source_id, target_id, edge_type, session_id, properties, weight)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        source,
                        target,
                        edge_data.get('type', 'related'),
                        session_id,
                        json.dumps(edge_data.get('properties', {})),
                        edge_data.get('weight', 1.0)
                    ))
            
            db.commit()
            logger.info(f"Persisted graph data for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error persisting graph for session {session_id}: {e}")
            db.rollback()
            raise
    
    async def graph_search(self, query: str, user_sessions: List[str] = None, 
                          k: int = 10) -> Dict[str, Any]:
        """GraphRAG search with NPU-accelerated embeddings"""
        try:
            # Generate query embedding
            query_embeddings = await embedding_service.generate_embeddings([query])
            if len(query_embeddings) == 0:
                return {'nodes': [], 'edges': [], 'context': ''}
            
            query_embedding = query_embeddings[0]
            
            db = next(get_db())
            
            # Build session filter
            session_filter = ""
            params = []
            
            if user_sessions:
                placeholders = ','.join(['?' for _ in user_sessions])
                session_filter = f"""
                    AND (node_id LIKE 'session_%' 
                         AND SUBSTR(node_id, 9) IN ({placeholders})
                         OR node_id IN (
                             SELECT source_id FROM graph_edges 
                             WHERE target_id LIKE 'session_%' 
                             AND SUBSTR(target_id, 9) IN ({placeholders})
                         )
                         OR node_id IN (
                             SELECT target_id FROM graph_edges 
                             WHERE source_id LIKE 'session_%' 
                             AND SUBSTR(source_id, 9) IN ({placeholders})
                         ))
                """
                params.extend(user_sessions * 3)
            
            # Find similar nodes
            cursor = db.execute(f"""
                SELECT node_id, node_type, name, properties, embedding
                FROM graph_nodes
                WHERE embedding IS NOT NULL {session_filter}
            """, params)
            
            node_scores = []
            
            for row in cursor.fetchall():
                try:
                    stored_embedding = pickle.loads(row[4])
                    similarity = np.dot(query_embedding, stored_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding) + 1e-8
                    )
                    
                    node_scores.append({
                        'node_id': row[0],
                        'node_type': row[1],
                        'name': row[2],
                        'properties': json.loads(row[3]) if row[3] else {},
                        'similarity': float(similarity)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing node embedding: {e}")
                    continue
            
            # Get top-k nodes
            node_scores.sort(key=lambda x: x['similarity'], reverse=True)
            top_nodes = node_scores[:k]
            
            if not top_nodes:
                return {'nodes': [], 'edges': [], 'context': 'No relevant nodes found'}
            
            # Extract subgraph around top nodes
            subgraph_nodes = set()
            for node in top_nodes:
                node_id = node['node_id']
                subgraph_nodes.add(node_id)
                
                # Add neighbors (1-hop)
                edge_cursor = db.execute("""
                    SELECT source_id, target_id FROM graph_edges 
                    WHERE source_id = ? OR target_id = ?
                """, (node_id, node_id))
                
                for edge_row in edge_cursor.fetchall():
                    subgraph_nodes.add(edge_row[0])
                    subgraph_nodes.add(edge_row[1])
            
            # Get all edges in subgraph
            edges = []
            if subgraph_nodes:
                placeholders = ','.join(['?' for _ in subgraph_nodes])
                edge_cursor = db.execute(f"""
                    SELECT source_id, target_id, edge_type, properties, weight
                    FROM graph_edges
                    WHERE source_id IN ({placeholders}) 
                    AND target_id IN ({placeholders})
                """, list(subgraph_nodes) * 2)
                
                for edge_row in edge_cursor.fetchall():
                    edges.append({
                        'source': edge_row[0],
                        'target': edge_row[1],
                        'type': edge_row[2],
                        'properties': json.loads(edge_row[3]) if edge_row[3] else {},
                        'weight': edge_row[4]
                    })
            
            # Build context from subgraph
            context = self._build_context_from_results(top_nodes, edges, query)
            
            return {
                'nodes': top_nodes,
                'edges': edges,
                'context': context,
                'query': query,
                'total_nodes': len(subgraph_nodes)
            }
            
        except Exception as e:
            logger.error(f"Error in graph search: {e}")
            return {'nodes': [], 'edges': [], 'context': f'Search error: {e}'}
        finally:
            if 'db' in locals():
                db.close()
    
    def _build_context_from_results(self, nodes: List[Dict], edges: List[Dict], 
                                   query: str) -> str:
        """Build natural language context from graph search results"""
        if not nodes:
            return "No relevant information found in the knowledge graph."
        
        context_parts = []
        
        # Group nodes by type
        node_types = defaultdict(list)
        for node in nodes:
            node_types[node['node_type']].append(node)
        
        # Build context for each type
        for node_type, type_nodes in node_types.items():
            if node_type == 'session':
                sessions = [n['name'] or n['node_id'] for n in type_nodes[:3]]
                context_parts.append(f"Found relevant information in sessions: {', '.join(sessions)}")
            
            elif node_type == 'decision':
                decisions = [n['name'][:100] + '...' if len(n['name']) > 100 else n['name'] 
                           for n in type_nodes[:3]]
                context_parts.append(f"Related decisions: {'; '.join(decisions)}")
            
            elif node_type == 'action_item':
                actions = [n['name'][:100] + '...' if len(n['name']) > 100 else n['name'] 
                         for n in type_nodes[:3]]
                context_parts.append(f"Related action items: {'; '.join(actions)}")
            
            elif node_type == 'topic':
                topics = [n['name'] for n in type_nodes[:5]]
                context_parts.append(f"Related topics: {', '.join(topics)}")
            
            elif node_type == 'person':
                people = [n['name'] for n in type_nodes[:5]]
                context_parts.append(f"Relevant people: {', '.join(people)}")
        
        return '\n'.join(context_parts) if context_parts else "Graph search completed but no specific context available."
    
    async def get_node_context(self, node_id: str, depth: int = 2, 
                              user_sessions: List[str] = None) -> Dict[str, Any]:
        """Get context around a specific node"""
        try:
            db = next(get_db())
            
            # Check if user has access to this node
            if user_sessions and node_id.startswith('session_'):
                session_id = node_id[8:]  # Remove 'session_' prefix
                if session_id not in user_sessions:
                    return {'error': 'Access denied to this session'}
            
            # Get the center node
            cursor = db.execute("""
                SELECT node_type, name, properties FROM graph_nodes WHERE node_id = ?
            """, (node_id,))
            
            center_row = cursor.fetchone()
            if not center_row:
                return {'error': 'Node not found'}
            
            center_node = {
                'node_id': node_id,
                'node_type': center_row[0],
                'name': center_row[1],
                'properties': json.loads(center_row[2]) if center_row[2] else {}
            }
            
            # Get connected nodes up to specified depth
            visited = set()
            current_level = {node_id}
            all_nodes = {node_id: center_node}
            all_edges = []
            
            for level in range(depth):
                next_level = set()
                
                for current_node in current_level:
                    if current_node in visited:
                        continue
                    visited.add(current_node)
                    
                    # Get connected nodes
                    edge_cursor = db.execute("""
                        SELECT source_id, target_id, edge_type, properties, weight
                        FROM graph_edges
                        WHERE source_id = ? OR target_id = ?
                    """, (current_node, current_node))
                    
                    for edge_row in edge_cursor.fetchall():
                        source, target = edge_row[0], edge_row[1]
                        
                        # Add edge
                        all_edges.append({
                            'source': source,
                            'target': target,
                            'type': edge_row[2],
                            'properties': json.loads(edge_row[3]) if edge_row[3] else {},
                            'weight': edge_row[4]
                        })
                        
                        # Add connected node to next level
                        connected_node = target if source == current_node else source
                        if connected_node not in all_nodes:
                            next_level.add(connected_node)
                
                # Get node data for next level
                if next_level:
                    placeholders = ','.join(['?' for _ in next_level])
                    node_cursor = db.execute(f"""
                        SELECT node_id, node_type, name, properties
                        FROM graph_nodes
                        WHERE node_id IN ({placeholders})
                    """, list(next_level))
                    
                    for node_row in node_cursor.fetchall():
                        all_nodes[node_row[0]] = {
                            'node_id': node_row[0],
                            'node_type': node_row[1],
                            'name': node_row[2],
                            'properties': json.loads(node_row[3]) if node_row[3] else {}
                        }
                
                current_level = next_level
            
            return {
                'center': center_node,
                'nodes': list(all_nodes.values()),
                'edges': all_edges,
                'stats': {
                    'total_nodes': len(all_nodes),
                    'total_edges': len(all_edges),
                    'depth': depth
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting node context for {node_id}: {e}")
            return {'error': f'Failed to get node context: {e}'}
        finally:
            if 'db' in locals():
                db.close()


# Global instance
knowledge_graph = MeetingKnowledgeGraph()