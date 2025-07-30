import React, { useState } from 'react';
import { Mic, MicOff } from 'lucide-react';

export const SimpleRecordButton: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `${new Date().toLocaleTimeString()}: ${msg}`]);
    console.log(msg);
  };

  const handleRecord = async () => {
    if (isRecording) {
      // Stop recording
      if (!sessionId) {
        addLog('No session to stop');
        return;
      }
      
      try {
        addLog(`Stopping session ${sessionId}...`);
        const stopRes = await fetch(`/api/recording-sessions/${sessionId}/stop`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        
        addLog(`Stop response: ${stopRes.status}`);
        if (stopRes.ok) {
          setIsRecording(false);
          setSessionId(null);
          addLog('Recording stopped!');
        } else {
          const error = await stopRes.text();
          addLog(`Stop error: ${error}`);
        }
      } catch (err) {
        addLog(`Stop exception: ${err}`);
      }
      
    } else {
      // Start recording
      try {
        // Step 1: Create session
        addLog('Creating session...');
        const createRes = await fetch('/api/recording-sessions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          },
          body: JSON.stringify({
            name: `Test Recording ${new Date().toLocaleTimeString()}`,
            description: 'Simple test'
          })
        });
        
        addLog(`Create response: ${createRes.status}`);
        if (!createRes.ok) {
          const error = await createRes.text();
          addLog(`Create error: ${error}`);
          return;
        }
        
        const createData = await createRes.json();
        const newSessionId = createData.session?.session_id || createData.session_id;
        addLog(`Session created: ${newSessionId}`);
        setSessionId(newSessionId);
        
        // Step 2: Start recording
        addLog('Starting recording...');
        const startRes = await fetch(`/api/recording-sessions/${newSessionId}/start`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        
        addLog(`Start response: ${startRes.status}`);
        if (startRes.ok) {
          setIsRecording(true);
          addLog('Recording started!');
        } else {
          const error = await startRes.text();
          addLog(`Start error: ${error}`);
        }
        
      } catch (err) {
        addLog(`Exception: ${err}`);
      }
    }
  };

  return (
    <div className="fixed bottom-20 right-6 z-50">
      <button
        onClick={handleRecord}
        className={`p-6 rounded-full shadow-lg transition-all ${
          isRecording 
            ? 'bg-red-600 hover:bg-red-700 animate-pulse' 
            : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
        }`}
      >
        {isRecording ? <MicOff className="w-8 h-8 text-white" /> : <Mic className="w-8 h-8 text-white" />}
      </button>
      
      {logs.length > 0 && (
        <div className="absolute bottom-20 right-0 w-80 max-h-60 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs font-mono">
          {logs.map((log, i) => (
            <div key={i} className="text-gray-300">{log}</div>
          ))}
        </div>
      )}
    </div>
  );
};