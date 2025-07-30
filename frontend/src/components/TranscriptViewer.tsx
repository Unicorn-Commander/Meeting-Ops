import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  Edit,
  Save,
  X,
  Search,
  User,
  Clock,
  Hash,
  Sparkles,
  Copy,
  Check
} from 'lucide-react';

interface TranscriptSegment {
  speaker?: string;
  text: string;
  start_time?: number;
  end_time?: number;
  confidence?: number;
}

interface TranscriptViewerProps {
  sessionId: string;
  onClose?: () => void;
}

export const TranscriptViewer: React.FC<TranscriptViewerProps> = ({ 
  sessionId, 
  onClose 
}) => {
  const [transcript, setTranscript] = useState<string>('');
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [summary, setSummary] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [showSpeakers, setShowSpeakers] = useState(true);
  const [copied, setCopied] = useState(false);
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    fetchTranscript();
  }, [sessionId]);

  const fetchTranscript = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/session/${sessionId}/transcript`);
      const data = await response.json();
      
      if (data.raw?.segments) {
        setSegments(data.raw.segments);
        setTranscript(data.raw.segments.map((s: TranscriptSegment) => s.text).join(' '));
      } else {
        setTranscript(data.transcript || '');
      }
      
      setEditedText(data.transcript || '');
    } catch (error) {
      console.error('Failed to fetch transcript:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      // TODO: Implement save endpoint
      console.log('Saving edited transcript:', editedText);
      setTranscript(editedText);
      setEditing(false);
    } catch (error) {
      console.error('Failed to save transcript:', error);
    }
  };

  const handleExport = async (format: 'txt' | 'json' | 'pdf') => {
    try {
      const response = await fetch(`/api/session/${sessionId}/export?format=${format}`);
      const data = await response.json();
      
      let blob: Blob;
      if (format === 'pdf' && data.content_base64) {
        // Decode base64 PDF
        const binaryString = atob(data.content_base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        blob = new Blob([bytes], { type: 'application/pdf' });
      } else if (format === 'json') {
        blob = new Blob([JSON.stringify(data.content || data, null, 2)], { type: 'application/json' });
      } else {
        blob = new Blob([data.content || ''], { type: 'text/plain' });
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transcript_${sessionId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export transcript:', error);
    }
  };

  const handleSummarize = async () => {
    try {
      setSummarizing(true);
      const response = await fetch('/api/summarize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          text: transcript
        })
      });
      const data = await response.json();
      setSummary(data.summary);
    } catch (error) {
      console.error('Failed to generate summary:', error);
    } finally {
      setSummarizing(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(transcript);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatTime = (seconds?: number): string => {
    if (!seconds) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const highlightedTranscript = () => {
    if (!searchTerm) return transcript;
    
    const regex = new RegExp(`(${searchTerm})`, 'gi');
    return transcript.replace(regex, '<mark class="bg-yellow-200">$1</mark>');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-lg h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5" />
          Transcript - Session {sessionId}
        </h2>
        
        <div className="flex items-center gap-2">
          {!editing ? (
            <button
              onClick={() => setEditing(true)}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
              title="Edit transcript"
            >
              <Edit className="w-4 h-4" />
            </button>
          ) : (
            <>
              <button
                onClick={handleSave}
                className="p-2 hover:bg-green-100 text-green-600 rounded transition-colors"
                title="Save changes"
              >
                <Save className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setEditedText(transcript);
                }}
                className="p-2 hover:bg-red-100 text-red-600 rounded transition-colors"
                title="Cancel"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          )}
          
          <button
            onClick={handleCopy}
            className="p-2 hover:bg-gray-100 rounded transition-colors"
            title="Copy to clipboard"
          >
            {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
          </button>
          
          <div className="relative group">
            <button className="p-2 hover:bg-gray-100 rounded transition-colors">
              <Download className="w-4 h-4" />
            </button>
            <div className="absolute right-0 mt-2 w-32 bg-white border rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
              <button
                onClick={() => handleExport('txt')}
                className="block w-full text-left px-4 py-2 hover:bg-gray-100"
              >
                Export as TXT
              </button>
              <button
                onClick={() => handleExport('json')}
                className="block w-full text-left px-4 py-2 hover:bg-gray-100"
              >
                Export as JSON
              </button>
              <button
                onClick={() => handleExport('pdf')}
                className="block w-full text-left px-4 py-2 hover:bg-gray-100"
              >
                Export as PDF
              </button>
            </div>
          </div>
          
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="p-4 border-b flex items-center gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search in transcript..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showTimestamps}
            onChange={(e) => setShowTimestamps(e.target.checked)}
            className="rounded"
          />
          <Clock className="w-4 h-4" />
          Timestamps
        </label>
        
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showSpeakers}
            onChange={(e) => setShowSpeakers(e.target.checked)}
            className="rounded"
          />
          <User className="w-4 h-4" />
          Speakers
        </label>
        
        <button
          onClick={handleSummarize}
          disabled={summarizing}
          className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors flex items-center gap-2"
        >
          <Sparkles className="w-4 h-4" />
          {summarizing ? 'Summarizing...' : 'Summarize'}
        </button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="p-4 bg-purple-50 border-b">
          <h3 className="font-semibold mb-2 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-600" />
            AI Summary
          </h3>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{summary}</p>
        </div>
      )}

      {/* Transcript Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {editing ? (
          <textarea
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            className="w-full h-full p-4 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
          />
        ) : (
          <div className="space-y-4">
            {segments.length > 0 ? (
              segments.map((segment, index) => (
                <div key={index} className="flex gap-4">
                  {showTimestamps && segment.start_time && (
                    <span className="text-sm text-gray-500 font-mono whitespace-nowrap">
                      {formatTime(segment.start_time)}
                    </span>
                  )}
                  {showSpeakers && segment.speaker && (
                    <span className="text-sm font-semibold text-blue-600 whitespace-nowrap">
                      {segment.speaker}:
                    </span>
                  )}
                  <p 
                    className="flex-1 text-gray-800"
                    dangerouslySetInnerHTML={{ 
                      __html: searchTerm 
                        ? segment.text.replace(
                            new RegExp(`(${searchTerm})`, 'gi'), 
                            '<mark class="bg-yellow-200">$1</mark>'
                          )
                        : segment.text 
                    }}
                  />
                </div>
              ))
            ) : (
              <p 
                className="text-gray-800 whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: highlightedTranscript() }}
              />
            )}
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="p-2 border-t text-sm text-gray-500 flex items-center justify-between">
        <span>{transcript.split(' ').length} words</span>
        {segments.length > 0 && (
          <span>{segments.length} segments</span>
        )}
      </div>
    </div>
  );
};