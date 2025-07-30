
import React, { useState } from 'react';
import SessionList from './SessionList';
import TranscriptViewer from './TranscriptViewer';

const SessionManager: React.FC = () => {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
      {!selectedSession ? (
        <SessionList onSelectSession={setSelectedSession} />
      ) : (
        <>
          <button onClick={() => setSelectedSession(null)}>&larr; Back to Sessions</button>
          <TranscriptViewer sessionId={selectedSession} />
        </>
      )}
    </div>
  );
};

export default SessionManager;
