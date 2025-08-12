import React, { useState, useEffect } from 'react';
import {
  Brain, Zap, FileCheck, Settings, Save, RotateCcw,
  ChevronDown, ChevronUp, Info, AlertCircle, CheckCircle,
  Cpu, Cloud, Server, Timer, Volume2, MessageSquare
} from 'lucide-react';
import { config } from '../config';

// Agent Types - 3 Agent Architecture
interface AgentConfig {
  id: string;
  name: string;
  displayName: string;
  description: string;
  icon: React.ComponentType<{className?: string}>;
  color: string;
  purpose: string;
  provider: 'local' | 'openai' | 'anthropic' | 'gemma' | 'custom';
  model: string;
  settings: {
    temperature: number;
    maxTokens: number;
    updateInterval: number; // seconds
    priority: 'speed' | 'accuracy' | 'balanced';
    contextWindow: number;
    streaming: boolean;
  };
  endpoints: {
    generate: string;
    stream: string;
    config: string;
  };
}

const DEFAULT_AGENTS: AgentConfig[] = [
  {
    id: 'hermes',
    name: 'hermes',
    displayName: 'Hermes (Live Agent)',
    description: 'Fast real-time summarization during meetings',
    icon: Zap,
    color: 'purple',
    purpose: 'Live note-taking, key point extraction, real-time summaries',
    provider: 'local',
    model: 'gemma3n:e4b',
    settings: {
      temperature: 0.3,
      maxTokens: 1024,
      updateInterval: 30,
      priority: 'speed',
      contextWindow: 4096,
      streaming: true
    },
    endpoints: {
      generate: '/api/agents/hermes/generate',
      stream: '/api/agents/hermes/stream',
      config: '/api/agents/hermes/config'
    }
  },
  {
    id: 'athena',
    name: 'athena',
    displayName: 'Athena (Analysis Agent)',
    description: 'Comprehensive post-meeting analysis and reports',
    icon: Brain,
    color: 'blue',
    purpose: 'Deep analysis, comprehensive reports, strategic insights',
    provider: 'local',
    model: 'gemma3n:latest',
    settings: {
      temperature: 0.7,
      maxTokens: 8192,
      updateInterval: 300,
      priority: 'accuracy',
      contextWindow: 32768,
      streaming: false
    },
    endpoints: {
      generate: '/api/agents/athena/generate',
      stream: '/api/agents/athena/stream',
      config: '/api/agents/athena/config'
    }
  },
  {
    id: 'minerva',
    name: 'minerva',
    displayName: 'Minerva (Correction Agent)',
    description: 'Transcript correction and vocabulary enhancement',
    icon: FileCheck,
    color: 'green',
    purpose: 'Transcription correction, custom vocabulary, context enhancement',
    provider: 'local',
    model: 'gemma3n:small',
    settings: {
      temperature: 0.1,
      maxTokens: 2048,
      updateInterval: 60,
      priority: 'accuracy',
      contextWindow: 8192,
      streaming: false
    },
    endpoints: {
      generate: '/api/agents/minerva/generate',
      stream: '/api/agents/minerva/stream',
      config: '/api/agents/minerva/config'
    }
  }
];

const MODEL_OPTIONS = {
  local: [
    'gemma3n:e4b',
    'gemma3n:latest',
    'gemma3n:small',
    'gemma2b:latest',
    'llama3.2:3b',
    'llama3.2:1b',
    'qwen2.5:3b',
    'phi3:mini'
  ],
  openai: [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-turbo',
    'gpt-3.5-turbo'
  ],
  anthropic: [
    'claude-3-5-sonnet-20241022',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229'
  ]
};

interface WhisperConfig {
  model: 'large-v3' | 'large-v2' | 'large' | 'medium' | 'small' | 'base';
  device: 'npu' | 'gpu' | 'cpu';
  diarization: boolean;
  wordTimestamps: boolean;
  vad: boolean;
  language: 'auto' | 'en' | 'es' | 'fr' | 'de' | 'it' | 'pt' | 'ru' | 'ja' | 'zh';
  accuracy: 'highest' | 'high' | 'balanced' | 'fast';
  retranscription: 'always' | 'on_completion' | 'manual' | 'never';
}

export const AgentConfiguration: React.FC = () => {
  const [agents, setAgents] = useState<AgentConfig[]>(DEFAULT_AGENTS);
  const [whisperConfig, setWhisperConfig] = useState<WhisperConfig>({
    model: 'large-v3',
    device: 'npu',
    diarization: true,
    wordTimestamps: true,
    vad: true,
    language: 'auto',
    accuracy: 'highest',
    retranscription: 'on_completion'
  });
  const [expandedAgent, setExpandedAgent] = useState<string | null>('hermes');
  const [isDirty, setIsDirty] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');

  // Load configuration from backend
  useEffect(() => {
    loadConfiguration();
  }, []);

  const loadConfiguration = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/agents/configuration`);
      if (response.ok) {
        const data = await response.json();
        if (data.agents) setAgents(data.agents);
        if (data.whisper) setWhisperConfig(data.whisper);
      }
    } catch (error) {
      console.error('Failed to load agent configuration:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const saveConfiguration = async () => {
    setSaveStatus('saving');
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/agents/configuration`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          agents,
          whisper: whisperConfig
        })
      });

      if (response.ok) {
        setSaveStatus('success');
        setIsDirty(false);
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
        setTimeout(() => setSaveStatus('idle'), 3000);
      }
    } catch (error) {
      console.error('Failed to save configuration:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  };

  const resetToDefaults = () => {
    setAgents(DEFAULT_AGENTS);
    setWhisperConfig({
      model: 'large-v3',
      device: 'npu',
      diarization: true,
      wordTimestamps: true,
      vad: true,
      language: 'auto',
      accuracy: 'highest',
      retranscription: 'on_completion'
    });
    setIsDirty(true);
  };

  const updateAgent = (agentId: string, updates: Partial<AgentConfig>) => {
    setAgents(prev => prev.map(agent => 
      agent.id === agentId ? { ...agent, ...updates } : agent
    ));
    setIsDirty(true);
  };

  const updateAgentSettings = (agentId: string, settings: Partial<AgentConfig['settings']>) => {
    setAgents(prev => prev.map(agent => 
      agent.id === agentId 
        ? { ...agent, settings: { ...agent.settings, ...settings } }
        : agent
    ));
    setIsDirty(true);
  };

  const getProviderIcon = (provider: string) => {
    switch (provider) {
      case 'local': return Server;
      case 'openai': case 'anthropic': return Cloud;
      case 'custom': return Cpu;
      default: return Server;
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Agent Configuration</h2>
          <p className="text-gray-400 text-sm mt-1">
            Configure the 3-agent AI system for transcription, analysis, and correction
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={resetToDefaults}
            className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
          >
            <RotateCcw className="w-4 h-4 mr-2 inline" />
            Reset Defaults
          </button>
          <button
            onClick={saveConfiguration}
            disabled={!isDirty || saveStatus === 'saving'}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              !isDirty 
                ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                : saveStatus === 'saving'
                ? 'bg-blue-600/50 text-blue-300 cursor-wait'
                : saveStatus === 'success'
                ? 'bg-green-600 text-white'
                : saveStatus === 'error'
                ? 'bg-red-600 text-white'
                : 'bg-blue-600 hover:bg-blue-500 text-white'
            }`}
          >
            {saveStatus === 'saving' && <Timer className="w-4 h-4 mr-2 inline animate-spin" />}
            {saveStatus === 'success' && <CheckCircle className="w-4 h-4 mr-2 inline" />}
            {saveStatus === 'error' && <AlertCircle className="w-4 h-4 mr-2 inline" />}
            {saveStatus === 'idle' && <Save className="w-4 h-4 mr-2 inline" />}
            {saveStatus === 'saving' ? 'Saving...' : 
             saveStatus === 'success' ? 'Saved!' :
             saveStatus === 'error' ? 'Failed' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* WhisperX Configuration */}
      <div className="mb-8 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
        <div className="flex items-center gap-2 mb-4">
          <Volume2 className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">WhisperX Transcription</h3>
          <div className="ml-auto px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">
            NPU Optimized
          </div>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Model</label>
            <select
              value={whisperConfig.model}
              onChange={(e) => {
                setWhisperConfig(prev => ({ ...prev, model: e.target.value as any }));
                setIsDirty(true);
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            >
              <option value="large-v3">Large-v3 (Best)</option>
              <option value="large-v2">Large-v2</option>
              <option value="large">Large</option>
              <option value="medium">Medium</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs text-gray-400 mb-1">Device</label>
            <select
              value={whisperConfig.device}
              onChange={(e) => {
                setWhisperConfig(prev => ({ ...prev, device: e.target.value as any }));
                setIsDirty(true);
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            >
              <option value="npu">NPU (220x faster)</option>
              <option value="gpu">GPU</option>
              <option value="cpu">CPU</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs text-gray-400 mb-1">Retranscription</label>
            <select
              value={whisperConfig.retranscription}
              onChange={(e) => {
                setWhisperConfig(prev => ({ ...prev, retranscription: e.target.value as any }));
                setIsDirty(true);
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            >
              <option value="on_completion">After Recording</option>
              <option value="always">Always</option>
              <option value="manual">Manual Only</option>
              <option value="never">Never</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs text-gray-400 mb-1">Features</label>
            <div className="flex flex-col gap-1">
              <label className="flex items-center text-xs text-gray-300">
                <input
                  type="checkbox"
                  checked={whisperConfig.diarization}
                  onChange={(e) => {
                    setWhisperConfig(prev => ({ ...prev, diarization: e.target.checked }));
                    setIsDirty(true);
                  }}
                  className="mr-2 rounded bg-gray-700"
                />
                Diarization
              </label>
              <label className="flex items-center text-xs text-gray-300">
                <input
                  type="checkbox"
                  checked={whisperConfig.wordTimestamps}
                  onChange={(e) => {
                    setWhisperConfig(prev => ({ ...prev, wordTimestamps: e.target.checked }));
                    setIsDirty(true);
                  }}
                  className="mr-2 rounded bg-gray-700"
                />
                Word Timestamps
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Agent Configuration */}
      <div className="space-y-4">
        {agents.map((agent) => {
          const Icon = agent.icon;
          const ProviderIcon = getProviderIcon(agent.provider);
          const isExpanded = expandedAgent === agent.id;
          
          return (
            <div key={agent.id} className="bg-gray-800/50 rounded-lg border border-gray-700">
              <button
                onClick={() => setExpandedAgent(isExpanded ? null : agent.id)}
                className="w-full p-4 flex items-center justify-between hover:bg-gray-800/70 transition-colors rounded-lg"
              >
                <div className="flex items-center gap-4">
                  <div className={`p-2 rounded-lg bg-${agent.color}-500/20`}>
                    <Icon className={`w-5 h-5 text-${agent.color}-400`} />
                  </div>
                  <div className="text-left">
                    <h4 className="text-white font-medium">{agent.displayName}</h4>
                    <p className="text-gray-400 text-sm">{agent.description}</p>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    <ProviderIcon className="w-4 h-4 text-gray-400" />
                    <span className="text-xs text-gray-400 uppercase">{agent.provider}</span>
                  </div>
                </div>
                {isExpanded ? (
                  <ChevronUp className="w-5 h-5 text-gray-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-gray-400" />
                )}
              </button>
              
              {isExpanded && (
                <div className="p-4 border-t border-gray-700">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Basic Configuration */}
                    <div>
                      <h5 className="text-sm font-medium text-white mb-3">Model Configuration</h5>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Provider</label>
                          <select
                            value={agent.provider}
                            onChange={(e) => updateAgent(agent.id, { provider: e.target.value as any })}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                          >
                            <option value="local">Local (Ollama)</option>
                            <option value="openai">OpenAI</option>
                            <option value="anthropic">Anthropic</option>
                            <option value="custom">Custom</option>
                          </select>
                        </div>
                        
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Model</label>
                          <select
                            value={agent.model}
                            onChange={(e) => updateAgent(agent.id, { model: e.target.value })}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                          >
                            {MODEL_OPTIONS[agent.provider]?.map(model => (
                              <option key={model} value={model}>{model}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>
                    
                    {/* Advanced Settings */}
                    <div>
                      <h5 className="text-sm font-medium text-white mb-3">Performance Settings</h5>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">
                            Temperature: {agent.settings.temperature}
                          </label>
                          <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.1"
                            value={agent.settings.temperature}
                            onChange={(e) => updateAgentSettings(agent.id, { 
                              temperature: parseFloat(e.target.value) 
                            })}
                            className="w-full"
                          />
                        </div>
                        
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Update Interval (seconds)</label>
                          <input
                            type="number"
                            min="10"
                            max="600"
                            value={agent.settings.updateInterval}
                            onChange={(e) => updateAgentSettings(agent.id, { 
                              updateInterval: parseInt(e.target.value) 
                            })}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                          />
                        </div>
                        
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Priority</label>
                          <select
                            value={agent.settings.priority}
                            onChange={(e) => updateAgentSettings(agent.id, { 
                              priority: e.target.value as any 
                            })}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                          >
                            <option value="speed">Speed (Lower accuracy)</option>
                            <option value="balanced">Balanced</option>
                            <option value="accuracy">Accuracy (Slower)</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Purpose and Role */}
                  <div className="mt-4 p-3 bg-gray-900/50 rounded border">
                    <div className="flex items-start gap-2">
                      <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs font-medium text-blue-400 mb-1">Purpose & Role</p>
                        <p className="text-xs text-gray-300">{agent.purpose}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      
      {/* Status Information */}
      <div className="mt-6 p-4 bg-gray-800/30 rounded border border-gray-700">
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <MessageSquare className="w-4 h-4" />
          <span>
            3-Agent System: Hermes (Live) → Minerva (Correction) → Athena (Analysis)
          </span>
        </div>
      </div>
    </div>
  );
};