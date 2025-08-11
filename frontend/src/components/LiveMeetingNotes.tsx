import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, MessageSquare, Brain, Clock, Users, 
  CheckCircle, AlertCircle, ChevronRight, Loader2,
  ToggleLeft, ToggleRight, Sparkles, Target,
  Calendar, Flag, TrendingUp, Zap
} from 'lucide-react';
import { config } from '../config';
import { LiveTranscriptionChat } from './LiveTranscriptionChat';

interface ActionItem {
  task: string;
  owner: string;
  deadline: string;
  priority?: 'high' | 'medium' | 'low';
}

interface MeetingNotes {
  summary: string;
  keyPoints: string[];
  decisions: string[];
  actionItems: ActionItem[];
  questions: string[];
  nextSteps: string[];
  participants: string[];
  sentiment: 'positive' | 'neutral' | 'negative';
  topics: string[];
  lastUpdated: string;
  isIncremental?: boolean;
}

interface LiveMeetingNotesProps {
  sessionId: string;
  isRecording: boolean;
  className?: string;
}

export const LiveMeetingNotes: React.FC<LiveMeetingNotesProps> = ({
  sessionId,
  isRecording,
  className = ''
}) => {
  const [notes, setNotes] = useState<MeetingNotes | null>(null);
  const [viewMode, setViewMode] = useState<'notes' | 'transcript'>('notes');
  const [isGenerating, setIsGenerating] = useState(false);
  const [lastGenerationTime, setLastGenerationTime] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const generationIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!sessionId || !isRecording) return;

    // Connect to meeting notes WebSocket
    const wsUrl = `${config.wsEndpoints.base}/ws/meeting-notes/${sessionId}`;
    console.log('[LiveMeetingNotes] Connecting to:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[LiveMeetingNotes] WebSocket connected');
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'notes_update') {
          console.log('[LiveMeetingNotes] Received notes update');
          setNotes(data.notes);
          setLastGenerationTime(new Date());
          setIsGenerating(false);
        } else if (data.type === 'generating') {
          setIsGenerating(true);
        } else if (data.type === 'error') {
          setError(data.message);
          setIsGenerating(false);
        }
      } catch (error) {
        console.error('[LiveMeetingNotes] Error parsing message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('[LiveMeetingNotes] WebSocket error:', error);
      setError('Connection error');
    };

    ws.onclose = () => {
      console.log('[LiveMeetingNotes] WebSocket closed');
    };

    // Set up periodic generation indicator (every 30 seconds)
    generationIntervalRef.current = setInterval(() => {
      const now = new Date();
      if (lastGenerationTime) {
        const secondsSinceLastGen = (now.getTime() - lastGenerationTime.getTime()) / 1000;
        if (secondsSinceLastGen >= 25) {
          setIsGenerating(true);
        }
      }
    }, 5000);

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
      if (generationIntervalRef.current) {
        clearInterval(generationIntervalRef.current);
      }
    };
  }, [sessionId, isRecording, lastGenerationTime]);

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'positive': return 'text-green-400';
      case 'negative': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getSentimentIcon = (sentiment: string) => {
    switch (sentiment) {
      case 'positive': return '😊';
      case 'negative': return '😟';
      default: return '😐';
    }
  };

  const getPriorityColor = (priority?: string) => {
    switch (priority) {
      case 'high': return 'bg-red-500/20 text-red-400 border-red-500';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500';
      case 'low': return 'bg-green-500/20 text-green-400 border-green-500';
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500';
    }
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  return (
    <div className={`bg-gray-950 rounded-xl border border-gray-800 overflow-hidden ${className}`}>
      {/* Header with Toggle */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Brain className="w-6 h-6 text-purple-400" />
              {isGenerating && (
                <div className="absolute -top-1 -right-1">
                  <Sparkles className="w-4 h-4 text-yellow-400 animate-pulse" />
                </div>
              )}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">Live Meeting Intelligence</h3>
              <p className="text-xs text-gray-400">
                {isGenerating ? 'Generating notes...' : 
                 lastGenerationTime ? `Last updated: ${formatTime(lastGenerationTime.toISOString())}` :
                 'Waiting for content...'}
              </p>
            </div>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-2 bg-gray-900/50 rounded-lg p-1">
            <button
              onClick={() => setViewMode('notes')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded transition-all ${
                viewMode === 'notes'
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span className="text-sm">Notes</span>
            </button>
            <button
              onClick={() => setViewMode('transcript')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded transition-all ${
                viewMode === 'transcript'
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              <span className="text-sm">Transcript</span>
            </button>
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="h-[600px] overflow-y-auto">
        {viewMode === 'notes' ? (
          <div className="p-6 space-y-6">
            {error && (
              <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {!notes && !isGenerating && !error && (
              <div className="flex flex-col items-center justify-center py-12">
                <Brain className="w-16 h-16 text-gray-600 mb-4" />
                <p className="text-gray-400 text-center">
                  Meeting notes will appear here as the conversation progresses
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  Notes update every 30-60 seconds during recording
                </p>
              </div>
            )}

            {isGenerating && !notes && (
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-purple-400 animate-spin mb-4" />
                <p className="text-gray-300">Analyzing conversation...</p>
                <p className="text-xs text-gray-500 mt-1">This may take a few moments</p>
              </div>
            )}

            {notes && (
              <>
                {/* Summary Section */}
                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider">
                      Meeting Summary
                    </h4>
                    <span className={`text-sm ${getSentimentColor(notes.sentiment)}`}>
                      {getSentimentIcon(notes.sentiment)} {notes.sentiment}
                    </span>
                  </div>
                  <p className="text-gray-200 leading-relaxed">
                    {notes.summary || 'No summary available yet'}
                  </p>
                </div>

                {/* Key Points */}
                {notes.keyPoints.length > 0 && (
                  <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Target className="w-4 h-4" />
                      Key Points
                    </h4>
                    <ul className="space-y-2">
                      {notes.keyPoints.map((point, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                          <span className="text-gray-200">{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Action Items */}
                {notes.actionItems.length > 0 && (
                  <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      Action Items
                    </h4>
                    <div className="space-y-3">
                      {notes.actionItems.map((item, index) => (
                        <div
                          key={index}
                          className={`p-3 rounded-lg border-l-4 ${getPriorityColor(item.priority)}`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <p className="text-white font-medium">{item.task}</p>
                              <div className="flex items-center gap-4 mt-2 text-xs">
                                <span className="text-gray-400">
                                  <Users className="w-3 h-3 inline mr-1" />
                                  {item.owner || 'Unassigned'}
                                </span>
                                <span className="text-gray-400">
                                  <Calendar className="w-3 h-3 inline mr-1" />
                                  {item.deadline || 'No deadline'}
                                </span>
                              </div>
                            </div>
                            {item.priority && (
                              <Flag className={`w-4 h-4 ${
                                item.priority === 'high' ? 'text-red-400' :
                                item.priority === 'medium' ? 'text-yellow-400' :
                                'text-green-400'
                              }`} />
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Decisions */}
                {notes.decisions.length > 0 && (
                  <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Zap className="w-4 h-4" />
                      Decisions Made
                    </h4>
                    <ul className="space-y-2">
                      {notes.decisions.map((decision, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                          <span className="text-gray-200">{decision}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Open Questions */}
                {notes.questions.length > 0 && (
                  <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      Open Questions
                    </h4>
                    <ul className="space-y-2">
                      {notes.questions.map((question, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <span className="text-yellow-400">?</span>
                          <span className="text-gray-200">{question}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Next Steps */}
                {notes.nextSteps.length > 0 && (
                  <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                    <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4" />
                      Next Steps
                    </h4>
                    <ul className="space-y-2">
                      {notes.nextSteps.map((step, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <span className="text-purple-400">{index + 1}.</span>
                          <span className="text-gray-200">{step}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Topics & Participants */}
                <div className="grid grid-cols-2 gap-4">
                  {notes.topics.length > 0 && (
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                      <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3">
                        Topics Discussed
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {notes.topics.map((topic, index) => (
                          <span
                            key={index}
                            className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded-full text-xs"
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {notes.participants.length > 0 && (
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                      <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wider mb-3">
                        Participants
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {notes.participants.map((participant, index) => (
                          <span
                            key={index}
                            className="px-2 py-1 bg-blue-500/20 text-blue-300 rounded-full text-xs"
                          >
                            {participant}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        ) : (
          /* Transcript View */
          <LiveTranscriptionChat
            transcriptions={[]} // Will be passed from parent
            isRecording={isRecording}
            className="h-full"
          />
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-800 bg-gray-900/30 px-4 py-3">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>
            {notes?.isIncremental ? 'Incremental update' : 'Full analysis'}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            Updates every 30-60 seconds
          </span>
        </div>
      </div>
    </div>
  );
};