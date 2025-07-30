
import React, { useEffect, useState } from 'react';

interface Session {
  session_id: string;
  path: string;
  size: number;
  mtime: number;
}

const SessionList: React.FC<{ onSelectSession?: (sessionId: string) => void }> = ({ onSelectSession }) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/sessions')
      .then(res => res.json())
      .then(data => {
        setSessions(data.sessions || []);
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to fetch sessions');
        setLoading(false);
      });
  }, []);

  if (loading) return <div>Loading sessions...</div>;
  if (error) return <div>{error}</div>;

  return (
    <div>
      <h2>Sessions</h2>
      <ul>
        {sessions.map(session => (
          <li key={session.session_id}>
            <button onClick={() => onSelectSession && onSelectSession(session.session_id)}>
              {session.session_id} ({(session.size / 1024).toFixed(1)} KB, {new Date(session.mtime * 1000).toLocaleString()})
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default SessionList;
