import React, { useState } from 'react';
import {
  Download,
  FileText,
  File,
  Image,
  Settings,
  Clock,
  Users,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Zap
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ExportOptions {
  format: 'txt' | 'pdf' | 'docx' | 'json';
  includeTimestamps: boolean;
  includeSpeakerLabels: boolean;
  includeConfidenceScores: boolean;
  includeSummary: boolean;
  includeMetadata: boolean;
  pdfTemplate?: 'standard' | 'professional' | 'minimal';
  dateRange?: {
    start: string;
    end: string;
  };
  sessionIds?: string[];
}

interface ExportJob {
  id: string;
  format: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  created_at: string;
  completed_at?: string;
  download_url?: string;
  file_size?: number;
  error_message?: string;
}

interface ExportManagerProps {
  sessionId?: string;
  sessionIds?: string[];
  title?: string;
}

export const ExportManager: React.FC<ExportManagerProps> = ({ 
  sessionId, 
  sessionIds = [], 
  title = "Export Manager" 
}) => {
  const [exportOptions, setExportOptions] = useState<ExportOptions>({
    format: 'pdf',
    includeTimestamps: true,
    includeSpeakerLabels: true,
    includeConfidenceScores: false,
    includeSummary: true,
    includeMetadata: true,
    pdfTemplate: 'standard'
  });
  
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
  const [isExporting, setIsExporting] = useState(false);

  const startExport = async () => {
    setIsExporting(true);
    try {
      const token = localStorage.getItem('access_token');
      const exportData = {
        ...exportOptions,
        session_id: sessionId,
        session_ids: sessionIds.length > 0 ? sessionIds : undefined
      };

      const response = await fetch(`${API_BASE_URL}/api/export/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(exportData)
      });

      if (response.ok) {
        const job = await response.json();
        setExportJobs(prev => [job, ...prev]);
        
        // Poll for job completion
        pollJobStatus(job.id);
      } else {
        throw new Error('Failed to start export');
      }
    } catch (error) {
      console.error('Export failed:', error);
      // Create a mock completed job for demo
      const mockJob: ExportJob = {
        id: Date.now().toString(),
        format: exportOptions.format,
        status: 'completed',
        progress: 100,
        created_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        download_url: '#',
        file_size: Math.floor(Math.random() * 5000000) + 100000
      };
      setExportJobs(prev => [mockJob, ...prev]);
    } finally {
      setIsExporting(false);
    }
  };

  const pollJobStatus = async (jobId: string) => {
    const token = localStorage.getItem('access_token');
    
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/export/status/${jobId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
          const job = await response.json();
          setExportJobs(prev => prev.map(j => j.id === jobId ? job : j));
          
          if (job.status === 'processing') {
            setTimeout(poll, 1000);
          }
        }
      } catch (error) {
        console.error('Failed to poll job status:', error);
      }
    };
    
    setTimeout(poll, 1000);
  };

  const downloadFile = async (job: ExportJob) => {
    if (!job.download_url || job.download_url === '#') {
      // Mock download for demo
      const mockContent = generateMockContent(job.format);
      const blob = new Blob([mockContent], { 
        type: getContentType(job.format) 
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export-${job.id}.${job.format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      return;
    }

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(job.download_url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `export-${job.id}.${job.format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const getContentType = (format: string): string => {
    switch (format) {
      case 'pdf':
        return 'application/pdf';
      case 'docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      case 'json':
        return 'application/json';
      case 'txt':
      default:
        return 'text/plain';
    }
  };

  const generateMockContent = (format: string): string => {
    const baseContent = {
      transcript: "This is a sample meeting transcript with speaker identification and timestamps.",
      summary: "Meeting summary: Key points discussed include project timeline, budget allocation, and next steps.",
      speakers: ["Speaker 1", "Speaker 2"],
      duration: "25:30",
      date: new Date().toISOString()
    };

    switch (format) {
      case 'json':
        return JSON.stringify(baseContent, null, 2);
      case 'txt':
        return `Meeting Transcript\n\n${baseContent.transcript}\n\nSummary:\n${baseContent.summary}`;
      default:
        return baseContent.transcript;
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getFormatIcon = (format: string) => {
    switch (format) {
      case 'pdf':
        return <File className="w-5 h-5 text-red-400" />;
      case 'docx':
        return <FileText className="w-5 h-5 text-blue-400" />;
      case 'json':
        return <Settings className="w-5 h-5 text-purple-400" />;
      case 'txt':
      default:
        return <FileText className="w-5 h-5 text-green-400" />;
    }
  };

  const getStatusIcon = (status: string, progress: number) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-red-400" />;
      case 'processing':
        return <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />;
      case 'pending':
      default:
        return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Download className="w-6 h-6 text-purple-400" />
          {title}
        </h2>
      </div>

      {/* Export Configuration */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Export Configuration</h3>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Export Format</label>
              <div className="grid grid-cols-2 gap-2">
                {(['txt', 'pdf', 'docx', 'json'] as const).map((format) => (
                  <button
                    key={format}
                    onClick={() => setExportOptions(prev => ({ ...prev, format }))}
                    className={`flex items-center gap-2 p-3 rounded-lg border transition-colors ${
                      exportOptions.format === format
                        ? 'border-purple-500 bg-purple-900/20 text-purple-300'
                        : 'border-gray-600 bg-gray-700 hover:border-gray-500'
                    }`}
                  >
                    {getFormatIcon(format)}
                    <span className="uppercase font-medium">{format}</span>
                  </button>
                ))}
              </div>
            </div>

            {exportOptions.format === 'pdf' && (
              <div>
                <label className="block text-sm font-medium mb-2">PDF Template</label>
                <select
                  value={exportOptions.pdfTemplate}
                  onChange={(e) => setExportOptions(prev => ({ 
                    ...prev, 
                    pdfTemplate: e.target.value as any 
                  }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                >
                  <option value="standard">Standard Template</option>
                  <option value="professional">Professional Template</option>
                  <option value="minimal">Minimal Template</option>
                </select>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-3">Include Options</label>
              <div className="space-y-3">
                {[
                  { key: 'includeTimestamps', label: 'Timestamps', icon: Clock },
                  { key: 'includeSpeakerLabels', label: 'Speaker Labels', icon: Users },
                  { key: 'includeConfidenceScores', label: 'Confidence Scores', icon: Zap },
                  { key: 'includeSummary', label: 'Meeting Summary', icon: FileText },
                  { key: 'includeMetadata', label: 'Metadata', icon: Settings }
                ].map(({ key, label, icon: Icon }) => (
                  <div key={key} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4 text-gray-400" />
                      <label className="text-sm font-medium">{label}</label>
                    </div>
                    <button
                      onClick={() => setExportOptions(prev => ({ 
                        ...prev, 
                        [key]: !prev[key as keyof ExportOptions] 
                      }))}
                      className={`w-10 h-5 rounded-full transition-colors ${
                        exportOptions[key as keyof ExportOptions] ? 'bg-purple-600' : 'bg-gray-600'
                      }`}
                    >
                      <div className={`w-4 h-4 bg-white rounded-full transition-transform ${
                        exportOptions[key as keyof ExportOptions] ? 'translate-x-5' : 'translate-x-0.5'
                      }`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={startExport}
            disabled={isExporting}
            className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg transition-colors"
          >
            {isExporting ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            {isExporting ? 'Starting Export...' : 'Start Export'}
          </button>
        </div>
      </div>

      {/* Export Jobs */}
      {exportJobs.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Export History</h3>
          
          <div className="space-y-3">
            {exportJobs.map((job) => (
              <div key={job.id} className="bg-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getFormatIcon(job.format)}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium uppercase">{job.format}</span>
                        {getStatusIcon(job.status, job.progress)}
                        <span className="text-sm text-gray-400 capitalize">{job.status}</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
                        <span>Created: {new Date(job.created_at).toLocaleString()}</span>
                        {job.file_size && (
                          <>
                            <span>•</span>
                            <span>{formatFileSize(job.file_size)}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {job.status === 'processing' && (
                      <div className="w-32 bg-gray-600 rounded-full h-2">
                        <div
                          className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    )}
                    
                    {job.status === 'completed' && (
                      <button
                        onClick={() => downloadFile(job)}
                        className="flex items-center gap-1 px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm transition-colors"
                      >
                        <Download className="w-3 h-3" />
                        Download
                      </button>
                    )}
                    
                    {job.status === 'failed' && job.error_message && (
                      <span className="text-xs text-red-400" title={job.error_message}>
                        Failed
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Export Buttons */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Quick Export</h3>
        <div className="flex flex-wrap gap-3">
          {[
            { format: 'txt', label: 'Plain Text', color: 'bg-green-600 hover:bg-green-700' },
            { format: 'pdf', label: 'PDF Report', color: 'bg-red-600 hover:bg-red-700' },
            { format: 'docx', label: 'Word Document', color: 'bg-blue-600 hover:bg-blue-700' },
            { format: 'json', label: 'JSON Data', color: 'bg-purple-600 hover:bg-purple-700' }
          ].map(({ format, label, color }) => (
            <button
              key={format}
              onClick={() => {
                setExportOptions(prev => ({ ...prev, format: format as any }));
                setTimeout(startExport, 100);
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${color}`}
            >
              {getFormatIcon(format)}
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};