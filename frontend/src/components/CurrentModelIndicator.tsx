import React, { useState, useEffect } from 'react';
import { Badge } from './ui/badge';
import { Cpu, Zap, Target, Brain } from 'lucide-react';
import config from '../config';

interface ModelInfo {
  granite: { name: 'Granite 3.3', color: 'bg-blue-500', icon: Target };
  phi4: { name: 'Phi4-mini', color: 'bg-green-500', icon: Zap };
  gemma: { name: 'Gemma3n', color: 'bg-purple-500', icon: Brain };
}

const MODEL_INFO: ModelInfo = {
  granite: { name: 'Granite 3.3', color: 'bg-blue-500', icon: Target },
  phi4: { name: 'Phi4-mini', color: 'bg-green-500', icon: Zap },
  gemma: { name: 'Gemma3n', color: 'bg-purple-500', icon: Brain },
};

export const CurrentModelIndicator: React.FC = () => {
  const [currentProvider, setCurrentProvider] = useState<string>('granite');
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const fetchModelStatus = async () => {
      try {
        const response = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.meetingNotes.status}`);
        if (response.ok) {
          const data = await response.json();
          setCurrentProvider(data.current_provider);
          setIsConnected(data.connected);
        }
      } catch (error) {
        console.error('Failed to fetch model status:', error);
        setIsConnected(false);
      }
    };

    fetchModelStatus();
    
    // Refresh every 10 seconds
    const interval = setInterval(fetchModelStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const modelInfo = MODEL_INFO[currentProvider as keyof ModelInfo] || MODEL_INFO.granite;
  const IconComponent = modelInfo.icon;

  return (
    <div className="flex items-center gap-2">
      <div className={`p-1.5 rounded-lg ${modelInfo.color} text-white`}>
        <IconComponent className="h-3 w-3" />
      </div>
      <div className="flex items-center gap-1">
        <span className="text-xs font-medium text-gray-300">{modelInfo.name}</span>
        <div className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-green-500' : 'bg-red-500'
        }`} />
      </div>
    </div>
  );
};

export default CurrentModelIndicator;