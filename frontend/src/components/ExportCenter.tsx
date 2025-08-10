import React, { useState, useEffect } from 'react';
import { 
  Download, FileText, FileSpreadsheet, Mail, Calendar,
  Check, X, Clock, Filter, Search, Package, Archive,
  Send, Settings, ChevronDown, ChevronRight, Loader2
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ExportJob {
  id: string;
  sessionIds: string[];
  format: 'txt' | 'pdf' | 'docx' | 'csv' | 'json' | 'srt';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  createdAt: string;
  completedAt?: string;
  fileSize?: number;
  downloadUrl?: string;
  error?: string;
  options: {
    includeTimestamps: boolean;
    includeSpeakers: boolean;
    includeInsights: boolean;
    mergeFiles: boolean;
  };
}

interface Session {
  id: string;
  name: string;
  date: string;
  duration: number;
  hasTranscript: boolean;
  hasAudio: boolean;
  speakerCount: number;
}

interface ExportTemplate {
  id: string;
  name: string;
  format: string;
  options: any;
  description: string;
}

export const ExportCenter: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessions, setSelectedSessions] = useState<Set<string>>(new Set());
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
  const [activeTab, setActiveTab] = useState<'new' | 'history' | 'templates'>('new');
  const [exportFormat, setExportFormat] = useState<string>('pdf');
  const [exportOptions, setExportOptions] = useState({
    includeTimestamps: true,
    includeSpeakers: true,
    includeInsights: false,
    mergeFiles: false,
    emailTo: '',
    scheduleTime: ''
  });
  const [templates, setTemplates] = useState<ExportTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDate, setFilterDate] = useState<'all' | 'today' | 'week' | 'month'>('all');

  useEffect(() => {
    fetchSessions();
    fetchExportHistory();
    fetchTemplates();
  }, []);

  const fetchSessions = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/simple/recording-sessions`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSessions(data.map((s: any) => ({
          id: s.id,
          name: s.name || 'Untitled Session',
          date: s.created_at,
          duration: s.duration || 0,
          hasTranscript: true,
          hasAudio: !!s.audio_file_url,
          speakerCount: s.speaker_count || 1
        })));
      } else {
        // Mock data
        setSessions([
          { id: '1', name: 'Team Standup', date: '2025-01-09', duration: 900, hasTranscript: true, hasAudio: true, speakerCount: 4 },
          { id: '2', name: 'Client Meeting', date: '2025-01-08', duration: 3600, hasTranscript: true, hasAudio: true, speakerCount: 2 },
          { id: '3', name: 'Project Review', date: '2025-01-07', duration: 2700, hasTranscript: true, hasAudio: false, speakerCount: 5 },
          { id: '4', name: 'Brainstorming Session', date: '2025-01-06', duration: 1800, hasTranscript: true, hasAudio: true, speakerCount: 3 }
        ]);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const fetchExportHistory = async () => {
    // Mock export history for now
    setExportJobs([
      {
        id: '1',
        sessionIds: ['1', '2'],
        format: 'pdf',
        status: 'completed',
        progress: 100,
        createdAt: '2025-01-09T10:00:00',
        completedAt: '2025-01-09T10:01:00',
        fileSize: 2457600,
        downloadUrl: '/exports/export-1.pdf',
        options: {
          includeTimestamps: true,
          includeSpeakers: true,
          includeInsights: true,
          mergeFiles: true
        }
      },
      {
        id: '2',
        sessionIds: ['3'],
        format: 'docx',
        status: 'processing',
        progress: 65,
        createdAt: '2025-01-09T11:00:00',
        options: {
          includeTimestamps: false,
          includeSpeakers: true,
          includeInsights: false,
          mergeFiles: false
        }
      }
    ]);
  };

  const fetchTemplates = async () => {
    // Mock templates
    setTemplates([
      {
        id: '1',
        name: 'Meeting Minutes',
        format: 'pdf',
        description: 'Standard meeting minutes with action items',
        options: {
          includeTimestamps: false,
          includeSpeakers: true,
          includeInsights: true,
          mergeFiles: true
        }
      },
      {
        id: '2',
        name: 'Full Transcript',
        format: 'docx',
        description: 'Complete transcript with timestamps',
        options: {
          includeTimestamps: true,
          includeSpeakers: true,
          includeInsights: false,
          mergeFiles: false
        }
      },
      {
        id: '3',
        name: 'Summary Report',
        format: 'pdf',
        description: 'Executive summary with key insights',
        options: {
          includeTimestamps: false,
          includeSpeakers: false,
          includeInsights: true,
          mergeFiles: true
        }
      }
    ]);
  };

  const handleExport = async () => {
    if (selectedSessions.size === 0) {
      toast.error('Please select at least one session to export');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/export/batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_ids: Array.from(selectedSessions),
          format: exportFormat,
          options: exportOptions
        })
      });

      if (response.ok) {
        const job = await response.json();
        toast.success('Export job started successfully');
        setExportJobs([job, ...exportJobs]);
        setSelectedSessions(new Set());
      } else {
        // Simulate success for demo
        const newJob: ExportJob = {
          id: Date.now().toString(),
          sessionIds: Array.from(selectedSessions),
          format: exportFormat as any,
          status: 'processing',
          progress: 0,
          createdAt: new Date().toISOString(),
          options: {
            includeTimestamps: exportOptions.includeTimestamps,
            includeSpeakers: exportOptions.includeSpeakers,
            includeInsights: exportOptions.includeInsights,
            mergeFiles: exportOptions.mergeFiles
          }
        };
        setExportJobs([newJob, ...exportJobs]);
        toast.success('Export job created (demo mode)');
        
        // Simulate progress
        setTimeout(() => {
          setExportJobs(prev => prev.map(job => 
            job.id === newJob.id 
              ? { ...job, status: 'completed', progress: 100, downloadUrl: '/demo-export.pdf' }
              : job
          ));
        }, 3000);
      }
    } catch (error) {
      console.error('Export failed:', error);
      toast.error('Failed to start export job');
    } finally {
      setLoading(false);
    }
  };

  const toggleSessionSelection = (sessionId: string) => {
    const newSelection = new Set(selectedSessions);
    if (newSelection.has(sessionId)) {
      newSelection.delete(sessionId);
    } else {
      newSelection.add(sessionId);
    }
    setSelectedSessions(newSelection);
  };

  const selectAllSessions = () => {
    if (selectedSessions.size === filteredSessions.length) {
      setSelectedSessions(new Set());
    } else {
      setSelectedSessions(new Set(filteredSessions.map(s => s.id)));
    }
  };

  const applyTemplate = (template: ExportTemplate) => {
    setExportFormat(template.format);
    setExportOptions({
      ...exportOptions,
      ...template.options
    });
    toast.success(`Applied "${template.name}" template`);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <Check className="w-4 h-4 text-green-400" />;
      case 'failed': return <X className="w-4 h-4 text-red-400" />;
      case 'processing': return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const filteredSessions = sessions.filter(session => {
    const matchesSearch = session.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesDate = filterDate === 'all' || 
      (filterDate === 'today' && new Date(session.date).toDateString() === new Date().toDateString()) ||
      (filterDate === 'week' && new Date(session.date) > new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)) ||
      (filterDate === 'month' && new Date(session.date) > new Date(Date.now() - 30 * 24 * 60 * 60 * 1000));
    return matchesSearch && matchesDate;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Export Center</h2>
        <div className="flex items-center space-x-4">
          <button
            onClick={() => setActiveTab('new')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              activeTab === 'new' ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            New Export
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              activeTab === 'history' ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            History
          </button>
          <button
            onClick={() => setActiveTab('templates')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              activeTab === 'templates' ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            Templates
          </button>
        </div>
      </div>

      {activeTab === 'new' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Session Selection */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-bold">Select Sessions</h3>
                <div className="flex items-center space-x-2">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      placeholder="Search sessions..."
                      className="pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                    />
                  </div>
                  <select
                    value={filterDate}
                    onChange={(e) => setFilterDate(e.target.value as any)}
                    className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="all">All Time</option>
                    <option value="today">Today</option>
                    <option value="week">Last Week</option>
                    <option value="month">Last Month</option>
                  </select>
                </div>
              </div>

              <div className="mb-4">
                <button
                  onClick={selectAllSessions}
                  className="text-sm text-purple-400 hover:text-purple-300"
                >
                  {selectedSessions.size === filteredSessions.length ? 'Deselect All' : 'Select All'}
                </button>
                <span className="ml-4 text-sm text-gray-400">
                  {selectedSessions.size} of {filteredSessions.length} selected
                </span>
              </div>

              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredSessions.map(session => (
                  <div
                    key={session.id}
                    onClick={() => toggleSessionSelection(session.id)}
                    className={`p-4 rounded-lg border cursor-pointer transition-all ${
                      selectedSessions.has(session.id)
                        ? 'bg-purple-600/20 border-purple-500'
                        : 'bg-gray-700/50 border-gray-600 hover:border-gray-500'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-semibold">{session.name}</h4>
                        <p className="text-sm text-gray-400">
                          {new Date(session.date).toLocaleDateString()} • {formatDuration(session.duration)} • {session.speakerCount} speakers
                        </p>
                      </div>
                      <div className="flex items-center space-x-2">
                        {session.hasTranscript && <FileText className="w-4 h-4 text-green-400" />}
                        {session.hasAudio && <Package className="w-4 h-4 text-blue-400" />}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Export Options */}
          <div className="space-y-4">
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="text-xl font-bold mb-4">Export Options</h3>
              
              {/* Format Selection */}
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Format</label>
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                >
                  <option value="pdf">PDF Document</option>
                  <option value="docx">Word Document</option>
                  <option value="txt">Plain Text</option>
                  <option value="csv">CSV Spreadsheet</option>
                  <option value="json">JSON Data</option>
                  <option value="srt">SRT Subtitles</option>
                </select>
              </div>

              {/* Options */}
              <div className="space-y-3">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={exportOptions.includeTimestamps}
                    onChange={(e) => setExportOptions({...exportOptions, includeTimestamps: e.target.checked})}
                    className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <span>Include timestamps</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={exportOptions.includeSpeakers}
                    onChange={(e) => setExportOptions({...exportOptions, includeSpeakers: e.target.checked})}
                    className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <span>Include speaker labels</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={exportOptions.includeInsights}
                    onChange={(e) => setExportOptions({...exportOptions, includeInsights: e.target.checked})}
                    className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <span>Include AI insights</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={exportOptions.mergeFiles}
                    onChange={(e) => setExportOptions({...exportOptions, mergeFiles: e.target.checked})}
                    className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <span>Merge into single file</span>
                </label>
              </div>

              {/* Email Option */}
              <div className="mt-4">
                <label className="block text-sm font-medium mb-2">Email to (optional)</label>
                <input
                  type="email"
                  value={exportOptions.emailTo}
                  onChange={(e) => setExportOptions({...exportOptions, emailTo: e.target.value})}
                  placeholder="email@example.com"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>

              {/* Export Button */}
              <button
                onClick={handleExport}
                disabled={loading || selectedSessions.size === 0}
                className={`w-full mt-6 px-4 py-3 rounded-lg font-medium transition-colors flex items-center justify-center ${
                  loading || selectedSessions.size === 0
                    ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                    : 'bg-purple-600 hover:bg-purple-700'
                }`}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    Export {selectedSessions.size} Session{selectedSessions.size !== 1 ? 's' : ''}
                  </>
                )}
              </button>
            </div>

            {/* Quick Templates */}
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="text-lg font-bold mb-3">Quick Templates</h3>
              <div className="space-y-2">
                {templates.slice(0, 3).map(template => (
                  <button
                    key={template.id}
                    onClick={() => applyTemplate(template)}
                    className="w-full text-left p-3 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
                  >
                    <div className="font-medium">{template.name}</div>
                    <div className="text-xs text-gray-400">{template.description}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Export History</h3>
          <div className="space-y-3">
            {exportJobs.map(job => (
              <div key={job.id} className="p-4 bg-gray-700/50 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(job.status)}
                    <div>
                      <div className="font-medium">
                        {job.sessionIds.length} session{job.sessionIds.length !== 1 ? 's' : ''} • {job.format.toUpperCase()}
                      </div>
                      <div className="text-sm text-gray-400">
                        {new Date(job.createdAt).toLocaleString()}
                        {job.fileSize && ` • ${formatFileSize(job.fileSize)}`}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    {job.status === 'processing' && (
                      <div className="w-32 bg-gray-600 rounded-full h-2">
                        <div 
                          className="bg-blue-500 h-2 rounded-full transition-all"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    )}
                    {job.downloadUrl && (
                      <button className="px-3 py-1 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm">
                        Download
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map(template => (
            <div key={template.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <div className="flex items-start justify-between mb-3">
                <h4 className="text-lg font-semibold">{template.name}</h4>
                <span className="px-2 py-1 bg-gray-700 rounded text-sm">{template.format.toUpperCase()}</span>
              </div>
              <p className="text-sm text-gray-400 mb-4">{template.description}</p>
              <div className="space-y-1 text-sm">
                {template.options.includeTimestamps && (
                  <div className="flex items-center text-green-400">
                    <Check className="w-3 h-3 mr-1" /> Timestamps
                  </div>
                )}
                {template.options.includeSpeakers && (
                  <div className="flex items-center text-green-400">
                    <Check className="w-3 h-3 mr-1" /> Speaker labels
                  </div>
                )}
                {template.options.includeInsights && (
                  <div className="flex items-center text-green-400">
                    <Check className="w-3 h-3 mr-1" /> AI insights
                  </div>
                )}
              </div>
              <button
                onClick={() => {
                  applyTemplate(template);
                  setActiveTab('new');
                }}
                className="w-full mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors"
              >
                Use Template
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};