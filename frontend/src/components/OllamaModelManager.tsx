import React, { useState, useEffect } from 'react';
import { Trash2, Download, Play, Settings, Search, Cpu, Zap, HardDrive, Info, ChevronDown, ChevronUp, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface OllamaModel {
  name: string;
  size: number;
  size_human: string;
  modified: string;
  digest: string;
  details: any;
}

interface AvailableModel {
  name: string;
  description: string;
  size: string;
  use_case: string;
}

export const OllamaModelManager: React.FC = () => {
  const [installedModels, setInstalledModels] = useState<OllamaModel[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [runningModels, setRunningModels] = useState<any[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<{[key: string]: number}>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [testPrompt, setTestPrompt] = useState('Hello, how are you?');
  const [testResult, setTestResult] = useState<{[key: string]: any}>({});
  const [expandedSections, setExpandedSections] = useState<{[key: string]: boolean}>({
    installed: true,
    available: true,
    test: false
  });

  useEffect(() => {
    loadModels();
    searchAvailableModels();
  }, []);

  const loadModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/ollama/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setInstalledModels(data.models || []);
      }

      // Load running models
      const runningResp = await fetch('/api/ai/ollama/running', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (runningResp.ok) {
        const runningData = await runningResp.json();
        setRunningModels(runningData.models || []);
      }
    } catch (error) {
      console.error('Error loading models:', error);
    }
  };

  const searchAvailableModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/ollama/search?query=${searchQuery}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAvailableModels(data.models || []);
      }
    } catch (error) {
      console.error('Error searching models:', error);
    }
  };

  const downloadModel = async (modelName: string) => {
    setIsLoading(true);
    setDownloadProgress(prev => ({ ...prev, [modelName]: 0 }));

    try {
      const token = localStorage.getItem('access_token');
      
      // Start download
      const response = await fetch('/api/ai/ollama/pull', {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ model_name: modelName })
      });

      if (response.ok) {
        // Simulate progress (in real implementation, use WebSocket)
        const interval = setInterval(() => {
          setDownloadProgress(prev => {
            const current = prev[modelName] || 0;
            if (current >= 100) {
              clearInterval(interval);
              loadModels();
              return prev;
            }
            return { ...prev, [modelName]: current + 10 };
          });
        }, 1000);
      }
    } catch (error) {
      console.error('Error downloading model:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteModel = async (modelName: string) => {
    if (!confirm(`Delete model ${modelName}?`)) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/ollama/models/${encodeURIComponent(modelName)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        loadModels();
      }
    } catch (error) {
      console.error('Error deleting model:', error);
    }
  };

  const testModel = async (modelName: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/ollama/test', {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          model_name: modelName,
          prompt: testPrompt 
        })
      });

      if (response.ok) {
        const result = await response.json();
        setTestResult(prev => ({ ...prev, [modelName]: result }));
      }
    } catch (error) {
      console.error('Error testing model:', error);
    }
  };

  const getModelInfo = async (modelName: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/ollama/models/${encodeURIComponent(modelName)}/info`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const info = await response.json();
        console.log('Model info:', info);
        // Could show in a modal
      }
    } catch (error) {
      console.error('Error getting model info:', error);
    }
  };

  const isModelRunning = (modelName: string) => {
    return runningModels.some(m => m.name === modelName);
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Cpu className="h-5 w-5 text-blue-400" />
            Ollama Model Manager
          </h3>
          <Tooltip content="Manage AI models for meeting summarization. Ollama runs locally for privacy.">
            <Info className="h-4 w-4 text-gray-400" />
          </Tooltip>
        </div>

        {/* Installed Models Section */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 mb-6">
          <button
            onClick={() => toggleSection('installed')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                <HardDrive className="h-5 w-5 text-blue-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">Installed Models</h4>
                <p className="text-sm text-gray-500">{installedModels.length} models ready to use</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {installedModels.length > 0 && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                  Active
                </span>
              )}
              {expandedSections.installed ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
            </div>
          </button>
          
          {expandedSections.installed && (
            <div className="border-t border-gray-200 p-4">
              {installedModels.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <HardDrive className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p>No models installed yet</p>
                  <p className="text-sm mt-1">Download a model from the available models below</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {installedModels.map(model => (
                    <div key={model.name} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h5 className="font-medium">{model.name}</h5>
                            {isModelRunning(model.name) && (
                              <Tooltip content="Model is currently loaded in memory">
                                <span className="flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                                  <Zap className="h-3 w-3" />
                                  Running
                                </span>
                              </Tooltip>
                            )}
                          </div>
                          <div className="flex items-center gap-4 text-sm text-gray-500">
                            <span className="flex items-center gap-1">
                              <HardDrive className="h-3 w-3" />
                              {model.size_human}
                            </span>
                            <span>Modified: {new Date(model.modified).toLocaleDateString()}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Tooltip content="Test this model with a prompt">
                            <button
                              onClick={() => testModel(model.name)}
                              className="p-2 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                            >
                              <Play className="h-4 w-4" />
                            </button>
                          </Tooltip>
                          <Tooltip content="View model details">
                            <button
                              onClick={() => getModelInfo(model.name)}
                              className="p-2 text-gray-600 hover:bg-gray-100 rounded transition-colors"
                            >
                              <Settings className="h-4 w-4" />
                            </button>
                          </Tooltip>
                          <Tooltip content="Delete this model">
                            <button
                              onClick={() => deleteModel(model.name)}
                              className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </Tooltip>
                        </div>
                      </div>

                      {/* Test Result */}
                      {testResult[model.name] && (
                        <div className="mt-3 p-3 bg-white rounded border border-gray-200">
                          <div className="flex items-start gap-2">
                            <CheckCircle className="h-4 w-4 text-green-500 mt-0.5" />
                            <div className="flex-1 text-sm">
                              <p className="font-medium mb-1">Test Result:</p>
                              <p className="text-gray-700">{testResult[model.name].response}</p>
                              <p className="text-xs text-gray-500 mt-2">
                                Speed: {testResult[model.name].tokens_per_second?.toFixed(1)} tokens/sec
                              </p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Available Models Section */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 mb-6">
          <button
            onClick={() => toggleSection('available')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                <Download className="h-5 w-5 text-purple-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">Available Models</h4>
                <p className="text-sm text-gray-500">Download new models from Ollama library</p>
              </div>
            </div>
            {expandedSections.available ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
          </button>
          
          {expandedSections.available && (
            <div className="border-t border-gray-200 p-4">
              {/* Search Bar */}
              <div className="mb-4">
                <div className="relative">
                  <Search className="h-4 w-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyUp={(e) => e.key === 'Enter' && searchAvailableModels()}
                    placeholder="Search models..."
                    className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <Tooltip content="Press Enter to search">
                    <Info className="h-4 w-4 absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                  </Tooltip>
                </div>
              </div>

              <div className="space-y-3">
                {availableModels.map(model => {
                  const isInstalled = installedModels.some(m => m.name === model.name);
                  const progress = downloadProgress[model.name];

                  return (
                    <div key={model.name} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h5 className="font-medium mb-1">{model.name}</h5>
                          <p className="text-sm text-gray-600 mb-2">{model.description}</p>
                          <div className="flex items-center gap-4 text-xs text-gray-500">
                            <span className="flex items-center gap-1">
                              <HardDrive className="h-3 w-3" />
                              {model.size}
                            </span>
                            <span className="flex items-center gap-1">
                              <Zap className="h-3 w-3" />
                              {model.use_case}
                            </span>
                          </div>
                        </div>
                        <div className="ml-4">
                          {isInstalled ? (
                            <div className="flex items-center gap-1 text-green-600 text-sm">
                              <CheckCircle className="h-4 w-4" />
                              <span>Installed</span>
                            </div>
                          ) : progress !== undefined ? (
                            <div className="w-32">
                              <div className="flex items-center gap-2 mb-1">
                                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                                <span className="text-sm text-blue-600">Downloading</span>
                              </div>
                              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                                <div 
                                  className="h-2 bg-blue-600 rounded-full transition-all duration-300"
                                  style={{ width: `${progress}%` }}
                                />
                              </div>
                              <p className="text-xs text-center mt-1 text-gray-500">{progress}%</p>
                            </div>
                          ) : (
                            <Tooltip content="Download this model to use it for summarization">
                              <button
                                onClick={() => downloadModel(model.name)}
                                disabled={isLoading}
                                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                              >
                                <Download className="h-4 w-4" />
                                Download
                              </button>
                            </Tooltip>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Test Prompt Section */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <button
            onClick={() => toggleSection('test')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                <Play className="h-5 w-5 text-green-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">Test Models</h4>
                <p className="text-sm text-gray-500">Try models with custom prompts</p>
              </div>
            </div>
            {expandedSections.test ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
          </button>
          
          {expandedSections.test && (
            <div className="border-t border-gray-200 p-4">
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Test Prompt</label>
                  <textarea
                    value={testPrompt}
                    onChange={(e) => setTestPrompt(e.target.value)}
                    className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows={3}
                    placeholder="Enter a prompt to test the models..."
                  />
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Info className="h-4 w-4" />
                  <span>Click the play button next to any installed model to test it</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};