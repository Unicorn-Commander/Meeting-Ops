# Unified Agent - Quick Start Guide

**TL;DR: Single agent powered by granite3.3:8b handles all meeting tasks**

## 🚀 **Quick Setup**

```bash
# 1. Create agent table and default agent
cd backend
./venv/bin/python create_unified_agent_table.py

# 2. Start backend
./start-backend.sh

# 3. Start frontend (accessible on all IPs)
cd frontend
npm run dev -- --host 0.0.0.0

# 4. Access GUI
# http://your-server-ip:7778
# Navigate to: Advanced Tools > Meeting Agent
```

## 🎯 **What It Does**

| Feature | Description |
|---------|-------------|
| **Progressive Summaries** | 50→75→113 words, real-time during recording |
| **Auto Titles** | "Q4 Budget Planning Meeting" automatically generated |
| **All-in-One** | Executive summary + bullets + actions + decisions |
| **Editable** | Like Open WebUI - edit system prompt, model, settings |
| **granite3.3:8b** | Single powerful model for everything |

## 🔧 **Key Files**

| File | Purpose |
|------|---------|
| `models/unified_agent.py` | Agent database model |
| `services/unified_agent_service.py` | Core agent logic |
| `api/unified_agent_api.py` | REST API endpoints |
| `frontend/src/pages/admin/UnifiedAgent.tsx` | Configuration GUI |

## 📊 **API Endpoints**

```bash
# Get agent config
GET /api/unified-agent/agent

# Update agent  
PUT /api/unified-agent/agent
Content-Type: application/json
{
  "name": "My Meeting Agent",
  "system_prompt": "You are...",
  "model_name": "granite3.3:8b"
}

# Test agent
POST /api/unified-agent/test

# Reset to defaults
POST /api/unified-agent/agent/reset
```

## 🧪 **Test It**

1. Go to `Advanced Tools > Meeting Agent`
2. Click "Test Agent" button
3. Should see JSON response with sample meeting analysis
4. Start a recording to see live progressive summaries

## 🎨 **Customize System Prompt**

Default prompt:
```
You are a professional meeting assistant powered by Granite 3.3 8B.

Analyze meeting transcripts and provide structured insights:

EXECUTIVE SUMMARY: Provide a 2-3 sentence overview
KEY POINTS: List 3-5 main topics as bullet points  
ACTION ITEMS: Extract tasks with owners
DECISIONS: List important decisions
MEETING TITLE: Suggest descriptive title

Be accurate, actionable, and focus on follow-up.
```

Edit this freely like Open WebUI custom models!

## 🔄 **Progressive Intervals**

Smart algorithm: starts fast, gets longer
- **50 words**: ~30 seconds speech → first summary
- **75 words**: next summary  
- **113 words**: next summary
- **169, 254, 381, 500**: continuing progression
- **Cap at 500**: max interval for long meetings

## 🎉 **Benefits vs Old System**

| Old (Complex) | New (Unified) |
|---------------|---------------|
| Multiple agents with roles | Single editable agent |
| phi4-mini → granite3.3 pipeline | granite3.3:8b for everything |
| Complex configuration | Simple Open WebUI style |
| Time-based intervals | Smart word-based intervals |
| No auto-naming | Automatic meeting titles |
| Hard to maintain | Easy to understand |

## 🛠️ **Troubleshooting**

| Problem | Solution |
|---------|----------|
| "No agent configured" | Run `create_unified_agent_table.py` |
| "Model not found" | `ollama pull granite3.3:8b` |
| "Test fails" | Check Ollama is running: `ollama serve` |
| "No summaries during recording" | Check word count is increasing |

## 📱 **Quick Demo**

1. **Configure**: Edit agent in GUI
2. **Test**: Use built-in test with sample transcript  
3. **Record**: Start recording, see live analysis
4. **Stop**: Get final summary + auto-generated title

The agent will show:
- Active agent info during recording
- Progressive interval data (50→75→113...)
- Real-time summaries 
- Final comprehensive summary
- Auto-generated meeting title

**That's it! Much simpler than the old system.** 🎉