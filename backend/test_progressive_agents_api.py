#!/usr/bin/env python3
"""
Test the Progressive Agents API endpoints
"""
import requests
import json

BASE_URL = "http://localhost:9050"

def test_agents_endpoints():
    """Test all agent endpoints"""
    print("🧪 Testing Progressive Agents API...")
    
    # Test GET all agents
    print("\n1. Testing GET /api/advanced/agents")
    response = requests.get(f"{BASE_URL}/api/advanced/agents")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        agents = response.json()
        print(f"   Found {len(agents)} agents:")
        for agent in agents:
            print(f"   - {agent['name']} ({agent['role']}) - Active: {agent['is_active']}")
        
        if agents:
            agent_id = agents[0]['id']
            
            # Test GET specific agent
            print(f"\n2. Testing GET /api/advanced/agents/{agent_id}")
            response = requests.get(f"{BASE_URL}/api/advanced/agents/{agent_id}")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                agent = response.json()
                print(f"   Agent: {agent['name']}")
                print(f"   Progressive config: {agent['progressive_config']}")
    else:
        print(f"   Error: {response.text}")
    
    # Test GET active agent (might fail due to UUID issue)
    print("\n3. Testing GET /api/advanced/agents/active")
    response = requests.get(f"{BASE_URL}/api/advanced/agents/active")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        active_agent = response.json()
        if active_agent:
            print(f"   Active agent: {active_agent['name']}")
        else:
            print("   No active agent")
    else:
        print(f"   Error: {response.text}")

def test_providers_endpoints():
    """Test all provider endpoints"""
    print("\n🧪 Testing AI Providers API...")
    
    # Test GET all providers
    print("\n1. Testing GET /api/advanced/ai-providers")
    response = requests.get(f"{BASE_URL}/api/advanced/ai-providers")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        providers = response.json()
        print(f"   Found {len(providers)} providers:")
        for provider in providers:
            print(f"   - {provider['name']} ({provider['type']}) - Active: {provider['is_active']}")
    else:
        print(f"   Error: {response.text}")
    
    # Test GET active provider
    print("\n2. Testing GET /api/advanced/ai-providers/active")
    response = requests.get(f"{BASE_URL}/api/advanced/ai-providers/active")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        active_provider = response.json()
        if active_provider:
            print(f"   Active provider: {active_provider['name']}")
        else:
            print("   No active provider")
    else:
        print(f"   Error: {response.text}")

def test_create_agent():
    """Test creating a new agent"""
    print("\n🧪 Testing Agent Creation...")
    
    new_agent = {
        "name": "Test Analyst Agent",
        "description": "A test agent for detailed analysis",
        "role": "meeting-analyst",
        "personality": "Analytical, thorough, strategic. Provides deep insights.",
        "capabilities": {"analysis": True, "strategic_thinking": True},
        "sections": {
            "executive": "Executive summary",
            "analysis": "Deep analysis",
            "insights": "Key insights"
        },
        "trigger_type": "progressive",
        "progressive_config": {
            "initialWordCount": 200,
            "intervalMultiplier": 1.5,
            "maxInterval": 1000,
            "modelSize": "large"
        }
    }
    
    print("   Creating new agent...")
    response = requests.post(f"{BASE_URL}/api/advanced/agents", json=new_agent)
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        created_agent = response.json()
        print(f"   Created agent: {created_agent['name']} (ID: {created_agent['id']})")
        return created_agent['id']
    else:
        print(f"   Error: {response.text}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("PROGRESSIVE AGENTS API TEST")
    print("=" * 60)
    
    test_agents_endpoints()
    test_providers_endpoints()
    
    # Test creating an agent
    new_agent_id = test_create_agent()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)