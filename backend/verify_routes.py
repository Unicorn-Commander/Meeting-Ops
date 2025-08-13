#!/usr/bin/env python3
"""
Verify that new API routes are properly loaded
"""
import sys
import os
sys.path.append('.')

# Set environment to prevent warnings
os.environ.setdefault('DATABASE_URL', 'sqlite:///temp.db')

def main():
    try:
        # Import the main app
        from main import app
        
        print("🔍 Checking FastAPI routes...")
        
        # Get all routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                for method in route.methods:
                    if method != "HEAD":  # Skip HEAD methods
                        routes.append(f"{method} {route.path}")
        
        # Sort routes
        routes.sort()
        
        # Check for our new endpoints
        new_endpoints = [
            "GET /api/settings/application",
            "PUT /api/settings/application", 
            "GET /api/settings/agents",
            "PUT /api/settings/agents",
            "POST /api/settings/agents/prompts",
            "GET /api/vocabulary",
            "POST /api/vocabulary/terms",
            "GET /api/meeting-intelligence-real/live-templates/{session_id}",
            "GET /api/sessions/{session_id}/templates",
            "GET /api/summarization-templates"
        ]
        
        print(f"\n📊 Total routes found: {len(routes)}")
        print("\n🔍 Checking for new API endpoints:")
        
        found_endpoints = []
        missing_endpoints = []
        
        for endpoint in new_endpoints:
            # Check if endpoint exists (allowing for path parameters)
            endpoint_found = False
            for route in routes:
                if endpoint.split()[0] == route.split()[0]:  # Same method
                    route_path = route.split()[1]
                    endpoint_path = endpoint.split()[1]
                    
                    # Handle path parameters
                    if "{" in endpoint_path:
                        endpoint_pattern = endpoint_path.replace("{session_id}", "*").replace("{term_id}", "*").replace("{prompt_id}", "*")
                        route_pattern = route_path.replace("{session_id}", "*").replace("{term_id}", "*").replace("{prompt_id}", "*") 
                        if endpoint_pattern == route_pattern:
                            endpoint_found = True
                            break
                    elif endpoint_path == route_path:
                        endpoint_found = True
                        break
            
            if endpoint_found:
                found_endpoints.append(endpoint)
                print(f"   ✅ {endpoint}")
            else:
                missing_endpoints.append(endpoint)
                print(f"   ❌ {endpoint}")
        
        print(f"\n📈 Results:")
        print(f"   Found: {len(found_endpoints)}/{len(new_endpoints)} endpoints")
        print(f"   Missing: {len(missing_endpoints)} endpoints")
        
        if missing_endpoints:
            print(f"\n❌ Missing endpoints:")
            for endpoint in missing_endpoints:
                print(f"   - {endpoint}")
        
        # Print some sample routes for debugging
        print(f"\n📋 Sample routes (showing first 20):")
        for route in routes[:20]:
            print(f"   {route}")
        
        if len(routes) > 20:
            print(f"   ... and {len(routes) - 20} more")
        
        return len(missing_endpoints) == 0
        
    except Exception as e:
        print(f"❌ Error checking routes: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)