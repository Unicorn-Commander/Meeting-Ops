#!/usr/bin/env python3
"""
Initialize Progressive Agents Database Schema
Run this script to create the new tables for the progressive meeting agent system
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Direct database URL
DATABASE_URL = "postgresql://meeting_ops_user:REMOVED@localhost:5432/meeting_ops_db"

# Import models directly
from models.progressive_agents import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_progressive_agents_db():
    """Initialize the progressive agents database tables"""
    try:
        # Create engine
        engine = create_engine(DATABASE_URL)
        
        # Create tables
        logger.info("Creating progressive agents tables...")
        Base.metadata.create_all(engine)
        
        # Load and execute the schema with default data
        schema_file = os.path.join(os.path.dirname(__file__), "progressive_agents_schema.sql")
        
        if os.path.exists(schema_file):
            logger.info("Loading schema file with default data...")
            
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            # Create session
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            session = SessionLocal()
            
            try:
                # Execute schema (split by statements)
                statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
                
                for statement in statements:
                    if statement.upper().startswith(('CREATE', 'INSERT', 'UPDATE')):
                        try:
                            session.execute(text(statement))
                            session.commit()
                        except Exception as e:
                            if "already exists" in str(e).lower():
                                logger.info(f"Table/constraint already exists, continuing...")
                            else:
                                logger.warning(f"Statement failed (continuing): {e}")
                            session.rollback()
                
                logger.info("✅ Progressive agents database initialized successfully")
                
                # Verify tables exist
                result = session.execute(text("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('meeting_agents', 'ai_providers', 'progressive_summaries', 'progressive_session_state')
                """))
                
                tables = [row[0] for row in result]
                logger.info(f"Created tables: {tables}")
                
                # Verify default data
                result = session.execute(text("SELECT name, role FROM meeting_agents"))
                agents = result.fetchall()
                logger.info(f"Default agents: {[(name, role) for name, role in agents]}")
                
                result = session.execute(text("SELECT name, type FROM ai_providers"))
                providers = result.fetchall()
                logger.info(f"Default providers: {[(name, ptype) for name, ptype in providers]}")
                
            finally:
                session.close()
        
        else:
            logger.warning(f"Schema file not found: {schema_file}")
        
        logger.info("🚀 Progressive agents system ready!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize progressive agents database: {e}")
        return False

if __name__ == "__main__":
    success = init_progressive_agents_db()
    sys.exit(0 if success else 1)