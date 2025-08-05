import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { FileText, Clock, User, Download, Brain, Loader2 } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  speaker?: string;
  text: string;
  timestamp: number;
  confidence?: number;
}

interface SessionDetailsData {
  session_id: string;
  name: string;
  start_time: string;
  end_time?: string;
  transcription: TranscriptionSegment[];
}

export const SessionDetails: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<SessionDetailsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState('');
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    fetchSessionDetails();
  }, [sessionId]);

  const fetchSessionDetails = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/recording-sessions/${sessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSession(data);
      } else {
        console.error('Failed to fetch session details');
      }
    } catch (error) {
      console.error('Error fetching session details:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateSummary = async (template: string) => {
    if (!session) return;
    setSummarizing(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/summarize`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ session_id: session.session_id, template }),
      });
      if (response.ok) {
        const data = await response.json();
        setSummary(data.summary);
      } else {
        console.error('Failed to generate summary');
      }
    } catch (error) {
      console.error('Error generating summary:', error);
    } finally {
      setSummarizing(false);
    }
  };

  const handleDownloadTranscript = async () => {
    if (!session) return;
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/recording-sessions/${session.session_id}/export?format=txt`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript-${session.session_id}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        console.error('Failed to download transcript:', response.statusText);
      }
    } catch (error) {
      console.error('Error downloading transcript:', error);
    }
  };

  const handleDownloadAudio = async () => {
    if (!session) return;
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/files/session/${session.session_id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        if (data.files && data.files.length > 0) {
          const audioFile = data.files.find((file: any) => file.file_type === 'audio');
          if (audioFile) {
            const downloadUrl = `/api/files/${audioFile.file_id}/download`;
            const downloadResponse = await fetch(downloadUrl, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (downloadResponse.ok) {
              const blob = await downloadResponse.blob();
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = audioFile.filename;
              document.body.appendChild(a);
              a.click();
              window.URL.revokeObjectURL(url);
              document.body.removeChild(a);
            } else {
              console.error('Failed to download audio file:', downloadResponse.statusText);
            }
          } else {
            console.warn('No audio file found for this session.');
          }
        } else {
          console.warn('No files found for this session.');
        }
      } else {
        console.error('Failed to fetch session files:', response.statusText);
      }
    } catch (error) {
      console.error('Error downloading audio:', error);
    }
  };

  if (loading) {
    return <div className="text-center p-8"><Loader2 className="w-8 h-8 animate-spin mx-auto" /></div>;
  }

  if (!session) {
    return <div className="text-center p-8 text-red-500">Session not found</div>;
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">{session.name}</h1>
      <div className="flex items-center gap-4 text-sm text-gray-500 mb-6">
        <div className="flex items-center gap-1"><Clock className="w-4 h-4" /> {new Date(session.start_time).toLocaleString()}</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2"><FileText className="w-5 h-5" /> Transcript</h2>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-4">
            {session.transcription.map((segment) => (
              <div key={segment.id} className="flex gap-3">
                <div className="font-semibold text-gray-700 w-24 text-right">{segment.speaker || 'Unknown'}</div>
                <div className="flex-1">
                  <p className="text-gray-800">{segment.text}</p>
                  <div className="text-xs text-gray-400 mt-1">{new Date(segment.timestamp).toLocaleTimeString()}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2"><Brain className="w-5 h-5" /> Summarization</h2>
            <div className="space-y-2">
              <button onClick={() => generateSummary('meeting_minutes')} className="w-full text-left p-2 bg-gray-100 hover:bg-gray-200 rounded">Meeting Minutes</button>
              <button onClick={() => generateSummary('action_items')} className="w-full text-left p-2 bg-gray-100 hover:bg-gray-200 rounded">Action Items</button>
              <button onClick={() => generateSummary('key_takeaways')} className="w-full text-left p-2 bg-gray-100 hover:bg-gray-200 rounded">Key Takeaways</button>
            </div>
            {summarizing && <Loader2 className="w-5 h-5 animate-spin mt-4" />}
            {summary && (
              <div className="mt-4 border-t pt-4">
                <h3 className="font-semibold mb-2">Summary:</h3>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{summary}</p>
              </div>
            )}
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2"><Download className="w-5 h-5" /> Export</h2>
            <div className="space-y-2">
              <button onClick={handleDownloadTranscript} className="w-full text-left p-2 bg-gray-100 hover:bg-gray-200 rounded">Download Transcript (.txt)</button>
              <button onClick={handleDownloadAudio} className="w-full text-left p-2 bg-gray-100 hover:bg-gray-200 rounded">Download Audio (.wav)</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
