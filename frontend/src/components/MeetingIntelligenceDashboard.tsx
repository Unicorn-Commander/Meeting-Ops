import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Brain, FileText, ListChecks, Clipboard, BarChart3, Flag,
  Eye, EyeOff, RefreshCw, Loader2, Settings, Wifi, WifiOff,
  Zap, Clock, Target, Users, Calendar, TrendingUp, Grid3X3,
  FileBarChart, GitBranch, CheckSquare
} from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

interface MeetingData {
  transcript: string;
  notes: any;
  sessionId: string;
  duration: number;
  participants: string[];
  topics: string[];
}

interface TemplateConfig {
  id: string;
  name: string;
  icon: React.ComponentType<{className?: string}>;
  description: string;
  color: string;
  auto: boolean;
  keywords: string[];
  type: 'live' | 'final';  // Live notes vs final reports
  priority: number; // For auto-selection ordering
}

interface ActionItem {
  task: string;
  owner: string;
  priority: 'high' | 'medium' | 'low';
  deadline?: string;
  status: 'pending' | 'completed';
}

interface ParsedData {
  actionItems: ActionItem[];
  keyPoints: string[];
  decisions: string[];
  summary: string;
  participants: string[];
}

export const MeetingIntelligenceDashboard: React.FC<{
  meetingData: MeetingData;
  isRecording: boolean;
  className?: string;
}> = ({ meetingData, isRecording, className = '' }) => {
  const { getOrgQueryUrl } = useOrg();
  
  // State management with localStorage persistence
  const [activeLiveTemplates, setActiveLiveTemplates] = useState<string[]>(() => {
    const saved = localStorage.getItem('meeting-intelligence-live-templates');
    return saved ? JSON.parse(saved) : ['executive-summary'];
  });
  const [activeFinalTemplates, setActiveFinalTemplates] = useState<string[]>(() => {
    const saved = localStorage.getItem('meeting-intelligence-final-templates');
    return saved ? JSON.parse(saved) : ['full-report', 'action-items'];
  });
  const [viewMode, setViewMode] = useState<'live' | 'final'>(() => {
    const saved = localStorage.getItem('meeting-intelligence-view-mode');
    return saved ? JSON.parse(saved) : 'live';
  });
  const [autoDetectionLive, setAutoDetectionLive] = useState(() => {
    const saved = localStorage.getItem('meeting-intelligence-auto-live');
    return saved ? JSON.parse(saved) : true;
  });
  const [autoDetectionFinal, setAutoDetectionFinal] = useState(() => {
    const saved = localStorage.getItem('meeting-intelligence-auto-final');
    return saved ? JSON.parse(saved) : true;
  });
  const [liveAiEnabled, setLiveAiEnabled] = useState(() => {
    const saved = localStorage.getItem('meeting-intelligence-live-ai-enabled');
    return saved ? JSON.parse(saved) : true;
  });
  // Generated content state with persistence
  const [realNotes, setRealNotes] = useState<any>(() => {
    const saved = localStorage.getItem(`meeting-intelligence-live-notes-${meetingData.sessionId}`);
    return saved ? JSON.parse(saved) : null;
  });
  const [finalReport, setFinalReport] = useState<any>(() => {
    const saved = localStorage.getItem(`meeting-intelligence-final-report-${meetingData.sessionId}`);
    return saved ? JSON.parse(saved) : null;
  });
  const [notesLoading, setNotesLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  // Static color class mapping for Tailwind (dynamic class names are not compiled)
  const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    purple: { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500' },
    blue: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500' },
    red: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500' },
    yellow: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500' },
    green: { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500' },
    orange: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500' },
    indigo: { bg: 'bg-indigo-500/20', text: 'text-indigo-400', border: 'border-indigo-500' },
    pink: { bg: 'bg-pink-500/20', text: 'text-pink-400', border: 'border-pink-500' },
    cyan: { bg: 'bg-cyan-500/20', text: 'text-cyan-400', border: 'border-cyan-500' },
  };

  // Template configurations - live notes vs final reports
  const templates: TemplateConfig[] = useMemo(() => [
    // LIVE TEMPLATES - Real-time notes during conversation
    {
      id: 'executive-summary',
      name: 'Executive Summary',
      icon: Target,
      description: 'Key points and takeaways as they happen',
      color: 'purple',
      auto: true,
      keywords: ['summary', 'key', 'important', 'main'],
      type: 'live',
      priority: 1
    },
    {
      id: 'bullet-points',
      name: 'Bullet Points',
      icon: ListChecks,
      description: 'Quick bullet points of discussion topics',
      color: 'blue',
      auto: true,
      keywords: ['point', 'topic', 'discuss', 'mention'],
      type: 'live',
      priority: 2
    },
    {
      id: 'key-decisions',
      name: 'Key Decisions',
      icon: Flag,
      description: 'Important decisions made in real-time',
      color: 'red',
      auto: true,
      keywords: ['decide', 'decision', 'choose', 'approve', 'agree'],
      type: 'live',
      priority: 3
    },
    {
      id: 'action-alerts',
      name: 'Action Alerts',
      icon: Zap,
      description: 'Immediate action items as they come up',
      color: 'yellow',
      auto: true,
      keywords: ['action', 'task', 'todo', 'assign', 'follow up'],
      type: 'live',
      priority: 4
    },

    // FINAL TEMPLATES - Comprehensive reports after completion
    {
      id: 'full-report',
      name: 'Full Report',
      icon: FileText,
      description: 'Comprehensive meeting report with context',
      color: 'blue',
      auto: true,
      keywords: ['meeting', 'discussion', 'conversation'],
      type: 'final',
      priority: 1
    },
    {
      id: 'action-items',
      name: 'Action Items Matrix',
      icon: CheckSquare,
      description: 'Detailed task assignments with owners and deadlines',
      color: 'green',
      auto: true,
      keywords: ['action', 'task', 'assign', 'deadline', 'responsible'],
      type: 'final',
      priority: 2
    },
    {
      id: 'responsibility-matrix',
      name: 'Responsibility Matrix',
      icon: Grid3X3,
      description: 'RACI matrix showing who does what',
      color: 'orange',
      auto: true,
      keywords: ['responsible', 'accountable', 'assign', 'owner', 'team'],
      type: 'final',
      priority: 3
    },
    {
      id: 'project-plan',
      name: 'Project Plan',
      icon: GitBranch,
      description: 'Timeline and milestones from discussion',
      color: 'indigo',
      auto: true,
      keywords: ['project', 'timeline', 'milestone', 'schedule', 'deadline'],
      type: 'final',
      priority: 4
    },
    {
      id: 'gantt-chart',
      name: 'Gantt Chart Data',
      icon: FileBarChart,
      description: 'Task dependencies and timeline visualization',
      color: 'pink',
      auto: false,
      keywords: ['gantt', 'timeline', 'dependency', 'schedule'],
      type: 'final',
      priority: 5
    },
    {
      id: 'executive-brief',
      name: 'Executive Brief',
      icon: TrendingUp,
      description: 'High-level summary for leadership',
      color: 'cyan',
      auto: true,
      keywords: ['executive', 'leadership', 'summary', 'brief'],
      type: 'final',
      priority: 6
    }
  ], []);

  // Parse meeting data
  const parsedData = useMemo((): ParsedData => {
    const notes = realNotes || meetingData.notes;
    if (!notes) {
      return {
        actionItems: [],
        keyPoints: [],
        decisions: [],
        summary: '',
        participants: meetingData.participants || []
      };
    }

    const actionItems: ActionItem[] = (notes.actionItems || []).map((item: any) => ({
      task: item.task || item.text || '',
      owner: item.owner || 'Unassigned',
      priority: item.priority || 'medium',
      deadline: item.deadline,
      status: 'pending' as const
    }));

    return {
      actionItems,
      keyPoints: notes.keyPoints || [],
      decisions: notes.decisions || [],
      summary: notes.summary || '',
      participants: notes.participants || meetingData.participants || []
    };
  }, [realNotes, meetingData.notes, meetingData.participants]);

  // Track previous transcript length to detect new content

  // Persist state changes to localStorage
  useEffect(() => {
    localStorage.setItem('meeting-intelligence-live-templates', JSON.stringify(activeLiveTemplates));
  }, [activeLiveTemplates]);

  useEffect(() => {
    localStorage.setItem('meeting-intelligence-final-templates', JSON.stringify(activeFinalTemplates));
  }, [activeFinalTemplates]);

  useEffect(() => {
    localStorage.setItem('meeting-intelligence-view-mode', JSON.stringify(viewMode));
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem('meeting-intelligence-auto-live', JSON.stringify(autoDetectionLive));
  }, [autoDetectionLive]);

  useEffect(() => {
    localStorage.setItem('meeting-intelligence-auto-final', JSON.stringify(autoDetectionFinal));
  }, [autoDetectionFinal]);

  useEffect(() => {
    localStorage.setItem('meeting-intelligence-live-ai-enabled', JSON.stringify(liveAiEnabled));
  }, [liveAiEnabled]);

  // Persist generated content
  useEffect(() => {
    if (realNotes && meetingData.sessionId) {
      localStorage.setItem(`meeting-intelligence-live-notes-${meetingData.sessionId}`, JSON.stringify(realNotes));
    }
  }, [realNotes, meetingData.sessionId]);

  useEffect(() => {
    if (finalReport && meetingData.sessionId) {
      localStorage.setItem(`meeting-intelligence-final-report-${meetingData.sessionId}`, JSON.stringify(finalReport));
    }
  }, [finalReport, meetingData.sessionId]);

  // Known Issue #1 (resolved): the live-notes WebSocket endpoint
  // (/api/meeting-intelligence/ws/live-notes/{id}) was never built on the
  // backend, so the old connect-and-stream attempt only produced console
  // errors on every recording render. Live notes are not generated client-side;
  // the canonical summary loads via the fetchNotes effect below (GET
  // recording-sessions/{id} -> session.summary). This effect just tears down any
  // stale socket and reflects "not connected".
  useEffect(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
  }, [meetingData.sessionId, isRecording, liveAiEnabled]);

  // Fetch existing notes if not recording
  useEffect(() => {
    if (!meetingData.sessionId || isRecording || realNotes) return;

    // Load any existing server-generated analysis for this session. The
    // session's `summary` (canonical session endpoint) IS the source of truth;
    // a dedicated /api/meeting-notes endpoint may come later but isn't needed.
    // Failures are non-fatal: we just fall through to the empty state.
    const fetchNotes = async () => {
      setNotesLoading(true);
      try {
        const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${meetingData.sessionId}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        });

        if (response.ok) {
          const data = await response.json();
          // Use summary data from the session if available
          if (data.summary) {
            setRealNotes(data.summary);
          }
        }
      } catch (error) {
        console.error('[MeetingIntelligence] Failed to fetch notes:', error);
      } finally {
        setNotesLoading(false);
      }
    };

    fetchNotes();
  }, [meetingData.sessionId, isRecording, realNotes]);

  // Auto-detect relevant LIVE templates based on content (only when auto-detection is enabled)
  useEffect(() => {
    if (!autoDetectionLive || !meetingData.transcript) return;

    const liveTemplates = templates.filter(t => t.type === 'live');
    const detectedTemplates = liveTemplates
      .filter(template => 
        template.auto && 
        template.keywords.some(keyword => 
          meetingData.transcript.toLowerCase().includes(keyword)
        )
      )
      .sort((a, b) => a.priority - b.priority)
      .map(t => t.id);

    // Always include executive summary, add detected ones
    const newActiveTemplates = ['executive-summary', ...detectedTemplates.filter(id => id !== 'executive-summary')];
    
    // Only update if significantly different (avoid constant updates)
    if (JSON.stringify(newActiveTemplates.sort()) !== JSON.stringify(activeLiveTemplates.sort())) {
      console.log('[MeetingIntelligence] Auto-detected live templates:', newActiveTemplates);
      setActiveLiveTemplates(newActiveTemplates);
    }
  }, [meetingData.transcript, autoDetectionLive, templates]);

  // Auto-detect relevant FINAL templates based on content (only when auto-detection is enabled)
  useEffect(() => {
    if (!autoDetectionFinal || !meetingData.transcript) return;

    const finalTemplates = templates.filter(t => t.type === 'final');
    const detectedTemplates = finalTemplates
      .filter(template => 
        template.auto && 
        template.keywords.some(keyword => 
          meetingData.transcript.toLowerCase().includes(keyword)
        )
      )
      .sort((a, b) => a.priority - b.priority)
      .map(t => t.id);

    // Always include full report, add detected ones
    const newActiveTemplates = ['full-report', ...detectedTemplates.filter(id => id !== 'full-report')];
    
    // Only update if significantly different (avoid constant updates)
    if (JSON.stringify(newActiveTemplates.sort()) !== JSON.stringify(activeFinalTemplates.sort())) {
      console.log('[MeetingIntelligence] Auto-detected final templates:', newActiveTemplates);
      setActiveFinalTemplates(newActiveTemplates);
    }
  }, [meetingData.transcript, autoDetectionFinal, templates]);

  const toggleTemplate = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (!template) return;

    if (template.type === 'live') {
      setActiveLiveTemplates(prev => 
        prev.includes(templateId)
          ? prev.filter(id => id !== templateId)
          : [...prev, templateId]
      );
    } else {
      setActiveFinalTemplates(prev => 
        prev.includes(templateId)
          ? prev.filter(id => id !== templateId)
          : [...prev, templateId]
      );
    }
  };

  // Clear functions
  const clearLiveNotes = () => {
    setRealNotes(null);
    if (meetingData.sessionId) {
      localStorage.removeItem(`meeting-intelligence-live-notes-${meetingData.sessionId}`);
    }
  };

  const clearFinalReport = () => {
    setFinalReport(null);
    if (meetingData.sessionId) {
      localStorage.removeItem(`meeting-intelligence-final-report-${meetingData.sessionId}`);
    }
  };

  const clearAll = () => {
    clearLiveNotes();
    clearFinalReport();
  };

  const renderTemplate = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (!template) return null;

    // Get the current data based on view mode
    const currentNotes = viewMode === 'live' ? realNotes : finalReport;
    
    // Map template IDs to data keys
    const dataKeyMap: {[key: string]: string} = {
      'executive-summary': 'executive_summary',
      'bullet-points': 'bullet_points',
      'key-decisions': 'key_decisions',
      'action-alerts': 'action_alerts',
      'full-report': 'full_report',
      'action-items': 'action_items',
      'responsibility-matrix': 'responsibility_matrix',
      'project-plan': 'project_plan',
      'gantt-chart': 'gantt_chart',
      'executive-brief': 'executive_brief'
    };

    const dataKey = dataKeyMap[templateId];
    const templateData = currentNotes?.[dataKey];

    // Render based on template type and data
    if (!templateData) {
      return (
        <div className="text-center py-4 text-gray-500">
          <p className="text-xs">No {viewMode === 'live' ? 'live notes' : 'report'} available yet. Templates will show content when analysis completes.</p>
        </div>
      );
    }

    // Handle different data types
    if (typeof templateData === 'string') {
      return (
        <div className="space-y-2">
          <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
            {templateData}
          </p>
        </div>
      );
    }

    if (Array.isArray(templateData)) {
      return (
        <div className="space-y-2">
          {templateData.map((item, index) => {
            if (typeof item === 'string') {
              return (
                <div key={index} className="flex items-start gap-2">
                  <span className="text-purple-400 mt-1">•</span>
                  <p className="text-gray-200 text-sm flex-1">{item}</p>
                </div>
              );
            }
            // Handle structured items (like action items)
            if (typeof item === 'object' && item !== null) {
              return (
                <div key={index} className="p-2 rounded-lg bg-gray-800/50 border-l-2 border-purple-500">
                  {item.task && <p className="text-sm font-medium text-white">{item.task}</p>}
                  {item.owner && <p className="text-xs text-gray-400 mt-1">Owner: {item.owner}</p>}
                  {item.priority && (
                    <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs bg-purple-500/20 text-purple-400">
                      {item.priority}
                    </span>
                  )}
                  {item.deadline && <p className="text-xs text-gray-500 mt-1">Due: {item.deadline}</p>}
                </div>
              );
            }
            return null;
          })}
        </div>
      );
    }

    // Handle object data (like full reports)
    if (typeof templateData === 'object' && templateData !== null) {
      return (
        <div className="space-y-3">
          {Object.entries(templateData).map(([key, value]) => (
            <div key={key} className="space-y-1">
              <h5 className="text-xs font-semibold text-purple-400 capitalize">
                {key.replace(/_/g, ' ')}
              </h5>
              {typeof value === 'string' ? (
                <p className="text-xs text-gray-300">{value}</p>
              ) : Array.isArray(value) ? (
                <ul className="space-y-1">
                  {value.map((item, idx) => (
                    <li key={idx} className="text-xs text-gray-300 pl-3">• {String(item)}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gray-400">{JSON.stringify(value)}</p>
              )}
            </div>
          ))}
        </div>
      );
    }

    // Fallback for legacy template IDs (keep for backward compatibility)
    switch (templateId) {
      case 'minutes':
        return (
          <div className="space-y-3">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="font-semibold text-blue-400 mb-2 text-sm">Meeting Summary</h4>
              <p className="text-gray-200 leading-relaxed text-xs">
                {parsedData.summary || 'Meeting summary will appear here as the discussion progresses...'}
              </p>
            </div>
            
            {parsedData.participants.length > 0 && (
              <div className="bg-gray-800/50 rounded-lg p-3">
                <h4 className="font-semibold text-blue-400 mb-2 text-sm">Participants</h4>
                <div className="flex flex-wrap gap-1">
                  {parsedData.participants.map((participant, index) => (
                    <span key={index} className="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded-full text-xs">
                      {participant}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        );

      case 'actions':
        return (
          <div className="space-y-2">
            {parsedData.actionItems.length === 0 ? (
              <div className="text-center py-4 text-gray-500">
                <ListChecks className="w-8 h-8 mx-auto mb-2 text-gray-600" />
                <p className="text-xs">No action items identified yet</p>
                <p className="text-xs mt-1">Action items will appear as they're discussed</p>
              </div>
            ) : (
              parsedData.actionItems.map((item, index) => (
                <div
                  key={index}
                  className="p-2 rounded-lg border-l-2 border-green-500 bg-green-500/10"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-white text-sm">{item.task}</p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                        <span>Owner: {item.owner}</span>
                        {item.deadline && <span>Due: {item.deadline}</span>}
                      </div>
                    </div>
                    <span className="px-1.5 py-0.5 rounded-full text-xs bg-green-500/20 text-green-400 border border-green-500">
                      {item.priority}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        );

      case 'decisions':
        return (
          <div className="space-y-2">
            {parsedData.decisions.length === 0 ? (
              <div className="text-center py-4 text-gray-500">
                <Flag className="w-8 h-8 mx-auto mb-2 text-gray-600" />
                <p className="text-xs">No decisions recorded yet</p>
                <p className="text-xs mt-1">Decisions will be captured as they're made</p>
              </div>
            ) : (
              parsedData.decisions.map((decision, index) => (
                <div
                  key={index}
                  className="p-2 bg-gray-800/50 rounded-lg border-l-2 border-red-500"
                >
                  <div className="flex items-start gap-2">
                    <Flag className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                    <p className="text-white text-sm">{decision}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        );

      default:
        return null;
    }
  };
  
  return (
    <div className={`bg-gray-950 rounded-xl border border-gray-800 flex flex-col ${className}`}>
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800 p-4 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Brain className="w-6 h-6 text-purple-400" />
            <div>
              <h3 className="text-lg font-semibold text-white">
                {isRecording ? 'Live Meeting Intelligence' : 'Session Analysis'}
              </h3>
              <p className="text-xs text-gray-400">
                {isRecording 
                  ? 'Real-time AI insights during your meeting'
                  : 'AI analysis of recorded session'
                }
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">

            {/* Only show connection status when recording */}
            {isRecording && (
              <div 
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
                  wsConnected ? 'text-green-400' : 'text-orange-400'
                }`}
                title={wsConnected 
                  ? 'AI service connected - insights updating in real-time'
                  : 'AI service disconnected - insights not updating'
                }
              >
                {wsConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
                {wsConnected ? 'Connected' : 'Disconnected'}
              </div>
            )}

            {/* Live AI Toggle - enable/disable real-time AI processing */}
            {isRecording && (
              <button
                onClick={() => {
                  setLiveAiEnabled(!liveAiEnabled);
                }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                  liveAiEnabled 
                    ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
                title="Enable/disable real-time AI analysis during recording"
              >
                <Brain className="w-3 h-3" />
                Live AI {liveAiEnabled ? 'ON' : 'OFF'}
              </button>
            )}

            {/* Clear Button - context aware */}
            {(viewMode === 'live' ? realNotes : finalReport) && (
              <button
                onClick={viewMode === 'live' ? clearLiveNotes : clearFinalReport}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors bg-red-500/20 text-red-400 hover:bg-red-500/30"
                title={`Clear ${viewMode === 'live' ? 'live notes' : 'final report'} - this will remove all generated content`}
              >
                <RefreshCw className="w-3 h-3" />
                Clear {viewMode === 'live' ? 'Live' : 'Report'}
              </button>
            )}

            {/* Auto-detect Button with clear explanation */}
            <button
              onClick={() => viewMode === 'live' ? setAutoDetectionLive(!autoDetectionLive) : setAutoDetectionFinal(!autoDetectionFinal)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                (viewMode === 'live' ? autoDetectionLive : autoDetectionFinal)
                  ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
              title={
                viewMode === 'live'
                  ? `Auto-detect ${autoDetectionLive ? 'ON' : 'OFF'}: ${autoDetectionLive 
                    ? 'Automatically shows relevant live templates based on conversation keywords (decisions, actions, etc.)'
                    : 'Manual template selection - you choose which live templates to show'}`
                  : `Auto-detect ${autoDetectionFinal ? 'ON' : 'OFF'}: ${autoDetectionFinal 
                    ? 'Automatically shows relevant final reports based on meeting content (project plans, action matrices, etc.)'
                    : 'Manual template selection - you choose which final reports to generate'}`
              }
            >
              {(viewMode === 'live' ? autoDetectionLive : autoDetectionFinal) ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
              Smart Templates {(viewMode === 'live' ? autoDetectionLive : autoDetectionFinal) ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>

        {/* Live Intelligence Template Selector */}
        <div className="mt-4">
          <div className="mb-2">
            <h4 className="text-sm font-medium text-gray-300">
              ⚡ Live Intelligence Templates
              <span className="text-gray-500 ml-2 text-xs">
                ({activeLiveTemplates.length} active)
              </span>
            </h4>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {templates
              .filter(template => template.type === 'live')
              .map(template => {
                const isActive = activeLiveTemplates.includes(template.id);
                const Icon = template.icon;
                return (
                  <button
                    key={template.id}
                    onClick={() => toggleTemplate(template.id)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                      isActive
                        ? `${colorClasses[template.color]?.bg} ${colorClasses[template.color]?.text} border ${colorClasses[template.color]?.border}`
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    <Icon className="w-3 h-3" />
                    {template.name}
                    {template.auto && (
                      <div className="w-1 h-1 bg-green-400 rounded-full ml-1"></div>
                    )}
                  </button>
                );
              })}
          </div>
          <div className="mt-3 p-3 bg-gray-800/30 rounded-lg border border-gray-700">
            <div className="text-xs text-gray-400">
              <strong className="text-gray-300">Live Intelligence:</strong>
              {' '}
              Real-time AI analysis during conversation. Templates show different views of the meeting as it happens.
            </div>
            <div className="text-xs text-gray-500 mt-2 flex items-center gap-4">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 bg-green-400 rounded-full"></span>
                <strong>AUTO:</strong> AI selects relevant templates based on conversation
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
                <strong>MANUAL:</strong> You choose which insights to display
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Content Area - Live Intelligence Only */}
      <div className="p-4 flex-1 overflow-hidden">
        {activeLiveTemplates.length === 0 ? (
          <div className="text-center py-12">
            <Brain className="w-16 h-16 mx-auto text-gray-600 mb-4" />
            <p className="text-gray-400">Select intelligence templates to display</p>
            <p className="text-xs text-gray-500 mt-2">
              Enable Smart Templates to automatically show relevant insights
            </p>
          </div>
        ) : (
          <div className={`grid ${
            activeLiveTemplates.length === 1 ? 'grid-cols-1' : 
            activeLiveTemplates.length === 2 ? 'grid-cols-1 lg:grid-cols-2' : 
            'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3'
          } gap-4 h-full`}>
            {activeLiveTemplates.map(templateId => {
              const template = templates.find(t => t.id === templateId);
              if (!template) return null;

              const Icon = template.icon;
              return (
                <div key={templateId} className="bg-gray-900/50 rounded-lg border border-gray-800 flex flex-col h-[300px]">
                  <div className="flex items-center justify-between p-3 border-b border-gray-800 flex-shrink-0">
                    <h4 className={`flex items-center gap-2 text-sm font-semibold ${colorClasses[template.color]?.text || 'text-gray-400'}`}>
                      <Icon className="w-4 h-4" />
                      {template.name}
                      {isRecording && (
                        <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full border border-green-500/50">
                          LIVE
                        </span>
                      )}
                      {template.auto && (
                        <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/50">
                          AUTO
                        </span>
                      )}
                    </h4>
                    <button
                      onClick={() => toggleTemplate(templateId)}
                      className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
                      title="Hide this template"
                    >
                      <EyeOff className="w-3 h-3" />
                    </button>
                  </div>
                  
                  {/* Template Content - Fixed height with scrolling */}
                  <div className="flex-1 overflow-y-auto p-3 min-h-0">
                    {realNotes ? (
                      renderTemplate(templateId)
                    ) : (
                      <div className="text-center py-6 text-gray-500">
                        <Icon className="w-8 h-8 mx-auto mb-2 text-gray-600" />
                        <p className="text-xs">
                          {isRecording
                            ? 'Insights will appear as the meeting progresses'
                            : notesLoading
                              ? 'Loading session analysis…'
                              : 'No analysis available for this session yet'}
                        </p>
                        {!isRecording && !notesLoading && meetingData.transcript && (
                          <p className="text-xs mt-1 text-gray-600">
                            The summary is generated automatically when processing completes.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-800 bg-gray-900/30 px-4 py-3 flex-shrink-0">
        <div className="flex items-center justify-between text-xs text-gray-400">
          {isRecording ? (
            <span className="flex items-center gap-1">
              <div className={`w-2 h-2 rounded-full ${liveAiEnabled && wsConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`}></div>
              Live AI analysis {liveAiEnabled ? (wsConnected ? 'active' : 'connecting') : 'disabled'}
            </span>
          ) : meetingData.transcript ? (
            <span className="flex items-center gap-1">
              <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
              Session analysis available
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <div className="w-2 h-2 bg-gray-500 rounded-full"></div>
              Start recording to enable live intelligence
            </span>
          )}
          <span>
            {activeLiveTemplates.length} template{activeLiveTemplates.length !== 1 ? 's' : ''} active
          </span>
        </div>
      </div>
    </div>
  );
};
