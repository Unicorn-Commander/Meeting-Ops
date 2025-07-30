import React, { useState, useEffect } from 'react';
import { Brain, RefreshCw, FileText, Users, Target, Clock, Loader2 } from 'lucide-react';
import { Tooltip } from './Tooltip';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface SummaryData {
  executive_summary?: string;
  key_points?: string[];
  action_items?: Array<{
    task: string;
    assignee?: string;
    priority?: string;
    deadline?: string;
  }>;
  decisions?: string[];
  topics_discussed?: string[];
  speaker_insights?: Array<{
    speaker_id: string;
    speaker_name?: string;
    total_contributions: number;
    speaking_style?: string;
  }>;
  sentiment?: {
    overall_tone: string;
    engagement: string;
    collaboration: string;
  };
}

interface LiveSummarizationProps {
  sessionId: string | null;
  isActive: boolean;
  templateType?: string;
}

export const LiveSummarization: React.FC<LiveSummarizationProps> = ({ 
  sessionId, 
  isActive,
  templateType 
}) => {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionId && isActive && autoRefresh) {
      // Initial fetch
      fetchSummary();
      
      // Set up auto-refresh every 30 seconds
      const interval = setInterval(() => {
        fetchSummary();
      }, 30000);

      return () => clearInterval(interval);
    }
  }, [sessionId, isActive, autoRefresh]);

  const fetchSummary = async () => {
    if (!sessionId) return;

    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}/summary?template=${templateType || 'general'}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setSummary(data.summary);
        setLastUpdate(new Date());
      } else {
        setError('Failed to fetch summary');
      }
    } catch (error) {
      console.error('Error fetching summary:', error);
      setError('Error connecting to summary service');
    } finally {
      setIsLoading(false);
    }
  };

  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString();
  };

  if (!isActive) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4 text-green-400 flex items-center gap-2">
          <Brain className="h-5 w-5" />
          Live AI Summary
        </h3>
        <div className="bg-gray-900 rounded-lg p-8 text-center">
          <div className="w-16 h-16 bg-gray-700 rounded-full mx-auto mb-4 flex items-center justify-center">
            <Brain className="h-8 w-8 text-gray-500" />
          </div>
          <p className="text-gray-400">AI summary will appear here during recording</p>
          <p className="text-sm text-gray-500 mt-2">Updates every 30 seconds</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-green-400 flex items-center gap-2">
          <Brain className="h-5 w-5" />
          Live AI Summary
        </h3>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="text-xs text-gray-400">
              Updated: {formatTime(lastUpdate)}
            </span>
          )}
          <Tooltip content="Toggle auto-refresh">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`p-2 rounded transition-colors ${
                autoRefresh 
                  ? 'bg-green-900/30 text-green-400 hover:bg-green-900/50' 
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              <RefreshCw className={`h-4 w-4 ${autoRefresh ? 'animate-spin-slow' : ''}`} />
            </button>
          </Tooltip>
          <Tooltip content="Refresh summary now">
            <button
              onClick={fetchSummary}
              disabled={isLoading}
              className="p-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
            </button>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-700 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Executive Summary */}
        {summary?.executive_summary && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-blue-400 mb-2 flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Executive Summary
            </h4>
            <p className="text-gray-300 leading-relaxed">
              {summary.executive_summary}
            </p>
          </div>
        )}

        {/* Key Points */}
        {summary?.key_points && summary.key_points.length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-purple-400 mb-2">Key Points</h4>
            <ul className="space-y-2">
              {summary.key_points.map((point, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-purple-400 mt-1">•</span>
                  <span className="text-gray-300">{point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action Items */}
        {summary?.action_items && summary.action_items.length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-yellow-400 mb-3 flex items-center gap-2">
              <Target className="h-4 w-4" />
              Action Items
            </h4>
            <div className="space-y-3">
              {summary.action_items.map((item, idx) => (
                <div key={idx} className="bg-gray-800 rounded p-3">
                  <p className="text-white mb-2">{item.task}</p>
                  <div className="flex items-center gap-4 text-sm">
                    {item.assignee && (
                      <div className="flex items-center gap-1">
                        <Users className="h-3 w-3 text-gray-400" />
                        <span className="text-gray-300">{item.assignee}</span>
                      </div>
                    )}
                    {item.priority && (
                      <span className={`px-2 py-1 rounded text-xs ${
                        item.priority === 'high' 
                          ? 'bg-red-900/30 text-red-400'
                          : item.priority === 'medium'
                          ? 'bg-yellow-900/30 text-yellow-400'
                          : 'bg-green-900/30 text-green-400'
                      }`}>
                        {item.priority}
                      </span>
                    )}
                    {item.deadline && (
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3 text-gray-400" />
                        <span className="text-gray-300">{item.deadline}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Decisions */}
        {summary?.decisions && summary.decisions.length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-green-400 mb-2">Decisions Made</h4>
            <ul className="space-y-2">
              {summary.decisions.map((decision, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-green-400 mt-1">✓</span>
                  <span className="text-gray-300">{decision}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Speaker Insights */}
        {summary?.speaker_insights && summary.speaker_insights.length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-indigo-400 mb-3 flex items-center gap-2">
              <Users className="h-4 w-4" />
              Speaker Participation
            </h4>
            <div className="space-y-2">
              {summary.speaker_insights.map((speaker, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-gray-300">
                    {speaker.speaker_name || `Speaker ${speaker.speaker_id.slice(-4)}`}
                  </span>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-gray-400">
                      {speaker.total_contributions} contributions
                    </span>
                    {speaker.speaking_style && (
                      <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">
                        {speaker.speaking_style}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Meeting Sentiment */}
        {summary?.sentiment && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h4 className="font-medium text-pink-400 mb-3">Meeting Sentiment</h4>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-xs text-gray-400 mb-1">Overall Tone</p>
                <p className="text-sm font-medium text-gray-300 capitalize">
                  {summary.sentiment.overall_tone}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-1">Engagement</p>
                <p className="text-sm font-medium text-gray-300 capitalize">
                  {summary.sentiment.engagement}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-1">Collaboration</p>
                <p className="text-sm font-medium text-gray-300 capitalize">
                  {summary.sentiment.collaboration}
                </p>
              </div>
            </div>
          </div>
        )}

        {!summary && !isLoading && !error && (
          <div className="text-center py-8 text-gray-400">
            <Brain className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p>Summary will appear here as the meeting progresses</p>
            <p className="text-sm mt-1">First summary available after 1 minute</p>
          </div>
        )}
      </div>
    </div>
  );
};