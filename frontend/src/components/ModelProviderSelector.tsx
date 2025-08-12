import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Brain, Zap, Target } from 'lucide-react';
import config from '../config';

interface ModelProvider {
  id: string;
  name: string;
  description: string;
  parameters: string;
  icon: React.ComponentType<any>;
  badge: string;
  color: string;
}

interface ProviderStatus {
  current_provider: string;
  connected: boolean;
  active_sessions: number;
  service_type: string;
}

const MODEL_PROVIDERS: ModelProvider[] = [
  {
    id: 'granite',
    name: 'Granite 3.3',
    description: 'Balanced performance and quality for comprehensive analysis',
    parameters: '8.2B parameters',
    icon: Target,
    badge: 'Balanced',
    color: 'bg-blue-500',
  },
  {
    id: 'phi4',
    name: 'Phi4-mini',
    description: 'Fastest real-time updates and live transcription',
    parameters: '3.8B parameters',
    icon: Zap,
    badge: 'Fastest',
    color: 'bg-green-500',
  },
  {
    id: 'gemma',
    name: 'Gemma3n',
    description: 'Most detailed analysis and comprehensive insights',
    parameters: '6.9B parameters',
    icon: Brain,
    badge: 'Detailed',
    color: 'bg-purple-500',
  },
];

export const ModelProviderSelector: React.FC = () => {
  const [currentProvider, setCurrentProvider] = useState<string>('granite');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch current provider status
  const fetchStatus = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.meetingNotes.status}`);
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
        setCurrentProvider(data.current_provider);
      }
    } catch (err) {
      console.error('Failed to fetch provider status:', err);
    }
  };

  // Switch provider
  const switchProvider = async (providerId: string) => {
    if (providerId === currentProvider) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(
        `${config.apiBaseUrl}${config.apiEndpoints.meetingNotes.switchProvider}?provider=${providerId}`,
        { method: 'POST' }
      );
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setCurrentProvider(data.provider);
          await fetchStatus(); // Refresh status
        } else {
          setError(`Failed to switch to ${providerId}`);
        }
      } else {
        setError(`HTTP Error: ${response.status}`);
      }
    } catch (err) {
      setError(`Network error: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Load status on mount
  useEffect(() => {
    fetchStatus();
    
    // Refresh status every 10 seconds
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-purple-500" />
          AI Model Provider
          {status && (
            <Badge variant="outline" className="ml-auto">
              {status.active_sessions} active sessions
            </Badge>
          )}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Choose the AI model for meeting notes and analysis
        </p>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-3 mb-4">
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODEL_PROVIDERS.map((provider) => {
            const IconComponent = provider.icon;
            const isActive = currentProvider === provider.id;
            const isConnected = status?.connected && isActive;
            
            return (
              <div
                key={provider.id}
                className={`relative border rounded-lg p-4 cursor-pointer transition-all duration-200 ${
                  isActive
                    ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
                onClick={() => switchProvider(provider.id)}
              >
                {/* Status indicator */}
                <div className="absolute top-2 right-2">
                  {isActive && (
                    <div className={`w-3 h-3 rounded-full ${
                      isConnected ? 'bg-green-500' : 'bg-yellow-500'
                    }`} />
                  )}
                </div>
                
                {/* Model info */}
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${provider.color} text-white`}>
                    <IconComponent className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900">{provider.name}</h3>
                    <p className="text-sm text-gray-600 mt-1">{provider.description}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant={isActive ? "default" : "secondary"} className="text-xs">
                        {provider.badge}
                      </Badge>
                      <span className="text-xs text-gray-500">{provider.parameters}</span>
                    </div>
                  </div>
                </div>
                
                {/* Action button */}
                <Button
                  size="sm"
                  variant={isActive ? "secondary" : "outline"}
                  className="w-full mt-3"
                  disabled={isLoading || isActive}
                  onClick={(e) => {
                    e.stopPropagation();
                    switchProvider(provider.id);
                  }}
                >
                  {isLoading && currentProvider !== provider.id ? (
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 border-2 border-current border-t-transparent animate-spin rounded-full" />
                      Switching...
                    </span>
                  ) : isActive ? (
                    <span className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-green-500 rounded-full" />
                      Active
                    </span>
                  ) : (
                    'Select'
                  )}
                </Button>
              </div>
            );
          })}
        </div>
        
        {/* Current status */}
        {status && (
          <div className="mt-6 p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Current Provider:</span>
              <span className="text-blue-600">{status.service_type}</span>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="font-medium">Connection:</span>
              <span className={status.connected ? 'text-green-600' : 'text-red-600'}>
                {status.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ModelProviderSelector;