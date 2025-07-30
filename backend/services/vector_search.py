"""
Vector search service using Qdrant for semantic search capabilities
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct
import hashlib

logger = logging.getLogger(__name__)


class VectorSearchService:
    def __init__(self, 
                 qdrant_url: str = None,
                 collection_name: str = "meeting_transcripts",
                 embedding_model: str = "all-MiniLM-L6-v2"):
        """
        Initialize the vector search service
        
        Args:
            qdrant_url: URL of the Qdrant service
            collection_name: Name of the collection to use
            embedding_model: Name of the sentence transformer model
        """
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.collection_name = collection_name
        
        # Initialize Qdrant client
        self.client = QdrantClient(url=self.qdrant_url)
        
        # Initialize embedding model
        logger.info(f"Loading embedding model: {embedding_model}")
        self.encoder = SentenceTransformer(embedding_model)
        self.vector_size = self.encoder.get_sentence_embedding_dimension()
        
        # Create collection if it doesn't exist
        self._ensure_collection()
        
    def _ensure_collection(self):
        """Ensure the collection exists with proper configuration"""
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    ),
                    # Optimize for search performance
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=10000,
                        memmap_threshold=50000
                    ),
                    # Configure indexing
                    hnsw_config=models.HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                        full_scan_threshold=10000
                    )
                )
                
                # Create payload indexes for filtering
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="session_id",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="speaker",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="timestamp",
                    field_schema=models.PayloadSchemaType.INTEGER
                )
                
                logger.info(f"Collection {self.collection_name} created successfully")
                
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise
    
    def index_transcription_segment(self, 
                                  segment_id: str,
                                  text: str,
                                  session_id: str,
                                  speaker: Optional[str] = None,
                                  timestamp: Optional[int] = None,
                                  metadata: Optional[Dict[str, Any]] = None):
        """
        Index a single transcription segment
        
        Args:
            segment_id: Unique ID for the segment
            text: The transcription text
            session_id: ID of the recording session
            speaker: Speaker name/ID
            timestamp: Unix timestamp
            metadata: Additional metadata
        """
        try:
            # Generate embedding
            embedding = self.encoder.encode(text).tolist()
            
            # Prepare payload
            payload = {
                "text": text,
                "session_id": session_id,
                "speaker": speaker or "unknown",
                "timestamp": timestamp or int(datetime.now().timestamp()),
                "indexed_at": datetime.now().isoformat()
            }
            
            if metadata:
                payload.update(metadata)
            
            # Create point
            point = PointStruct(
                id=segment_id,
                vector=embedding,
                payload=payload
            )
            
            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.debug(f"Indexed segment {segment_id} for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error indexing segment: {e}")
            raise
    
    def index_full_transcript(self, 
                            session_id: str,
                            segments: List[Dict[str, Any]],
                            batch_size: int = 100):
        """
        Index a full transcript with all its segments
        
        Args:
            session_id: Recording session ID
            segments: List of segment dictionaries
            batch_size: Number of segments to index at once
        """
        logger.info(f"Indexing {len(segments)} segments for session {session_id}")
        
        points = []
        for i, segment in enumerate(segments):
            try:
                # Generate unique ID for segment
                segment_id = f"{session_id}_{i}_{hashlib.md5(segment['text'].encode()).hexdigest()[:8]}"
                
                # Generate embedding
                embedding = self.encoder.encode(segment['text']).tolist()
                
                # Prepare payload
                payload = {
                    "text": segment['text'],
                    "session_id": session_id,
                    "speaker": segment.get('speaker', 'unknown'),
                    "timestamp": segment.get('timestamp', int(datetime.now().timestamp())),
                    "start_time": segment.get('start_time'),
                    "end_time": segment.get('end_time'),
                    "confidence": segment.get('confidence'),
                    "indexed_at": datetime.now().isoformat()
                }
                
                # Create point
                point = PointStruct(
                    id=segment_id,
                    vector=embedding,
                    payload=payload
                )
                
                points.append(point)
                
                # Batch upsert
                if len(points) >= batch_size:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=points
                    )
                    logger.info(f"Indexed batch of {len(points)} segments")
                    points = []
                    
            except Exception as e:
                logger.error(f"Error processing segment {i}: {e}")
                continue
        
        # Index remaining points
        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Indexed final batch of {len(points)} segments")
        
        logger.info(f"Completed indexing for session {session_id}")
    
    def search(self, 
               query: str,
               limit: int = 10,
               session_id: Optional[str] = None,
               speaker: Optional[str] = None,
               time_range: Optional[tuple] = None,
               score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Search for similar transcription segments
        
        Args:
            query: Search query text
            limit: Maximum number of results
            session_id: Filter by session ID
            speaker: Filter by speaker
            time_range: Tuple of (start_timestamp, end_timestamp)
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with scores and metadata
        """
        try:
            # Generate query embedding
            query_vector = self.encoder.encode(query).tolist()
            
            # Build filter conditions
            filter_conditions = []
            
            if session_id:
                filter_conditions.append(
                    models.FieldCondition(
                        key="session_id",
                        match=models.MatchValue(value=session_id)
                    )
                )
            
            if speaker:
                filter_conditions.append(
                    models.FieldCondition(
                        key="speaker",
                        match=models.MatchValue(value=speaker)
                    )
                )
            
            if time_range:
                start_time, end_time = time_range
                filter_conditions.append(
                    models.FieldCondition(
                        key="timestamp",
                        range=models.Range(
                            gte=start_time,
                            lte=end_time
                        )
                    )
                )
            
            # Combine filters
            search_filter = None
            if filter_conditions:
                search_filter = models.Filter(
                    must=filter_conditions
                )
            
            # Perform search
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold
            )
            
            # Format results
            results = []
            for hit in search_result:
                result = {
                    "score": hit.score,
                    "segment_id": hit.id,
                    **hit.payload
                }
                results.append(result)
            
            logger.info(f"Search found {len(results)} results for query: '{query[:50]}...'")
            return results
            
        except Exception as e:
            logger.error(f"Error performing search: {e}")
            return []
    
    def find_similar_segments(self, 
                            segment_text: str,
                            limit: int = 5,
                            exclude_session: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find segments similar to a given segment
        
        Args:
            segment_text: Text to find similar segments for
            limit: Maximum number of results
            exclude_session: Session ID to exclude from results
            
        Returns:
            List of similar segments
        """
        filter_conditions = []
        if exclude_session:
            filter_conditions.append(
                models.FieldCondition(
                    key="session_id",
                    match=models.MatchExcept(except_=[exclude_session])
                )
            )
        
        search_filter = models.Filter(must=filter_conditions) if filter_conditions else None
        
        return self.search(
            query=segment_text,
            limit=limit,
            score_threshold=0.5
        )
    
    def get_session_summary_vectors(self, session_id: str) -> Optional[np.ndarray]:
        """
        Get average vector representation of a session
        
        Args:
            session_id: Recording session ID
            
        Returns:
            Average vector or None if no segments found
        """
        try:
            # Retrieve all vectors for the session
            result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="session_id",
                            match=models.MatchValue(value=session_id)
                        )
                    ]
                ),
                with_vectors=True,
                limit=1000
            )
            
            if not result[0]:
                return None
            
            # Extract vectors
            vectors = [point.vector for point in result[0]]
            
            # Calculate average
            avg_vector = np.mean(vectors, axis=0)
            
            return avg_vector
            
        except Exception as e:
            logger.error(f"Error getting session summary: {e}")
            return None
    
    def delete_session(self, session_id: str):
        """Delete all vectors for a session"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="session_id",
                                match=models.MatchValue(value=session_id)
                            )
                        ]
                    )
                )
            )
            logger.info(f"Deleted all vectors for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error deleting session vectors: {e}")
            raise
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection"""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": info.name,
                "vector_count": info.vectors_count,
                "indexed_vectors": info.indexed_vectors_count,
                "points_count": info.points_count,
                "segments_count": info.segments_count,
                "status": info.status,
                "config": {
                    "vector_size": info.config.params.vectors.size,
                    "distance": info.config.params.vectors.distance
                }
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}


# Singleton instance
_vector_search_service = None


def get_vector_search_service() -> VectorSearchService:
    """Get or create the vector search service singleton"""
    global _vector_search_service
    if _vector_search_service is None:
        _vector_search_service = VectorSearchService()
    return _vector_search_service