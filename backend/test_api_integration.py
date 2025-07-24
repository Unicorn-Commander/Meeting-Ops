#!/usr/bin/env python3
"""
Test script to verify API endpoint integration
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import init_database, get_db
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text

def test_database_connection():
    """Test database connection and tables"""
    print("Testing database connection...")
    try:
        db = next(get_db())
        
        # Test if tables exist
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        tables = [r[0] for r in result]
        print(f"Found tables: {tables}")
        
        # Check for our custom tables
        expected_tables = ['sessions', 'transcriptions', 'speakers', 'settings', 'users', 'audio_files']
        missing_tables = [t for t in expected_tables if t not in tables]
        
        if missing_tables:
            print(f"⚠️  Missing tables: {missing_tables}")
        else:
            print("✅ All expected tables exist")
            
        # Test FTS table
        try:
            result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='transcriptions_fts'")).fetchone()
            if result:
                print("✅ FTS table exists")
            else:
                print("⚠️  FTS table missing (will be created on first use)")
        except Exception as e:
            print(f"⚠️  FTS check error: {e}")
            
        db.close()
        print("✅ Database connection successful")
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_imports():
    """Test all critical imports"""
    print("\nTesting imports...")
    
    imports_to_test = [
        ("services.embedding_service", "embedding_service"),
        ("services.knowledge_graph_service", "knowledge_graph"),
        ("services.unified_search_service", "search_service"),
        ("services.memory_service", "meeting_intelligence"),
        ("api.search", "router"),
        ("api.intelligence", "router"),
    ]
    
    failed_imports = []
    
    for module_name, attr_name in imports_to_test:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            if hasattr(module, attr_name):
                print(f"✅ {module_name}.{attr_name}")
            else:
                print(f"⚠️  {module_name} imported but {attr_name} not found")
                failed_imports.append(module_name)
        except Exception as e:
            print(f"❌ {module_name}: {e}")
            failed_imports.append(module_name)
    
    return len(failed_imports) == 0

def test_service_initialization():
    """Test service initialization"""
    print("\nTesting service initialization...")
    
    try:
        from services.embedding_service import embedding_service
        print("✅ Embedding service initialized")
    except Exception as e:
        print(f"❌ Embedding service error: {e}")
        
    try:
        from services.knowledge_graph_service import knowledge_graph
        print("✅ Knowledge graph service initialized")
    except Exception as e:
        print(f"❌ Knowledge graph service error: {e}")
        
    try:
        from services.unified_search_service import search_service
        print("✅ Search service initialized")
    except Exception as e:
        print(f"❌ Search service error: {e}")
        
    try:
        from services.memory_service import meeting_intelligence
        print("✅ Memory service initialized")
    except Exception as e:
        print(f"❌ Memory service error: {e}")

def test_api_routers():
    """Test API router imports"""
    print("\nTesting API routers...")
    
    try:
        from api.search import router as search_router
        endpoints = [route.path for route in search_router.routes]
        print(f"✅ Search router: {len(endpoints)} endpoints")
        print(f"   Endpoints: {', '.join(endpoints[:5])}...")
    except Exception as e:
        print(f"❌ Search router error: {e}")
        
    try:
        from api.intelligence import router as intelligence_router
        endpoints = [route.path for route in intelligence_router.routes]
        print(f"✅ Intelligence router: {len(endpoints)} endpoints")
        print(f"   Endpoints: {', '.join(endpoints[:5])}...")
    except Exception as e:
        print(f"❌ Intelligence router error: {e}")

def check_directories():
    """Check if required directories exist"""
    print("\nChecking directories...")
    
    directories = [
        "storage/embeddings",
        "storage/user_memory",
        "storage/graph",
        "storage/intelligence_cache"
    ]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"✅ {directory}")
        else:
            print(f"⚠️  {directory} missing (creating...)")
            os.makedirs(directory, exist_ok=True)
            print(f"   Created {directory}")

def main():
    """Run all tests"""
    print("="*50)
    print("API Integration Test Suite")
    print("="*50)
    
    # Initialize database
    init_database()
    
    # Run tests
    tests = [
        test_database_connection,
        test_imports,
        test_service_initialization,
        test_api_routers,
        check_directories
    ]
    
    all_passed = True
    for test in tests:
        if not test():
            all_passed = False
    
    print("\n" + "="*50)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.")
    print("="*50)

if __name__ == "__main__":
    main()