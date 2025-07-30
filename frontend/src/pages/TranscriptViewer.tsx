
import React, { useEffect, useState } from 'react';

interface TranscriptViewerProps {
  sessionId: string;
}

const TranscriptViewer: React.FC<TranscriptViewerProps> = ({ sessionId }) => {
  const [transcript, setTranscript] = useState('');
  const [raw, setRaw] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/session/${sessionId}/transcript`)
      .then(res => res.json())
      .then(data => {
        setTranscript(data.transcript || '');
        setRaw(data.raw || null);
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to fetch transcript');
        setLoading(false);
      });
  }, [sessionId]);

  const handleExport = (type: 'txt' | 'json') => {
    let content = '';
    let filename = '';
    if (type === 'txt') {
      content = transcript;
      filename = `${sessionId}.txt`;
    } else if (type === 'json') {
      content = JSON.stringify(raw || { transcript }, null, 2);
      filename = `${sessionId}.json`;
    }
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div>Loading transcript...</div>;
  if (error) return <div>{error}</div>;

  return (
    <div>
      <h2>Transcript for {sessionId}</h2>
      <textarea
        value={transcript}
        onChange={e => setTranscript(e.target.value)}
        rows={12}
        style={{ width: '100%' }}
      />
      <div style={{ marginTop: 10 }}>
        <button onClick={() => handleExport('txt')}>Export TXT</button>
        <button onClick={() => handleExport('json')}>Export JSON</button>
        {/* PDF export can be added with jsPDF or similar */}
      </div>
    </div>
  );
};

export default TranscriptViewer;
