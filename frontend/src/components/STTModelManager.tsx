import React, { useState, useEffect } from 'react';
import { Mic, Download, Trash2, Zap, Cpu, Activity, Battery, Info, CheckCircle, ChevronDown, ChevronUp, Loader2, HardDrive } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface STTModel {
  id: string;
  name: string;
  description: string;
  size: string;
  speed: string;
  accuracy: string;
  languages: string[];
  use_cases: string[];
  installed: boolean;
  current: boolean;
}

interface BenchmarkResult {
  inference_speed: string;
  memory_usage: string;
  npu_utilization: string;
  power_consumption: string;
  first_token_latency: string;
}

export const STTModelManager: React.FC = () => {
  const [models, setModels] = useState<STTModel[]>([]);
  const [currentModel, setCurrentModel] = useState<STTModel | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{[key: string]: number}>({});
  const [benchmarkResults, setBenchmarkResults] = useState<{[key: string]: BenchmarkResult}>({});
  const [isLoading, setIsLoading] = useState(false);
  const [showBenchmark, setShowBenchmark] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<{[key: string]: boolean}>({
    current: true,
    models: true,
    optimization: true
  });

  useEffect(() => {
    loadModels();
    loadCurrentModel();
  }, []);

  const loadModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/stt/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setModels(data.models || []);
      }
    } catch (error) {
      console.error('Error loading STT models:', error);
    }
  };

  const loadCurrentModel = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/stt/current', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setCurrentModel(data);
      }
    } catch (error) {
      console.error('Error loading current model:', error);
    }
  };

  const downloadModel = async (modelId: string) => {
    setIsLoading(true);
    setDownloadProgress(prev => ({ ...prev, [modelId]: 0 }));

    try {
      const token = localStorage.getItem('access_token');
            const response = await fetch(`/api/ai/stt/models/${modelId}/download`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        // Simulate progress
        const interval = setInterval(() => {
          setDownloadProgress(prev => {
            const current = prev[modelId] || 0;
            if (current >= 100) {
              clearInterval(interval);
              loadModels();
              return prev;
            }
            return { ...prev, [modelId]: current + 10 };
          });
        }, 500);
      }
    } catch (error) {
      console.error('Error downloading model:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteModel = async (modelId: string) => {
    if (!confirm(`Delete model ${modelId}?`)) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/stt/models/${modelId}`, {
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

  const setActiveModel = async (modelId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/stt/model`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
      });

      if (response.ok) {
        loadModels();
        loadCurrentModel();
      }
    } catch (error) {
      console.error('Error setting active model:', error);
    }
  };

  const testModel = async (modelId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/stt/test`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
      });

      if (response.ok) {
        const data = await response.json();
        console.log('Test results:', data);
        // You can add UI feedback here
      }
    } catch (error) {
      console.error('Error testing model:', error);
    }
  };

  const benchmarkModel = async (modelId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/ai/stt/benchmark/${modelId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setBenchmarkResults(prev => ({ ...prev, [modelId]: data.metrics }));
        setShowBenchmark(modelId);
      }
    } catch (error) {
      console.error('Error benchmarking model:', error);
    }
  };

  const getSpeedColor = (speed: string) => {
    if (speed.includes('10x')) return 'text-green-600';
    if (speed.includes('6x') || speed.includes('3x')) return 'text-blue-600';
    return 'text-orange-600';
  };

  const getAccuracyBadge = (accuracy: string) => {
    if (accuracy.includes('State-of-the-art')) return 'bg-purple-100 text-purple-700';
    if (accuracy.includes('Excellent')) return 'bg-green-100 text-green-700';
    if (accuracy.includes('Very good')) return 'bg-blue-100 text-blue-700';
    return 'bg-gray-100 text-gray-700';
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Mic className="h-5 w-5 text-purple-400" />
            NPU-Optimized STT Models
          </h3>
          <Tooltip content="Speech-to-text models optimized for NPU acceleration. Faster processing with lower power consumption.">
            <Info className="h-4 w-4 text-gray-400" />
          </Tooltip>
        </div>

        {/* Current Model Section */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 mb-6">
          <button
            onClick={() => toggleSection('current')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                <Zap className="h-5 w-5 text-blue-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">Active STT Model</h4>
                <p className="text-sm text-gray-500">Currently used for transcription</p>
              </div>
            </div>
            {expandedSections.current ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
          </button>
          
          {expandedSections.current && currentModel && (
            <div className="border-t border-gray-200 p-4">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h5 className="font-medium text-blue-900">{currentModel.name}</h5>
                    <p className="text-blue-700 mt-1 text-sm">{currentModel.description}</p>
                    <div className="flex items-center gap-4 mt-3 text-sm">
                      <div className="flex items-center gap-1">
                        <Zap className="h-4 w-4 text-blue-600" />
                        <span className={`font-medium ${getSpeedColor(currentModel.speed)}`}>
                          {currentModel.speed}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Cpu className="h-4 w-4 text-blue-600" />
                        <span className="text-blue-700">NPU Accelerated</span>
                      </div>
                    </div>
                  </div>
                  <span className={`px-3 py-1 text-xs rounded-full ${getAccuracyBadge(currentModel.accuracy)}`}>
                    {currentModel.accuracy}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Available Models Section */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 mb-6">
          <button
            onClick={() => toggleSection('models')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                <Mic className="h-5 w-5 text-purple-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">Available STT Models</h4>
                <p className="text-sm text-gray-500">Choose from 5 NPU-optimized models</p>
              </div>
            </div>
            {expandedSections.models ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
          </button>
          
          {expandedSections.models && (
            <div className="border-t border-gray-200 p-4">
              <div className="space-y-3">
                {models.map(model => {
                  const progress = downloadProgress[model.id];
                  const benchmark = benchmarkResults[model.id];

                  return (
                    <div key={model.id} className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
                      <div className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <h5 className="font-medium">{model.name}</h5>
                              {model.current && (
                                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                                  Active
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-gray-600">{model.description}</p>
                            
                            <div className="flex flex-wrap gap-4 mt-3 text-sm">
                              <Tooltip content="Model size on disk">
                                <div className="flex items-center gap-1">
                                  <HardDrive className="h-3 w-3 text-gray-400" />
                                  <span className="text-gray-500">Size:</span>
                                  <span className="font-medium">{model.size}</span>
                                </div>
                              </Tooltip>
                              <Tooltip content="Real-time processing speed">
                                <div className="flex items-center gap-1">
                                  <Zap className="h-3 w-3 text-gray-400" />
                                  <span className="text-gray-500">Speed:</span>
                                  <span className={`font-medium ${getSpeedColor(model.speed)}`}>
                                    {model.speed}
                                  </span>
                                </div>
                              </Tooltip>
                              <Tooltip content="Supported languages">
                                <div className="flex items-center gap-1">
                                  <span className="text-gray-500">Languages:</span>
                                  <span className="font-medium">{model.languages.join(', ')}</span>
                                </div>
                              </Tooltip>
                            </div>

                            <div className="flex items-center gap-2 mt-3">
                              <span className={`text-xs px-2 py-1 rounded ${getAccuracyBadge(model.accuracy)}`}>
                                {model.accuracy}
                              </span>
                              <span className="text-xs text-gray-500">
                                Best for: {model.use_cases.join(', ')}
                              </span>
                            </div>
                          </div>

                          <div className="flex flex-col items-end gap-2 ml-4">
                            {model.installed ? (
                              <>
                                {!model.current && (
                                  <Tooltip content="Use this model for transcription">
                                    <button
                                      onClick={() => setActiveModel(model.id)}
                                      className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                                    >
                                      Set Active
                                    </button>
                                  </Tooltip>
                                )}
                                <div className="flex gap-1">
                                  <Tooltip content="Benchmark performance">
                                    <button
                                      onClick={() => testModel(model.id)}
                                      className="p-2 text-gray-600 hover:bg-gray-100 rounded transition-colors"
                                    >
                                      <Activity className="h-4 w-4" />
                                    </button>
                                  </Tooltip>
                                  <Tooltip content="Delete this model">
                                    <button
                                      onClick={() => deleteModel(model.id)}
                                      className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </button>
                                  </Tooltip>
                                </div>
                              </>
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
                              <Tooltip content="Download and optimize for NPU">
                                <button
                                  onClick={() => downloadModel(model.id)}
                                  disabled={isLoading}
                                  className="flex items-center gap-2 px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                  <Download className="h-4 w-4" />
                                  Download
                                </button>
                              </Tooltip>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Benchmark Results */}
                      {showBenchmark === model.id && benchmark && (
                        <div className="border-t bg-white p-4">
                          <h6 className="font-medium mb-3 flex items-center gap-2">
                            <Activity className="h-4 w-4 text-gray-600" />
                            Benchmark Results
                          </h6>
                          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                            <Tooltip content="Processing speed compared to real-time">
                              <div className="bg-gray-50 rounded p-2">
                                <p className="text-gray-500 text-xs">Inference Speed</p>
                                <p className="font-medium">{benchmark.inference_speed}</p>
                              </div>
                            </Tooltip>
                            <Tooltip content="RAM usage during transcription">
                              <div className="bg-gray-50 rounded p-2">
                                <p className="text-gray-500 text-xs">Memory Usage</p>
                                <p className="font-medium">{benchmark.memory_usage}</p>
                              </div>
                            </Tooltip>
                            <Tooltip content="NPU core utilization percentage">
                              <div className="bg-gray-50 rounded p-2">
                                <p className="text-gray-500 text-xs">NPU Utilization</p>
                                <p className="font-medium">{benchmark.npu_utilization}</p>
                              </div>
                            </Tooltip>
                            <Tooltip content="Power consumption during inference">
                              <div className="bg-gray-50 rounded p-2">
                                <p className="text-gray-500 text-xs">Power</p>
                                <p className="font-medium flex items-center gap-1">
                                  <Battery className="h-3 w-3" />
                                  {benchmark.power_consumption}
                                </p>
                              </div>
                            </Tooltip>
                            <Tooltip content="Time to first transcription output">
                              <div className="bg-gray-50 rounded p-2">
                                <p className="text-gray-500 text-xs">First Token</p>
                                <p className="font-medium">{benchmark.first_token_latency}</p>
                              </div>
                            </Tooltip>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* NPU Optimization Info */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <button
            onClick={() => toggleSection('optimization')}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                <Cpu className="h-5 w-5 text-green-600" />
              </div>
              <div className="text-left">
                <h4 className="font-medium">NPU Optimization Benefits</h4>
                <p className="text-sm text-gray-500">Why NPU acceleration matters</p>
              </div>
            </div>
            {expandedSections.optimization ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
          </button>
          
          {expandedSections.optimization && (
            <div className="border-t border-gray-200 p-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Tooltip content="NPU processes audio much faster than CPU">
                  <div className="bg-green-50 rounded-lg p-4 text-center">
                    <Zap className="h-8 w-8 text-green-600 mx-auto mb-2" />
                    <p className="font-medium text-green-900">Speed Boost</p>
                    <p className="text-sm text-green-700 mt-1">4-10x faster than CPU</p>
                  </div>
                </Tooltip>
                <Tooltip content="NPU uses significantly less power">
                  <div className="bg-blue-50 rounded-lg p-4 text-center">
                    <Battery className="h-8 w-8 text-blue-600 mx-auto mb-2" />
                    <p className="font-medium text-blue-900">Power Efficiency</p>
                    <p className="text-sm text-blue-700 mt-1">10x better than CPU</p>
                  </div>
                </Tooltip>
                <Tooltip content="Quantization maintains high accuracy">
                  <div className="bg-purple-50 rounded-lg p-4 text-center">
                    <CheckCircle className="h-8 w-8 text-purple-600 mx-auto mb-2" />
                    <p className="font-medium text-purple-900">Accuracy</p>
                    <p className="text-sm text-purple-700 mt-1">99%+ retention with INT8</p>
                  </div>
                </Tooltip>
              </div>
              
              <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                <div className="flex items-start gap-3">
                  <Info className="h-5 w-5 text-gray-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-gray-700">
                    <p className="font-medium mb-1">About NPU Optimization</p>
                    <p>
                      These models use INT8/INT4 quantization and custom MLIR kernels designed specifically 
                      for AMD Phoenix NPU (16 TOPS INT8). The optimization provides massive speedups while 
                      maintaining accuracy, perfect for real-time transcription.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};