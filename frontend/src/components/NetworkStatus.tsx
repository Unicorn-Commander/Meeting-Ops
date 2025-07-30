import React from 'react';
import { Wifi, WifiOff, Zap, AlertTriangle, CheckCircle } from 'lucide-react';
import { useConnectionStatus } from '../hooks/useConnectionStatus';

interface NetworkStatusProps {
  className?: string;
  showDetails?: boolean;
}

export const NetworkStatus: React.FC<NetworkStatusProps> = ({ 
  className = '', 
  showDetails = false 
}) => {
  const connectionStatus = useConnectionStatus();
  const networkAdaptations = connectionStatus.getNetworkAdaptations();

  const getStatusIcon = () => {
    if (!connectionStatus.isOnline) {
      return <WifiOff className="w-4 h-4 text-red-400" />;
    }
    
    switch (networkAdaptations.connectionQuality) {
      case 'excellent':
        return <Zap className="w-4 h-4 text-green-400" />;
      case 'good':
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'slow':
        return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      default:
        return <Wifi className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = () => {
    if (!connectionStatus.isOnline) return 'text-red-400';
    
    switch (networkAdaptations.connectionQuality) {
      case 'excellent':
      case 'good':
        return 'text-green-400';
      case 'slow':
        return 'text-yellow-400';
      default:
        return 'text-gray-400';
    }
  };

  const getStatusText = () => {
    if (!connectionStatus.isOnline) return 'Offline';
    
    switch (networkAdaptations.connectionQuality) {
      case 'excellent':
        return 'Excellent';
      case 'good':
        return 'Good';
      case 'slow':
        return 'Slow';
      default:
        return 'Connected';
    }
  };

  if (!showDetails) {
    return (
      <div className={`flex items-center gap-1 ${className}`}>
        {getStatusIcon()}
        <span className={`text-xs ${getStatusColor()}`}>
          {getStatusText()}
        </span>
      </div>
    );
  }

  return (
    <div className={`bg-gray-800 p-3 rounded-lg ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          <span className={`text-sm font-medium ${getStatusColor()}`}>
            Network Status
          </span>
        </div>
        <span className={`text-xs ${getStatusColor()}`}>
          {getStatusText()}
        </span>
      </div>

      {connectionStatus.isOnline && (
        <div className="space-y-1 text-xs text-gray-400">
          <div className="flex justify-between">
            <span>Latency:</span>
            <span className={connectionStatus.latency && connectionStatus.latency > 1000 ? 'text-yellow-400' : 'text-green-400'}>
              {connectionStatus.latency ? `${connectionStatus.latency}ms` : 'Measuring...'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Last Check:</span>
            <span>
              {Math.floor((Date.now() - connectionStatus.lastCheck) / 1000)}s ago
            </span>
          </div>
          {connectionStatus.isSlowConnection && (
            <div className="mt-2 p-2 bg-yellow-900/30 border border-yellow-600 rounded text-yellow-200">
              <div className="flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                <span className="text-xs">Network optimization active</span>
              </div>
            </div>
          )}
        </div>
      )}

      {!connectionStatus.isOnline && (
        <div className="mt-2 p-2 bg-red-900/30 border border-red-600 rounded text-red-200">
          <div className="flex items-center gap-1">
            <WifiOff className="w-3 h-3" />
            <span className="text-xs">Using cached data when available</span>
          </div>
        </div>
      )}
    </div>
  );
};