Looking at your impressive system architecture, I see you've already built a sophisticated platform with NPU acceleration, real-time transcription, and meeting management. Here's what I'd recommend for making your meetings searchable, incorporating both traditional search and GraphRAG:

## Enhanced Search Architecture for Your System

### 1. **Extend Your Database Schema**

```sql
-- Add to your existing schema
CREATE TABLE meeting_embeddings (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES recording_sessions(id),
    chunk_id VARCHAR(255) UNIQUE,
    chunk_text TEXT,
    chunk_type VARCHAR(50), -- 'transcript', 'summary', 'action_item'
    embedding BLOB, -- Store as binary for SQLite
    start_time FLOAT,
    end_time FLOAT,
    speaker_id VARCHAR(255),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge graph tables
CREATE TABLE graph_nodes (
    id INTEGER PRIMARY KEY,
    node_type VARCHAR(50), -- 'person', 'topic', 'decision', 'project'
    node_id VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    properties JSON,
    embedding BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE graph_edges (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES graph_nodes(id),
    target_id INTEGER REFERENCES graph_nodes(id),
    edge_type VARCHAR(50), -- 'discussed', 'decided', 'assigned_to'
    session_id INTEGER REFERENCES recording_sessions(id),
    properties JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search
CREATE VIRTUAL TABLE transcriptions_fts USING fts5(
    session_id, text, speaker_id,
    content=transcriptions
);
```

### 2. **NPU-Accelerated Embedding Generation**

Since you have NPU acceleration, leverage it for embeddings:

```python
# backend/services/embedding_service.py
import onnxruntime as ort
from typing import List, Dict
import numpy as np

class NPUEmbeddingService:
    def __init__(self):
        # Use NPU-optimized embedding model
        providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
        self.session = ort.InferenceSession(
            "models/all-MiniLM-L6-v2-int8.onnx",
            providers=providers
        )
        
    async def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using NPU acceleration"""
        # Tokenize and prepare inputs
        inputs = self.tokenize(texts)
        
        # Run on NPU
        embeddings = self.session.run(
            None, 
            {self.session.get_inputs()[0].name: inputs}
        )[0]
        
        return embeddings
    
    def chunk_transcript(self, session_id: str) -> List[Dict]:
        """Smart chunking strategy for transcripts"""
        chunks = []
        
        # Get transcription segments
        segments = db.query(Transcription).filter_by(
            session_id=session_id
        ).order_by(Transcription.start_time).all()
        
        # Strategy 1: Speaker-based chunks
        current_chunk = []
        current_speaker = None
        
        for segment in segments:
            if segment.speaker_id != current_speaker and current_chunk:
                chunks.append({
                    'type': 'speaker_segment',
                    'text': ' '.join([s.text for s in current_chunk]),
                    'speaker': current_speaker,
                    'start_time': current_chunk[0].start_time,
                    'end_time': current_chunk[-1].end_time
                })
                current_chunk = []
            
            current_chunk.append(segment)
            current_speaker = segment.speaker_id
        
        # Strategy 2: Sliding window chunks for overlap
        window_size = 10  # segments
        stride = 5
        
        for i in range(0, len(segments), stride):
            window = segments[i:i+window_size]
            if window:
                chunks.append({
                    'type': 'sliding_window',
                    'text': ' '.join([s.text for s in window]),
                    'start_time': window[0].start_time,
                    'end_time': window[-1].end_time
                })
        
        return chunks
```

### 3. **GraphRAG Integration**

```python
# backend/services/graph_service.py
import networkx as nx
from typing import List, Dict, Tuple
import spacy

class MeetingGraphService:
    def __init__(self, embedding_service: NPUEmbeddingService):
        self.nlp = spacy.load("en_core_web_sm")
        self.embedding_service = embedding_service
        self.graph = nx.MultiDiGraph()
        
    async def build_session_graph(self, session_id: str):
        """Extract entities and build graph from session"""
        session = db.query(RecordingSession).get(session_id)
        
        # Add session node
        session_node = f"session_{session_id}"
        self.graph.add_node(
            session_node,
            type='session',
            title=session.title,
            date=session.start_time,
            properties={
                'duration': (session.end_time - session.start_time).seconds,
                'participants': session.settings.get('participants', [])
            }
        )
        
        # Extract entities from transcript
        transcript = await self.get_full_transcript(session_id)
        doc = self.nlp(transcript)
        
        # Add person nodes from speakers
        speakers = db.query(Transcription.speaker_id).filter_by(
            session_id=session_id
        ).distinct().all()
        
        for speaker in speakers:
            person_node = f"person_{speaker[0]}"
            self.graph.add_node(person_node, type='person', name=speaker[0])
            self.graph.add_edge(person_node, session_node, 
                              type='attended', weight=1.0)
        
        # Extract topics using NER and keywords
        topics = self.extract_topics(doc)
        for topic in topics:
            topic_node = f"topic_{topic['name'].lower().replace(' ', '_')}"
            if not self.graph.has_node(topic_node):
                self.graph.add_node(topic_node, type='topic', name=topic['name'])
            
            self.graph.add_edge(session_node, topic_node, 
                              type='discussed', 
                              context=topic['context'],
                              relevance=topic['relevance'])
        
        # Extract decisions and action items
        decisions = await self.extract_decisions(session_id)
        for decision in decisions:
            decision_node = f"decision_{session_id}_{decision['id']}"
            self.graph.add_node(
                decision_node, 
                type='decision',
                description=decision['text'],
                timestamp=decision['timestamp']
            )
            self.graph.add_edge(session_node, decision_node, type='decided')
            
            # Link to topics
            for topic in decision['related_topics']:
                topic_node = f"topic_{topic.lower().replace(' ', '_')}"
                if self.graph.has_node(topic_node):
                    self.graph.add_edge(decision_node, topic_node, 
                                      type='relates_to')
        
        # Save to database
        await self.persist_graph_to_db(session_id)
    
    async def graph_search(self, query: str, k: int = 10) -> Dict:
        """GraphRAG search with NPU-accelerated embeddings"""
        # Generate query embedding
        query_embedding = await self.embedding_service.generate_embeddings([query])
        
        # Find similar nodes
        node_scores = []
        for node, data in self.graph.nodes(data=True):
            if 'embedding' in data:
                similarity = np.dot(query_embedding[0], data['embedding'])
                node_scores.append((node, similarity, data))
        
        # Get top-k nodes
        top_nodes = sorted(node_scores, key=lambda x: x[1], reverse=True)[:k]
        
        # Extract subgraph
        subgraph_nodes = set()
        for node, score, data in top_nodes:
            # Add node and its neighbors (1-hop)
            subgraph_nodes.add(node)
            subgraph_nodes.update(self.graph.neighbors(node))
            subgraph_nodes.update(self.graph.predecessors(node))
        
        subgraph = self.graph.subgraph(subgraph_nodes)
        
        # Build context from subgraph
        context = self.build_context_from_subgraph(subgraph, query)
        
        return {
            'subgraph': nx.node_link_data(subgraph),
            'context': context,
            'relevant_sessions': self.extract_sessions_from_subgraph(subgraph)
        }
```

### 4. **Integrate with Your WebSocket Architecture**

```python
# backend/services/search_websocket.py
from fastapi import WebSocket
from typing import Optional

class SearchWebSocketManager:
    def __init__(self, graph_service: MeetingGraphService):
        self.graph_service = graph_service
        self.active_searches: Dict[str, WebSocket] = {}
    
    async def search_handler(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        search_id = str(uuid.uuid4())
        self.active_searches[search_id] = websocket
        
        try:
            while True:
                data = await websocket.receive_json()
                
                if data['type'] == 'search_query':
                    # Perform hybrid search
                    results = await self.hybrid_search(
                        query=data['query'],
                        filters=data.get('filters', {}),
                        search_type=data.get('search_type', 'hybrid')
                    )
                    
                    await websocket.send_json({
                        'type': 'search_results',
                        'results': results,
                        'search_id': search_id
                    })
                
                elif data['type'] == 'graph_explore':
                    # Interactive graph exploration
                    node_id = data['node_id']
                    expansion = await self.graph_service.expand_node(node_id)
                    
                    await websocket.send_json({
                        'type': 'graph_update',
                        'expansion': expansion
                    })
                    
        except Exception as e:
            logger.error(f"Search websocket error: {e}")
        finally:
            del self.active_searches[search_id]
    
    async def hybrid_search(self, query: str, filters: Dict, 
                          search_type: str = 'hybrid') -> Dict:
        """Combine multiple search strategies"""
        results = {}
        
        # 1. Vector similarity search
        if search_type in ['hybrid', 'semantic']:
            embedding = await self.embedding_service.generate_embeddings([query])
            vector_results = await self.vector_search(embedding[0], filters)
            results['semantic'] = vector_results
        
        # 2. Full-text search
        if search_type in ['hybrid', 'keyword']:
            fts_results = await self.fulltext_search(query, filters)
            results['keyword'] = fts_results
        
        # 3. Graph-based search
        if search_type in ['hybrid', 'graph']:
            graph_results = await self.graph_service.graph_search(query)
            results['graph'] = graph_results
        
        # 4. Rerank and combine
        if search_type == 'hybrid':
            results['combined'] = await self.rerank_results(results)
        
        return results
```

### 5. **Add Search API Endpoints**

```python
# backend/api/search.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/search", tags=["search"])

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
    """Unified search across all meeting data"""
    filters = {
        'organization_id': current_user.organization_id,
        'date_range': (date_from, date_to),
        'speakers': speakers
    }
    
    results = await search_service.hybrid_search(
        query=q,
        filters=filters,
        search_type=search_type,
        limit=limit
    )
    
    return results

@router.get("/graph/explore/{node_id}")
async def explore_graph_node(
    node_id: str,
    depth: int = Query(2, le=5),
    current_user: User = Depends(get_current_user)
):
    """Explore knowledge graph from a specific node"""
    subgraph = await graph_service.get_node_context(
        node_id=node_id,
        depth=depth,
        user=current_user
    )
    
    return {
        'node': subgraph['center'],
        'connections': subgraph['edges'],
        'metadata': subgraph['stats']
    }

@router.post("/index/session/{session_id}")
async def index_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin)
):
    """Trigger indexing for a specific session"""
    background_tasks.add_task(
        index_session_task,
        session_id=session_id
    )
    
    return {"message": "Indexing started", "session_id": session_id}
```

### 6. **Frontend Search Component**

```typescript
// frontend/src/components/UnifiedSearch.tsx
import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { SearchResults } from './SearchResults';
import { GraphVisualization } from './GraphVisualization';

export const UnifiedSearch: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [searchType, setSearchType] = useState('hybrid');
  
  const { sendMessage, lastMessage } = useWebSocket('/ws/search');
  
  const handleSearch = () => {
    sendMessage({
      type: 'search_query',
      query,
      search_type: searchType,
      filters: {
        date_from: dateFrom,
        date_to: dateTo,
        speakers: selectedSpeakers
      }
    });
  };
  
  useEffect(() => {
    if (lastMessage?.type === 'search_results') {
      setResults(lastMessage.results);
    }
  }, [lastMessage]);
  
  return (
    <div className="search-interface">
      <div className="search-bar">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search meetings, decisions, topics..."
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
        />
        
        <select 
          value={searchType} 
          onChange={(e) => setSearchType(e.target.value)}
        >
          <option value="hybrid">Hybrid</option>
          <option value="semantic">Semantic</option>
          <option value="keyword">Keyword</option>
          <option value="graph">Graph</option>
        </select>
      </div>
      
      {results && (
        <>
          <SearchResults results={results} />
          {searchType === 'graph' && (
            <GraphVisualization 
              data={results.graph.subgraph}
              onNodeClick={(nodeId) => exploreNode(nodeId)}
            />
          )}
        </>
      )}
    </div>
  );
};
```

### 7. **Storage Organization**

Extend your existing file structure:

```
/audio_files/
├── sessions/
│   ├── {session_id}/
│   │   ├── recording.wav
│   │   ├── segments/
│   │   ├── exports/
│   │   ├── embeddings/           # New
│   │   │   ├── chunks.json
│   │   │   └── embeddings.npy
│   │   └── graph/                # New
│   │       ├── nodes.json
│   │       └── edges.json
├── indexes/                      # New
│   ├── vector_index/
│   └── graph_cache/
```

## Key Benefits of This Approach

1. **Leverages Your NPU**: Use the NPU for embedding generation, getting significant speedup
2. **Real-time Updates**: WebSocket integration means search updates as meetings progress
3. **Hybrid Search**: Combines semantic, keyword, and graph-based search
4. **Privacy-First**: All processing stays local, no external APIs needed
5. **Scalable**: Can handle millions of meeting segments with proper indexing

The GraphRAG component will be particularly powerful for queries like:
- "What decisions did we make about the product roadmap in Q4?"
- "Show me all meetings where Sarah discussed budgets"
- "What topics lead to the most action items?"
- "Who typically attends security-related meetings?"

This integrates seamlessly with your existing architecture while adding powerful search capabilities that leverage your NPU acceleration.