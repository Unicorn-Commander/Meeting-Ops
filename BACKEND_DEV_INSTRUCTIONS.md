# Backend Developer Instructions - Knowledge Analytics System
**Project:** Meeting-Ops Knowledge Intelligence  
**Focus:** Speaker networks, semantic search, cross-meeting memory

---

## 🎯 Mission: Build Knowledge System Backend

You're building the backend for a **knowledge intelligence system** that tracks relationships, topics, and insights across all meetings - not just basic analytics charts.

### Core Requirements:
- **Semantic Search**: Find content across all meetings
- **Speaker Networks**: Track who talks to whom  
- **Topic Clustering**: Group related discussions
- **Action Item Tracking**: Link action items across meetings
- **Meeting Memory**: RAG-based system for organizational knowledge

---

## 📋 Your Task List (4-6 hours)

### Priority 1: Knowledge API Endpoints (2 hours)
Create `/backend/api/knowledge.py` with these endpoints:

```python
# 1. Embed Meeting Content
POST /api/knowledge/embed-session/{session_id}
# Body: {} (no params needed)
# Action: Generate embeddings for session and store in Qdrant
# Response: {"success": true, "embeddings_count": 15}

# 2. Semantic Search  
GET /api/knowledge/search?query=string&limit=10
# Action: Search across all meeting embeddings
# Response: {"results": [{"session_id": "...", "text": "...", "score": 0.8}]}

# 3. Related Meetings
GET /api/knowledge/related/{session_id}?limit=5
# Action: Find meetings with similar content/speakers
# Response: {"related": [{"id": "...", "title": "...", "similarity": 0.7}]}

# 4. Speaker Network Data
GET /api/knowledge/speakers/network
# Action: Return speaker interaction data
# Response: {"nodes": [...], "edges": [...]} # For graph visualization

# 5. Topic Clusters
GET /api/knowledge/topics/clusters
# Action: Group meetings by topic similarity
# Response: {"clusters": [{"topic": "Budget", "sessions": [...]}]}
```

### Priority 2: Embedding Pipeline (2 hours)
Create `/backend/services/knowledge_service.py`:

```python
class KnowledgeService:
    def __init__(self):
        # Initialize Qdrant client
        # Initialize embedding model (sentence-transformers)
        
    async def embed_session(self, session_id: str):
        """Generate and store embeddings for a completed session"""
        # 1. Get session with transcript and summary
        # 2. Create embeddings for:
        #    - Full summary (main embedding)
        #    - Action items (individual embeddings)  
        #    - Key decisions (individual embeddings)
        #    - Speaker quotes (individual embeddings)
        # 3. Store in Qdrant with metadata:
        #    - session_id, timestamp, speakers, topics
        
    async def semantic_search(self, query: str, limit: int = 10):
        """Search across all embedded content"""
        # 1. Embed the query
        # 2. Search Qdrant
        # 3. Return results with session context
        
    async def get_related_sessions(self, session_id: str, limit: int = 5):
        """Find similar meetings"""
        # 1. Get session's main embedding
        # 2. Find nearest neighbors in Qdrant
        # 3. Return session summaries
```

### Priority 3: Speaker Analytics (1 hour)
Enhance `/backend/services/analytics_service.py`:

```python
async def get_speaker_network(self):
    """Build speaker relationship graph"""
    # Query: Which speakers appear in meetings together
    # Return: Nodes (speakers) and edges (co-attendance frequency)
    
async def get_topic_clusters(self):
    """Group meetings by topic similarity"""  
    # Use embeddings to cluster similar meetings
    # Return: Topic groups with representative sessions
```

### Priority 4: Database Schema (30 minutes)
Add to `/backend/database/models.py`:

```python
class SpeakerInteraction(Base):
    __tablename__ = "speaker_interactions"
    
    id = Column(Integer, primary_key=True)
    speaker1 = Column(String(100), nullable=False)
    speaker2 = Column(String(100), nullable=False)  
    session_id = Column(String(100), nullable=False)
    interaction_strength = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

class TopicMention(Base):
    __tablename__ = "topic_mentions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False)
    topic_keywords = Column(JSON)
    topic_cluster_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## 🔧 Technical Implementation Guide

### Qdrant Setup
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient("http://localhost:6333")

# Create collection if not exists
client.recreate_collection(
    collection_name="meeting_knowledge",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
)
```

### Embedding Model
```python
from sentence_transformers import SentenceTransformer

# Use lightweight but good model
model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dimensions
```

### Speaker Network Algorithm
```python
def build_speaker_network(sessions):
    """Build graph where edges = speakers who attended same meetings"""
    nodes = set()
    edges = []
    
    for session in sessions:
        speakers = session.speakers
        nodes.update(speakers)
        
        # Add edges for all speaker pairs in this meeting
        for i, speaker1 in enumerate(speakers):
            for speaker2 in speakers[i+1:]:
                edges.append({
                    "source": speaker1,
                    "target": speaker2, 
                    "weight": 1  # Could be speaking time, frequency, etc.
                })
    
    return {"nodes": list(nodes), "edges": edges}
```

---

## 🔄 Coordination with Frontend

### Update COORDINATION.md every time you:
1. Complete an API endpoint (mark it READY)
2. Need frontend to test something  
3. Get blocked on anything
4. Finish a major component

### API Testing
Test each endpoint with curl before marking READY:

```bash
# Test embedding
curl -X POST http://localhost:9050/api/knowledge/embed-session/session_123

# Test search  
curl "http://localhost:9050/api/knowledge/search?query=budget&limit=5"

# Test speaker network
curl http://localhost:9050/api/knowledge/speakers/network
```

---

## 📊 Success Criteria

Your backend is complete when:
- [ ] All 5 knowledge endpoints respond correctly
- [ ] Qdrant contains embeddings for existing sessions
- [ ] Speaker network returns real relationship data
- [ ] Semantic search finds relevant content across meetings
- [ ] Related meetings API suggests sensible connections
- [ ] Topic clusters group similar meetings logically

---

## 🐛 Common Issues & Solutions

**Qdrant Connection Issues:**
```bash
# Check if Qdrant is running
curl http://localhost:6333/collections
```

**Embedding Model Too Large:**
```python
# Use smaller model if needed
model = SentenceTransformer('all-MiniLM-L6-v2')  # 22MB
```

**No Session Data:**
```python
# Create test sessions first
# Use existing recording sessions as test data
```

---

## 📝 Implementation Notes

- **Start with simple versions** - don't over-engineer
- **Use existing session data** - embed whatever meetings exist
- **Test incrementally** - one endpoint at a time  
- **Coordinate with frontend** - they're building the UI for your data
- **Focus on knowledge** - this is about relationships and memory, not basic charts

---

## 🚀 Ready to Start?

1. Read this entire document
2. Update COORDINATION.md with your status
3. Start with Priority 1: Knowledge API endpoints
4. Test each endpoint before moving to next
5. Coordinate with frontend through COORDINATION.md

**Remember:** You're building an intelligent meeting memory system, not just analytics. Think about how organizations want to find and connect information across all their meetings.

**File to monitor:** `/home/ucadmin/Meeting-Ops/COORDINATION.md` (check every 1 minute)