import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, MicOff, Play, Pause, Square, Circle, Flag, Star, 
  Download, Upload, Mail, Calendar, Clock, Users, 
  Volume2, Headphones, Settings, Zap, AlertCircle,
  CheckCircle, Info, TrendingUp, Activity, BarChart3,
  Save, Share2, Filter, Search, ChevronDown, MoreVertical
} from 'lucide-react';
import { SimpleAlwaysOnTranscription } from '../SimpleAlwaysOnTranscription';
import { TranscriptionSettings } from '../TranscriptionSettings';

interface RecordingStats {
  duration: string;
  speakers: number;
  segments: number;
  flagged: number;
  wordCount: number;
  silenceRatio: number;
}

interface QuickAction {
  id: string;
  label: string;
  icon: React.ElementType;
  action: () => void;
  variant: 'primary' | 'secondary' | 'success' | 'warning' | 'danger';
  disabled?: boolean;
}

export const RecordingHub: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('meeting');
  const [audioLevel, setAudioLevel] = useState(0);
  const [npuStatus, setNpuStatus] = useState<'active' | 'idle' | 'error'>('idle');
  
  const intervalRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Recording stats
  const [stats, setStats] = useState<RecordingStats>({
    duration: '00:00:00',
    speakers: 0,
    segments: 0,
    flagged: 0,
    wordCount: 0,
    silenceRatio: 0
  });

  // Recording presets
  const recordingPresets = [
    { id: 'meeting', label: 'Meeting', icon: Users, settings: { quality: 'high', speakers: true } },
    { id: 'interview', label: 'Interview', icon: Mic, settings: { quality: 'ultra', speakers: true } },
    { id: 'lecture', label: 'Lecture', icon: Volume2, settings: { quality: 'medium', speakers: false } },
    { id: 'conference', label: 'Conference', icon: Headphones, settings: { quality: 'high', speakers: true } },
    { id: 'custom', label: 'Custom', icon: Settings, settings: {} }
  ];

  // Quick actions
  const quickActions: QuickAction[] = [
    {
      id: 'start',
      label: isRecording ? 'Stop' : 'Start',
      icon: isRecording ? Square : Circle,
      action: () => toggleRecording(),
      variant: isRecording ? 'danger' : 'success',
      disabled: false
    },
    {
      id: 'pause',
      label: isPaused ? 'Resume' : 'Pause',
      icon: isPaused ? Play : Pause,
      action: () => togglePause(),
      variant: 'secondary',
      disabled: !isRecording
    },
    {
      id: 'flag',
      label: 'Flag Moment',
      icon: Flag,
      action: () => flagMoment(),
      variant: 'warning',
      disabled: !isRecording
    },
    {
      id: 'save',
      label: 'Quick Save',
      icon: Save,
      action: () => quickSave(),
      variant: 'primary',
      disabled: !activeSession
    },
    {
      id: 'export',
      label: 'Export',
      icon: Download,
      action: () => exportSession(),
      variant: 'secondary',
      disabled: !activeSession
    },
    {
      id: 'email',
      label: 'Email',
      icon: Mail,
      action: () => emailSummary(),
      variant: 'secondary',
      disabled: !activeSession
    },
    {
      id: 'schedule',
      label: 'Schedule',
      icon: Calendar,
      action: () => scheduleRecording(),
      variant: 'secondary',
      disabled: isRecording
    }
  ];

  // Timer effect
  useEffect(() => {
    if (isRecording && !isPaused) {
      intervalRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isRecording, isPaused]);

  // Format time
  const formatTime = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Actions
  const toggleRecording = () => {
    setIsRecording(!isRecording);
    if (!isRecording) {
      setActiveSession(`session_${Date.now()}`);
      setNpuStatus('active');
      setRecordingTime(0);
    } else {
      setNpuStatus('idle');
    }
  };

  const togglePause = () => {
    setIsPaused(!isPaused);
  };

  const flagMoment = () => {
    console.log('Flagging current moment');
    setStats(prev => ({ ...prev, flagged: prev.flagged + 1 }));
  };

  const quickSave = () => {
    console.log('Quick saving session');
  };

  const exportSession = () => {
    console.log('Exporting session');
  };

  const emailSummary = () => {
    console.log('Emailing summary');
  };

  const scheduleRecording = () => {
    console.log('Opening schedule dialog');
  };

  // Simulate audio level
  useEffect(() => {
    const audioInterval = setInterval(() => {
      if (isRecording && !isPaused) {
        setAudioLevel(Math.random() * 100);
      } else {
        setAudioLevel(0);
      }
    }, 100);
    return () => clearInterval(audioInterval);
  }, [isRecording, isPaused]);

  return (
    <div className="flex flex-col h-full bg-gray-950 text-white">
      {/* Header Bar */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 border-b border-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                isRecording ? 'bg-red-500 animate-pulse' : 'bg-gray-700'
              }`}>
                {isRecording ? <Mic className="w-5 h-5 text-white" /> : <MicOff className="w-5 h-5 text-gray-400" />}
              </div>
              <div>
                <h1 className="text-xl font-bold">Recording Hub</h1>
                <p className="text-xs text-gray-400">
                  {isRecording ? 'Recording in progress' : 'Ready to record'}
                </p>
              </div>
            </div>

            {/* Recording Timer */}
            {isRecording && (
              <div className="flex items-center gap-3 px-4 py-2 bg-black/30 rounded-lg">
                <Circle className="w-3 h-3 text-red-500 fill-red-500 animate-pulse" />
                <span className="font-mono text-lg font-semibold">{formatTime(recordingTime)}</span>
                {isPaused && <span className="text-xs text-yellow-400">(Paused)</span>}
              </div>
            )}

            {/* NPU Status */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
              npuStatus === 'active' ? 'bg-green-500/20 text-green-400' :
              npuStatus === 'error' ? 'bg-red-500/20 text-red-400' :
              'bg-gray-500/20 text-gray-400'
            }`}>
              <Zap className="w-4 h-4" />
              <span className="text-xs font-medium">
                NPU: {npuStatus === 'active' ? '16 TOPS Active' : 'Idle'}
              </span>
            </div>
          </div>

          {/* Preset Selector */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-gray-800 rounded-lg p-1">
              {recordingPresets.map(preset => (
                <button
                  key={preset.id}
                  onClick={() => setSelectedPreset(preset.id)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded transition-all ${
                    selectedPreset === preset.id
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                  title={preset.label}
                >
                  <preset.icon className="w-4 h-4" />
                  <span className="text-sm hidden lg:inline">{preset.label}</span>
                </button>
              ))}
            </div>

            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <Settings className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>
      </div>

      {/* Quick Actions Bar */}
      <div className="bg-gray-900 border-b border-gray-800 p-3">
        <div className="flex items-center gap-2 overflow-x-auto">
          {quickActions.map(action => (
            <button
              key={action.id}
              onClick={action.action}
              disabled={action.disabled}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
                transition-all duration-200 whitespace-nowrap
                ${action.disabled ? 'opacity-50 cursor-not-allowed' : 'hover:scale-105 active:scale-95'}
                ${action.variant === 'primary' ? 'bg-purple-600 hover:bg-purple-700 text-white' :
                  action.variant === 'secondary' ? 'bg-gray-700 hover:bg-gray-600 text-gray-200' :
                  action.variant === 'success' ? 'bg-green-600 hover:bg-green-700 text-white' :
                  action.variant === 'warning' ? 'bg-yellow-600 hover:bg-yellow-700 text-white' :
                  action.variant === 'danger' ? 'bg-red-600 hover:bg-red-700 text-white' :
                  'bg-gray-700 hover:bg-gray-600 text-gray-200'
                }
              `}
            >
              <action.icon className="w-4 h-4" />
              {action.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex gap-4 p-4 overflow-hidden">
        {/* Left Panel - Transcription */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Stats Bar */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <div className="grid grid-cols-6 gap-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-purple-400">{stats.speakers}</p>
                <p className="text-xs text-gray-500">Speakers</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-400">{stats.segments}</p>
                <p className="text-xs text-gray-500">Segments</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-yellow-400">{stats.flagged}</p>
                <p className="text-xs text-gray-500">Flagged</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-400">{stats.wordCount}</p>
                <p className="text-xs text-gray-500">Words</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-pink-400">{Math.round(stats.silenceRatio)}%</p>
                <p className="text-xs text-gray-500">Silence</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-cyan-400">{audioLevel.toFixed(0)}</p>
                <p className="text-xs text-gray-500">Audio Level</p>
              </div>
            </div>
          </div>

          {/* Transcription and Insights */}
          <div className="flex-1 flex flex-col gap-4 overflow-hidden">
            {/* Live Transcription */}
            <div className="flex-1 min-h-0">
              <SimpleAlwaysOnTranscription 
                userRole="superuser"
                className="h-full"
              />
            </div>
            
            {/* AI Insights Panel */}
            <div className="h-80 overflow-hidden">
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 h-full">
                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-purple-400" />
                  Real-Time Insights
                </h3>
                <div className="space-y-3 h-full overflow-y-auto">
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <p className="text-sm text-gray-300">
                      🎯 <span className="font-semibold text-purple-400">Key Topic Detected:</span> NPU performance optimization discussion
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <p className="text-sm text-gray-300">
                      🗣️ <span className="font-semibold text-blue-400">Speaker Activity:</span> 3 speakers identified, balanced participation
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <p className="text-sm text-gray-300">
                      📊 <span className="font-semibold text-green-400">Sentiment:</span> 78% positive, high engagement detected
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <p className="text-sm text-gray-300">
                      ⚡ <span className="font-semibold text-yellow-400">Action Item:</span> "Implement INT8 optimization by next week"
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel - Visualizations & Settings */}
        <div className="w-96 flex flex-col gap-4 overflow-y-auto">
          {/* Waveform Visualizer */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
              <Volume2 className="w-4 h-4 text-blue-400" />
              Audio Waveform
            </h3>
            
            {/* Simplified waveform display */}
            <div className="bg-gray-800 rounded-lg h-32 flex items-center justify-center relative overflow-hidden">
              <div className="flex items-end gap-1 h-full p-2">
                {Array.from({ length: 64 }).map((_, i) => (
                  <div
                    key={i}
                    className={`w-1 bg-gradient-to-t transition-all duration-100 ${
                      isRecording 
                        ? 'from-purple-500 to-pink-400' 
                        : 'from-gray-600 to-gray-500'
                    }`}
                    style={{
                      height: isRecording 
                        ? `${20 + Math.sin((Date.now() / 100 + i) * 0.5) * 30 + Math.random() * 20}%`
                        : '2px'
                    }}
                  />
                ))}
              </div>
              
              {!isRecording && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <p className="text-gray-500 text-sm">Start recording to see waveform</p>
                </div>
              )}
            </div>
          </div>
          
          {/* NPU Performance Monitor */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4 text-green-400" />
              NPU Performance
            </h3>
            
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Utilization</span>
                <span className="text-green-400 font-semibold">87%</span>
              </div>
              
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div className="bg-gradient-to-r from-green-500 to-blue-500 h-2 rounded-full w-[87%] transition-all duration-500"></div>
              </div>
              
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-gray-500">Processing Speed</p>
                  <p className="text-purple-400 font-semibold">220x Real-time</p>
                </div>
                <div>
                  <p className="text-gray-500">Latency</p>
                  <p className="text-blue-400 font-semibold">&lt;50ms</p>
                </div>
              </div>
            </div>
          </div>

          {/* Settings Panel */}
          {showSettings && (
            <TranscriptionSettings 
              userRole="superuser"
              onSettingsChange={(settings) => {
                console.log('Settings updated:', settings);
              }}
            />
          )}
        </div>
      </div>

      {/* Audio Level Visualizer */}
      <div className="bg-gray-900 border-t border-gray-800 p-3">
        <div className="flex items-center gap-3">
          <Volume2 className="w-4 h-4 text-gray-400" />
          <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 transition-all duration-100"
              style={{ width: `${audioLevel}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 font-mono w-12 text-right">
            {audioLevel.toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
};