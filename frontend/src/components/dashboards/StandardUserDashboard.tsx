import React, { useState, useEffect } from 'react';
import { RecordingControls } from '../RecordingControls';
import { SessionList } from '../SessionList';
import { LiveTranscription } from '../LiveTranscription';
import { AudioLevelMeter } from '../AudioLevelMeter';
import { 
  Mic, 
  Upload, 
  FileText, 
  Clock, 
  Activity,
  TrendingUp,
  Calendar,
  Download
} from 'lucide-react';

interface UserStats {
  totalSessions: number;
  totalDuration: number;
  thisWeek: number;
  lastRecording: string;
}

export const StandardUserDashboard: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [userStats, setUserStats] = useState<UserStats>({
    totalSessions: 0,
    totalDuration: 0,
    thisWeek: 0,
    lastRecording: 'Never'
  });
  const [activeTab, setActiveTab] = useState<'record' | 'sessions' | 'upload'>('record');

  useEffect(() => {
    // Fetch user statistics
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/sessions?user_only=true');
        if (response.ok) {
          const sessions = await response.json();
          // Calculate stats from sessions
          const stats = {
            totalSessions: sessions.length,
            totalDuration: sessions.reduce((acc: number, s: any) => acc + (s.duration || 0), 0),
            thisWeek: sessions.filter((s: any) => {
              const date = new Date(s.created_at);
              const weekAgo = new Date();
              weekAgo.setDate(weekAgo.getDate() - 7);
              return date > weekAgo;
            }).length,
            lastRecording: sessions[0]?.created_at ? 
              new Date(sessions[0].created_at).toLocaleDateString() : 
              'Never'
          };
          setUserStats(stats);
        }
      } catch (error) {
        console.error('Failed to fetch user stats:', error);
      }
    };

    fetchStats();
  }, []);

  const handleStartRecording = async () => {
    try {
      const response = await fetch('/api/recording/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `Recording ${new Date().toLocaleString()}`,
          description: 'Created from user dashboard'
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setCurrentSessionId(data.session_id);
        setIsRecording(true);
      }
    } catch (error) {
      console.error('Failed to start recording:', error);
    }
  };

  const handleStopRecording = async () => {
    if (!currentSessionId) return;
    
    try {
      const response = await fetch(`/api/recording/stop/${currentSessionId}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        setIsRecording(false);
        setCurrentSessionId(null);
      }
    } catch (error) {
      console.error('Failed to stop recording:', error);
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-2">
          My Dashboard
        </h1>
        <p className="text-gray-400">
          Record meetings and manage your transcriptions
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <FileText className="w-6 h-6 text-purple-400" />
          </div>
          <h3 className="text-xl font-bold text-gray-100">
            {userStats.totalSessions}
          </h3>
          <p className="text-sm text-gray-400">Total Sessions</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <Clock className="w-6 h-6 text-blue-400" />
          </div>
          <h3 className="text-xl font-bold text-gray-100">
            {Math.round(userStats.totalDuration / 3600)}h
          </h3>
          <p className="text-sm text-gray-400">Total Duration</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <TrendingUp className="w-6 h-6 text-green-400" />
          </div>
          <h3 className="text-xl font-bold text-gray-100">
            {userStats.thisWeek}
          </h3>
          <p className="text-sm text-gray-400">This Week</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <Calendar className="w-6 h-6 text-pink-400" />
          </div>
          <h3 className="text-lg font-bold text-gray-100">
            {userStats.lastRecording}
          </h3>
          <p className="text-sm text-gray-400">Last Recording</p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-4 mb-6 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('record')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'record'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          <span className="flex items-center gap-2">
            <Mic className="w-4 h-4" />
            Record
          </span>
          {activeTab === 'record' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('sessions')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'sessions'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          <span className="flex items-center gap-2">
            <FileText className="w-4 h-4" />
            My Sessions
          </span>
          {activeTab === 'sessions' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('upload')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'upload'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          <span className="flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Upload Audio
          </span>
          {activeTab === 'upload' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'record' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recording Controls */}
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-200 mb-4">
                Recording Control
              </h2>
              
              {/* Audio Level Meter */}
              <div className="mb-6">
                <AudioLevelMeter />
              </div>

              {/* Record Button */}
              <div className="flex justify-center mb-6">
                <button
                  onClick={isRecording ? handleStopRecording : handleStartRecording}
                  className={`relative w-24 h-24 rounded-full transition-all ${
                    isRecording 
                      ? 'bg-red-600 hover:bg-red-700' 
                      : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                >
                  <div className={`absolute inset-2 rounded-full ${
                    isRecording ? 'bg-red-800' : 'bg-purple-800'
                  }`} />
                  {isRecording && (
                    <div className="absolute inset-0 rounded-full animate-ping bg-red-600 opacity-20" />
                  )}
                  <Mic className="w-8 h-8 text-white absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2" />
                </button>
              </div>

              <div className="text-center">
                <p className="text-sm text-gray-400">
                  {isRecording ? 'Recording in progress...' : 'Click to start recording'}
                </p>
                {currentSessionId && (
                  <p className="text-xs text-gray-500 mt-1">
                    Session ID: {currentSessionId}
                  </p>
                )}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-200 mb-4">
                Quick Actions
              </h2>
              <div className="space-y-3">
                <button className="w-full flex items-center gap-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
                  <Download className="w-5 h-5 text-blue-400" />
                  <span>Export Last Recording</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
                  <Activity className="w-5 h-5 text-green-400" />
                  <span>View Audio Levels</span>
                </button>
              </div>
            </div>
          </div>

          {/* Live Transcription */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Live Transcription
            </h2>
            {isRecording && currentSessionId ? (
              <LiveTranscription sessionId={currentSessionId} isRecording={isRecording} />
            ) : (
              <div className="text-center py-12 text-gray-400">
                <Mic className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p>Start recording to see live transcription</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'sessions' && (
        <div>
          <div className="mb-4 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-200">
              My Recording Sessions
            </h2>
            <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
              Export All
            </button>
          </div>
          <SessionList 
            onSelectSession={(session) => console.log('Selected:', session)}
          />
        </div>
      )}

      {activeTab === 'upload' && (
        <div className="max-w-2xl mx-auto">
          <div className="bg-gray-800 rounded-lg p-8">
            <div className="text-center">
              <Upload className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-gray-200 mb-2">
                Upload Audio File
              </h2>
              <p className="text-gray-400 mb-6">
                Upload audio files for transcription and analysis
              </p>
              
              <div className="border-2 border-dashed border-gray-600 rounded-lg p-8 mb-4">
                <input
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  id="audio-upload"
                />
                <label
                  htmlFor="audio-upload"
                  className="cursor-pointer block"
                >
                  <p className="text-gray-300 mb-2">
                    Drop audio files here or click to browse
                  </p>
                  <p className="text-sm text-gray-500">
                    Supported formats: MP3, WAV, M4A, OGG
                  </p>
                </label>
              </div>
              
              <button className="px-6 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
                Process Audio
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};