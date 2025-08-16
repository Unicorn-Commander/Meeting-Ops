# Unified Agent System - Engineering Guide

**Meeting-Ops Simplified AI Architecture**  
*Inspired by Open WebUI's approach to custom models*

---

## 🎯 **Architecture Overview**

### **Problem Solved**
The original system had complex multi-agent architecture with multiple roles, providers, and configurations. This was difficult to maintain and configure. We simplified to a **single unified agent** that handles all meeting tasks.

### **Solution: Unified Agent**
- **One Agent**: Handles all tasks (summaries, actions, decisions, titles)
- **One Model**: Granite 3.3 8B for all analysis
- **Editable**: Like Open WebUI custom models
- **Progressive**: Smart word-based intervals
- **Auto-naming**: Sessions get meaningful titles

---

## 🏗️ **System Components**

### **Backend Architecture**

```
┌─────────────────────────────────────────────┐
│                Frontend GUI                 │
│  (Advanced Tools > Meeting Agent)          │
└─────────────┬───────────────────────────────┘
              │ HTTP API + WebSocket
┌─────────────▼───────────────────────────────┐
│           Unified Agent API                 │
│     /api/unified-agent/*                    │
└─────────────┬───────────────────────────────┘
              │
┌─────────────▼───────────────────────────────┐
│        Unified Agent Service               │
│   - Meeting analysis                       │
│   - Progressive summarization              │
│   - Title generation                       │
└─────────────┬───────────────────────────────┘
              │
┌─────────────▼───────────────────────────────┐
│         Granite 3.3 8B Model              │
│        (via Ollama API)                    │
└─────────────────────────────────────────────┘
```

### **Key Files**

| Component | File Path | Purpose |
|-----------|-----------|---------|
| **Database Model** | `models/unified_agent.py` | Agent configuration storage |
| **Backend Service** | `services/unified_agent_service.py` | Core logic and Ollama integration |
| **API Endpoints** | `api/unified_agent_api.py` | REST API for configuration |
| **WebSocket Integration** | `api/websocket_auto_summary.py` | Real-time progressive summaries |
| **Frontend GUI** | `frontend/src/pages/admin/UnifiedAgent.tsx` | Configuration interface |
| **Live Recording** | `frontend/src/pages/LiveRecording.tsx` | Shows agent status during recording |

---

## 🛠️ **Implementation Details**

### **Database Schema**

```sql
-- Unified Meeting Agent Table
CREATE TABLE unified_meeting_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL DEFAULT 'Meeting Assistant',
    description TEXT DEFAULT 'AI assistant for meeting transcription and analysis',
    personality VARCHAR(200) DEFAULT 'Professional and concise',
    
    -- System Prompt (fully editable like Open WebUI)
    system_prompt TEXT DEFAULT 'You are a professional meeting assistant...',
    
    -- Model Configuration  
    provider_type VARCHAR(50) DEFAULT 'ollama',
    model_name VARCHAR(100) DEFAULT 'granite3.3:8b',
    model_config JSON DEFAULT '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}',
    
    -- Progressive Settings
    progressive_config JSON DEFAULT '{
        "initial_interval": 50,
        "multiplier": 1.5, 
        "max_interval": 500,
        "enabled": true
    }',
    
    -- Output Template
    output_template JSON DEFAULT '{
        "executive": "Brief executive summary",
        "bullets": ["Key point 1", "Key point 2"], 
        "actions": [{"action": "...", "owner": "...", "priority": "medium"}],
        "decisions": ["Important decision"],
        "title": "Suggested meeting title"
    }',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### **Progressive Algorithm**

The agent uses smart progressive intervals that start fast and get longer:

```python
# Progressive Interval Logic
initial_interval = 50       # Start at 50 words
multiplier = 1.5            # Increase by 1.5x each time  
max_interval = 500          # Cap at 500 words

# Sequence: 50 → 75 → 113 → 169 → 254 → 381 → 500 → 500...
```

**Benefits:**
- **Early insights**: Quick summaries when meeting starts
- **Efficient processing**: Longer intervals as meeting progresses
- **Consistent updates**: Regular analysis throughout meeting
- **Resource optimization**: Less frequent processing for long meetings

### **Granite 3.3 8B Integration**

```python
# Ollama API Call
async def _call_granite_model(self, transcript: str, agent: UnifiedMeetingAgent):
    response = await requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "granite3.3:8b",
            "prompt": f"""{agent.system_prompt}
            
TRANSCRIPT:
{transcript}

RESPOND WITH JSON:
{{
    "executive": "Brief summary",
    "bullets": ["Key point 1", "Key point 2"],
    "actions": [{{"action": "Task", "owner": "Person", "priority": "high"}}],
    "decisions": ["Decision made"],
    "title": "Meeting title"
}}""",
            "stream": False,
            "format": "json",
            "options": agent.model_config
        }
    )
```

---

## 🔧 **Configuration Guide**

### **Default Agent Configuration**

When first created, the agent has these default settings:

```python
default_agent = UnifiedMeetingAgent(
    name="Meeting Assistant",
    description="AI assistant for meeting transcription and analysis using Granite 3.3 8B",
    personality="Professional, concise, and actionable",
    
    system_prompt="""You are a professional meeting assistant powered by Granite 3.3 8B.

Analyze meeting transcripts and provide structured insights:

EXECUTIVE SUMMARY: Provide a 2-3 sentence overview of the meeting's purpose and outcomes.

KEY POINTS: List 3-5 main topics, decisions, or discussion points as bullet points.

ACTION ITEMS: Extract specific tasks, follow-ups, or assignments with owners when mentioned.

DECISIONS: List important decisions, agreements, or conclusions reached.

MEETING TITLE: Suggest a descriptive title based on the meeting content.

Be accurate, actionable, and focus on what matters most for follow-up.""",
    
    provider_type="ollama",
    model_name="granite3.3:8b",
    
    progressive_config={
        "initial_interval": 50,
        "multiplier": 1.5,
        "max_interval": 500,
        "enabled": True
    }
)
```

### **Customization Options**

**1. System Prompt (Full Control)**
- Edit the entire prompt like Open WebUI custom models
- Define agent personality and behavior
- Specify output format and style
- Add domain-specific instructions

**2. Model Settings**
- **Provider**: Ollama (default), OpenAI, Anthropic
- **Model**: granite3.3:8b (default), or other available models
- **Temperature**: Creativity level (0.0-2.0)
- **Max Tokens**: Response length (100-4000)
- **Top P**: Nucleus sampling (0.0-1.0)

**3. Progressive Configuration**
- **Initial Interval**: Starting word count (25-200)
- **Multiplier**: Growth rate (1.1-3.0) 
- **Max Interval**: Maximum word count (200-1000)
- **Enabled**: Toggle progressive analysis on/off

---

## 🚀 **API Reference**

### **Endpoints**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/unified-agent/status` | Get agent system status |
| `GET` | `/api/unified-agent/agent` | Get current agent configuration |
| `PUT` | `/api/unified-agent/agent` | Update agent configuration |
| `POST` | `/api/unified-agent/agent/reset` | Reset to default configuration |
| `GET` | `/api/unified-agent/models` | Get available models |
| `GET` | `/api/unified-agent/providers` | Get available providers |
| `POST` | `/api/unified-agent/test` | Test agent with sample transcript |

### **WebSocket Messages**

**Progressive Summary Message:**
```json
{
    "type": "progressive_summary",
    "session_id": "abc123",
    "agent": {
        "id": "agent-uuid",
        "name": "Meeting Assistant", 
        "role": "unified"
    },
    "summary_data": {
        "word_count_at_summary": 150,
        "interval_used": 75,
        "next_interval": 113,
        "model_size": "granite3.3:8b",
        "sections": {
            "executive": "Meeting summary...",
            "bullets": ["Point 1", "Point 2"],
            "actions": [{"action": "Task", "owner": "John", "priority": "high"}],
            "decisions": ["Decision made"],
            "title": "Q4 Planning Meeting"
        }
    },
    "timestamp": "2025-01-14T10:30:00Z"
}
```

**Final Summary Message:**
```json
{
    "type": "final_summary", 
    "summary": {
        "executive": "Comprehensive final summary",
        "bullets": ["All key points"],
        "actions": [{"action": "Complete task list", "owner": "Team", "priority": "high"}],
        "decisions": ["All decisions made"],
        "title": "Final meeting title"
    },
    "meeting_title": "Q4 Budget Planning Session",
    "summary_count": 5
}
```

---

## 🧪 **Testing & Debugging**

### **Built-in Test Function**

The system includes a test function that sends a sample transcript to the agent:

```python
# Test with sample transcript
sample_transcript = """
John: Welcome everyone to our Q4 planning meeting. We need to discuss the budget for next quarter.
Sarah: I've prepared the financial projections. We're looking at a 15% increase in marketing spend.
Mike: That sounds reasonable. What about the product development timeline?
Sarah: We should have the new feature ready by December 15th. John, can you handle the client communication?
John: Absolutely. I'll reach out to the key accounts this week.
"""
```

**Expected Output:**
```json
{
    "success": true,
    "test_result": {
        "executive": "Q4 planning meeting focused on budget allocation and project timelines",
        "bullets": [
            "15% increase in marketing spend approved",
            "New feature delivery scheduled for December 15th", 
            "Client communication assigned to John"
        ],
        "actions": [
            {"action": "Reach out to key accounts", "owner": "John", "priority": "medium"}
        ],
        "decisions": [
            "Approved 15% marketing budget increase",
            "Set December 15th deadline for new feature"
        ],
        "title": "Q4 Budget and Timeline Planning"
    }
}
```

### **Debug Logging**

The system logs detailed information for debugging:

```python
# Service logs
logger.info(f"Started meeting analysis for session {session_id}")
logger.info(f"  Agent: {agent.name}")
logger.info(f"  Model: {agent.model_name}")
logger.info(f"  Initial interval: {config.initial_word_count} words")

# Progressive logs  
logger.info(f"Generated progressive summary for session {session_id}")
logger.info(f"  Word count: {interval_info['current_word_count']}")
logger.info(f"  Interval: {interval_info['current_interval']} words")
logger.info(f"  Processing time: {processing_time}ms")
```

### **Common Issues & Solutions**

| Issue | Cause | Solution |
|-------|-------|----------|
| "No agent configured" | Database table not created | Run `create_unified_agent_table.py` |
| "Model request failed" | Ollama not running | Start Ollama: `ollama serve` |
| "granite3.3:8b not found" | Model not pulled | Pull model: `ollama pull granite3.3:8b` |
| "Invalid JSON response" | Model output malformed | Check system prompt format |
| "Progressive summaries not triggering" | Word count not increasing | Check transcription service |

---

## 🔄 **Migration from Legacy System**

### **What Changed**

| Old System | New System |
|------------|------------|
| Multiple complex agents with roles | Single unified agent |
| phi4-mini → granite3.3 pipeline | granite3.3:8b for everything |
| Complex configuration | Simple, editable configuration |
| Time-based intervals | Word-based progressive intervals |
| Multiple provider management | Single active provider |
| No auto-naming | Automatic meeting titles |

### **Backward Compatibility**

The old system is still available but marked as "Legacy" in the navigation:
- `Advanced Tools > AI Settings (Legacy)`
- `Advanced Tools > Multi-Agents (Legacy)`

The WebSocket endpoint supports both message formats:
- `progressive_summary` (new unified agent)
- `auto_summary` (legacy system)

### **Migration Steps**

1. **Create unified agent table:**
   ```bash
   cd backend
   ./venv/bin/python create_unified_agent_table.py
   ```

2. **Update frontend navigation:**
   - New: `Advanced Tools > Meeting Agent`
   - Legacy: `Advanced Tools > Multi-Agents (Legacy)`

3. **Start using unified agent:**
   - Configure in GUI
   - Test with built-in function
   - Start recording to see live analysis

---

## 📈 **Performance Characteristics**

### **Model Performance**
- **Model**: Granite 3.3 8B parameters
- **Provider**: Ollama (local inference)
- **Average Response Time**: 2-5 seconds
- **Memory Usage**: ~16GB for model + inference
- **Concurrent Sessions**: Limited by available GPU memory

### **Progressive Intervals**
- **Initial Response**: ~50 words (30-60 seconds of speech)
- **Scaling**: 50 → 75 → 113 → 169 → 254 → 381 → 500
- **Processing Time**: 2-5 seconds per summary
- **Resource Efficiency**: Decreasing frequency as meeting progresses

### **Storage Requirements**
- **Agent Configuration**: ~5KB per agent (JSON)
- **Progressive Summaries**: ~2KB per summary
- **Session Storage**: Existing transcription storage unchanged

---

## 🛡️ **Security Considerations**

### **Data Privacy**
- **Local Processing**: All AI inference happens locally via Ollama
- **No External APIs**: Data never leaves the system (unless explicitly configured)
- **Database Security**: Agent configurations stored in encrypted PostgreSQL

### **Access Control**
- **Role-based Access**: Only admin/superuser/manager can edit agent
- **Authentication Required**: JWT tokens for all API access
- **WebSocket Security**: Session-based authentication

### **System Prompt Security**
- **Injection Prevention**: System prompts are parameterized
- **Content Filtering**: Responses are parsed and validated
- **Error Handling**: Malformed responses fallback to safe defaults

---

## 📝 **Best Practices**

### **Agent Configuration**

**✅ Do:**
- Start with default configuration and iterate
- Test changes with built-in test function
- Keep system prompts clear and specific
- Use appropriate temperature settings (0.7 for balance)
- Set reasonable progressive intervals (50-500 words)

**❌ Don't:**
- Make drastic changes without testing
- Use very high temperature (>1.5) for business meetings
- Set intervals too low (<25 words) or too high (>1000 words)
- Include sensitive information in system prompts
- Disable progressive analysis unless necessary

### **System Prompt Writing**

**Good System Prompt Structure:**
```
You are a [role] powered by [model].

[Task description]

[Output format requirements]

[Quality guidelines]

Be [personality traits].
```

**Example:**
```
You are a professional meeting assistant powered by Granite 3.3 8B.

Analyze meeting transcripts and provide structured insights.

Generate:
- Executive summary (2-3 sentences)
- Key bullet points (3-5 items)
- Action items with owners
- Important decisions
- Meeting title

Be accurate, concise, and actionable.
```

### **Monitoring & Maintenance**

1. **Regular Testing**: Use built-in test function monthly
2. **Log Monitoring**: Check backend logs for errors
3. **Performance Tracking**: Monitor response times
4. **Model Updates**: Keep Ollama and models updated
5. **Configuration Backup**: Export agent configurations

---

## 🔮 **Future Enhancements**

### **Planned Features**
- **Multiple Agents**: Support for different meeting types
- **Custom Templates**: Pre-built configurations for industries
- **Model Comparison**: A/B testing different models
- **Fine-tuning**: Custom model training on meeting data
- **Integration APIs**: Connect with external tools
- **Analytics Dashboard**: Agent performance metrics

### **Architecture Evolution**
- **Microservices**: Split agent service into smaller components
- **Caching Layer**: Redis cache for frequent configurations
- **Load Balancing**: Multiple Ollama instances for scale
- **Model Registry**: Centralized model management
- **Configuration Versioning**: Track agent changes over time

---

This guide provides comprehensive documentation for the Unified Agent System. For additional support, refer to the main CLAUDE.md documentation or check the backend logs for detailed debugging information.