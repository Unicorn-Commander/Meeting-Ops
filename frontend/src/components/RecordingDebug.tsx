import React, { useState } from 'react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { Mic, MicOff, AlertCircle, CheckCircle } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const RecordingDebug: React.FC = () => {
  const { token } = useAuthentikAuth();
  const [isRecording, setIsRecording] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const addLog = (message: string, type: 'info' | 'error' | 'success' = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, `[${timestamp}] ${type.toUpperCase()}: ${message}`]);
  };

  const testRecording = async () => {
    setLogs([]);
    addLog('Starting recording test...');
    addLog(`Token present: ${token ? 'YES' : 'NO'}`);
    addLog(`API URL: ${API_BASE_URL || 'Using proxy'}`);

    try {
      // Step 1: Create session
      addLog('Creating recording session...');
      const createResponse = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: `Debug Recording ${new Date().toLocaleString()}`,
          description: 'Debug test from RecordingDebug component'
        })
      });

      addLog(`Create response status: ${createResponse.status}`);
      
      if (!createResponse.ok) {
        const errorText = await createResponse.text();
        addLog(`Create failed: ${errorText}`, 'error');
        return;
      }

      const createData = await createResponse.json();
      addLog(`Create response: ${JSON.stringify(createData)}`, 'success');
      
      const newSessionId = createData.session?.session_id || createData.session_id;
      if (!newSessionId) {
        addLog('No session ID in response!', 'error');
        return;
      }
      
      setSessionId(newSessionId);
      addLog(`Session ID: ${newSessionId}`, 'success');

      // Step 2: Start recording
      addLog('Starting recording...');
      const startResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${newSessionId}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      addLog(`Start response status: ${startResponse.status}`);
      
      if (!startResponse.ok) {
        const errorText = await startResponse.text();
        addLog(`Start failed: ${errorText}`, 'error');
        return;
      }

      const startData = await startResponse.json();
      addLog(`Start response: ${JSON.stringify(startData)}`, 'success');
      
      setIsRecording(true);
      addLog('Recording started successfully!', 'success');
      
    } catch (error) {
      addLog(`Exception: ${error}`, 'error');
      console.error('Recording test error:', error);
    }
  };

  const stopRecording = async () => {
    if (!sessionId) {
      addLog('No session ID to stop!', 'error');
      return;
    }

    try {
      addLog('Stopping recording...');
      const stopResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      addLog(`Stop response status: ${stopResponse.status}`);
      
      if (!stopResponse.ok) {
        const errorText = await stopResponse.text();
        addLog(`Stop failed: ${errorText}`, 'error');
        return;
      }

      const stopData = await stopResponse.json();
      addLog(`Stop response: ${JSON.stringify(stopData)}`, 'success');
      
      setIsRecording(false);
      addLog('Recording stopped successfully!', 'success');
      
    } catch (error) {
      addLog(`Exception: ${error}`, 'error');
    }
  };

  return (
    <div className="p-6 bg-gray-800 rounded-lg">
      <h2 className="text-xl font-bold text-white mb-4">Recording Debug Panel</h2>
      
      <div className="flex gap-4 mb-6">
        <button
          onClick={testRecording}
          disabled={isRecording}
          className={`flex items-center gap-2 px-4 py-2 rounded ${
            isRecording 
              ? 'bg-gray-600 text-gray-400 cursor-not-allowed' 
              : 'bg-green-600 hover:bg-green-700 text-white'
          }`}
        >
          <Mic className="w-4 h-4" />
          Start Recording Test
        </button>
        
        <button
          onClick={stopRecording}
          disabled={!isRecording}
          className={`flex items-center gap-2 px-4 py-2 rounded ${
            !isRecording 
              ? 'bg-gray-600 text-gray-400 cursor-not-allowed' 
              : 'bg-red-600 hover:bg-red-700 text-white'
          }`}
        >
          <MicOff className="w-4 h-4" />
          Stop Recording
        </button>
        
        <button
          onClick={() => setLogs([])}
          className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded"
        >
          Clear Logs
        </button>
      </div>

      <div className="bg-gray-900 rounded p-4 max-h-96 overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-400 mb-2">Debug Logs:</h3>
        {logs.length === 0 ? (
          <p className="text-gray-500">No logs yet. Click "Start Recording Test" to begin.</p>
        ) : (
          <div className="space-y-1">
            {logs.map((log, index) => {
              const isError = log.includes('ERROR:');
              const isSuccess = log.includes('SUCCESS:');
              return (
                <div 
                  key={index} 
                  className={`text-xs font-mono ${
                    isError ? 'text-red-400' : isSuccess ? 'text-green-400' : 'text-gray-300'
                  }`}
                >
                  {log}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {sessionId && (
        <div className="mt-4 p-3 bg-blue-900/50 border border-blue-700 rounded">
          <p className="text-sm text-blue-300">
            Current Session ID: <span className="font-mono">{sessionId}</span>
          </p>
        </div>
      )}
    </div>
  );
};