import React, { useState, useEffect } from 'react';
import { 
  Download, Trash2, Zap, Cpu, Activity, Battery, Info, CheckCircle, 
  ChevronDown, ChevronUp, Loader2, HardDrive, Mic, Brain, MessageSquare,
  Settings, Play, Pause, RefreshCw, AlertCircle, Check
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Alert, AlertDescription } from './ui/alert';

interface Model {
  id: string;
  name: string;
  type: 'stt' | 'llm';
  size: number;
  downloaded: boolean;
  active: boolean;
  language?: string;
  provider?: string;
  capabilities?: string[];
  performance?: {
    speed: number;
    accuracy: number;
    memory_usage: number;
  };
  hardware_requirements?: {
    min_ram?: number;
    min_vram?: number;
    npu_required?: boolean;
    cpu_threads?: number;
  };
  parameters?: {
    context_length?: number;
    temperature?: number;
    max_tokens?: number;
  };
}

interface SystemStatus {
  npu_available: boolean;
  onnx_providers: string[];
  memory_available: number;
  disk_space: number;
  active_models: {
    stt?: string;
    llm?: string;
  };
}

interface DownloadProgress {
  modelId: string;
  progress: number;
  speed: number;
  eta: string;
}

export const AIModelsManager: React.FC = () => {
  const [models, setModels] = useState<Model[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [downloads, setDownloads] = useState<Map<string, DownloadProgress>>(new Map());
  const [selectedTab, setSelectedTab] = useState<'stt' | 'llm'>('stt');
  const [loading, setLoading] = useState(true);
  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);

  useEffect(() => {
    loadModels();
    loadSystemStatus();
    const interval = setInterval(loadSystemStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Mock data for demonstration
        const mockModels: Model[] = [
          // STT Models
          {
            id: 'whisper-tiny',
            name: 'Whisper Tiny',
            type: 'stt',
            size: 39 * 1024 * 1024,
            downloaded: true,
            active: true,
            language: 'Multilingual',
            provider: 'OpenAI',
            capabilities: ['transcription', 'translation'],
            performance: { speed: 10, accuracy: 85, memory_usage: 500 },
            hardware_requirements: { min_ram: 2, npu_required: false }
          },
          {
            id: 'whisper-base',
            name: 'Whisper Base',
            type: 'stt',
            size: 74 * 1024 * 1024,
            downloaded: true,
            active: false,
            language: 'Multilingual',
            provider: 'OpenAI',
            capabilities: ['transcription', 'translation', 'timestamps'],
            performance: { speed: 8, accuracy: 90, memory_usage: 800 },
            hardware_requirements: { min_ram: 4, npu_required: false }
          },
          {
            id: 'whisper-small',
            name: 'Whisper Small',
            type: 'stt',
            size: 244 * 1024 * 1024,
            downloaded: false,
            active: false,
            language: 'Multilingual',
            provider: 'OpenAI',
            capabilities: ['transcription', 'translation', 'timestamps', 'diarization'],
            performance: { speed: 6, accuracy: 93, memory_usage: 1500 },
            hardware_requirements: { min_ram: 6, npu_required: true }
          },
          {
            id: 'whisperx-medium',
            name: 'WhisperX Medium (NPU)',
            type: 'stt',
            size: 769 * 1024 * 1024,
            downloaded: false,
            active: false,
            language: 'Multilingual',
            provider: 'WhisperX',
            capabilities: ['transcription', 'translation', 'timestamps', 'diarization', 'word-level'],
            performance: { speed: 4, accuracy: 95, memory_usage: 3000 },
            hardware_requirements: { min_ram: 8, npu_required: true }
          },
          // LLM Models
          {
            id: 'llama2-7b',
            name: 'Llama 2 7B',
            type: 'llm',
            size: 3.8 * 1024 * 1024 * 1024,
            downloaded: false,
            active: false,
            provider: 'Meta',
            capabilities: ['chat', 'completion', 'summarization'],
            parameters: { context_length: 4096, temperature: 0.7, max_tokens: 2048 },
            performance: { speed: 50, accuracy: 92, memory_usage: 8000 },
            hardware_requirements: { min_ram: 16, min_vram: 8, cpu_threads: 8 }
          },
          {
            id: 'mistral-7b',
            name: 'Mistral 7B Instruct',
            type: 'llm',
            size: 4.1 * 1024 * 1024 * 1024,
            downloaded: true,
            active: true,
            provider: 'Mistral AI',
            capabilities: ['chat', 'completion', 'summarization', 'code'],
            parameters: { context_length: 8192, temperature: 0.7, max_tokens: 4096 },
            performance: { speed: 45, accuracy: 94, memory_usage: 8500 },
            hardware_requirements: { min_ram: 16, min_vram: 8, cpu_threads: 8 }
          },
          {
            id: 'phi-2',
            name: 'Phi-2',
            type: 'llm',
            size: 2.7 * 1024 * 1024 * 1024,
            downloaded: false,
            active: false,
            provider: 'Microsoft',
            capabilities: ['chat', 'completion', 'reasoning'],
            parameters: { context_length: 2048, temperature: 0.7, max_tokens: 1024 },
            performance: { speed: 60, accuracy: 88, memory_usage: 6000 },
            hardware_requirements: { min_ram: 8, min_vram: 4, cpu_threads: 4 }
          },
          {
            id: 'qwen-1.8b',
            name: 'Qwen 1.8B',
            type: 'llm',
            size: 1.8 * 1024 * 1024 * 1024,
            downloaded: false,
            active: false,
            provider: 'Alibaba',
            capabilities: ['chat', 'completion', 'multilingual'],
            parameters: { context_length: 2048, temperature: 0.7, max_tokens: 1024 },
            performance: { speed: 80, accuracy: 85, memory_usage: 4000 },
            hardware_requirements: { min_ram: 6, min_vram: 2, cpu_threads: 4 }
          }
        ];
        setModels(mockModels);
      }
    } catch (error) {
      console.error('Error loading models:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSystemStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/status', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSystemStatus({
          npu_available: data.npu_available || false,
          onnx_providers: data.onnx_providers || ['CPUExecutionProvider'],
          memory_available: 16384, // Mock: 16GB
          disk_space: 250 * 1024, // Mock: 250GB
          active_models: {
            stt: 'whisper-tiny',
            llm: 'mistral-7b'
          }
        });
      }
    } catch (error) {
      console.error('Error loading system status:', error);
    }
  };

  const handleDownload = async (modelId: string) => {
    const model = models.find(m => m.id === modelId);
    if (!model) return;

    // Simulate download progress
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.random() * 10;
      if (progress >= 100) {
        progress = 100;
        clearInterval(interval);
        setDownloads(prev => {
          const newMap = new Map(prev);
          newMap.delete(modelId);
          return newMap;
        });
        setModels(prev => prev.map(m => 
          m.id === modelId ? { ...m, downloaded: true } : m
        ));
      } else {
        setDownloads(prev => new Map(prev).set(modelId, {
          modelId,
          progress,
          speed: 5.2 + Math.random() * 2,
          eta: `${Math.ceil((100 - progress) / 10)}m ${Math.floor(Math.random() * 60)}s`
        }));
      }
    }, 500);
  };

  const handleDelete = async (modelId: string) => {
    if (!confirm('Are you sure you want to delete this model?')) return;
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/models/${modelId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        setModels(prev => prev.map(m => 
          m.id === modelId ? { ...m, downloaded: false, active: false } : m
        ));
      }
    } catch (error) {
      console.error('Error deleting model:', error);
    }
  };

  const handleActivate = async (modelId: string, type: 'stt' | 'llm') => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/models/${modelId}/activate`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ type })
      });
      
      if (response.ok) {
        setModels(prev => prev.map(m => ({
          ...m,
          active: m.type === type ? m.id === modelId : m.active
        })));
      }
    } catch (error) {
      console.error('Error activating model:', error);
    }
  };

  const handleTest = async (modelId: string) => {
    setTestingModel(modelId);
    
    try {
      const token = localStorage.getItem('access_token');
      const model = models.find(m => m.id === modelId);
      
      if (model?.type === 'stt') {
        // Test STT model with audio
        const response = await fetch(`/api/models/${modelId}/test`, {
          method: 'POST',
          headers: { 
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            test_type: 'audio',
            sample: 'default' 
          })
        });
        
        if (response.ok) {
          const result = await response.json();
          alert(`Test successful! Transcription: "${result.transcription}"\nTime: ${result.time}ms`);
        }
      } else if (model?.type === 'llm') {
        // Test LLM model with prompt
        const response = await fetch(`/api/models/${modelId}/test`, {
          method: 'POST',
          headers: { 
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            test_type: 'prompt',
            prompt: 'Hello, please summarize the key points from a meeting.' 
          })
        });
        
        if (response.ok) {
          const result = await response.json();
          alert(`Test successful!\nResponse: "${result.response}"\nTokens: ${result.tokens}\nTime: ${result.time}ms`);
        }
      }
    } catch (error) {
      console.error('Error testing model:', error);
      alert('Test failed! Check console for details.');
    } finally {
      setTestingModel(null);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const getAccelerationIcon = () => {
    if (!systemStatus) return <Cpu className="w-4 h-4" />;
    if (systemStatus.npu_available) return <Zap className="w-4 h-4 text-green-500" />;
    if (systemStatus.onnx_providers.includes('DmlExecutionProvider')) return <Activity className="w-4 h-4 text-blue-500" />;
    return <Cpu className="w-4 h-4 text-gray-500" />;
  };

  const renderModelCard = (model: Model) => {
    const isDownloading = downloads.has(model.id);
    const downloadProgress = downloads.get(model.id);
    const isExpanded = expandedModel === model.id;

    return (
      <Card key={model.id} className={`${model.active ? 'border-blue-500' : ''}`}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {model.type === 'stt' ? (
                <Mic className="w-5 h-5 text-blue-500" />
              ) : (
                <Brain className="w-5 h-5 text-purple-500" />
              )}
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  {model.name}
                  {model.active && (
                    <Badge variant="default" className="text-xs">Active</Badge>
                  )}
                  {model.hardware_requirements?.npu_required && (
                    <Badge variant="outline" className="text-xs">
                      <Zap className="w-3 h-3 mr-1" />
                      NPU
                    </Badge>
                  )}
                </CardTitle>
                <p className="text-sm text-gray-500">
                  {model.provider} • {formatSize(model.size)}
                  {model.language && ` • ${model.language}`}
                </p>
              </div>
            </div>
            <button
              onClick={() => setExpandedModel(isExpanded ? null : model.id)}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
            >
              {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>
          </div>
        </CardHeader>
        
        <CardContent className="space-y-4">
          {/* Quick Actions */}
          <div className="flex items-center gap-2">
            {!model.downloaded ? (
              <Button
                onClick={() => handleDownload(model.id)}
                disabled={isDownloading}
                size="sm"
                className="flex items-center gap-2"
              >
                {isDownloading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Downloading...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    Download
                  </>
                )}
              </Button>
            ) : (
              <>
                <Button
                  onClick={() => handleActivate(model.id, model.type)}
                  disabled={model.active}
                  size="sm"
                  variant={model.active ? "default" : "outline"}
                  className="flex items-center gap-2"
                >
                  {model.active ? (
                    <>
                      <CheckCircle className="w-4 h-4" />
                      Active
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Activate
                    </>
                  )}
                </Button>
                <Button
                  onClick={() => handleTest(model.id)}
                  disabled={!model.active || testingModel === model.id}
                  size="sm"
                  variant="outline"
                  className="flex items-center gap-2"
                >
                  {testingModel === model.id ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Testing...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Test
                    </>
                  )}
                </Button>
                <Button
                  onClick={() => handleDelete(model.id)}
                  disabled={model.active}
                  size="sm"
                  variant="ghost"
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </>
            )}
          </div>

          {/* Download Progress */}
          {isDownloading && downloadProgress && (
            <div className="space-y-2">
              <Progress value={downloadProgress.progress} className="h-2" />
              <div className="flex justify-between text-xs text-gray-500">
                <span>{downloadProgress.progress.toFixed(1)}%</span>
                <span>{downloadProgress.speed.toFixed(1)} MB/s</span>
                <span>ETA: {downloadProgress.eta}</span>
              </div>
            </div>
          )}

          {/* Expanded Details */}
          {isExpanded && (
            <div className="space-y-3 pt-3 border-t">
              {/* Capabilities */}
              {model.capabilities && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">Capabilities</p>
                  <div className="flex flex-wrap gap-1">
                    {model.capabilities.map(cap => (
                      <Badge key={cap} variant="secondary" className="text-xs">
                        {cap}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Performance */}
              {model.performance && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">Performance</p>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <p className="text-gray-500">Speed</p>
                      <p className="font-medium">{model.performance.speed}x realtime</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Accuracy</p>
                      <p className="font-medium">{model.performance.accuracy}%</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Memory</p>
                      <p className="font-medium">{model.performance.memory_usage} MB</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Hardware Requirements */}
              {model.hardware_requirements && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">Requirements</p>
                  <div className="space-y-1 text-sm text-gray-600">
                    {model.hardware_requirements.min_ram && (
                      <p>• Minimum RAM: {model.hardware_requirements.min_ram} GB</p>
                    )}
                    {model.hardware_requirements.min_vram && (
                      <p>• Minimum VRAM: {model.hardware_requirements.min_vram} GB</p>
                    )}
                    {model.hardware_requirements.cpu_threads && (
                      <p>• CPU Threads: {model.hardware_requirements.cpu_threads}</p>
                    )}
                    {model.hardware_requirements.npu_required && (
                      <p className="text-orange-600">• NPU Acceleration Required</p>
                    )}
                  </div>
                </div>
              )}

              {/* Model Parameters (LLM only) */}
              {model.parameters && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">Parameters</p>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    {model.parameters.context_length && (
                      <div>
                        <p className="text-gray-500">Context</p>
                        <p className="font-medium">{model.parameters.context_length}</p>
                      </div>
                    )}
                    {model.parameters.temperature !== undefined && (
                      <div>
                        <p className="text-gray-500">Temperature</p>
                        <p className="font-medium">{model.parameters.temperature}</p>
                      </div>
                    )}
                    {model.parameters.max_tokens && (
                      <div>
                        <p className="text-gray-500">Max Tokens</p>
                        <p className="font-medium">{model.parameters.max_tokens}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const sttModels = models.filter(m => m.type === 'stt');
  const llmModels = models.filter(m => m.type === 'llm');

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="w-8 h-8 text-purple-500" />
          <div>
            <h1 className="text-2xl font-bold">AI Models Management</h1>
            <p className="text-gray-600">Manage speech-to-text and language models</p>
          </div>
        </div>
        <Button
          onClick={loadModels}
          variant="outline"
          className="flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      {/* System Status */}
      {systemStatus && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              System Status
              {getAccelerationIcon()}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-500">Acceleration</p>
                <p className="font-medium flex items-center gap-2">
                  {systemStatus.npu_available ? (
                    <>
                      <Zap className="w-4 h-4 text-green-500" />
                      NPU Available
                    </>
                  ) : systemStatus.onnx_providers.includes('DmlExecutionProvider') ? (
                    <>
                      <Activity className="w-4 h-4 text-blue-500" />
                      GPU Available
                    </>
                  ) : (
                    <>
                      <Cpu className="w-4 h-4 text-gray-500" />
                      CPU Only
                    </>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Memory Available</p>
                <p className="font-medium">{(systemStatus.memory_available / 1024).toFixed(1)} GB</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Disk Space</p>
                <p className="font-medium">{(systemStatus.disk_space / 1024).toFixed(1)} GB</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Active Models</p>
                <p className="font-medium">
                  STT: {systemStatus.active_models.stt || 'None'}<br />
                  LLM: {systemStatus.active_models.llm || 'None'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* NPU Warning */}
      {systemStatus && !systemStatus.npu_available && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            NPU acceleration not detected. Some models may run slower than expected. 
            Make sure you're using Python 3.13 environment with NPU drivers installed.
          </AlertDescription>
        </Alert>
      )}

      {/* Model Tabs */}
      <Tabs value={selectedTab} onValueChange={(v) => setSelectedTab(v as 'stt' | 'llm')}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="stt" className="flex items-center gap-2">
            <Mic className="w-4 h-4" />
            Speech-to-Text Models ({sttModels.length})
          </TabsTrigger>
          <TabsTrigger value="llm" className="flex items-center gap-2">
            <Brain className="w-4 h-4" />
            Language Models ({llmModels.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="stt" className="space-y-4 mt-4">
          {loading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : sttModels.length === 0 ? (
            <Card>
              <CardContent className="text-center py-8">
                <Mic className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">No STT models available</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {sttModels.map(renderModelCard)}
            </div>
          )}
        </TabsContent>

        <TabsContent value="llm" className="space-y-4 mt-4">
          {loading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : llmModels.length === 0 ? (
            <Card>
              <CardContent className="text-center py-8">
                <Brain className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">No language models available</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {llmModels.map(renderModelCard)}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Model Configuration Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Model Configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="font-medium mb-2">STT Configuration</h3>
              <div className="space-y-2">
                <label className="flex items-center justify-between text-sm">
                  <span>Enable VAD (Voice Activity Detection)</span>
                  <input type="checkbox" defaultChecked className="toggle" />
                </label>
                <label className="flex items-center justify-between text-sm">
                  <span>Enable Speaker Diarization</span>
                  <input type="checkbox" defaultChecked className="toggle" />
                </label>
                <label className="flex items-center justify-between text-sm">
                  <span>Word-level Timestamps</span>
                  <input type="checkbox" className="toggle" />
                </label>
              </div>
            </div>
            <div>
              <h3 className="font-medium mb-2">LLM Configuration</h3>
              <div className="space-y-2">
                <label className="flex items-center justify-between text-sm">
                  <span>Enable Streaming</span>
                  <input type="checkbox" defaultChecked className="toggle" />
                </label>
                <label className="flex items-center justify-between text-sm">
                  <span>Use System Prompt</span>
                  <input type="checkbox" defaultChecked className="toggle" />
                </label>
                <label className="text-sm">
                  <span className="block mb-1">Default Temperature</span>
                  <input 
                    type="range" 
                    min="0" 
                    max="1" 
                    step="0.1" 
                    defaultValue="0.7" 
                    className="w-full"
                  />
                </label>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};