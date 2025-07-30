import { useState, useEffect, useCallback } from 'react';

export default function useWebSocket(url: string) {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isConnected, setIsConnected] = useState(false);

  // Connect to WebSocket
  useEffect(() => {
    const ws = new WebSocket(url);
    
    ws.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'audio_level') {
          setAudioLevel(data.level);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };
    
    ws.onclose = () => {
      setIsConnected(false);
      console.log('WebSocket disconnected');
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    setSocket(ws);
    
    return () => {
      ws.close();
    };
  }, [url]);

  return { audioLevel, isConnected };
}
