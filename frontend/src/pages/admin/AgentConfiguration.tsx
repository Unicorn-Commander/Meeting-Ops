import React, { useState, useEffect } from 'react';
import {
  Settings, Brain, Zap, Activity, Save, RotateCcw, Plus,
  Cpu, MemoryStick, Timer, Bot, Database, Edit, Trash2,
  Copy, Star, Play, Pause, AlertCircle, CheckCircle, 
  Info, X, ChevronDown, ChevronUp
} from 'lucide-react';
import { config } from '../../config';

interface Agent {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  provider_type: string;
  model_name: string;
  model_settings: {
    temperature: number;
    max_tokens: number;
    context_length: string;
    top_p?: number;
    frequency_penalty?: number;
  };
  status: 'active' | 'inactive' | 'error';
  created_at: string;
  last_used?: string;
  usage_count?: number;
  is_default?: boolean;
  tags?: string[];
  use_case: 'live' | 'final' | 'general' | 'custom';
}

interface ModelInfo {
  name: string;
  speed: string;
  best_for: string;
  memory: string;
  port?: number;
  status: 'ready' | 'loading' | 'error';
}

const MODEL_PERFORMANCE: Record<string, ModelInfo> = {
  'granite-3.3-2b-instruct': {
    name: 'Granite 3.3 2B Instruct',
    speed: '~850 t/s',
    best_for: 'Summaries, chat, insights',
    memory: '~1.5GB',
    port: 11437,
    status: 'ready'
  }
};

const AGENT_TEMPLATES = {
  live_summarizer: {
    name: 'Live Summarizer',
    description: 'Fast real-time meeting summaries during recording',
    system_prompt: `You are a live meeting summarizer. Generate concise, real-time summaries as the meeting progresses.

Focus on:
- Key points being discussed right now
- Important decisions being made
- Action items as they emerge
- Keep summaries under 3 sentences
- Update incrementally

Be immediate and actionable in your responses.`,
    model_name: 'granite-3.3-2b-instruct',
    use_case: 'live' as const,
    model_settings: { temperature: 0.3, max_tokens: 512, context_length: '8K' }
  },
  final_analyst: {
    name: 'Final Analyst',
    description: 'Comprehensive post-meeting analysis and documentation',
    system_prompt: `You are a comprehensive meeting analyst. Analyze the complete meeting transcript to create detailed documentation.

Provide:
- Executive summary (2-3 paragraphs)
- Complete action items with owners and deadlines
- Key decisions made with context
- Follow-up recommendations
- Meeting effectiveness assessment

Be thorough and professional in your analysis.`,
    model_name: 'granite-3.3-2b-instruct',
    use_case: 'final' as const,
    model_settings: { temperature: 0.7, max_tokens: 2048, context_length: '8K' }
  },
  action_extractor: {
    name: 'Action Item Extractor',
    description: 'Specialized in identifying and categorizing action items',
    system_prompt: `You are an action item extraction specialist. Focus solely on identifying actionable tasks from meeting discussions.

For each action item, provide:
- Clear, specific task description
- Assigned person (if mentioned)
- Deadline or timeframe (if mentioned)
- Priority level (high/medium/low)
- Dependencies on other tasks

Format as structured lists for easy tracking.`,
    model_name: 'granite-3.3-2b-instruct',
    use_case: 'custom' as const,
    model_settings: { temperature: 0.4, max_tokens: 1024, context_length: '16K' }
  },
  decision_tracker: {
    name: 'Decision Tracker',
    description: 'Tracks and documents key decisions made in meetings',
    system_prompt: `You are a decision tracking specialist. Identify and document all significant decisions made during meetings.

For each decision, capture:
- What was decided
- Who made the decision
- Context and reasoning
- Impact and implications
- Any dissenting opinions
- Implementation requirements

Focus on decisions that will affect future work or strategy.`,
    model_name: 'granite-3.3-2b-instruct',
    use_case: 'custom' as const,
    model_settings: { temperature: 0.5, max_tokens: 1024, context_length: '16K' }
  }
};

export const AgentConfiguration: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  useEffect(() => {
    loadAgents();
    loadAvailableModels();
  }, []);

  const loadAgents = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agents`);
      if (response.ok) {
        const data = await response.json();
        setAgents(data.agents || []);
      } else {
        console.warn('Failed to load agents, using defaults');
        createDefaultAgents();
      }
    } catch (error) {
      console.error('Error loading agents:', error);
      createDefaultAgents();
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableModels = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/models`);
      if (response.ok) {
        const data = await response.json();
        setModels(data.models || []);
      }
    } catch (error) {
      console.error('Error loading models:', error);
      setModels(['granite-3.3-2b-instruct']);
    }
  };

  const createDefaultAgents = () => {
    const defaultAgents: Agent[] = Object.entries(AGENT_TEMPLATES).map(([key, template], index) => ({
      id: `agent-${key}`,
      ...template,
      provider_type: 'llamacpp',
      status: 'active' as const,
      created_at: new Date().toISOString(),
      is_default: index === 0,
      tags: [template.use_case],
    }));
    setAgents(defaultAgents);
  };

  const saveAgent = async (agent: Agent) => {
    setSaving(agent.id);
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agents/${agent.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agent)
      });
      
      if (response.ok) {
        setAgents(prev => prev.map(a => a.id === agent.id ? agent : a));
        setStatus(`Agent "${agent.name}" saved successfully`);
        setTimeout(() => setStatus(''), 3000);
      } else {
        setStatus(`Failed to save agent "${agent.name}"`);
      }
    } catch (error) {
      console.error('Error saving agent:', error);
      setStatus(`Error saving agent "${agent.name}"`);
    } finally {
      setSaving(null);
    }
  };

  const createAgent = async (template?: keyof typeof AGENT_TEMPLATES) => {
    const templateData = template ? AGENT_TEMPLATES[template] : {
      name: 'New Agent',
      description: 'Custom meeting analysis agent',
      system_prompt: 'You are a helpful meeting assistant.',
      model_name: 'granite-3.3-2b-instruct',
      use_case: 'general' as const,
      model_settings: { temperature: 0.7, max_tokens: 1024, context_length: '32K' }
    };

    const newAgent: Agent = {
      id: `agent-${Date.now()}`,
      ...templateData,
      provider_type: 'llamacpp',
      status: 'inactive',
      created_at: new Date().toISOString(),
      tags: [templateData.use_case],
    };

    setAgents(prev => [...prev, newAgent]);
    setEditingAgent(newAgent);
    setShowCreateModal(false);
  };

  const duplicateAgent = (agent: Agent) => {
    const duplicatedAgent: Agent = {
      ...agent,
      id: `agent-${Date.now()}`,
      name: `${agent.name} (Copy)`,
      status: 'inactive',
      created_at: new Date().toISOString(),
      is_default: false,
    };
    setAgents(prev => [...prev, duplicatedAgent]);
  };

  const deleteAgent = async (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    if (!agent) return;
    
    if (!confirm(`Delete agent "${agent.name}"? This action cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agents/${agentId}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        setAgents(prev => prev.filter(a => a.id !== agentId));
        setStatus(`Agent "${agent.name}" deleted`);
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (error) {
      console.error('Error deleting agent:', error);
      setStatus(`Error deleting agent "${agent.name}"`);
    }
  };

  const toggleAgentStatus = async (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    if (!agent) return;
    const newStatus = agent.status === 'active' ? 'inactive' : 'active';
    // Optimistically update local state
    setAgents(prev => prev.map(a =>
      a.id === agentId ? { ...a, status: newStatus } : a
    ));
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agents/${agentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...agent, status: newStatus })
      });
      if (response.ok) {
        setStatus(`Agent "${agent.name}" ${newStatus === 'active' ? 'activated' : 'deactivated'}`);
        setTimeout(() => setStatus(''), 3000);
      } else {
        // Revert on failure
        setAgents(prev => prev.map(a =>
          a.id === agentId ? { ...a, status: agent.status } : a
        ));
        setStatus(`Failed to update agent "${agent.name}" status`);
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (error) {
      console.error('Error toggling agent status:', error);
      // Revert on failure
      setAgents(prev => prev.map(a =>
        a.id === agentId ? { ...a, status: agent.status } : a
      ));
      setStatus(`Error updating agent "${agent.name}" status`);
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const setDefaultAgent = async (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    if (!agent) return;
    const previousAgents = [...agents];
    // Optimistically update local state
    setAgents(prev => prev.map(a => ({
      ...a,
      is_default: a.id === agentId
    })));
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agents/${agentId}/set-default`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        setStatus(`"${agent.name}" set as default agent`);
        setTimeout(() => setStatus(''), 3000);
      } else {
        // Revert on failure
        setAgents(previousAgents);
        setStatus(`Failed to set "${agent.name}" as default`);
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (error) {
      console.error('Error setting default agent:', error);
      // Revert on failure
      setAgents(previousAgents);
      setStatus(`Error setting "${agent.name}" as default`);
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const getUseCaseColor = (useCase: string) => {
    switch (useCase) {
      case 'live': return 'bg-green-500/10 text-green-400 border-green-500/30';
      case 'final': return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'custom': return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      default: return 'bg-gray-500/10 text-gray-400 border-gray-500/30';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-white p-6">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-zinc-400">Loading agents...</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                <Bot className="w-8 h-8 text-purple-400" />
                AI Agent Configuration
              </h1>
              <p className="text-zinc-400">
                Create and manage specialized AI agents for different meeting analysis tasks
              </p>
            </div>
            
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl font-medium transition-colors"
            >
              <Plus className="w-5 h-5" />
              Create Agent
            </button>
          </div>
        </div>

        {/* Status Message */}
        {status && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${
            status.includes('Error') || status.includes('Failed') 
              ? 'bg-red-900/50 border border-red-500/30 text-red-200' 
              : 'bg-green-900/50 border border-green-500/30 text-green-200'
          }`}>
            {status.includes('Error') || status.includes('Failed') 
              ? <AlertCircle className="w-5 h-5" />
              : <CheckCircle className="w-5 h-5" />
            }
            {status}
          </div>
        )}

        {/* Agents Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {agents.map(agent => (
            <div
              key={agent.id}
              className="bg-zinc-900/70 rounded-2xl border border-zinc-800 overflow-hidden hover:border-zinc-700 transition-all"
            >
              {/* Agent Card Header */}
              <div className="p-6 border-b border-zinc-800">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-semibold text-white">{agent.name}</h3>
                      {agent.is_default && (
                        <Star className="w-4 h-4 text-yellow-400 fill-current" />
                      )}
                    </div>
                    <p className="text-sm text-zinc-400 line-clamp-2">{agent.description}</p>
                  </div>
                  
                  <div className="flex items-center gap-1 ml-4">
                    <button
                      onClick={() => toggleAgentStatus(agent.id)}
                      className={`p-1 rounded ${
                        agent.status === 'active' 
                          ? 'text-green-400 hover:bg-green-900/20' 
                          : 'text-zinc-500 hover:bg-zinc-800'
                      }`}
                      title={agent.status === 'active' ? 'Deactivate' : 'Activate'}
                    >
                      {agent.status === 'active' ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                
                <div className="flex items-center gap-2 mb-3">
                  <span className={`px-2 py-1 text-xs rounded-full border ${getUseCaseColor(agent.use_case)}`}>
                    {agent.use_case}
                  </span>
                  <span className={`px-2 py-1 text-xs rounded-full ${
                    agent.status === 'active' 
                      ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                      : 'bg-zinc-700/50 text-zinc-500 border border-zinc-600/30'
                  }`}>
                    {agent.status}
                  </span>
                </div>
                
                <div className="flex items-center gap-4 text-xs text-zinc-500">
                  <div className="flex items-center gap-1">
                    <Brain className="w-3 h-3" />
                    {MODEL_PERFORMANCE[agent.model_name]?.name || agent.model_name}
                  </div>
                  <div className="flex items-center gap-1">
                    <Timer className="w-3 h-3" />
                    {MODEL_PERFORMANCE[agent.model_name]?.speed || 'Unknown'}
                  </div>
                </div>
              </div>

              {/* Agent Actions */}
              <div className="p-4 bg-zinc-800/30">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setEditingAgent(agent)}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                  >
                    <Edit className="w-4 h-4" />
                    Edit
                  </button>
                  
                  <button
                    onClick={() => duplicateAgent(agent)}
                    className="p-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-zinc-200 transition-colors"
                    title="Duplicate agent"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                  
                  {!agent.is_default && (
                    <button
                      onClick={() => setDefaultAgent(agent.id)}
                      className="p-2 bg-zinc-800 hover:bg-yellow-900/50 rounded-lg text-zinc-200 hover:text-yellow-400 transition-colors"
                      title="Set as default"
                    >
                      <Star className="w-4 h-4" />
                    </button>
                  )}
                  
                  <button
                    onClick={() => deleteAgent(agent.id)}
                    className="p-2 bg-zinc-800 hover:bg-red-900/50 rounded-lg text-zinc-200 hover:text-red-400 transition-colors"
                    title="Delete agent"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Create Agent Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-zinc-900 rounded-2xl border border-zinc-800 p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white">Create New Agent</h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-medium text-white mb-3">Choose Template</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(AGENT_TEMPLATES).map(([key, template]) => (
                      <button
                        key={key}
                        onClick={() => createAgent(key as keyof typeof AGENT_TEMPLATES)}
                        className="p-4 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700 hover:border-zinc-600 rounded-lg text-left transition-colors"
                      >
                        <div className="font-medium text-white mb-1">{template.name}</div>
                        <div className="text-sm text-zinc-400 mb-2">{template.description}</div>
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-1 text-xs rounded border ${getUseCaseColor(template.use_case)}`}>
                            {template.use_case}
                          </span>
                          <span className="text-xs text-zinc-500">{MODEL_PERFORMANCE[template.model_name]?.name}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                
                <div className="border-t border-zinc-800 pt-4">
                  <button
                    onClick={() => createAgent()}
                    className="w-full p-4 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700 hover:border-zinc-600 rounded-lg transition-colors"
                  >
                    <div className="font-medium text-white mb-1">Custom Agent</div>
                    <div className="text-sm text-zinc-400">Start with a blank template</div>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Edit Agent Modal */}
        {editingAgent && (
          <AgentEditModal
            agent={editingAgent}
            models={models}
            onSave={(updatedAgent) => {
              saveAgent(updatedAgent);
              setEditingAgent(null);
            }}
            onCancel={() => setEditingAgent(null)}
            isSaving={saving === editingAgent.id}
          />
        )}
      </div>
    </div>
  );
};

// Agent Edit Modal Component
interface AgentEditModalProps {
  agent: Agent;
  models: string[];
  onSave: (agent: Agent) => void;
  onCancel: () => void;
  isSaving: boolean;
}

const AgentEditModal: React.FC<AgentEditModalProps> = ({ 
  agent, 
  models, 
  onSave, 
  onCancel, 
  isSaving 
}) => {
  const [editedAgent, setEditedAgent] = useState<Agent>({ ...agent });
  const [activeTab, setActiveTab] = useState<'basic' | 'prompt' | 'advanced'>('basic');

  const updateField = (field: string, value: any) => {
    if (field.includes('.')) {
      const [parent, child] = field.split('.');
      setEditedAgent(prev => ({
        ...prev,
        [parent]: { ...(prev[parent as keyof Agent] as Record<string, unknown>), [child]: value }
      }));
    } else {
      setEditedAgent(prev => ({ ...prev, [field]: value }));
    }
  };

  const tabs = [
    { id: 'basic', label: 'Basic Settings', icon: Settings },
    { id: 'prompt', label: 'System Prompt', icon: Database },
    { id: 'advanced', label: 'Advanced', icon: Cpu },
  ];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 rounded-2xl border border-zinc-800 p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-white">Edit Agent: {editedAgent.name}</h2>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-zinc-800">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-zinc-800 text-white border-b-2 border-purple-500'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="space-y-6">
          {activeTab === 'basic' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Agent Name</label>
                  <input
                    type="text"
                    value={editedAgent.name}
                    onChange={(e) => updateField('name', e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Use Case</label>
                  <select
                    value={editedAgent.use_case}
                    onChange={(e) => updateField('use_case', e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="live">Live Analysis</option>
                    <option value="final">Final Analysis</option>
                    <option value="custom">Custom Purpose</option>
                    <option value="general">General Purpose</option>
                  </select>
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">Description</label>
                <textarea
                  value={editedAgent.description}
                  onChange={(e) => updateField('description', e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Model</label>
                  <select
                    value={editedAgent.model_name}
                    onChange={(e) => updateField('model_name', e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  >
                    {models.map(model => (
                      <option key={model} value={model}>
                        {MODEL_PERFORMANCE[model]?.name || model}
                      </option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Provider</label>
                  <select
                    value={editedAgent.provider_type}
                    onChange={(e) => updateField('provider_type', e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="llamacpp">llama.cpp Vulkan (Local)</option>
                    <option value="ollama">Ollama (Local)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'prompt' && (
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">System Prompt</label>
              <textarea
                value={editedAgent.system_prompt}
                onChange={(e) => updateField('system_prompt', e.target.value)}
                rows={20}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500 font-mono text-sm"
                placeholder="Define how this agent should behave..."
              />
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    Temperature: {editedAgent.model_settings.temperature}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={editedAgent.model_settings.temperature}
                    onChange={(e) => updateField('model_settings.temperature', parseFloat(e.target.value))}
                    className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                  />
                  <div className="flex justify-between text-xs text-zinc-500 mt-1">
                    <span>Focused</span>
                    <span>Creative</span>
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Max Tokens</label>
                  <input
                    type="number"
                    value={editedAgent.model_settings.max_tokens}
                    onChange={(e) => updateField('model_settings.max_tokens', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    min="128"
                    max="8192"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Context Length</label>
                  <select
                    value={editedAgent.model_settings.context_length}
                    onChange={(e) => updateField('model_settings.context_length', e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="8K">8K tokens</option>
                    <option value="16K">16K tokens</option>
                    <option value="32K">32K tokens</option>
                    <option value="128K">128K tokens</option>
                  </select>
                </div>
              </div>
              
              {/* Model Performance Info */}
              {MODEL_PERFORMANCE[editedAgent.model_name] && (
                <div className="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700">
                  <h4 className="font-medium text-white mb-3">Model Performance</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <span className="text-zinc-400">Speed</span>
                      <div className="text-green-400">{MODEL_PERFORMANCE[editedAgent.model_name].speed}</div>
                    </div>
                    <div>
                      <span className="text-zinc-400">Memory</span>
                      <div className="text-blue-400">{MODEL_PERFORMANCE[editedAgent.model_name].memory}</div>
                    </div>
                    <div>
                      <span className="text-zinc-400">Best For</span>
                      <div className="text-purple-400">{MODEL_PERFORMANCE[editedAgent.model_name].best_for}</div>
                    </div>
                    <div>
                      <span className="text-zinc-400">Status</span>
                      <div className="text-green-400">Ready</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-4 mt-8 pt-6 border-t border-zinc-800">
          <button
            onClick={() => onSave(editedAgent)}
            disabled={isSaving}
            className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl font-medium transition-colors disabled:opacity-50"
          >
            <Save className="w-5 h-5" />
            {isSaving ? 'Saving...' : 'Save Agent'}
          </button>
          
          <button
            onClick={onCancel}
            className="px-6 py-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-xl font-medium transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};