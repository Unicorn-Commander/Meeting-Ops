import React from 'react';
import { LLMSettings } from '../components/settings/LLMSettings';
import { Brain, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const LLMSettingsPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Settings
          </button>

          <div className="flex items-center gap-4">
            <Brain className="w-8 h-8 text-purple-400" />
            <div>
              <h1 className="text-3xl font-bold">LLM Configuration</h1>
              <p className="text-gray-400 mt-1">
                Configure AI model endpoints for Meeting Intelligence
              </p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <LLMSettings />

        {/* Additional Info */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Current Configuration */}
          <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Current Setup</h3>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-gray-500">Hardware:</span>
                <span className="ml-2 text-gray-300">AMD 8945HS with 780M iGPU</span>
              </div>
              <div>
                <span className="text-gray-500">HSA Override:</span>
                <span className="ml-2 text-gray-300 font-mono">11.0.3</span>
              </div>
              <div>
                <span className="text-gray-500">Docker Image:</span>
                <span className="ml-2 text-gray-300">ollama/ollama:rocm</span>
              </div>
              <div>
                <span className="text-gray-500">Primary Model:</span>
                <span className="ml-2 text-gray-300">Gemma3n E4B (8k context)</span>
              </div>
              <div>
                <span className="text-gray-500">Test Model:</span>
                <span className="ml-2 text-gray-300">Gemma3 27B (128k context)</span>
              </div>
            </div>
          </div>

          {/* Performance Tips */}
          <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Performance Tips</h3>
            <ul className="space-y-2 text-sm text-gray-300">
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Local models provide faster response times but require GPU resources</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Remote models can handle larger context windows without local memory constraints</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Enable fallback to ensure continuous service during model updates</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Test endpoints regularly to ensure connectivity and model availability</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Preload models in RAM for optimal first-response performance</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};