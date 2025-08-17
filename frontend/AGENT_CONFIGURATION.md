# AI Agent Configuration System

## Overview
The Agent Configuration system provides a comprehensive interface for creating, managing, and configuring multiple specialized AI agents for different meeting analysis tasks. Each agent can have its own purpose, model, and configuration.

## Features

### ✅ Multi-Agent Card System
- **Individual Agent Cards**: Each agent has its own configuration card
- **Visual Status Indicators**: Active/inactive status with color coding
- **Agent Templates**: Pre-built specialized agents for common use cases
- **Custom Agents**: Create completely custom agents from scratch

### ✅ Agent Management
- **Create Agents**: Use templates or start from blank
- **Edit Agents**: Full configuration editing with tabbed interface
- **Duplicate Agents**: Copy existing agents for quick setup
- **Delete Agents**: Remove unwanted agents
- **Default Agent**: Set which agent is used by default

### ✅ Model Management
- **Available Models**:
  - `phi-4-mini` - 28.40 t/s, 3.2GB RAM - Best for live summaries
  - `granite3.3:8b` - ~15 t/s, 5.1GB RAM - Best for final analysis
  - `qwen3-30b` - 26.54 t/s, 17.6GB RAM - Premium quality analysis

### ✅ Built-in Agent Templates
- **Live Summarizer**: Fast real-time meeting summaries (Phi-4-Mini)
- **Final Analyst**: Comprehensive post-meeting analysis (Granite 3.3 8B)
- **Action Item Extractor**: Specialized in identifying actionable tasks
- **Decision Tracker**: Documents key decisions made in meetings
- **Custom Agent**: Start with a blank template

### ✅ Advanced Configuration
- **System Prompt**: Fully editable prompt engineering with 20-line editor
- **Temperature Control**: 0.0 (focused) to 1.0 (creative) with visual slider
- **Context Length**: 8K, 16K, 32K, or 128K tokens
- **Provider Support**: Ollama, OpenAI, Anthropic
- **Use Case Tags**: Live, Final, Custom, General purpose categorization

## Navigation
Access via: **Main Menu → AI Agents** (🤖 icon)
Route: `/admin/agents`

## API Integration

### Endpoints Used
```typescript
GET  /api/unified-agent/agent     // Get current configuration
PUT  /api/unified-agent/agent     // Update configuration
GET  /api/unified-agent/models    // Get available models
POST /api/unified-agent/reset     // Reset to defaults
GET  /api/unified-agent/status    // Get system status
```

### Configuration Structure
```typescript
interface AgentConfig {
  name: string;
  description: string;
  system_prompt: string;
  provider_type: "ollama" | "openai" | "anthropic";
  model_name: string;
  model_settings: {
    temperature: number;        // 0.0 - 1.0
    max_tokens: number;         // 512 - 8192
    context_length: string;     // "8K" | "32K" | "128K"
  };
  dual_agent_mode?: boolean;
  live_agent?: {
    model_name: string;
    model_settings: any;
  };
  final_agent?: {
    model_name: string;
    model_settings: any;
  };
}
```

## Default Configuration

### System Prompt
```
You are a professional meeting assistant specialized in analyzing meeting transcripts and providing structured summaries.

Your responsibilities:
- Generate concise executive summaries (2-3 sentences)
- Extract key discussion points and decisions
- Identify action items with clear ownership
- Note important decisions and next steps
- Maintain professional, neutral tone
- Focus on business value and outcomes

Format your responses as clear, actionable insights that help teams stay organized and productive.
```

### Model Settings
- **Default Model**: granite3.3:8b
- **Temperature**: 0.7 (balanced creativity)
- **Max Tokens**: 2048
- **Context Length**: 32K

## Usage

### Single Agent Setup
1. Navigate to AI Agents page
2. Configure basic settings (name, description)
3. Select model and adjust parameters
4. Customize system prompt
5. Save configuration

### Dual Agent Setup
1. Enable "Dual-Agent Mode" toggle
2. Configure Live Agent (recommended: phi-4-mini, temp: 0.3)
3. Configure Final Agent (recommended: granite3.3:8b, temp: 0.7)
4. Set default fallback configuration
5. Save configuration

## Performance Optimization

### Recommended Configurations

#### For Speed (Real-time Focus)
- **Model**: phi-4-mini
- **Temperature**: 0.3
- **Context**: 8K
- **Use Case**: Live transcription summaries

#### For Quality (Comprehensive Analysis)
- **Model**: qwen3-30b
- **Temperature**: 0.7
- **Context**: 32K
- **Use Case**: Final meeting reports

#### For Balance (Production Use)
- **Live**: phi-4-mini (temp: 0.3)
- **Final**: granite3.3:8b (temp: 0.7)
- **Use Case**: Most production deployments

## Troubleshooting

### Common Issues
1. **Model Not Loading**: Check if Ollama service is running on correct port
2. **Slow Performance**: Reduce context length or switch to faster model
3. **Poor Quality**: Increase temperature or use larger model
4. **Memory Issues**: Monitor RAM usage, switch to smaller model if needed

### Model Status Indicators
- 🟢 **Ready**: Model loaded and available
- 🟡 **Loading**: Model starting up
- 🔴 **Error**: Model failed to load

## Files Structure
```
frontend/src/pages/admin/
├── AgentConfiguration.tsx    # Main configuration page
└── ...

frontend/src/
├── AppRouterSimplified.tsx   # Added /admin/agents route
└── config.ts                 # API endpoint configuration
```

## Development Notes
- Component uses React hooks for state management
- Real-time configuration updates via PUT requests
- Responsive design with mobile support
- Tailwind CSS for styling
- TypeScript for type safety

## Future Enhancements
- [ ] Model performance monitoring
- [ ] A/B testing between configurations
- [ ] Configuration templates/presets
- [ ] Multi-language model support
- [ ] Custom model upload support