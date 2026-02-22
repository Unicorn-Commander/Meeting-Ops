import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, 
  MicOff, 
  Play, 
  Pause, 
  FileText, 
  ListChecks, 
  Flag, 
  Users, 
  Clock, 
  Sparkles,
  Activity,
  Cpu,
  HardDrive,
  CheckCircle,
  AlertCircle,
  Volume2,
  Bot,
  Brain,
  Target,
  MessageSquare,
  Zap
} from 'lucide-react';
import { config } from '../config';

interface SummaryFormats {
  executive: boolean;
  minutes: boolean;
  bullets: boolean;
  actions: boolean;
  decisions: boolean;
  tasks: boolean;
  transcript: boolean;
}

interface ActionItem {
  id: string;
  action: string;
  owner?: string;
  dueDate?: string;
  status: 'pending' | 'completed';
}

interface UnifiedAgent {
  id: string;
  name: string;
  description: string;
  provider_type: string;
  model_name: string;
  is_active: boolean;
}

interface ProgressiveSummaryMessage {
  type: 'progressive_summary';
  session_id: string;
  agent: {
    id: string;
    name: string;
    role: string;
  };
  summary_data: {
    word_count_at_summary: number;
    interval_used: number;
    next_interval: number;
    model_size: string;
    sections: Record<string, any>;
  };
  timestamp: string;
}

interface SessionData {
  id: string;
  title: string;
  startTime: string;
  duration: number;
  isRecording: boolean;
  transcript: string;
  isProcessingFinalSummary?: boolean;
  summary?: {
    executive?: string;
    bullets?: string[];
    actions?: ActionItem[];
    decisions?: string[];
    tasks?: Array<{task: string; assignee: string}>;
  };
}

export default function LiveRecording() {
  // Check for existing recording session on mount
  const getStoredSession = () => {
    const stored = localStorage.getItem('activeRecordingSession');
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch (e) {
        console.error('Failed to parse stored session:', e);
        localStorage.removeItem('activeRecordingSession');
      }
    }
    return null;
  };

  // Check for last meeting summary (persists until cleared/logout)
  const getStoredSummary = () => {
    const stored = localStorage.getItem('lastMeetingSummary');
    if (stored) {
      try {
        const summary = JSON.parse(stored);
        // Only load if it's a valid summary structure
        if (summary && typeof summary === 'object' && 
            (summary.executive || summary.bullets || summary.actions || summary.decisions)) {
          console.log('📋 Loaded valid stored summary from localStorage');
          return summary;
        } else {
          console.log('⚠️ Invalid summary structure in localStorage, clearing it');
          localStorage.removeItem('lastMeetingSummary');
        }
      } catch (e) {
        console.error('Failed to parse stored summary:', e);
        localStorage.removeItem('lastMeetingSummary');
      }
    }
    return null;
  };

  const storedSession = getStoredSession();
  
  const [isRecording, setIsRecording] = useState(storedSession?.isRecording || false);
  const [sessionData, setSessionData] = useState<SessionData | null>(storedSession);
  const [audioLevel, setAudioLevel] = useState(0);
  const [duration, setDuration] = useState(storedSession?.duration || 0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [summaryFormats, setSummaryFormats] = useState<SummaryFormats>({
    executive: true,
    minutes: false,
    bullets: true,
    actions: true,
    decisions: true,
    tasks: false,
    transcript: false
  });
  const [liveTranscript, setLiveTranscript] = useState<string[]>([]);
  const [autoSummary, setAutoSummary] = useState<any>(getStoredSummary());
  
  // Debug logging for autoSummary changes
  useEffect(() => {
    console.log('🔍🔍🔍 autoSummary state changed:', autoSummary);
    console.log('Has executive?', !!autoSummary?.executive);
    console.log('Has bullets?', !!autoSummary?.bullets);
    console.log('Has actions?', !!autoSummary?.actions);
    console.log('Has decisions?', !!autoSummary?.decisions);
  }, [autoSummary]);
  const [wordCount, setWordCount] = useState(0);
  const [nextUpdateWords, setNextUpdateWords] = useState(500);
  const [activeAgent, setActiveAgent] = useState<UnifiedAgent | null>(null);
  const [progressiveData, setProgressiveData] = useState<{
    intervalUsed: number;
    nextInterval: number;
    modelSize: string;
  } | null>(null);
  const [summarySettings, setSummarySettings] = useState({
    enableLiveSummarization: localStorage.getItem('enableLiveSummarization') !== null 
      ? localStorage.getItem('enableLiveSummarization') === 'true'
      : true, // Default ON for new users
    enableFinalSummary: true,
    summaryTriggerMode: 'word_count', // 'word_count' or 'time'
    summaryWordCountInterval: 500, // Fixed 500 word intervals
    summaryUpdateInterval: 60 // seconds (for legacy time mode)
  });
  // Removed showLiveIntelligence - summaries now integrated into sections
  const [audioDevices, setAudioDevices] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [llmModelName, setLlmModelName] = useState<string>('Granite 3.3 2B');
  const [sttModelName, setSttModelName] = useState<string>('Whisper large-v3-turbo');
  
  const wsRef = useRef<WebSocket | null>(null);
  const audioWsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<Date | null>(storedSession && storedSession.startTime ? (() => {
    const date = new Date(storedSession.startTime);
    return isNaN(date.getTime()) ? null : date;
  })() : null);

  // Clear invalid summary data on mount
  useEffect(() => {
    const stored = localStorage.getItem('lastMeetingSummary');
    if (stored) {
      try {
        const summary = JSON.parse(stored);
        // Remove invalid summary structure
        if (summary && summary.type === 'progressive_trigger') {
          console.log('🧹 Clearing invalid progressive_trigger from localStorage');
          localStorage.removeItem('lastMeetingSummary');
          setAutoSummary(null);
        }
      } catch (e) {
        // Invalid JSON, clear it
        localStorage.removeItem('lastMeetingSummary');
      }
    }
  }, []); // Run once on mount

  // Save session state to localStorage whenever it changes
  useEffect(() => {
    if (sessionData) {
      const toStore = {
        ...sessionData,
        isRecording,
        duration,
        startTime: startTimeRef.current ? startTimeRef.current.toISOString() : sessionData.startTime
      };
      localStorage.setItem('activeRecordingSession', JSON.stringify(toStore));
    } else if (!isRecording) {
      localStorage.removeItem('activeRecordingSession');
    }
  }, [sessionData, isRecording, duration]);

  // Reconnect to existing session if stored
  useEffect(() => {
    if (storedSession && storedSession.isRecording && storedSession.id) {
      console.log('Reconnecting to existing session:', storedSession.id);
      
      // Reconnect to enhanced WebSocket that provides both transcription and auto-summaries
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription-auto/${storedSession.id}`;
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Handle live transcription segments
          if (data.type === 'transcription') {
            const text = data.segment?.text || data.text || '';
            if (text.trim()) {
              console.log('Live transcription (reconnected):', text);
              setLiveTranscript(prev => [...prev, text]);
            }
          } 
          // Handle progressive summaries from backend agent system
          else if (data.type === 'progressive_summary') {
            console.log('🤖 Progressive summary received (reconnection):', data);
            
            // Handle both old and new formats
            let summaryContent, wordCount, nextInterval;
            
            if (data.summary_data) {
              // NEW unified agent format
              summaryContent = data.summary_data.sections;
              wordCount = data.summary_data.word_count_at_summary;
              nextInterval = data.summary_data.next_interval;
              
              // Update progressive interval data
              setProgressiveData({
                intervalUsed: data.summary_data.interval_used,
                nextInterval: data.summary_data.next_interval,
                modelSize: data.summary_data.model_size || 'Granite 3.3 2B'
              });
            } else if (data.data) {
              // OLD format compatibility
              summaryContent = data.data.summary || data.data;
              wordCount = data.data.word_count || wordCount;
              nextInterval = data.data.next_interval || 500;
              
              // Set basic progressive data for old format
              setProgressiveData({
                intervalUsed: wordCount || 0,
                nextInterval: nextInterval,
                modelSize: 'Legacy Format'
              });
            } else {
              console.warn('Unknown progressive summary format in reconnection:', data);
              return;
            }
            
            if (summaryContent) {
              console.log('📊 Setting autoSummary with progressive summary:', summaryContent);
              setAutoSummary(summaryContent);
              
              // Persist summary to localStorage
              localStorage.setItem('lastMeetingSummary', JSON.stringify(summaryContent));
              localStorage.setItem('lastMeetingTimestamp', new Date().toISOString());
              
              // Update word count info
              if (wordCount) {
                setWordCount(wordCount);
              }
              if (nextInterval) {
                setNextUpdateWords(nextInterval);
              }
              
              setSessionData(prev => prev ? {
                ...prev,
                summary: summaryContent
              } : null);
            }
          }
          // Handle legacy auto_summary format for backwards compatibility
          else if (data.type === 'auto_summary') {
            console.log('Auto-summary received (legacy):', data);
            setAutoSummary(data.summary);
            
            // Update word count info if provided
            if (data.word_count) {
              setWordCount(data.word_count);
            }
            if (data.next_update) {
              // Extract number from "in 500 words"
              const match = data.next_update.match(/(\d+)/);
              if (match) {
                setNextUpdateWords(parseInt(match[1]));
              }
            }
            
            setSessionData(prev => prev ? {
              ...prev,
              summary: data.summary
            } : null);
          } 
          // Handle progressive trigger notifications
          else if (data.type === 'progressive_trigger') {
            console.log('⏳ Progressive summary trigger received at', data.word_count, 'words');
            // Don't store this as a summary - it's just a notification
            // The actual summary should come separately
          } 
          else if (data.type === 'status') {
            console.log('Transcription status:', data.data);
          } else {
            // Log any unhandled message types
            console.log('🔍 Unhandled WebSocket message type:', data.type, 'Full message:', data);
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      wsRef.current = ws;
      
      // Audio levels are already connected via the always-on WebSocket
    }
    
    return () => {
      if (wsRef.current) wsRef.current.close();
      // Keep audio levels WebSocket running
    };
  }, []);

  // Connect to audio levels WebSocket (always on for monitoring)
  useEffect(() => {
    let reconnectTimer: NodeJS.Timeout;
    
    const connectAudioLevels = () => {
      try {
        const audioWs = new WebSocket(`${config.wsEndpoints.base}/ws/audio-levels`);
        
        audioWs.onopen = () => {
          console.log('Connected to audio level monitoring');
        };
        
        audioWs.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'audio_level' || data.level !== undefined) {
              setAudioLevel(data.level || data.audio_level || 0);
            }
          } catch (e) {
            console.error('Error parsing audio level:', e);
          }
        };
        
        audioWs.onerror = (error) => {
          console.debug('Audio level WebSocket error (this is normal on first load):', error);
        };
        
        audioWs.onclose = (event) => {
          console.debug('Audio level WebSocket closed, reconnecting in 3s...');
          reconnectTimer = setTimeout(() => {
            if (audioWsRef.current === audioWs) {
              connectAudioLevels();
            }
          }, 3000);
        };
        
        audioWsRef.current = audioWs;
      } catch (error) {
        console.debug('Failed to create audio WebSocket, retrying in 3s...');
        reconnectTimer = setTimeout(connectAudioLevels, 3000);
      }
    };
    
    // Delay initial connection to let backend fully initialize
    const initialDelay = setTimeout(connectAudioLevels, 1000);
    
    return () => {
      clearTimeout(initialDelay);
      clearTimeout(reconnectTimer);
      if (audioWsRef.current) {
        audioWsRef.current.close();
        audioWsRef.current = null;
      }
    };
  }, []); // Connect once on mount
  
  // Check audio devices
  useEffect(() => {
    const checkDevices = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/simple/audio-devices`);
        if (response.ok) {
          const data = await response.json();
          const devices = data.devices || data; // Handle both formats
          
          // Map devices to expected format
          const mappedDevices = devices.map((device: any) => ({
            id: device.deviceId || device.id || `hw:${device.index},0`,
            deviceId: device.deviceId || device.id || `hw:${device.index},0`,
            label: device.label || device.name || 'Unknown Device',
            name: device.name || device.label || 'Unknown Device',
            ...device
          }));
          
          setAudioDevices(mappedDevices);
          if (mappedDevices.length > 0 && !selectedDevice) {
            setSelectedDevice(mappedDevices[0].id || mappedDevices[0].deviceId);
          }
        }
      } catch (error) {
        console.error('Failed to fetch audio devices:', error);
      }
    };
    checkDevices();
  }, []);

  // Duration timer
  useEffect(() => {
    if (isRecording && startTimeRef.current) {
      // Calculate initial duration if reconnecting
      const now = new Date();
      const elapsed = Math.floor((now.getTime() - startTimeRef.current.getTime()) / 1000);
      setDuration(elapsed);
      
      intervalRef.current = setInterval(() => {
        const currentTime = new Date();
        const elapsedSeconds = Math.floor((currentTime.getTime() - startTimeRef.current!.getTime()) / 1000);
        setDuration(elapsedSeconds);
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRecording]);

  // Fetch LLM model name from backend
  useEffect(() => {
    const fetchModelInfo = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/settings/models`);
        if (response.ok) {
          const data = await response.json();
          const label = data.llm?.model_label || data.llm?.model || 'Granite 3.3 2B';
          setLlmModelName(label);
          // Set STT model name based on active backend
          if (data.stt?.active === 'whisper-server-vulkan') {
            const model = data.stt?.primary?.model || 'large-v3-turbo';
            setSttModelName(`Whisper ${model} (Vulkan)`);
          } else {
            const fallbackName = data.stt?.fallback?.name || 'WhisperX NPU';
            setSttModelName(fallbackName);
          }
        }
      } catch (error) {
        console.debug('Failed to fetch model info, using default:', error);
      }
    };
    fetchModelInfo();
  }, []);

  // Fetch auto-summarization settings and active agent
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/auto-summary/settings`);
        if (response.ok) {
          const settings = await response.json();
          setSummarySettings(settings);
        }
      } catch (error) {
        console.error('Failed to fetch summary settings:', error);
      }
    };
    
    const loadActiveAgent = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/unified-agent/agent`);
        if (response.ok) {
          const agent = await response.json();
          setActiveAgent(agent);
          console.log('Unified agent loaded:', agent);
        }
      } catch (error) {
        console.error('Failed to load unified agent:', error);
      }
    };
    
    fetchSettings();
    loadActiveAgent();
  }, []);

  const formatDuration = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Format timestamp for transcript lines based on when they were spoken
  const formatTimestamp = (lineIndex: number) => {
    // Calculate approximate time based on line index and average speaking rate
    // Assuming average 150 words per minute, ~10 words per line
    const secondsPerLine = 4; // Approximate seconds per transcript line
    const totalSeconds = lineIndex * secondsPerLine;
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTranscriptTimestamp = (lineIndex: number) => {
    // For live transcription, show elapsed time since recording started
    if (!startTimeRef.current) return '00:00';
    
    // Calculate seconds since start for this line
    // Assuming lines come in sequentially with ~5 second delays
    const secondsPerLine = 5;
    const elapsedSeconds = Math.min(lineIndex * secondsPerLine, duration);
    const mins = Math.floor(elapsedSeconds / 60);
    const secs = elapsedSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const startRecording = async () => {
    console.log('Starting recording...');
    setIsProcessing(true);
    try {
      // Create session
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          name: `Meeting ${new Date().toLocaleString()}`,
          description: 'Recording from Meeting-Ops'
        })
      });
      
      if (!response.ok) {
        const error = await response.text();
        console.error('Failed to create session:', error);
        throw new Error(`Failed to create session: ${error}`);
      }
      const session = await response.json();
      console.log('Session created:', session);
      
      // Connect to enhanced WebSocket BEFORE starting recording
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription-auto/${session.id}`;
      console.log('🔌 Connecting to WebSocket FIRST:', wsUrl);
      console.log('📊 Session ID:', session.id);
      console.log('⚙️ Summary settings:', summarySettings);
      const ws = new WebSocket(wsUrl);
      
      // Wait for WebSocket to connect before proceeding
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('WebSocket connection timeout'));
        }, 5000);
        
        ws.onopen = () => {
          clearTimeout(timeout);
          console.log('✅ WebSocket connected successfully to:', wsUrl);
          // Send initial message to register connection
          ws.send(JSON.stringify({
            type: 'register',
            session_id: session.id
          }));
          console.log('📤 Sent registration message for session:', session.id);
          resolve();
        };
        
        ws.onerror = (error) => {
          clearTimeout(timeout);
          console.error('❌ WebSocket connection error:', error);
          reject(new Error('WebSocket connection failed'));
        };
      });
      
      console.log('✅ WebSocket connected! Now starting recording...');
      
      // NOW start the actual recording (after WebSocket is connected)
      const startResponse = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id}/start`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_id: selectedDevice || undefined })
        }
      );
      
      if (!startResponse.ok) {
        const error = await startResponse.text();
        console.error('Failed to start recording:', error);
        ws.close(); // Close WebSocket if recording fails
        throw new Error(`Failed to start recording: ${error}`);
      }
      
      const startData = await startResponse.json();
      console.log('Recording started AFTER WebSocket connected:', startData);
      
      const newSession = {
        id: session.id,
        title: session.title || session.name,
        startTime: new Date().toISOString(),
        duration: 0,
        isRecording: true,
        transcript: ''
      };
      
      setSessionData(newSession);
      startTimeRef.current = new Date();
      // Don't reset autoSummary here - keep it if we have one
      // setAutoSummary(null); // Commented out to preserve summaries
      setWordCount(0); // Reset word count
      setNextUpdateWords(summarySettings.summaryWordCountInterval); // Reset next update
      
      // Set up message handler
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('📨 WebSocket message received:', data);
          console.log('📨 Message type:', data.type);
          
          // Handle live transcription segments - check multiple formats
          if (data.type === 'transcription' || data.type === 'transcript_segment') {
            const text = data.segment?.text || data.text || data.transcript || '';
            if (text.trim()) {
              console.log('Live transcription received:', text);
              setLiveTranscript(prev => [...prev, text]);
              
              // Update word count if provided
              if (data.word_count !== undefined) {
                console.log('📊 Word count update from backend:', data.word_count);
                setWordCount(data.word_count);
              } else if (data.segment_word_count !== undefined) {
                // Use segment word count if provided
                console.log('📊 Segment word count:', data.segment_word_count);
                setWordCount(prev => prev + data.segment_word_count);
              } else {
                // Count words locally as fallback
                const words = text.split(/\s+/).filter((w: string) => w.length > 0).length;
                console.log('📊 Local word count fallback:', words);
                setWordCount(prev => prev + words);
              }
            }
          } 
          // Handle progressive summaries from backend agent system
          else if (data.type === 'progressive_summary') {
            console.log('🎯🎯🎯 PROGRESSIVE SUMMARY RECEIVED! 🎯🎯🎯');
            console.log('🤖 Progressive summary received:', data);
            console.log('📦 Full data structure:', JSON.stringify(data, null, 2));
            
            // Log to help debug
            console.error('PROGRESSIVE SUMMARY DEBUG:', {
              hasData: !!data,
              hasSummaryData: !!data.summary_data,
              dataKeys: Object.keys(data),
              summaryDataKeys: data.summary_data ? Object.keys(data.summary_data) : 'none'
            });
            
            // Handle both old and new formats
            let summaryData, summaryContent, wordCount, nextInterval;
            
            if (data.summary_data) {
              // NEW unified agent format
              console.log('📊 Using NEW format - Agent:', data.agent);
              console.log('📊 Summary data structure:', data.summary_data);
              
              summaryData = data.summary_data;
              
              // Check if it's the new plain text format or structured format
              if (data.summary_data.text && typeof data.summary_data.text === 'string') {
                // New plain text format for progressive summaries
                console.log('📝 Plain text progressive summary:', data.summary_data.text);
                summaryContent = {
                  executive: data.summary_data.text,
                  bullets: [],
                  actions: [],
                  decisions: []
                };
                wordCount = data.summary_data.word_count || data.summary_data.word_count_at_summary;
              } else if (data.summary_data.sections) {
                // Structured format (for final summaries)
                console.log('📋 Structured sections content:', data.summary_data.sections);
                summaryContent = data.summary_data.sections;
                wordCount = data.summary_data.word_count_at_summary;
              } else {
                // Fallback to direct summary_data if it has the fields
                summaryContent = data.summary_data;
                wordCount = data.summary_data.word_count_at_summary;
              }
              
              nextInterval = data.summary_data.next_interval;
              
              // Update progressive interval data
              setProgressiveData({
                intervalUsed: data.summary_data.interval_used,
                nextInterval: data.summary_data.next_interval,
                modelSize: data.summary_data.model_size
              });
            } else if (data.data) {
              // OLD format compatibility
              console.log('📊 Using OLD format - Data:', data.data);
              summaryContent = data.data.summary || data.data;
              wordCount = data.data.word_count || wordCount;
              nextInterval = data.data.next_interval || 500;
              
              // Set basic progressive data for old format
              setProgressiveData({
                intervalUsed: wordCount || 0,
                nextInterval: nextInterval,
                modelSize: 'Legacy Format'
              });
            } else {
              console.warn('Unknown progressive summary format:', data);
              return;
            }
            
            if (summaryContent) {
              console.log('📊 Setting autoSummary from WebSocket (new session):', summaryContent);
              console.log('🔍 Summary content type:', typeof summaryContent);
              console.log('🔍 Summary keys:', summaryContent ? Object.keys(summaryContent) : 'null');
              
              // Force update with a callback to verify it's set
              setAutoSummary((prev: any) => {
                console.log('🔄 Previous autoSummary:', prev);
                console.log('🔄 New autoSummary being set:', summaryContent);
                return summaryContent;
              });
              
              // Persist summary to localStorage
              localStorage.setItem('lastMeetingSummary', JSON.stringify(summaryContent));
              localStorage.setItem('lastMeetingTimestamp', new Date().toISOString());
              
              // Update word count info
              if (wordCount) {
                console.log('📝 Updating word count to:', wordCount);
                setWordCount(wordCount);
              }
              if (nextInterval) {
                setNextUpdateWords(nextInterval);
              }
              
              setSessionData(prev => {
                const updated = prev ? {
                  ...prev,
                  summary: summaryContent
                } : null;
                console.log('💾 Updated session data with progressive summary:', updated?.summary);
                return updated;
              });
            }
          }
          // Handle legacy auto_summary format for backwards compatibility
          else if (data.type === 'auto_summary') {
            console.log('🤖 Auto-summary received (legacy):', data);
            console.log('📊 Summary data structure:', data.summary);
            
            setAutoSummary(data.summary);
            
            // Update word count info if provided
            if (data.word_count) {
              console.log('📝 Updating word count to:', data.word_count);
              setWordCount(data.word_count);
            }
            if (data.next_update) {
              console.log('⏰ Next update info:', data.next_update);
              // Extract number from "in 500 words"
              const match = data.next_update.match(/(\d+)/);
              if (match) {
                setNextUpdateWords(parseInt(match[1]));
              }
            }
            
            setSessionData(prev => {
              const updated = prev ? {
                ...prev,
                summary: data.summary
              } : null;
              console.log('💾 Updated session data with summary:', updated?.summary);
              return updated;
            });
          } 
          else if (data.type === 'status') {
            console.log('Transcription status:', data.data);
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        console.error('WebSocket URL was:', wsUrl);
      };
      
      ws.onclose = (event) => {
        console.log('🔌 WebSocket closed:', event.code, event.reason);
        console.log('Was connected to:', wsUrl);
        if (event.code !== 1000) {
          console.error('Abnormal WebSocket closure. Code:', event.code);
        }
      };
      
      wsRef.current = ws;
      
      // Audio levels are already connected via the always-on WebSocket
      
      setIsRecording(true);
      setDuration(0);
      
      // Show success feedback
      console.log('Recording started successfully!');
    } catch (error: any) {
      console.error('Failed to start recording:', error);
      alert(`Failed to start recording: ${error.message}`);
      setIsRecording(false);
    } finally {
      setIsProcessing(false);
    }
  };

  const stopRecording = async () => {
    if (!sessionData) {
      console.error('No session data to stop');
      return;
    }
    
    console.log('Stopping recording...');
    setIsProcessing(true);
    try {
      const stopResponse = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${sessionData.id}/stop`,
        { method: 'POST' }
      );
      
      if (!stopResponse.ok) {
        console.error('Stop response not ok');
      }
      
      // Clean up transcription WebSocket only (keep audio levels running)
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      
      // If final summary is enabled, wait for it
      if (summarySettings.enableFinalSummary) {
        // Show loading state for final summary
        setSessionData(prev => prev ? {
          ...prev,
          isProcessingFinalSummary: true
        } : null);
        
        // Poll for final summary (backend generates it asynchronously)
        setTimeout(async () => {
          try {
            const sessionResponse = await fetch(
              `${config.apiUrl}/api/simple/recording-sessions/${sessionData.id}`
            );
            if (sessionResponse.ok) {
              const updatedSession = await sessionResponse.json();
              if (updatedSession.final_summary) {
                setAutoSummary(updatedSession.final_summary);
                setSessionData(prev => prev ? {
                  ...prev,
                  summary: updatedSession.final_summary,
                  isProcessingFinalSummary: false
                } : null);
              }
            }
          } catch (error) {
            console.error('Failed to fetch final summary:', error);
          }
        }, 3000); // Give backend time to generate final summary
      }
      
      setIsRecording(false);
      // Keep audio level monitoring active
      startTimeRef.current = null;
      localStorage.removeItem('activeRecordingSession');
      
      // Fetch final session data with AI summaries
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${sessionData.id}`);
      if (response.ok) {
        const finalData = await response.json();
        setSessionData(prev => ({
          ...prev!,
          isRecording: false,
          transcript: finalData.transcript_text || liveTranscript.join(' '),
          summary: finalData.ai_insights
        }));
      }
    } catch (error) {
      console.error('Failed to stop recording:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  const toggleFormat = (format: keyof SummaryFormats) => {
    setSummaryFormats(prev => ({ ...prev, [format]: !prev[format] }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-4 pt-14 md:p-6 md:pt-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-6 md:mb-8">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-500 flex items-center justify-center shrink-0">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              Live Recording
            </h1>
            <p className="text-zinc-400 mt-1 text-sm md:text-base">AI-powered live meeting analysis and transcription</p>
          </div>

          {/* Format Toggles */}
          <div className="flex items-center gap-2 flex-wrap">
            {Object.entries({
              executive: 'Executive',
              minutes: 'Minutes',
              bullets: 'Bullets',
              actions: 'Actions',
              decisions: 'Decisions',
              tasks: 'Tasks',
              transcript: 'Transcript'
            }).map(([key, label]) => (
              <button
                key={key}
                onClick={() => toggleFormat(key as keyof SummaryFormats)}
                className={`px-3 py-1.5 text-xs rounded-full border transition-all min-h-[36px] ${
                  summaryFormats[key as keyof SummaryFormats]
                    ? 'bg-zinc-800 border-zinc-700 text-white'
                    : 'bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        {/* Left: Recording Control & Summaries */}
        <div className="lg:col-span-2 space-y-4 md:space-y-6">
          {/* Recording Control */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-4 md:p-8">
            <div className="flex flex-col items-center">
              {/* Audio Device Selector */}
              {!isRecording && audioDevices.length > 1 && (
                <div className="w-full max-w-xs mb-6">
                  <label className="block text-xs text-zinc-400 mb-1.5 text-center">Audio Input</label>
                  <select
                    value={selectedDevice}
                    onChange={(e) => setSelectedDevice(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:border-purple-500 focus:outline-none"
                  >
                    {audioDevices.map((device) => (
                      <option key={device.id} value={device.id}>
                        {device.type === 'USB' ? '\uD83C\uDFA4 ' : '\uD83D\uDCBB '}{device.name || device.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {/* Big Record Button */}
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={audioDevices.length === 0 || isProcessing}
                className={`relative w-32 h-32 rounded-full transition-all transform hover:scale-105 ${
                  isRecording 
                    ? 'bg-red-600 hover:bg-red-500 animate-pulse' 
                    : 'bg-gradient-to-br from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500'
                } ${(audioDevices.length === 0 || isProcessing) ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={isProcessing ? 'Processing...' : (isRecording ? 'Click to stop recording' : 'Click to start recording')}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  {isProcessing ? (
                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-white border-t-transparent" />
                  ) : isRecording ? (
                    <Pause className="w-12 h-12 text-white" />
                  ) : (
                    <Mic className="w-12 h-12 text-white" />
                  )}
                </div>
                {isRecording && (
                  <div className="absolute inset-0 rounded-full border-4 border-red-400 animate-ping" />
                )}
              </button>
              
              {/* Status */}
              <div className="mt-6 text-center">
                <div className="text-2xl font-semibold text-white">
                  {isRecording ? 'Recording...' : 'Ready to Record'}
                </div>
                {isRecording && (
                  <div className="text-4xl font-mono text-zinc-300 mt-2">
                    {formatDuration(duration)}
                  </div>
                )}
                {audioDevices.length === 0 && (
                  <div className="text-red-400 text-sm mt-2 flex items-center gap-2 justify-center">
                    <AlertCircle className="w-4 h-4" />
                    No audio device detected
                  </div>
                )}
              </div>
              
              {/* Pipeline Status & Active Agent */}
              {(isRecording || sessionData) && (
                <div className="mt-6 space-y-4">
                  {/* Active Agent Display */}
                  {activeAgent && (
                    <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800 max-w-xs">
                      <div className="flex items-center gap-3 mb-2">
                        <Bot className="w-5 h-5 text-purple-400" />
                        <span className="text-sm font-medium text-zinc-200">Active Agent</span>
                      </div>
                      <div className="text-xs text-zinc-300">
                        <div className="font-medium">{activeAgent.name}</div>
                        <div className="text-zinc-400 mt-1">{activeAgent.description}</div>
                        <div className="flex items-center gap-1 mt-2">
                          <Target className="w-3 h-3 text-blue-400" />
                          <span className="capitalize">{activeAgent.model_name}</span>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Progressive Interval Data */}
                  {progressiveData && (
                    <div className="p-3 rounded-xl bg-zinc-900/30 border border-zinc-700 max-w-xs">
                      <div className="flex items-center gap-2 mb-2">
                        <Brain className="w-4 h-4 text-green-400" />
                        <span className="text-xs font-medium text-zinc-300">Progressive Intervals</span>
                      </div>
                      <div className="text-xs text-zinc-400 space-y-1">
                        <div>Last: {progressiveData.intervalUsed} words</div>
                        <div>Next: {progressiveData.nextInterval} words</div>
                        <div>Model: {progressiveData.modelSize}</div>
                      </div>
                    </div>
                  )}
                  
                  {/* Pipeline Status */}
                  {sessionData && (
                    <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800 max-w-xs">
                      <div className="flex items-center gap-3 mb-3">
                        <Cpu className="w-5 h-5 text-blue-400" />
                        <span className="text-sm font-medium text-zinc-200">Pipeline Status</span>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-zinc-400">Recording</span>
                          <span className={`flex items-center gap-1 ${
                            isRecording ? 'text-green-400' : 'text-green-600'
                          }`}>
                            <CheckCircle className="w-3 h-3" />
                            {isRecording ? 'Active' : 'Complete'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-zinc-400">Transcription</span>
                          <span className={`flex items-center gap-1 ${
                            liveTranscript.length > 0 ? 'text-green-400' : 
                            isRecording ? 'text-yellow-400' : 'text-zinc-500'
                          }`}>
                            {liveTranscript.length > 0 ? (
                              <><CheckCircle className="w-3 h-3" /> Active</>
                            ) : isRecording ? (
                              <><div className="w-3 h-3 border border-yellow-400 border-t-transparent rounded-full animate-spin"></div> Processing</>
                            ) : (
                              <><div className="w-3 h-3 border border-zinc-500 rounded-full"></div> Pending</>
                            )}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-zinc-400">AI Summary</span>
                          <span className={`flex items-center gap-1 ${
                            autoSummary || sessionData?.summary ? 'text-green-400' : 
                            summarySettings.enableLiveSummarization && isRecording ? 'text-yellow-400' : 
                            'text-zinc-500'
                          }`}>
                            {autoSummary || sessionData?.summary ? (
                              <><CheckCircle className="w-3 h-3" /> Generated</>
                            ) : summarySettings.enableLiveSummarization && isRecording ? (
                              <><Brain className="w-3 h-3 animate-pulse" /> Analyzing</>
                            ) : (
                              <><div className="w-3 h-3 border border-zinc-500 rounded-full"></div> Pending</>
                            )}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Live Summarization Toggle - Simple On/Off */}
                  <div className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800 max-w-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Sparkles className="w-5 h-5 text-yellow-400" />
                        <span className="text-sm font-medium text-zinc-200">Live Summarization</span>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={summarySettings.enableLiveSummarization}
                          onChange={async (e) => {
                            const newSettings = {
                              ...summarySettings,
                              enableLiveSummarization: e.target.checked
                            };
                            setSummarySettings(newSettings);
                            localStorage.setItem('enableLiveSummarization', e.target.checked.toString());
                            // Update backend settings
                            try {
                              await fetch(`${config.apiUrl}/api/auto-summary/settings`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(newSettings)
                              });
                            } catch (error) {
                              console.error('Failed to update settings:', error);
                            }
                          }}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-fuchsia-600"></div>
                      </label>
                    </div>
                    <div className="mt-3 text-xs text-zinc-400">
                      {summarySettings.enableLiveSummarization
                        ? `Every 500 words • ${llmModelName}`
                        : 'Disabled • Enable for live AI analysis'
                      }
                    </div>
                  </div>
                </div>
              )}
              
              {/* Audio Level Meter - Removed due to monitoring issues */}
            </div>
          </div>


          {/* Live Meeting Summary */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <FileText className="w-5 h-5 text-fuchsia-400" />
                Meeting Summary
                <span className="text-xs text-zinc-400">(Live AI Updates)</span>
              </h3>
              {autoSummary?.executive && (
                <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                  Live Update
                </span>
              )}
            </div>
            <div className="text-zinc-300 leading-relaxed">
              {autoSummary?.executive ? (
                <div className="whitespace-pre-wrap text-sm">{autoSummary.executive}</div>
              ) : (
                <span className="text-zinc-500 italic">AI summary will appear here every 500 words...</span>
              )}
            </div>
            {isRecording && autoSummary?.executive && (
              <div className="mt-3 pt-3 border-t border-zinc-700">
                <span className="text-xs text-zinc-400">
                  Updated automatically • Powered by {llmModelName}
                </span>
              </div>
            )}
          </div>

          {/* Two Column Layout for Actions & Decisions - Only show if we have structured data */}
          {autoSummary?.actions || autoSummary?.decisions ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
            {/* Action Items */}
            {summaryFormats.actions && autoSummary?.actions && autoSummary.actions.length > 0 && (
              <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Flag className="w-5 h-5 text-orange-400" />
                    Action Items
                  </h3>
                  {autoSummary?.actions && autoSummary.actions.length > 0 && (
                    <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                      {autoSummary.actions.length} items
                    </span>
                  )}
                </div>
                <div className="space-y-3">
                  {autoSummary?.actions && autoSummary.actions.length > 0 ? (
                    autoSummary.actions.map((action: any, idx: number) => (
                      <div key={idx} className="flex items-start gap-3">
                        <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                        <div className="flex-1">
                          <div className="text-sm text-zinc-200">{action.action || action}</div>
                          {action.owner && (
                            <div className="text-xs text-zinc-400 mt-1">Owner: {action.owner}</div>
                          )}
                          {action.priority && (
                            <span className={`text-xs px-2 py-0.5 rounded-full mt-1 inline-block ${
                              action.priority === 'high' ? 'bg-red-500/20 text-red-300' :
                              action.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                              'bg-green-500/20 text-green-300'
                            }`}>
                              {action.priority}
                            </span>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <span className="text-zinc-500 text-sm italic">
                      Action items will appear here as they're identified...
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Key Decisions */}
            {summaryFormats.decisions && (
              <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <CheckCircle className="w-5 h-5 text-green-400" />
                    Key Decisions
                  </h3>
                  {autoSummary?.decisions && autoSummary.decisions.length > 0 && (
                    <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                      {autoSummary.decisions.length} made
                    </span>
                  )}
                </div>
                <div className="space-y-3">
                  {autoSummary?.decisions && autoSummary.decisions.length > 0 ? (
                    autoSummary.decisions.map((decision: any, idx: number) => (
                      <div key={idx} className="flex items-start gap-3">
                        <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5" />
                        <div className="text-sm text-zinc-200">{decision}</div>
                      </div>
                    ))
                  ) : (
                    <span className="text-zinc-500 text-sm italic">
                      Decisions will be tracked as they're made...
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
          ) : null}

          {/* Meeting Minutes */}
          {summaryFormats.minutes && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  Meeting Minutes
                </h3>
                {autoSummary?.minutes && (
                  <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                    Generated
                  </span>
                )}
              </div>
              <div className="text-zinc-300 leading-relaxed space-y-2">
                {autoSummary?.minutes ? (
                  typeof autoSummary.minutes === 'string' ? (
                    <div className="whitespace-pre-wrap">{autoSummary.minutes}</div>
                  ) : (
                    autoSummary.minutes.map((item: any, idx: number) => (
                      <div key={idx} className="text-sm">{item}</div>
                    ))
                  )
                ) : (
                  <span className="text-zinc-500 italic">Meeting minutes will appear here...</span>
                )}
              </div>
            </div>
          )}

          {/* Tasks */}
          {summaryFormats.tasks && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <ListChecks className="w-5 h-5 text-purple-400" />
                  Tasks
                </h3>
                {autoSummary?.tasks && autoSummary.tasks.length > 0 && (
                  <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                    {autoSummary.tasks.length} tasks
                  </span>
                )}
              </div>
              <div className="space-y-3">
                {autoSummary?.tasks && autoSummary.tasks.length > 0 ? (
                  autoSummary.tasks.map((task: any, idx: number) => (
                    <div key={idx} className="flex items-start gap-3">
                      <CheckCircle className="w-4 h-4 text-purple-400 mt-0.5" />
                      <div className="flex-1">
                        <div className="text-sm text-zinc-200">{task.task || task}</div>
                        {task.assignee && (
                          <div className="text-xs text-zinc-400 mt-1">Assignee: {task.assignee}</div>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <span className="text-zinc-500 text-sm italic">
                    Tasks will appear here as they're identified...
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Bullet Points */}
          {summaryFormats.bullets && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <ListChecks className="w-5 h-5 text-blue-400" />
                  Key Points
                </h3>
                {autoSummary?.bullets && autoSummary.bullets.length > 0 && (
                  <span className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-300 border border-green-500/30">
                    {autoSummary.bullets.length} points
                  </span>
                )}
              </div>
              <ul className="space-y-2">
                {autoSummary?.bullets && autoSummary.bullets.length > 0 ? (
                  autoSummary.bullets.map((bullet: any, idx: number) => (
                    <li key={idx} className="flex items-start gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5" />
                      <span className="text-sm text-zinc-200">{bullet}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-zinc-500 text-sm italic">
                    • Key points will appear here every 500 words...
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* Live Transcript (Optional) */}
          {summaryFormats.transcript && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Live Transcript</h3>
              <div className="h-64 overflow-y-auto space-y-2 font-mono text-xs text-zinc-300 bg-black/30 rounded-lg p-4">
                {liveTranscript.length > 0 ? (
                  liveTranscript.map((line, idx) => (
                    <div key={idx} className="flex gap-2">
                      <span className="text-zinc-500">[{formatTimestamp(idx)}]</span>
                      <span>{line}</span>
                    </div>
                  ))
                ) : (
                  <span className="text-zinc-500">
                    {isRecording ? 'Waiting for speech...' : 'Transcript will appear here during recording'}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: Status & Metrics */}
        <div className="space-y-4 md:space-y-6">
          {/* Agent & Pipeline Status */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-purple-400" />
              Agent & Pipeline Status
            </h3>
            
            {/* Active Agent Display */}
            <div className="mb-4 p-4 bg-purple-500/10 border border-purple-500/20 rounded-lg">
              <div className="flex items-center gap-3 mb-2">
                <Bot className="w-5 h-5 text-purple-400" />
                <div>
                  <div className="text-sm font-medium text-white">
                    {activeAgent ? activeAgent.name : 'Note-Taker'}
                  </div>
                  <div className="text-xs text-purple-300">
                    {activeAgent ? activeAgent.model_name : 'AI Assistant'}
                  </div>
                </div>
              </div>
              <div className="text-xs text-zinc-400">
                {activeAgent ? activeAgent.description : 'Configurable model for meeting analysis'}
              </div>
            </div>
            
            {/* Pipeline Status Grid */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              {/* Recording Status */}
              <div className="p-3 bg-zinc-800/50 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <Mic className={`w-4 h-4 ${isRecording ? 'text-red-400' : 'text-blue-400'}`} />
                  <span className="text-xs text-zinc-400">Recording</span>
                </div>
                <div className={`text-sm font-medium ${isRecording ? 'text-red-300' : 'text-zinc-300'}`}>
                  {isRecording ? 'Active' : 'Ready'}
                </div>
                <div className="text-xs text-zinc-500">{formatDuration(duration)}</div>
              </div>
              
              {/* Transcription Status */}
              <div className="p-3 bg-zinc-800/50 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-green-400" />
                  <span className="text-xs text-zinc-400">Transcription</span>
                </div>
                <div className="text-sm font-medium text-green-300">
                  {isRecording ? 'Live' : 'Ready'}
                </div>
                <div className="text-xs text-orange-300">{sttModelName}</div>
              </div>
              
              {/* AI Model Status */}
              <div className="p-3 bg-zinc-800/50 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className={`w-4 h-4 ${summarySettings.enableLiveSummarization ? 'text-yellow-400' : 'text-zinc-500'}`} />
                  <span className="text-xs text-zinc-400">AI Model</span>
                </div>
                <div className="text-sm font-medium text-yellow-300">
                  {summarySettings.enableLiveSummarization ? llmModelName : 'Standby'}
                </div>
                <div className="text-xs text-yellow-400">{summarySettings.enableLiveSummarization ? 'Port 11437' : 'Offline'}</div>
              </div>
              
              {/* Word Count Progress */}
              <div className="p-3 bg-zinc-800/50 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <Target className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs text-zinc-400">Progress</span>
                </div>
                <div className="text-sm font-medium text-cyan-300">
                  {wordCount} words
                </div>
                <div className="text-xs text-cyan-400">Next: {Math.ceil(wordCount / 500) * 500}</div>
              </div>
            </div>
            
            {/* Live Summarization Progress */}
            {isRecording && summarySettings.enableLiveSummarization && (
              <div className="mt-4 p-3 bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-500/20 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-purple-300">Live Summary Progress</span>
                  <span className="text-xs text-purple-400">{wordCount} / {Math.ceil(wordCount / 500) * 500}</span>
                </div>
                <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-purple-500 to-blue-500 transition-all duration-500"
                    style={{ width: `${Math.min((wordCount % 500) / 500 * 100, 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Live Transcription */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-green-400" />
              Live Transcription
            </h3>
            <div className="h-64 overflow-y-auto space-y-2 font-mono text-xs text-zinc-300 bg-black/30 rounded-lg p-4">
              {liveTranscript.length > 0 ? (
                liveTranscript.slice(-20).map((line, idx) => (
                  <div key={idx} className="animate-fadeIn">
                    <span className="text-zinc-500">[{formatTranscriptTimestamp(idx)}]</span>
                    <span className="ml-2">{line}</span>
                  </div>
                ))
              ) : (
                <div className="text-zinc-500 italic">
                  {isRecording ? (
                    <>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        <span>Listening for speech...</span>
                      </div>
                      <div className="mt-2 text-xs">Session: {sessionData?.id ? sessionData.id.substring(0, 8) + '...' : 'initializing'}</div>
                      <div className="mt-1 text-xs text-zinc-600">
                        Transcription appears after ~5 seconds of speech
                      </div>
                    </>
                  ) : (
                    'Transcript will appear here during recording'
                  )}
                </div>
              )}
            </div>
            
            {isRecording && (
              <div className="mt-4 pt-4 border-t border-zinc-800">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-400">Words Transcribed</span>
                  <span className="text-white font-mono">{wordCount}</span>
                </div>
                
                {/* Progressive Interval Info */}
                {progressiveData ? (
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-400">Progressive Summary</span>
                      <span className="text-zinc-300 text-xs">
                        Next at {progressiveData.nextInterval} words
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-500">Model Size</span>
                      <span className="text-zinc-400">{progressiveData.modelSize}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-500">Last Interval</span>
                      <span className="text-zinc-400">{progressiveData.intervalUsed} words</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex justify-between text-sm mt-2">
                    <span className="text-zinc-400">Auto-Summary</span>
                    <span className="text-zinc-300 text-xs">
                      {summarySettings.summaryTriggerMode === 'word_count' 
                        ? `Next at ${Math.ceil(wordCount / summarySettings.summaryWordCountInterval) * summarySettings.summaryWordCountInterval + summarySettings.summaryWordCountInterval} words`
                        : `Every ${summarySettings.summaryUpdateInterval}s`}
                    </span>
                  </div>
                )}
                
                {/* Active Agent Info */}
                {activeAgent && (
                  <div className="mt-3 pt-2 border-t border-zinc-700">
                    <div className="flex items-center gap-2 text-xs text-zinc-400">
                      <Bot className="w-3 h-3 text-purple-400" />
                      <span>Agent: {activeAgent.name}</span>
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      {activeAgent.model_name} • {activeAgent.provider_type}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Session Info */}
          {sessionData && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Session Info</h3>
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-zinc-400">Session ID</div>
                  <div className="text-sm font-mono text-zinc-200 mt-1">{sessionData.id}</div>
                </div>
                <div>
                  <div className="text-xs text-zinc-400">Started</div>
                  <div className="text-sm text-zinc-200 mt-1">
                    {new Date(sessionData.startTime).toLocaleTimeString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-zinc-400">Duration</div>
                  <div className="text-sm text-zinc-200 mt-1">{formatDuration(duration)}</div>
                </div>
              </div>
            </div>
          )}

          {/* Quick Actions */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <button 
                className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                disabled={!sessionData || isRecording}
              >
                Export Summary
              </button>
              <button 
                className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                disabled={!sessionData || isRecording}
              >
                Email Action Items
              </button>
              <button className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors">
                View All Sessions
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}