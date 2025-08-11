// API Configuration

const isDevelopment = import.meta.env.DEV;

// Make API URL dynamic - evaluated each time it's accessed
const getApiUrl = () => {
  // Check for environment variable first
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  
  // Otherwise use the current hostname with backend port
  // This works whether accessing via localhost, 192.168.x.x, or any other IP
  const host = window.location.hostname;
  return `http://${host}:9050`;
};

// Helper to get WebSocket base URL - also dynamic
const getWsBaseUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const apiUrl = getApiUrl();
  const host = apiUrl.replace('http://', '').replace('https://', '');
  return `${protocol}//${host}`;
};

export const config = {
  // Make apiBaseUrl a getter so it's evaluated dynamically
  get apiBaseUrl() {
    return getApiUrl();
  },
  
  apiEndpoints: {
    // Core endpoints
    status: '/api/status',
    sessions: '/api/recording-sessions',
    settings: '/api/settings',
    audioDevices: '/api/audio-devices',
    audioLevel: '/api/audio-level',
    systemInfo: '/api/system-info',
    
    // Simple recording endpoints
    simpleRecording: {
      sessions: '/api/simple/recording-sessions',
      start: (id: string) => `/api/simple/recording-sessions/${id}/start`,
      stop: (id: string) => `/api/simple/recording-sessions/${id}/stop`,
      session: (id: string) => `/api/simple/recording-sessions/${id}`,
      transcript: (id: string) => `/api/simple/recording-sessions/${id}/transcript`,
      export: (id: string) => `/api/simple/recording-sessions/${id}/export`,
      insights: (id: string) => `/api/simple/recording-sessions/${id}/insights`,
    },
    
    // Auth endpoints
    auth: {
      login: '/api/auth/login',
      logout: '/api/auth/logout',
      register: '/api/auth/register',
      profile: '/api/auth/profile',
      refresh: '/api/auth/refresh',
    },
    
    // Meeting management
    meetings: {
      analytics: '/api/meetings/analytics',
      insights: '/api/meetings/insights',
      speakers: '/api/meetings/speakers',
      keywords: '/api/meetings/keywords',
      summaries: '/api/meetings/summaries',
    },
    
    // System monitoring
    system: {
      npu: '/api/system/npu-status',
      services: '/api/system/services',
      metrics: '/api/system-info',
      logs: '/api/system/logs',
    },
    
    // AI/LLM endpoints
    ai: {
      models: '/api/ai/models',
      settings: '/api/ai/settings',
      transcriptionSettings: '/api/ai/transcription-settings',
      diarizationSettings: '/api/ai/diarization-settings',
    },
    
    // File management
    files: {
      list: '/api/files',
      upload: '/api/files/upload',
      download: (id: string) => `/api/files/${id}/download`,
      delete: (id: string) => `/api/files/${id}`,
    },
    
    // Export endpoints
    export: {
      pdf: (id: string) => `/api/export/${id}/pdf`,
      docx: (id: string) => `/api/export/${id}/docx`,
      txt: (id: string) => `/api/export/${id}/txt`,
      batch: '/api/export/batch',
    },
    
    // User management
    users: {
      list: '/api/users',
      create: '/api/users',
      update: (id: string) => `/api/users/${id}`,
      delete: (id: string) => `/api/users/${id}`,
      roles: '/api/users/roles',
    },
  },
  
  wsEndpoints: {
    // Base URL for WebSocket connections
    get base() {
      return getWsBaseUrl();
    },
    
    // Core WebSocket endpoints
    stream: (sessionId: string) => `${getWsBaseUrl()}/ws/stream/${sessionId}`,
    transcription: (sessionId: string) => `${getWsBaseUrl()}/ws/transcription/${sessionId}`,
    audioLevels: () => `${getWsBaseUrl()}/ws/audio-levels`,
    systemMetrics: () => `${getWsBaseUrl()}/ws/system-metrics`,
    
    // Transcription loop (real-time transcription)
    transcriptionLoop: () => `${getWsBaseUrl()}/api/transcription-loop/ws`,
    
    // Time-shift recording
    timeshift: {
      start: () => `${getWsBaseUrl()}/ws/timeshift/start`,
      stop: () => `${getWsBaseUrl()}/ws/timeshift/stop`,
      stream: (sessionId: string) => `${getWsBaseUrl()}/ws/timeshift/${sessionId}`,
    }
  },
  
  // Polling intervals (ms)
  polling: {
    status: 5000,
    sessions: 10000,
    audioLevel: 100,
    systemMetrics: 2000,
    npuStatus: 3000,
  },
  
  // External service URLs (configurable)
  externalServices: {
    ollama: import.meta.env.VITE_OLLAMA_URL || 'http://localhost:11434',
    inferenceServer: import.meta.env.VITE_INFERENCE_URL || 'http://localhost:8080',
  }
};

export default config;