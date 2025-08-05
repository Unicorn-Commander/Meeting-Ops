
import { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';

interface UseEnhancedWebSocketOptions {
  url: string;
  onMessage: (data: any) => void;
  onError?: (error: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
}

export const useEnhancedWebSocket = (options: UseEnhancedWebSocketOptions) => {
  const { url, onMessage, onError, onConnect, onDisconnect, reconnectInterval = 1000 } = options;
  const socketRef = useRef<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const connect = () => {
      socketRef.current = io(url, { reconnection: false });

      socketRef.current.on('connect', () => {
        setIsConnected(true);
        onConnect?.();
      });

      socketRef.current.on('disconnect', (reason) => {
        setIsConnected(false);
        onDisconnect?.();
        if (reason === 'io server disconnect') {
          // Server disconnected, try reconnect
          reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
        }
      });

      socketRef.current.on('error', (error) => {
        onError?.(error);
      });

      socketRef.current.on('message', (data) => {
        onMessage(data);
      });
    };

    connect();

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [url, onMessage, onError, onConnect, onDisconnect, reconnectInterval]);

  const sendMessage = (data: any) => {
    if (socketRef.current && isConnected) {
      socketRef.current.emit('message', data);
    }
  };

  return { isConnected, sendMessage };
};
