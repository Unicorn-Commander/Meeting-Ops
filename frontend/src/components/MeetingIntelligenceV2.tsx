import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Brain, Sparkles, FileText, Copy, Save, Download, RefreshCw,
  Clock, User, CheckCircle, AlertCircle, Edit2, Eye, EyeOff,
  Zap, Cpu, Loader2, ChevronDown, ChevronUp, Settings
} from 'lucide-react';
import { config } from '../config';

// AI Agent Names
const AI_AGENTS = {
  LIVE: {
    name: 'Hermes', // Fast messenger god - perfect for live updates
    icon: Zap,
    description: 'Real-time meeting assistant',
    color: 'purple'
  },
  COMPREHENSIVE: {
    name: 'Athena', // Goddess of wisdom - perfect for deep analysis
    icon: Brain,
    description: 'Deep analysis & comprehensive reports',
    color: 'blue'
  }
};

interface MeetingSummary {
  keyPoints: string;
  decisions: string;
  actionItems: string;
  participants: string;
  nextSteps: string;
  lastUpdated: string;
}

interface ComprehensiveReport {
  executiveSummary: string;
  detailedNotes: string;
  transcriptAnalysis: string;
  recommendations: string;
  risks: string;
  opportunities: string;
  timeline: string;
  generatedAt: string;
}

interface MeetingIntelligenceV2Props {
  sessionId: string;
  isRecording: boolean;
  transcript: string;
  onSummaryUpdate?: (summary: MeetingSummary) => void;
  className?: string;
}

export const MeetingIntelligenceV2: React.FC<MeetingIntelligenceV2Props> = ({
  sessionId,
  isRecording,
  transcript,
  onSummaryUpdate,
  className = ''
}) => {
  // Live Summary State (Hermes)
  const [liveSummary, setLiveSummary] = useState<MeetingSummary>({
    keyPoints: '',
    decisions: '',
    actionItems: '',
    participants: '',
    nextSteps: '',
    lastUpdated: new Date().toISOString()
  });
  
  // Comprehensive Report State (Athena)
  const [comprehensiveReport, setComprehensiveReport] = useState<ComprehensiveReport | null>(null);
  
  // UI State
  const [activeTab, setActiveTab] = useState<'live' | 'comprehensive'>('live');
  const [isEditing, setIsEditing] = useState<{ [key: string]: boolean }>({});
  const [autoGenerateLive, setAutoGenerateLive] = useState(true); // On by default for better UX
  const [useRealLLM, setUseRealLLM] = useState(true); // Use real LLM by default
  const [showRetranscription, setShowRetranscription] = useState(false);
  const [isRetranscribing, setIsRetranscribing] = useState(false);
  const [retranscriptionQuality, setRetranscriptionQuality] = useState<'fast' | 'balanced' | 'highest'>('highest');
  const [isGeneratingLive, setIsGeneratingLive] = useState(false);
  const [isGeneratingComprehensive, setIsGeneratingComprehensive] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [copySuccess, setCopySuccess] = useState<string | null>(null);
  
  // Refs
  const updateTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastTranscriptRef = useRef<string>('');
  const wsRef = useRef<WebSocket | null>(null);
  const recordingStartTime = useRef<number>(Date.now());
  const updateCount = useRef<number>(0);
  
  // Calculate adaptive interval based on meeting duration
  const getAdaptiveInterval = (): number => {
    const elapsed = (Date.now() - recordingStartTime.current) / 1000; // seconds
    
    // Start with 15 seconds, gradually increase
    if (elapsed < 300) return 15;        // First 5 minutes: 15 seconds
    if (elapsed < 600) return 30;        // 5-10 minutes: 30 seconds
    if (elapsed < 1800) return 60;       // 10-30 minutes: 1 minute
    if (elapsed < 3600) return 120;      // 30-60 minutes: 2 minutes
    return 180;                          // After 1 hour: 3 minutes
  };

  // Auto-generate live summary during recording
  useEffect(() => {
    if (!isRecording) {
      // Reset when recording stops
      recordingStartTime.current = Date.now();
      updateCount.current = 0;
      if (updateTimerRef.current) {
        clearInterval(updateTimerRef.current);
      }
      return;
    }
    
    if (!autoGenerateLive) {
      // Auto-generation is off
      if (updateTimerRef.current) {
        clearInterval(updateTimerRef.current);
      }
      return;
    }
    
    // Set recording start time
    if (updateCount.current === 0) {
      recordingStartTime.current = Date.now();
    }

    // Initial update after a short delay
    setTimeout(() => {
      if (transcript && transcript.length > 20) {
        console.log('[MeetingIntelligence] Initial auto-update');
        updateLiveSummary();
      }
    }, 3000);

    // Set up adaptive periodic updates
    const scheduleNextUpdate = () => {
      const interval = getAdaptiveInterval();
      console.log(`[MeetingIntelligence] Next update in ${interval} seconds`);
      
      updateTimerRef.current = setTimeout(() => {
        if (transcript && transcript.length > lastTranscriptRef.current.length) {
          console.log('[MeetingIntelligence] Auto-generating summary', {
            updateNumber: ++updateCount.current,
            interval,
            transcriptGrowth: transcript.length - lastTranscriptRef.current.length
          });
          updateLiveSummary();
          lastTranscriptRef.current = transcript;
        }
        // Schedule next update
        if (isRecording && autoGenerateLive) {
          scheduleNextUpdate();
        }
      }, interval * 1000);
    };
    
    scheduleNextUpdate();

    return () => {
      if (updateTimerRef.current) {
        clearTimeout(updateTimerRef.current);
      }
    };
  }, [isRecording, autoGenerateLive, transcript]);

  // WebSocket for real-time updates
  useEffect(() => {
    if (!isRecording || !sessionId) return;

    const wsUrl = `${config.wsEndpoints.base}/ws/meeting-intelligence/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[MeetingIntelligence] WebSocket connected');
      ws.send(JSON.stringify({
        type: 'config',
        agent: 'hermes',
        adaptiveInterval: getAdaptiveInterval()
      }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'live-summary') {
          setLiveSummary(prev => ({
            ...prev,
            ...data.summary,
            lastUpdated: new Date().toISOString()
          }));
        }
      } catch (err) {
        console.error('[MeetingIntelligence] WebSocket error:', err);
      }
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [sessionId, isRecording]);

  const updateLiveSummary = async () => {
    if (isGeneratingLive || !transcript) return;
    
    setIsGeneratingLive(true);
    try {
      // Use real LLM endpoint or simple mock based on setting
      const endpoint = useRealLLM 
        ? '/api/meeting-intelligence-real/live-notes'
        : '/api/meeting-intelligence-simple/live-notes';
      
      const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          transcript: transcript,
          agent: 'hermes',
          templates: ['key-points', 'decisions', 'action-items', 'participants', 'next-steps']
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[MeetingIntelligence] Received data:', data);
        const newSummary: MeetingSummary = {
          keyPoints: data.notes?.key_points?.content || data.notes?.executive_summary?.key_points?.join('\n• ') || liveSummary.keyPoints || '',
          decisions: data.notes?.decisions?.items?.join('\n') || liveSummary.decisions || '',
          actionItems: formatActionItems(data.notes?.action_items?.items) || liveSummary.actionItems || '',
          participants: Array.isArray(data.notes?.participants) ? data.notes.participants.join(', ') : (liveSummary.participants || ''),
          nextSteps: data.notes?.next_steps?.content || data.notes?.next_steps || liveSummary.nextSteps || '',
          lastUpdated: new Date().toISOString()
        };
        console.log('[MeetingIntelligence] Updated summary:', newSummary);
        
        // Preserve existing content and merge with new content
        setLiveSummary(prev => ({
          keyPoints: newSummary.keyPoints || prev.keyPoints,
          decisions: newSummary.decisions || prev.decisions,
          actionItems: newSummary.actionItems || prev.actionItems,
          participants: newSummary.participants || prev.participants,
          nextSteps: newSummary.nextSteps || prev.nextSteps,
          lastUpdated: newSummary.lastUpdated
        }));
        
        if (onSummaryUpdate) {
          onSummaryUpdate(newSummary);
        }
      }
    } catch (error) {
      console.error('[MeetingIntelligence] Failed to update live summary:', error);
    } finally {
      setIsGeneratingLive(false);
    }
  };

  const generateComprehensiveReport = async () => {
    if (isGeneratingComprehensive || !transcript) return;
    
    setIsGeneratingComprehensive(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/meeting-intelligence-simple/final-report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          transcript: transcript,
          agent: 'athena',
          live_summary: liveSummary
        })
      });

      if (response.ok) {
        const data = await response.json();
        setComprehensiveReport({
          executiveSummary: data.report?.sections?.overview?.content || 'Executive summary will be generated...',
          detailedNotes: data.report?.sections?.detailed_notes?.content || 'Detailed notes will be generated...',
          transcriptAnalysis: data.report?.sections?.analysis?.content || 'Transcript analysis will be generated...',
          recommendations: data.report?.sections?.recommendations?.content || 'Recommendations will be generated...',
          risks: data.report?.sections?.risks?.content || 'Risk assessment will be generated...',
          opportunities: data.report?.sections?.opportunities?.content || 'Opportunities will be generated...',
          timeline: data.report?.sections?.timeline?.content || 'Timeline will be generated...',
          generatedAt: new Date().toISOString()
        });
      }
    } catch (error) {
      console.error('[MeetingIntelligence] Failed to generate comprehensive report:', error);
    } finally {
      setIsGeneratingComprehensive(false);
    }
  };

  const formatActionItems = (items: any[]): string => {
    if (!items || items.length === 0) return '';
    return items.map(item => 
      `• ${item.task}${item.owner ? ` (${item.owner})` : ''}${item.deadline ? ` - Due: ${item.deadline}` : ''}`
    ).join('\n');
  };

  const handleFieldEdit = (field: string, value: string) => {
    if (activeTab === 'live') {
      setLiveSummary(prev => ({
        ...prev,
        [field]: value,
        lastUpdated: new Date().toISOString()
      }));
    } else if (comprehensiveReport) {
      setComprehensiveReport(prev => prev ? {
        ...prev,
        [field]: value,
        generatedAt: new Date().toISOString()
      } : null);
    }
  };

  const copyToClipboard = async (field: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopySuccess(field);
      setTimeout(() => setCopySuccess(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const saveSummary = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/meeting-intelligence/save-summary`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          live_summary: liveSummary,
          comprehensive_report: comprehensiveReport
        })
      });

      if (response.ok) {
        console.log('[MeetingIntelligence] Summary saved successfully');
      }
    } catch (error) {
      console.error('[MeetingIntelligence] Failed to save summary:', error);
    }
  };

  const exportSummary = () => {
    const data = {
      session_id: sessionId,
      generated_at: new Date().toISOString(),
      live_summary: liveSummary,
      comprehensive_report: comprehensiveReport
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `meeting-summary-${sessionId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Helper function to get proper color classes
  const getColorClass = (color: string) => {
    const colorMap: { [key: string]: string } = {
      purple: 'text-purple-400',
      blue: 'text-blue-400',
      green: 'text-green-400',
      orange: 'text-orange-400',
      yellow: 'text-yellow-400',
      red: 'text-red-400',
      cyan: 'text-cyan-400',
      indigo: 'text-indigo-400'
    };
    return colorMap[color] || 'text-gray-400';
  };

  const EditableField: React.FC<{
    label: string;
    field: string;
    value: string;
    icon: React.ComponentType<{className?: string}>;
    color: string;
  }> = ({ label, field, value, icon: Icon, color }) => {
    const [isEditingField, setIsEditingField] = useState(false);
    const [editValue, setEditValue] = useState(value);
    
    useEffect(() => {
      setEditValue(value);
    }, [value]);

    const handleSave = () => {
      handleFieldEdit(field, editValue);
      setIsEditingField(false);
    };

    return (
      <div className="bg-gray-800/50 rounded-lg p-4 border-l-4 border-l-purple-400">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Icon className={`w-4 h-4 ${getColorClass(color)}`} />
            <h4 className={`text-sm font-medium ${getColorClass(color)}`}>{label}</h4>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsEditingField(!isEditingField)}
              className="p-1 rounded hover:bg-gray-700 transition-colors"
              title={isEditingField ? 'View mode' : 'Edit mode'}
            >
              {isEditingField ? (
                <Eye className="w-3 h-3 text-gray-400" />
              ) : (
                <Edit2 className="w-3 h-3 text-gray-400" />
              )}
            </button>
            <button
              onClick={() => copyToClipboard(field, value)}
              className="p-1 rounded hover:bg-gray-700 transition-colors"
              title="Copy to clipboard"
            >
              {copySuccess === field ? (
                <CheckCircle className="w-3 h-3 text-green-400" />
              ) : (
                <Copy className="w-3 h-3 text-gray-400" />
              )}
            </button>
          </div>
        </div>
        
        {isEditingField ? (
          <div>
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="w-full bg-gray-900 text-gray-300 text-sm p-3 rounded border border-gray-700 focus:border-purple-500 focus:outline-none resize-none leading-relaxed"
              rows={6}
              autoFocus
            />
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => {
                  setEditValue(value);
                  setIsEditingField(false);
                }}
                className="px-2 py-1 text-xs bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-2 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-500"
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
            {value ? (
              <div className="space-y-2">
                {value.split('\n').filter(line => line.trim()).map((line, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    {line.trim().startsWith('•') ? (
                      <>
                        <span className={`${getColorClass(color)} text-sm mt-0.5 flex-shrink-0`}>•</span>
                        <span className="text-gray-300 leading-relaxed">{line.replace(/^•\s*/, '')}</span>
                      </>
                    ) : line.trim().startsWith('-') ? (
                      <>
                        <span className={`${getColorClass(color)} text-sm mt-0.5 flex-shrink-0`}>-</span>
                        <span className="text-gray-300 leading-relaxed">{line.replace(/^-\s*/, '')}</span>
                      </>
                    ) : (
                      <span className="text-gray-300 leading-relaxed">{line}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-3">
                  <Icon className={`w-5 h-5 ${getColorClass(color)} opacity-50`} />
                </div>
                <p className="text-gray-500 text-sm">
                  {isRecording ? `${label} will appear here as content is generated` : `Start recording to see ${label.toLowerCase()}`}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isRecording ? 'bg-green-500/20' : 'bg-gray-800'}`}>
              <Brain className={`w-5 h-5 ${isRecording ? 'text-green-400' : 'text-gray-400'}`} />
            </div>
            <div>
              <h3 className="text-sm font-medium text-white flex items-center gap-2">
                Meeting Intelligence
                {isRecording && autoGenerateLive && activeTab === 'live' && (
                  <span className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded-full animate-pulse">
                    AUTO
                  </span>
                )}
              </h3>
              <p className="text-xs text-gray-400">
                Powered by {activeTab === 'live' ? AI_AGENTS.LIVE.name : AI_AGENTS.COMPREHENSIVE.name}
                {autoGenerateLive && isRecording && activeTab === 'live' && (
                  <span className="ml-2 text-purple-400">• Auto-generating</span>
                )}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={saveSummary}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
              title="Save summary"
            >
              <Save className="w-4 h-4 text-gray-400" />
            </button>
            <button
              onClick={exportSummary}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
              title="Export summary"
            >
              <Download className="w-4 h-4 text-gray-400" />
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
            >
              <Settings className="w-4 h-4 text-gray-400" />
            </button>
          </div>
        </div>

        {/* Agent Tabs */}
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('live')}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg transition-colors ${
              activeTab === 'live'
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            <Zap className="w-4 h-4" />
            <span className="text-sm font-medium">{AI_AGENTS.LIVE.name}</span>
            {isRecording && activeTab === 'live' && (
              <span className="ml-2 w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            )}
          </button>
          
          <button
            onClick={() => setActiveTab('comprehensive')}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg transition-colors ${
              activeTab === 'comprehensive'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            <Brain className="w-4 h-4" />
            <span className="text-sm font-medium">{AI_AGENTS.COMPREHENSIVE.name}</span>
            {!isRecording && !comprehensiveReport && (
              <span className="ml-2 text-xs text-yellow-400">Ready</span>
            )}
          </button>
        </div>

        {/* Retranscription Controls - Show when recording is complete */}
        {!isRecording && sessionId && (
          <div className="mt-3">
            <button
              onClick={() => setShowRetranscription(!showRetranscription)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-orange-500/20 text-orange-400 text-sm hover:bg-orange-500/30 transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              Post-Recording Enhancement
              {showRetranscription ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            
            {showRetranscription && (
              <div className="mt-2 p-3 bg-orange-500/10 border border-orange-500/20 rounded-lg">
                <p className="text-xs text-orange-300 mb-3">
                  Re-analyze the complete recording with full context and speaker identification for maximum accuracy.
                </p>
                
                <div className="flex items-center gap-4 mb-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Quality</label>
                    <select
                      value={retranscriptionQuality}
                      onChange={(e) => setRetranscriptionQuality(e.target.value as any)}
                      className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-white"
                    >
                      <option value="fast">Fast (2x speed)</option>
                      <option value="balanced">Balanced</option>
                      <option value="highest">Highest (Recommended)</option>
                    </select>
                  </div>
                  
                  <button
                    onClick={startRetranscription}
                    disabled={isRetranscribing}
                    className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                      isRetranscribing
                        ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                        : 'bg-orange-600 hover:bg-orange-500 text-white'
                    }`}
                  >
                    {isRetranscribing ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
                        Processing...
                      </>
                    ) : (
                      'Start Enhancement'
                    )}
                  </button>
                </div>
                
                <div className="text-xs text-gray-500">
                  This will use Minerva (Correction Agent) + Athena (Analysis Agent) for comprehensive enhancement.
                </div>
              </div>
            )}
          </div>
        )}

        {/* Settings Panel */}
        {showSettings && activeTab === 'live' && (
          <div className="mt-3 p-3 bg-gray-800 rounded-lg">
            <h4 className="text-xs font-medium text-gray-300 mb-2">Live Generation Settings</h4>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs text-gray-400">
                  <span>Auto-Generate Live</span>
                </label>
                <button
                  onClick={() => setAutoGenerateLive(!autoGenerateLive)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    autoGenerateLive ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      autoGenerateLive ? 'translate-x-5' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              
              {autoGenerateLive && (
                <div className="text-xs text-gray-500 italic">
                  Updates adapt: 15s → 30s → 1m → 2m → 3m
                </div>
              )}
              
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs text-gray-400">
                  <span>Use Real LLM</span>
                </label>
                <button
                  onClick={() => setUseRealLLM(!useRealLLM)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    useRealLLM ? 'bg-green-600' : 'bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      useRealLLM ? 'translate-x-5' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              
              {!useRealLLM && (
                <div className="text-xs text-yellow-400">
                  ⚠️ Using mock data for testing
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3 max-h-[500px] overflow-y-auto">
        {activeTab === 'live' ? (
          /* Live Summary (Hermes) */
          <>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <Clock className="w-3 h-3" />
                <span>Last updated: {new Date(liveSummary.lastUpdated).toLocaleTimeString()}</span>
              </div>
              <div className="flex items-center gap-2">
                {isGeneratingLive && (
                  <div className="flex items-center gap-2 text-xs text-purple-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Generating...</span>
                  </div>
                )}
                <button
                  onClick={updateLiveSummary}
                  disabled={isGeneratingLive || !transcript}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors ${
                    isGeneratingLive || !transcript
                      ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-500 text-white'
                  }`}
                >
                  {isGeneratingLive ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  {autoGenerateLive ? 'Update Now' : 'Generate Summary'}
                </button>
              </div>
            </div>

            <EditableField
              label="Key Points"
              field="keyPoints"
              value={liveSummary.keyPoints}
              icon={Sparkles}
              color="purple"
            />

            <EditableField
              label="Decisions"
              field="decisions"
              value={liveSummary.decisions}
              icon={CheckCircle}
              color="green"
            />

            <EditableField
              label="Action Items"
              field="actionItems"
              value={liveSummary.actionItems}
              icon={FileText}
              color="blue"
            />

            <EditableField
              label="Participants"
              field="participants"
              value={liveSummary.participants}
              icon={User}
              color="orange"
            />

            <EditableField
              label="Next Steps"
              field="nextSteps"
              value={liveSummary.nextSteps}
              icon={ChevronUp}
              color="yellow"
            />
          </>
        ) : (
          /* Comprehensive Report (Athena) */
          <>
            {!comprehensiveReport ? (
              <div className="text-center py-8">
                <Brain className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <h4 className="text-sm font-medium text-gray-300 mb-2">
                  {isRecording ? 'Recording in Progress' : 'Comprehensive Analysis Available'}
                </h4>
                <p className="text-xs text-gray-500 mb-4">
                  {isRecording 
                    ? 'Comprehensive analysis will be available after recording stops'
                    : 'Generate a deep analysis of your meeting'}
                </p>
                <button
                  onClick={generateComprehensiveReport}
                  disabled={isRecording || isGeneratingComprehensive}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isRecording
                      ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                      : 'bg-blue-600 text-white hover:bg-blue-500'
                  }`}
                >
                  {isGeneratingComprehensive ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                      Analyzing...
                    </>
                  ) : (
                    'Generate Comprehensive Report'
                  )}
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <Clock className="w-3 h-3" />
                    <span>Generated: {new Date(comprehensiveReport.generatedAt).toLocaleString()}</span>
                  </div>
                  <button
                    onClick={generateComprehensiveReport}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-gray-800 hover:bg-gray-700 text-gray-400"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Regenerate
                  </button>
                </div>

                <EditableField
                  label="Executive Summary"
                  field="executiveSummary"
                  value={comprehensiveReport.executiveSummary}
                  icon={FileText}
                  color="blue"
                />

                <EditableField
                  label="Detailed Notes"
                  field="detailedNotes"
                  value={comprehensiveReport.detailedNotes}
                  icon={FileText}
                  color="purple"
                />

                <EditableField
                  label="Transcript Analysis"
                  field="transcriptAnalysis"
                  value={comprehensiveReport.transcriptAnalysis}
                  icon={Brain}
                  color="cyan"
                />

                <EditableField
                  label="Recommendations"
                  field="recommendations"
                  value={comprehensiveReport.recommendations}
                  icon={Sparkles}
                  color="green"
                />

                <EditableField
                  label="Risk Assessment"
                  field="risks"
                  value={comprehensiveReport.risks}
                  icon={AlertCircle}
                  color="red"
                />

                <EditableField
                  label="Opportunities"
                  field="opportunities"
                  value={comprehensiveReport.opportunities}
                  icon={Zap}
                  color="yellow"
                />

                <EditableField
                  label="Timeline & Milestones"
                  field="timeline"
                  value={comprehensiveReport.timeline}
                  icon={Clock}
                  color="indigo"
                />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};