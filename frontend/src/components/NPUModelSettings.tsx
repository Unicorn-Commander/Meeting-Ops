import React, { useState, useEffect } from 'react';
import { Zap, Cpu, Info, AlertCircle, Check, Loader2 } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface NPUModel {
  id: string;
  name: string;
  type: 'whisper' | 'diarization' | 'both';
  acceleration: 'npu' | 'gpu' | 'cpu';
  performance: {
    speed: number; // relative speed (1.0 = baseline)
    accuracy: number; // 0-100
    memory: number; // MB
  };
  supported: boolean;
  description: string;
}

const NPU_MODELS: NPUModel[] = [
  {
    id: 'whisperx-npu',
    name: 'WhisperX NPU (Recommended)',
    type: 'both',
    acceleration: 'npu',
    performance: {
      speed: 220,
      accuracy: 98,
      memory: 512
    },
    supported: true,
    description: 'Unified WhisperX with speaker diarization, optimized for AMD NPU Phoenix (16 TOPS INT8)'
  },
  {
    id: 'whisper-onnx-npu',
    name: 'Whisper ONNX NPU',
    type: 'whisper',
    acceleration: 'npu',
    performance: {
      speed: 150,
      accuracy: 96,
      memory: 384
    },
    supported: true,
    description: 'ONNX Runtime with INT8 quantization for NPU acceleration'
  },
  {
    id: 'whisper-base',
    name: 'Whisper Base',
    type: 'whisper',
    acceleration: 'cpu',
    performance: {
      speed: 1,
      accuracy: 94,
      memory: 1024
    },
    supported: true,
    description: 'Standard Whisper model running on CPU'
  },
  {
    id: 'whisper-small',
    name: 'Whisper Small',
    type: 'whisper',
    acceleration: 'cpu',
    performance: {
      speed: 0.8,
      accuracy: 95,
      memory: 2048
    },
    supported: true,
    description: 'Larger Whisper model with better accuracy'
  },
  {
    id: 'pyannote-diarization',
    name: 'Pyannote Speaker Diarization',
    type: 'diarization',
    acceleration: 'gpu',
    performance: {
      speed: 5,
      accuracy: 92,
      memory: 1536
    },
    supported: true,
    description: 'Speaker diarization using pyannote.audio (requires HuggingFace token)'
  }
];

interface NPUModelSettingsProps {
  currentModel?: string;
  npuAvailable: boolean;
  onModelChange: (modelId: string) => void;
}

export const NPUModelSettings: React.FC<NPUModelSettingsProps> = ({
  currentModel = 'whisper-base',
  npuAvailable,
  onModelChange
}) => {
  const [selectedModel, setSelectedModel] = useState(currentModel);
  const [isLoading, setIsLoading] = useState(false);
  const [testResult, setTestResult] = useState<{success: boolean; message: string} | null>(null);

  const handleModelSelect = async (modelId: string) => {
    setSelectedModel(modelId);
    setIsLoading(true);
    setTestResult(null);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/stt/model', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ model_id: modelId })
      });

      if (response.ok) {
        const data = await response.json();
        setTestResult({ success: true, message: 'Model changed successfully' });
        onModelChange(modelId);
      } else {
        setTestResult({ success: false, message: 'Failed to change model' });
      }
    } catch (error) {
      setTestResult({ success: false, message: 'Error changing model' });
    } finally {
      setIsLoading(false);
    }
  };

  const getAccelerationIcon = (acceleration: string) => {
    switch (acceleration) {
      case 'npu':
        return <Zap className="h-4 w-4 text-green-400" />;
      case 'gpu':
        return <Zap className="h-4 w-4 text-blue-400" />;
      default:
        return <Cpu className="h-4 w-4 text-gray-400" />;
    }
  };

  const getSpeedColor = (speed: number) => {
    if (speed >= 100) return 'text-green-400';
    if (speed >= 10) return 'text-blue-400';
    if (speed >= 2) return 'text-yellow-400';
    return 'text-gray-400';
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Zap className="h-5 w-5 text-yellow-400" />
          NPU Model Selection
        </h3>
        {npuAvailable ? (
          <div className="flex items-center gap-2 text-green-400 text-sm">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            NPU Available
          </div>
        ) : (
          <div className="flex items-center gap-2 text-yellow-400 text-sm">
            <AlertCircle className="h-4 w-4" />
            NPU Not Detected
          </div>
        )}
      </div>

      {!npuAvailable && (
        <div className="mb-6 p-4 bg-yellow-900/20 border border-yellow-700 rounded-lg">
          <p className="text-sm text-yellow-300">
            NPU acceleration is not available. Models will run on CPU/GPU fallback.
            For best performance, ensure you have compatible NPU hardware.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {NPU_MODELS.map((model) => {
          const isSelected = selectedModel === model.id;
          const isDisabled = model.acceleration === 'npu' && !npuAvailable;

          return (
            <div
              key={model.id}
              className={`border rounded-lg p-4 cursor-pointer transition-all ${
                isSelected 
                  ? 'border-blue-500 bg-gray-900' 
                  : 'border-gray-700 hover:border-gray-600 hover:bg-gray-900/50'
              } ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => !isDisabled && !isLoading && handleModelSelect(model.id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    {getAccelerationIcon(model.acceleration)}
                    <h4 className="font-medium text-white">{model.name}</h4>
                    {isSelected && (
                      <span className="px-2 py-1 text-xs bg-blue-600 text-white rounded">
                        Current
                      </span>
                    )}
                  </div>
                  
                  <p className="text-sm text-gray-400 mb-3">{model.description}</p>
                  
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Speed:</span>
                      <span className={`ml-2 font-medium ${getSpeedColor(model.performance.speed)}`}>
                        {model.performance.speed >= 2 ? `${model.performance.speed}x` : `${model.performance.speed.toFixed(1)}x`}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Accuracy:</span>
                      <span className="ml-2 font-medium text-white">
                        {model.performance.accuracy}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Memory:</span>
                      <span className="ml-2 font-medium text-white">
                        {model.performance.memory}MB
                      </span>
                    </div>
                  </div>

                  {model.type === 'both' && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="px-2 py-1 text-xs bg-purple-900/30 text-purple-400 rounded">
                        Transcription
                      </span>
                      <span className="px-2 py-1 text-xs bg-indigo-900/30 text-indigo-400 rounded">
                        Speaker Diarization
                      </span>
                    </div>
                  )}
                </div>

                <div className="ml-4">
                  {isLoading && isSelected ? (
                    <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />
                  ) : isSelected ? (
                    <Check className="h-5 w-5 text-green-400" />
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {testResult && (
        <div className={`mt-4 p-3 rounded-lg text-sm ${
          testResult.success 
            ? 'bg-green-900/20 border border-green-700 text-green-300'
            : 'bg-red-900/20 border border-red-700 text-red-300'
        }`}>
          {testResult.message}
        </div>
      )}

      <div className="mt-6 p-4 bg-gray-900 rounded-lg">
        <div className="flex items-start gap-3">
          <Info className="h-5 w-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-gray-300">
            <p className="mb-2">
              <strong>WhisperX NPU</strong> provides the best performance with unified transcription 
              and speaker diarization in a single pass. It achieves up to 7,866x real-time speed on 
              compatible NPU hardware.
            </p>
            <p>
              Models marked with the NPU icon require AMD NPU Phoenix or compatible hardware. 
              CPU fallback is available but with reduced performance.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};