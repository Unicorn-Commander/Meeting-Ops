import React, { useState, useEffect } from 'react';
import { FileText, Download, Mail, Calendar, Users, Target, Clock, Brain, X, Printer } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface SessionReportProps {
  sessionId: string;
  onClose: () => void;
}

interface SessionData {
  session_id: string;
  name: string;
  description?: string;
  start_time: string;
  end_time?: string;
  duration_seconds: number;
  meeting_type?: string;
  template_id?: string;
  total_transcriptions: number;
  total_speakers: number;
}

interface ReportData {
  session: SessionData;
  summary: {
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
      speaking_time_seconds?: number;
      speaking_style?: string;
    }>;
    sentiment?: {
      overall_tone: string;
      engagement: string;
      collaboration: string;
    };
    quality_metrics?: {
      speaker_participation_balance: number;
      avg_confidence: number;
      npu_accelerated: boolean;
    };
  };
  transcriptions?: Array<{
    text: string;
    speaker_id?: string;
    speaker_name?: string;
    timestamp: string;
    confidence: number;
  }>;
}

export const SessionReport: React.FC<SessionReportProps> = ({ sessionId, onClose }) => {
  const [report, setReport] = useState<ReportData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [exportFormat, setExportFormat] = useState<'pdf' | 'txt' | 'json'>('pdf');

  useEffect(() => {
    fetchReport();
  }, [sessionId]);

  const fetchReport = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('access_token');
      
      // Fetch session details and summary
      const response = await fetch(`/api/recording-sessions/${sessionId}/report`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setReport(data);
      } else {
        setError('Failed to load session report');
      }
    } catch (error) {
      console.error('Error fetching report:', error);
      setError('Error loading report');
    } finally {
      setIsLoading(false);
    }
  };

  const exportReport = async (format: 'pdf' | 'txt' | 'json') => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/recording-sessions/${sessionId}/export?format=${format}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `meeting_report_${sessionId}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Error exporting report:', error);
    }
  };

  const emailReport = async () => {
    const email = prompt('Enter email address to send the report:');
    if (!email) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/recording-sessions/${sessionId}/email`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email })
      });

      if (response.ok) {
        alert('Report sent successfully!');
      }
    } catch (error) {
      console.error('Error emailing report:', error);
      alert('Failed to send report');
    }
  };

  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m ${secs}s`;
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString();
  };

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-gray-800 rounded-lg p-8 max-w-4xl w-full mx-4 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
          <p className="text-gray-300">Loading session report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-gray-800 rounded-lg p-8 max-w-4xl w-full mx-4">
          <p className="text-red-400 text-center">{error || 'Failed to load report'}</p>
          <button
            onClick={onClose}
            className="mt-4 mx-auto block px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-gray-800 rounded-lg max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="bg-gray-900 px-6 py-4 flex items-center justify-between border-b border-gray-700">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <FileText className="h-6 w-6" />
              Session Report
            </h2>
            <p className="text-sm text-gray-400 mt-1">{report.session.name}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        {/* Action Bar */}
        <div className="bg-gray-850 px-6 py-3 flex items-center justify-between border-b border-gray-700">
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              <span>{formatDate(report.session.start_time)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              <span>{formatDuration(report.session.duration_seconds)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              <span>{report.session.total_speakers} speakers</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTranscript(!showTranscript)}
              className="px-3 py-1 text-sm bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
            >
              {showTranscript ? 'Hide' : 'Show'} Transcript
            </button>
            <Tooltip content="Email this report">
              <button
                onClick={emailReport}
                className="p-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
              >
                <Mail className="h-4 w-4" />
              </button>
            </Tooltip>
            <Tooltip content="Print report">
              <button
                onClick={() => window.print()}
                className="p-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
              >
                <Printer className="h-4 w-4" />
              </button>
            </Tooltip>
            <div className="flex items-center gap-1">
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as 'pdf' | 'txt' | 'json')}
                className="px-2 py-1 text-sm bg-gray-700 text-white rounded"
              >
                <option value="pdf">PDF</option>
                <option value="txt">Text</option>
                <option value="json">JSON</option>
              </select>
              <button
                onClick={() => exportReport(exportFormat)}
                className="flex items-center gap-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                <Download className="h-4 w-4" />
                Export
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-6 max-w-4xl mx-auto">
            {/* Executive Summary */}
            {report.summary.executive_summary && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-blue-400 mb-3 flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Executive Summary
                </h3>
                <p className="text-gray-300 leading-relaxed">
                  {report.summary.executive_summary}
                </p>
              </section>
            )}

            {/* Key Points */}
            {report.summary.key_points && report.summary.key_points.length > 0 && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-purple-400 mb-3">Key Points</h3>
                <ul className="space-y-2">
                  {report.summary.key_points.map((point, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-purple-400 mt-1">•</span>
                      <span className="text-gray-300">{point}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Action Items */}
            {report.summary.action_items && report.summary.action_items.length > 0 && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-yellow-400 mb-4 flex items-center gap-2">
                  <Target className="h-5 w-5" />
                  Action Items
                </h3>
                <div className="space-y-3">
                  {report.summary.action_items.map((item, idx) => (
                    <div key={idx} className="bg-gray-800 rounded-lg p-4">
                      <p className="text-white mb-2 font-medium">{item.task}</p>
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
              </section>
            )}

            {/* Decisions */}
            {report.summary.decisions && report.summary.decisions.length > 0 && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-green-400 mb-3">Decisions Made</h3>
                <ul className="space-y-2">
                  {report.summary.decisions.map((decision, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-green-400 mt-1">✓</span>
                      <span className="text-gray-300">{decision}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Speaker Analysis */}
            {report.summary.speaker_insights && report.summary.speaker_insights.length > 0 && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-indigo-400 mb-4 flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Speaker Analysis
                </h3>
                <div className="space-y-3">
                  {report.summary.speaker_insights.map((speaker, idx) => (
                    <div key={idx} className="bg-gray-800 rounded p-3 flex items-center justify-between">
                      <div>
                        <p className="font-medium text-white">
                          {speaker.speaker_name || `Speaker ${speaker.speaker_id.slice(-4)}`}
                        </p>
                        <p className="text-sm text-gray-400">
                          {speaker.total_contributions} contributions
                          {speaker.speaking_time_seconds && 
                            ` • ${Math.round(speaker.speaking_time_seconds / 60)} minutes`
                          }
                        </p>
                      </div>
                      {speaker.speaking_style && (
                        <span className="text-xs bg-gray-700 px-3 py-1 rounded text-gray-300">
                          {speaker.speaking_style}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Meeting Quality Metrics */}
            {report.summary.quality_metrics && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-pink-400 mb-4">Meeting Quality</h3>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="bg-gray-800 rounded p-4">
                    <p className="text-sm text-gray-400 mb-1">Participation Balance</p>
                    <p className="text-2xl font-bold text-white">
                      {(report.summary.quality_metrics.speaker_participation_balance * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="bg-gray-800 rounded p-4">
                    <p className="text-sm text-gray-400 mb-1">Avg Confidence</p>
                    <p className="text-2xl font-bold text-white">
                      {(report.summary.quality_metrics.avg_confidence * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="bg-gray-800 rounded p-4">
                    <p className="text-sm text-gray-400 mb-1">Processing</p>
                    <p className="text-2xl font-bold text-white">
                      {report.summary.quality_metrics.npu_accelerated ? 'NPU' : 'CPU'}
                    </p>
                  </div>
                </div>
              </section>
            )}

            {/* Full Transcript */}
            {showTranscript && report.transcriptions && (
              <section className="bg-gray-900 rounded-lg p-6">
                <h3 className="text-lg font-bold text-cyan-400 mb-4">Full Transcript</h3>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {report.transcriptions.map((segment, idx) => (
                    <div key={idx} className="border-l-4 border-gray-700 pl-4 py-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-400">
                          {segment.speaker_name || `Speaker ${segment.speaker_id?.slice(-4) || 'Unknown'}`}
                        </span>
                        <span className="text-xs text-gray-500">
                          {new Date(segment.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-gray-300">{segment.text}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};