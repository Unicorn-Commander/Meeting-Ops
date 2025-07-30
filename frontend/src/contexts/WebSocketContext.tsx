import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { useConnectionStatus } from '../hooks/useConnectionStatus';

interface WebSocketConnection {
  id: string;
  url: string;
  ws: WebSocket | null;
  status: 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';
  reconnectAttempts: number;
  messagesReceived: number;
  messagesSent: number;
  lastActivity: number;
  options: {
    reconnect: boolean;
    reconnectInterval: number;
    reconnectAttempts: number;
    heartbeatInterval: number;
    onMessage?: (data: any) => void;
  };
}

interface WebSocketContextType {
  connections: Map<string, WebSocketConnection>;
  createConnection: (
    id: string,
    url: string,
    options?: Partial<WebSocketConnection['options']>
  ) => WebSocketConnection;
  closeConnection: (id: string) => void;
  sendMessage: (id: string, message: string | object) => boolean;
  getConnection: (id: string) => WebSocketConnection | undefined;
  getAllConnections: () => WebSocketConnection[];
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

export const useWebSocketContext = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider');
  }
  return context;
};

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [connections, setConnections] = useState<Map<string, WebSocketConnection>>(new Map());
  const heartbeatTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const reconnectTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const connectionStatus = useConnectionStatus();

  const updateConnection = useCallback((id: string, updates: Partial<WebSocketConnection>) => {
    setConnections(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(id);
      if (existing) {
        newMap.set(id, { ...existing, ...updates, lastActivity: Date.now() });
      }
      return newMap;
    });
  }, []);

  const setupHeartbeat = useCallback((connection: WebSocketConnection) => {
    if (connection.options.heartbeatInterval <= 0) return;

    const sendHeartbeat = () => {
      if (connection.ws?.readyState === WebSocket.OPEN) {
        connection.ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
        updateConnection(connection.id, { messagesSent: connection.messagesSent + 1 });
      }
    };

    const timerId = setInterval(sendHeartbeat, connection.options.heartbeatInterval);
    heartbeatTimers.current.set(connection.id, timerId);
  }, [updateConnection]);

  const clearTimers = useCallback((id: string) => {
    const heartbeatTimer = heartbeatTimers.current.get(id);
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimers.current.delete(id);
    }

    const reconnectTimer = reconnectTimers.current.get(id);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimers.current.delete(id);
    }
  }, []);

  const attemptReconnect = useCallback((connection: WebSocketConnection) => {
    if (!connection.options.reconnect) return;
    if (connection.reconnectAttempts >= connection.options.reconnectAttempts) return;
    if (!connectionStatus.isOnline) return;

    const attempts = connection.reconnectAttempts + 1;
    const delay = Math.min(
      connection.options.reconnectInterval * Math.pow(1.5, connection.reconnectAttempts),
      30000
    );

    updateConnection(connection.id, { 
      status: 'reconnecting',
      reconnectAttempts: attempts 
    });

    console.log(`WebSocket ${connection.id}: Reconnecting in ${delay}ms (attempt ${attempts})`);

    const timerId = setTimeout(() => {
      createWebSocket(connection);
    }, delay);

    reconnectTimers.current.set(connection.id, timerId);
  }, [connectionStatus.isOnline, updateConnection]);

  const createWebSocket = useCallback((connection: WebSocketConnection) => {
    try {
      const ws = new WebSocket(connection.url);
      
      ws.onopen = () => {
        console.log(`WebSocket ${connection.id}: Connected`);
        updateConnection(connection.id, {
          ws,
          status: 'connected',
          reconnectAttempts: 0
        });
        setupHeartbeat(connection);
      };

      ws.onmessage = (event) => {
        updateConnection(connection.id, {
          messagesReceived: connection.messagesReceived + 1
        });

        if (connection.options.onMessage) {
          try {
            const data = JSON.parse(event.data);
            connection.options.onMessage(data);
          } catch {
            connection.options.onMessage(event.data);
          }
        }
      };

      ws.onclose = (event) => {
        console.log(`WebSocket ${connection.id}: Closed (${event.code})`);
        clearTimers(connection.id);
        updateConnection(connection.id, {
          ws: null,
          status: 'disconnected'
        });

        if (event.code !== 1000) {
          attemptReconnect(connection);
        }
      };

      ws.onerror = (error) => {
        console.error(`WebSocket ${connection.id}: Error`, error);
        updateConnection(connection.id, {
          status: 'error'
        });
      };

      updateConnection(connection.id, { ws, status: 'connecting' });
    } catch (error) {
      console.error(`WebSocket ${connection.id}: Failed to create`, error);
      updateConnection(connection.id, { status: 'error' });
      attemptReconnect(connection);
    }
  }, [updateConnection, setupHeartbeat, clearTimers, attemptReconnect]);

  const createConnection = useCallback((
    id: string,
    url: string,
    options: Partial<WebSocketConnection['options']> = {}
  ): WebSocketConnection => {
    const existing = connections.get(id);
    if (existing) {
      console.warn(`WebSocket connection ${id} already exists`);
      return existing;
    }

    const connection: WebSocketConnection = {
      id,
      url,
      ws: null,
      status: 'connecting',
      reconnectAttempts: 0,
      messagesReceived: 0,
      messagesSent: 0,
      lastActivity: Date.now(),
      options: {
        reconnect: true,
        reconnectInterval: 3000,
        reconnectAttempts: 10,
        heartbeatInterval: 30000,
        ...options
      }
    };

    setConnections(prev => new Map(prev).set(id, connection));
    createWebSocket(connection);

    return connection;
  }, [connections, createWebSocket]);

  const closeConnection = useCallback((id: string) => {
    const connection = connections.get(id);
    if (!connection) return;

    clearTimers(id);
    
    if (connection.ws) {
      connection.ws.close(1000, 'User disconnect');
    }

    setConnections(prev => {
      const newMap = new Map(prev);
      newMap.delete(id);
      return newMap;
    });
  }, [connections, clearTimers]);

  const sendMessage = useCallback((id: string, message: string | object): boolean => {
    const connection = connections.get(id);
    if (!connection?.ws || connection.ws.readyState !== WebSocket.OPEN) {
      console.warn(`WebSocket ${id}: Cannot send message - not connected`);
      return false;
    }

    const data = typeof message === 'string' ? message : JSON.stringify(message);
    connection.ws.send(data);
    updateConnection(id, { messagesSent: connection.messagesSent + 1 });
    return true;
  }, [connections, updateConnection]);

  const getConnection = useCallback((id: string) => {
    return connections.get(id);
  }, [connections]);

  const getAllConnections = useCallback((): WebSocketConnection[] => {
    return Array.from(connections.values());
  }, [connections]);

  // Monitor network status changes
  useEffect(() => {
    if (!connectionStatus.isOnline) {
      // Close all connections when offline
      connections.forEach(connection => {
        if (connection.ws) {
          connection.ws.close(1001, 'Network offline');
        }
      });
    } else {
      // Attempt to reconnect when back online
      connections.forEach(connection => {
        if (connection.status === 'disconnected' && connection.options.reconnect) {
          attemptReconnect(connection);
        }
      });
    }
  }, [connectionStatus.isOnline, connections, attemptReconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      connections.forEach(connection => {
        closeConnection(connection.id);
      });
    };
  }, []); // Only run on unmount

  const value: WebSocketContextType = {
    connections,
    createConnection,
    closeConnection,
    sendMessage,
    getConnection,
    getAllConnections
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};