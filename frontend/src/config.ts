// API Configuration

const isDevelopment = import.meta.env.DEV;
const apiUrl = import.meta.env.VITE_API_URL || '';

export const config = {
  // In production, we use relative URLs since nginx proxies /api to backend
  // In development, we use the full URL with port
  apiBaseUrl: isDevelopment && apiUrl ? apiUrl : '',
  
  apiEndpoints: {
    status: '/api/status',
    sessions: '/api/recording-sessions',
    settings: '/api/settings',
    audioDevices: '/api/audio-devices',
    audioLevel: '/api/audio-level',
    systemInfo: '/api/system-info',
  },
  
  wsEndpoints: {
    stream: (sessionId: string) => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = isDevelopment && apiUrl 
        ? apiUrl.replace('http://', '').replace('https://', '')
        : window.location.host;
      return `${protocol}//${host}/ws/stream/${sessionId}`;
    }
  },
  
  // Polling intervals (ms)
  polling: {
    status: 5000,
    sessions: 10000,
    audioLevel: 100,
  }
};

export default config;