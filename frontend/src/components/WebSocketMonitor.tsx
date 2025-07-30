import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle, XCircle, RefreshCw, Zap } from 'lucide-react';

interface WebSocketConnection {
  id: string;
  url: string;
  status: 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';
  latency?: number;
  messagesReceived: number;
  messagesSent: number;
  lastActivity: number;
  reconnectAttempts: number;
}

interface WebSocketMonitorProps {
  connections: WebSocketConnection[];
  className?: string;
  compact?: boolean;
}

export const WebSocketMonitor: React.FC<WebSocketMonitorProps> = ({ 
  connections, 
  className = '',
  compact = false 
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getStatusIcon = (status: WebSocketConnection['status']) => {
    switch (status) {
      case 'connected':
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'connecting':
        return <RefreshCw className="w-4 h-4 text-yellow-400 animate-spin" />;
      case 'reconnecting':
        return <RefreshCw className="w-4 h-4 text-orange-400 animate-spin" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-red-400" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: WebSocketConnection['status']) => {
    switch (status) {
      case 'connected':
        return 'text-green-400';
      case 'connecting':
        return 'text-yellow-400';
      case 'reconnecting':
        return 'text-orange-400';
      case 'error':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  const activeConnections = connections.filter(c => c.status === 'connected').length;
  const totalConnections = connections.length;
  const hasIssues = connections.some(c => c.status === 'error' || c.status === 'reconnecting');

  if (compact) {
    return (
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={`flex items-center gap-2 px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors ${className}`}
      >
        {hasIssues ? (
          <AlertTriangle className="w-4 h-4 text-yellow-400" />
        ) : activeConnections === totalConnections ? (
          <Zap className="w-4 h-4 text-green-400" />
        ) : (
          <Activity className="w-4 h-4 text-gray-400" />
        )}
        <span className="text-xs">
          WS: {activeConnections}/{totalConnections}
        </span>
      </button>
    );
  }

  return (
    <div className={`bg-gray-800 rounded-lg p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Activity className="w-4 h-4" />
          WebSocket Connections
        </h3>
        <span className="text-xs text-gray-400">
          {activeConnections}/{totalConnections} active
        </span>
      </div>

      <div className="space-y-2">
        {connections.map((connection) => (
          <div
            key={connection.id}
            className="bg-gray-900 rounded p-3 text-xs"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {getStatusIcon(connection.status)}
                <span className="font-mono text-gray-300 truncate max-w-[200px]">
                  {connection.url.replace(/^wss?:\/\//, '')}
                </span>
              </div>
              <span className={`capitalize ${getStatusColor(connection.status)}`}>
                {connection.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-gray-400">
              <div>
                <span className="block">Messages:</span>
                <span className="text-gray-300">
                  ↓ {connection.messagesReceived} ↑ {connection.messagesSent}
                </span>
              </div>
              {connection.latency !== undefined && (
                <div>
                  <span className="block">Latency:</span>
                  <span className={connection.latency > 100 ? 'text-yellow-400' : 'text-gray-300'}>
                    {connection.latency}ms
                  </span>
                </div>
              )}
            </div>

            {connection.reconnectAttempts > 0 && (
              <div className="mt-2 text-yellow-400">
                Reconnect attempts: {connection.reconnectAttempts}
              </div>
            )}

            <div className="mt-2 text-gray-500">
              Last activity: {new Date(connection.lastActivity).toLocaleTimeString()}
            </div>
          </div>
        ))}
      </div>

      {connections.length === 0 && (
        <div className="text-center text-gray-500 py-4">
          No active WebSocket connections
        </div>
      )}
    </div>
  );
};