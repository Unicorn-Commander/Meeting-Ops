import React, { useState, useEffect } from 'react';
import { Settings, Brain, Sliders, Save, RefreshCw, Info, ChevronDown, ChevronUp, FileText, Sparkles, Copy } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface LLMSettings {
  default_model: string;
  system_prompt: string;
  custom_instructions: string;
  parameters: {
    temperature: number;
    top_p: number;
    max_tokens: number;
    frequency_penalty: number;
    presence_penalty: number;
    num_ctx?: number;
    num_predict?: number;
    num_gpu?: number;
  };
}

const DEFAULT_PROMPTS = [
  {
    name: "Professional Summary",
    prompt: "You are a professional meeting assistant. Create clear, concise meeting summaries with a focus on key decisions, action items, and important discussions. Use professional language and structured formatting.",
    instructions: "Focus on clarity and actionable outcomes. Include participant names when relevant."
  },
  {
    name: "Detailed Minutes",
    prompt: "You are a meticulous meeting recorder. Capture comprehensive meeting minutes including all topics discussed, decisions made, action items assigned, and important quotes. Maintain chronological order.",
    instructions: "Include timestamps for major topics. Note who said what for important decisions."
  },
  {
    name: "Action-Focused",
    prompt: "You are an action-oriented meeting assistant. Prioritize extracting and organizing action items, deadlines, and responsibilities. Summarize discussions only as they relate to actionable outcomes.",
    instructions: "Bold action items. Include owner and due date for each task. Group by priority."
  },
  {
    name: "Executive Brief",
    prompt: "You are an executive assistant creating brief, high-level summaries for leadership. Focus on strategic decisions, key metrics, and critical issues. Keep summaries under 200 words.",
    instructions: "Use bullet points. Lead with most important information. Omit minor details."
  },
  {
    name: "Technical Discussion",
    prompt: "You are a technical meeting specialist. Accurately capture technical details, architecture decisions, code discussions, and engineering trade-offs. Preserve technical terminology.",
    instructions: "Include code snippets or technical diagrams mentioned. Note any technical decisions or blockers."
  }
];

export const LLMSettingsPanel: React.FC = () => {
  const [settings, setSettings] = useState<LLMSettings>({
    default_model: 'gemma3n:latest',
    system_prompt: 'You are a helpful meeting assistant that creates clear, concise meeting summaries.',
    custom_instructions: '',
    parameters: {
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 2048,
      frequency_penalty: 0.0,
      presence_penalty: 0.0,
      num_ctx: 4096,
      num_predict: 2048,
      num_gpu: 999
    }
  });

  const [isLoading, setIsLoading] = useState(false);
  const [savedMessage, setSavedMessage] = useState('');
  const [expandedSections, setExpandedSections] = useState<{[key: string]: boolean}>({
    model: true,
    prompt: false,
    params: false
  });
  const [showPromptPresets, setShowPromptPresets] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/llm/settings', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (error) {
      console.error('Error loading LLM settings:', error);
    }
  };

  const saveSettings = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/llm/settings', {
        method: 'PUT',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
      });
      
      if (response.ok) {
        setSavedMessage('Settings saved successfully!');
        setTimeout(() => setSavedMessage(''), 3000);
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      setSavedMessage('Error saving settings');
    } finally {
      setIsLoading(false);
    }
  };

  const resetToDefaults = () => {
    setSettings({
      default_model: 'gemma3n:latest',
      system_prompt: 'You are a helpful meeting assistant that creates clear, concise meeting summaries.',
      custom_instructions: '',
      parameters: {
        temperature: 0.7,
        top_p: 0.9,
        max_tokens: 2048,
        frequency_penalty: 0.0,
        presence_penalty: 0.0,
        num_ctx: 4096,
        num_predict: 2048,
        num_gpu: 999
      }
    });
  };

  const updateParameter = (key: string, value: number) => {
    setSettings(prev => ({
      ...prev,
      parameters: {
        ...prev.parameters,
        [key]: value
      }
    }));
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const getTemperatureDescription = (temp: number) => {
    if (temp < 0.3) return 'Very focused and deterministic';
    if (temp < 0.7) return 'Balanced creativity and consistency';
    if (temp < 1.0) return 'Creative with some variation';
    return 'Very creative and unpredictable';
  };

  const applyPromptPreset = (preset: typeof DEFAULT_PROMPTS[0]) => {
    setSettings(prev => ({
      ...prev,
      system_prompt: preset.prompt,
      custom_instructions: preset.instructions
    }));
    setShowPromptPresets(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Brain className="h-5 w-5 text-green-400" />
          LLM Settings
        </h3>
        <div className="flex items-center gap-2">
          {savedMessage && (
            <span className="text-sm text-green-600 animate-fade-in">{savedMessage}</span>
          )}
          <Tooltip content="Reset all settings to defaults">
            <button
              onClick={resetToDefaults}
              className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Reset
            </button>
          </Tooltip>
          <button
            onClick={saveSettings}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save className="h-4 w-4" />
            Save Settings
          </button>
        </div>
      </div>

      {/* Model Selection */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <button
          onClick={() => toggleSection('model')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <Brain className="h-5 w-5 text-green-600" />
            </div>
            <div className="text-left">
              <h4 className="font-medium">Model Selection</h4>
              <p className="text-sm text-gray-500">Choose the AI model for summarization</p>
            </div>
          </div>
          {expandedSections.model ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
        </button>
        
        {expandedSections.model && (
          <div className="border-t border-gray-200 p-4">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Default Model
                  <Tooltip content="The Ollama model used for meeting summarization">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="text"
                  value={settings.default_model}
                  onChange={(e) => setSettings(prev => ({ ...prev, default_model: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g., gemma3n:latest"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Currently using: <span className="font-medium">{settings.default_model}</span>
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* System Prompt */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <button
          onClick={() => toggleSection('prompt')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <FileText className="h-5 w-5 text-purple-600" />
            </div>
            <div className="text-left">
              <h4 className="font-medium">System Prompt & Instructions</h4>
              <p className="text-sm text-gray-500">Customize AI behavior and output</p>
            </div>
          </div>
          {expandedSections.prompt ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
        </button>
        
        {expandedSections.prompt && (
          <div className="border-t border-gray-200 p-4">
            <div className="space-y-4">
              {/* Prompt Presets */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Prompt Presets
                    <Tooltip content="Choose from pre-configured prompts for different meeting types">
                      <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                    </Tooltip>
                  </label>
                  <button
                    onClick={() => setShowPromptPresets(!showPromptPresets)}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    {showPromptPresets ? 'Hide' : 'Show'} Presets
                  </button>
                </div>
                
                {showPromptPresets && (
                  <div className="space-y-2 mb-4">
                    {DEFAULT_PROMPTS.map((preset, idx) => (
                      <div key={idx} className="bg-gray-50 rounded-lg p-3 hover:bg-gray-100 transition-colors">
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <h5 className="font-medium text-sm">{preset.name}</h5>
                            <p className="text-xs text-gray-600 mt-1">{preset.prompt.substring(0, 100)}...</p>
                          </div>
                          <button
                            onClick={() => applyPromptPreset(preset)}
                            className="ml-4 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                          >
                            Use This
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  System Prompt
                  <Tooltip content="Defines the AI's role and general behavior">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <textarea
                  value={settings.system_prompt}
                  onChange={(e) => setSettings(prev => ({ ...prev, system_prompt: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  rows={4}
                  placeholder="Enter the system prompt..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Custom Instructions
                  <Tooltip content="Additional specific instructions for this deployment">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <textarea
                  value={settings.custom_instructions}
                  onChange={(e) => setSettings(prev => ({ ...prev, custom_instructions: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  rows={3}
                  placeholder="Additional instructions for specific needs..."
                />
                <p className="text-xs text-gray-500 mt-1">
                  Examples: Focus on action items, use specific terminology, format preferences
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Parameters */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <button
          onClick={() => toggleSection('params')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Sliders className="h-5 w-5 text-blue-600" />
            </div>
            <div className="text-left">
              <h4 className="font-medium">Generation Parameters</h4>
              <p className="text-sm text-gray-500">Fine-tune model behavior</p>
            </div>
          </div>
          {expandedSections.params ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
        </button>
        
        {expandedSections.params && (
          <div className="border-t border-gray-200 p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Temperature */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Temperature: {settings.parameters.temperature}
                  <Tooltip content="Controls randomness in generation. Lower = more focused, Higher = more creative">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={settings.parameters.temperature}
                  onChange={(e) => updateParameter('temperature', parseFloat(e.target.value))}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {getTemperatureDescription(settings.parameters.temperature)}
                </p>
              </div>

              {/* Top P */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Top P: {settings.parameters.top_p}
                  <Tooltip content="Nucleus sampling - consider only tokens with cumulative probability">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={settings.parameters.top_p}
                  onChange={(e) => updateParameter('top_p', parseFloat(e.target.value))}
                  className="w-full"
                />
              </div>

              {/* Max Tokens */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Tokens
                  <Tooltip content="Maximum length of the generated summary">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="number"
                  value={settings.parameters.max_tokens}
                  onChange={(e) => updateParameter('max_tokens', parseInt(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="128"
                  max="8192"
                />
              </div>

              {/* Context Window */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Context Window
                  <Tooltip content="Total context size available to the model">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="number"
                  value={settings.parameters.num_ctx || 4096}
                  onChange={(e) => updateParameter('num_ctx', parseInt(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="2048"
                  max="32768"
                />
              </div>

              {/* Frequency Penalty */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Frequency Penalty: {settings.parameters.frequency_penalty}
                  <Tooltip content="Reduces repetition by penalizing frequently used tokens">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="range"
                  min="-2"
                  max="2"
                  step="0.1"
                  value={settings.parameters.frequency_penalty}
                  onChange={(e) => updateParameter('frequency_penalty', parseFloat(e.target.value))}
                  className="w-full"
                />
              </div>

              {/* Presence Penalty */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Presence Penalty: {settings.parameters.presence_penalty}
                  <Tooltip content="Encourages the model to talk about new topics">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <input
                  type="range"
                  min="-2"
                  max="2"
                  step="0.1"
                  value={settings.parameters.presence_penalty}
                  onChange={(e) => updateParameter('presence_penalty', parseFloat(e.target.value))}
                  className="w-full"
                />
              </div>

              {/* GPU Layers */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  GPU Layers
                  <Tooltip content="Number of model layers to offload to GPU. 999 = all layers">
                    <Info className="inline-block ml-1 h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
                <div className="flex items-center gap-4">
                  <input
                    type="number"
                    value={settings.parameters.num_gpu || 999}
                    onChange={(e) => updateParameter('num_gpu', parseInt(e.target.value))}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    min="0"
                    max="999"
                  />
                  <span className="text-sm text-gray-500">
                    {settings.parameters.num_gpu === 999 ? 'All layers on GPU' : `${settings.parameters.num_gpu} layers`}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Sparkles className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-800">
            <p className="font-medium mb-1">Ollama Integration</p>
            <p>
              These settings configure how the LLM generates meeting summaries. 
              The system uses Ollama running locally for privacy and performance.
              GPU acceleration is enabled for optimal speed.
            </p>
            <p className="mt-2">
              <strong>Tip:</strong> Lower temperature values (0.3-0.7) work best for 
              factual meeting summaries, while higher values can be used for creative brainstorming sessions.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};