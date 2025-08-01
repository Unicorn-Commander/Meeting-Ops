#!/usr/bin/env python3
"""
Test PostgreSQL and Qdrant Integration
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import init_database, get_db
from database.models import RecordingSession, Transcription
from services.vector_search import get_vector_search_service
from auth.models import User

async def test_postgres_connection():
    """Test PostgreSQL connection"""
    logger.info("Testing PostgreSQL connection...")
    
    try:
        db_url = os.getenv("DATABASE_URL", "postgresql://meeting_ops:REMOVED@localhost:5432/meeting_ops")
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ PostgreSQL connection successful")
            
            # Check version
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"PostgreSQL version: {version}")
            
            # Check tables
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            logger.info(f"Found {len(tables)} tables: {', '.join(tables)}")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        return False

async def test_qdrant_connection():
    """Test Qdrant connection"""
    logger.info("\nTesting Qdrant connection...")
    
    try:
        vector_service = get_vector_search_service()
        
        # Get collection info
        info = vector_service.get_collection_info()
        logger.info("✅ Qdrant connection successful")
        logger.info(f"Collection: {info.get('name')}")
        logger.info(f"Vectors: {info.get('vector_count')}")
        logger.info(f"Vector size: {info.get('config', {}).get('vector_size')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Qdrant connection failed: {e}")
        return False

async def test_data_operations():
    """Test basic data operations"""
    logger.info("\nTesting data operations...")
    
    db = next(get_db())
    
    try:
        # Create test session
        test_session = RecordingSession(
            session_id=f"test_{int(datetime.now().timestamp())}",
            name="Test Session for PostgreSQL",
            description="Testing PostgreSQL and Qdrant integration",
            start_time=datetime.utcnow(),
            status="active"
        )
        
        db.add(test_session)
        db.commit()
        db.refresh(test_session)
        
        logger.info(f"✅ Created test session: {test_session.session_id}")
        
        # Add test transcription
        test_transcription = Transcription(
            session_id=test_session.id,
            text="This is a test transcription for PostgreSQL and Qdrant integration.",
            confidence=0.95,
            timestamp=datetime.utcnow(),
            start_time_seconds=0.0,
            end_time_seconds=5.0,
            duration_seconds=5.0,
            processing_time_ms=100.0,
            npu_accelerated=False,
            speaker_id="SPEAKER_00"
        )
        
        db.add(test_transcription)
        db.commit()
        db.refresh(test_transcription)
        
        logger.info(f"✅ Created test transcription: {test_transcription.id}")
        
        # Test vector indexing
        vector_service = get_vector_search_service()
        
        segment_id = f"{test_session.session_id}_{test_transcription.id}"
        vector_service.index_transcription_segment(
            segment_id=segment_id,
            text=test_transcription.text,
            session_id=test_session.session_id,
            speaker=test_transcription.speaker_id,
            timestamp=int(datetime.utcnow().timestamp())
        )
        
        logger.info(f"✅ Indexed transcription in Qdrant: {segment_id}")
        
        # Test search
        results = vector_service.search(
            query="PostgreSQL integration test",
            limit=5
        )
        
        logger.info(f"✅ Search returned {len(results)} results")
        if results:
            logger.info(f"   Top result score: {results[0]['score']:.3f}")
            logger.info(f"   Top result text: {results[0]['text'][:50]}...")
        
        # Cleanup
        db.delete(test_transcription)
        db.delete(test_session)
        db.commit()
        
        vector_service.delete_session(test_session.session_id)
        
        logger.info("✅ Cleanup completed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Data operations failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

async def test_migration_data():
    """Check if migrated data is present"""
    logger.info("\nChecking for migrated data...")
    
    db = next(get_db())
    
    try:
        # Count records in each table
        tables = [
            ("Sessions", RecordingSession),
            ("Transcriptions", Transcription),
            ("Users", User)
        ]
        
        for table_name, model in tables:
            count = db.query(model).count()
            logger.info(f"{table_name}: {count} records")
        
        # Check vector collection
        vector_service = get_vector_search_service()
        info = vector_service.get_collection_info()
        logger.info(f"Vector collection: {info.get('points_count', 0)} points")
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking migrated data: {e}")
        return False
    finally:
        db.close()

async def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("PostgreSQL and Qdrant Integration Test")
    logger.info("=" * 60)
    
    # Initialize database
    logger.info("\nInitializing database...")
    init_database()
    
    # Run tests
    tests = [
        ("PostgreSQL Connection", test_postgres_connection),
        ("Qdrant Connection", test_qdrant_connection),
        ("Data Operations", test_data_operations),
        ("Migration Data", test_migration_data)
    ]
    
    results = []
    for test_name, test_func in tests:
        result = await test_func()
        results.append((test_name, result))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary:")
    logger.info("=" * 60)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        logger.info("\n🎉 All tests passed! PostgreSQL and Qdrant are working correctly.")
    else:
        logger.info("\n⚠️  Some tests failed. Please check the configuration.")
    
    return all_passed

if __name__ == "__main__":
    # Set up environment variables if not already set
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "postgresql://meeting_ops:REMOVED@localhost:5432/meeting_ops"
    if not os.getenv("QDRANT_URL"):
        os.environ["QDRANT_URL"] = "http://localhost:6333"
    
    # Run tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)