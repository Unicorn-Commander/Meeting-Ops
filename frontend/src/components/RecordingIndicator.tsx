import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Circle, Square, Clock } from 'lucide-react';
import { useRecording } from '../contexts/RecordingContext';

export const RecordingIndicator: React.FC = () => {
  const navigate = useNavigate();
  const { isRecording, recordingTime, activeSession } = useRecording();
  const [localTime, setLocalTime] = useState(recordingTime);

  useEffect(() => {
    setLocalTime(recordingTime);
  }, [recordingTime]);

  useEffect(() => {
    if (isRecording) {
      const interval = setInterval(() => {
        setLocalTime(prev => prev + 1);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [isRecording]);

  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  if (!isRecording) return null;

  return (
    <div
      onClick={() => navigate('/record')}
      className="fixed top-4 right-4 z-50 bg-red-600 text-white px-4 py-2 rounded-lg shadow-lg cursor-pointer hover:bg-red-700 transition-colors animate-pulse"
    >
      <div className="flex items-center gap-3">
        <Circle className="w-4 h-4 fill-white" />
        <span className="font-semibold">Recording</span>
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span className="font-mono text-sm">{formatTime(localTime)}</span>
        </div>
        {activeSession && (
          <span className="text-xs opacity-90 max-w-[200px] truncate">
            {activeSession.name}
          </span>
        )}
      </div>
    </div>
  );
};