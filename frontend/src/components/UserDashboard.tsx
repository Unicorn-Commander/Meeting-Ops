import React, { useState, useEffect } from 'react';
import {
  Mic,
  Play,
  Pause,
  Square,
  Folder,
  Settings,
  Clock,
  Users,
  Volume2,
  Home,
  FileText,
  Search,
  Download
} from 'lucide-react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';

interface Recording {
  id: number;
  name: string;
  duration: string;
  date: string;
  speakers: number;
  status: 'completed' | 'processing';
}

interface UserDashboardProps {
  onSwitchToAdmin?: () => void;
}

export const UserDashboard: React.FC<UserDashboardProps> = ({ onSwitchToAdmin }) => {
  const { user } = useAuthentikAuth();
  const [currentView, setCurrentView] = useState('home');
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [audioDevice, setAudioDevice] = useState('default');

  // Check if user has admin access
  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

  useEffect(() => {
    // Mock recordings data
    const mockRecordings: Recording[] = [
      {
        id: 1,
        name: 'Team Meeting - Product Planning',
        duration: '45:30',
        date: '2 hours ago',
        speakers: 4,
        status: 'completed'
      },
      {
        id: 2,
        name: 'Client Call - Project Review',
        duration: '28:15',
        date: 'Yesterday',
        speakers: 3,
        status: 'completed'
      },
      {
        id: 3,
        name: 'Weekly Standup',
        duration: '15:45',
        date: '2 days ago',
        speakers: 6,
        status: 'completed'
      }
    ];
    setRecordings(mockRecordings);
  }, []);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRecording) {
      interval = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRecording]);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleStartRecording = () => {
    setIsRecording(true);
    setRecordingTime(0);
  };

  const handleStopRecording = () => {
    setIsRecording(false);
    setRecordingTime(0);
    // Add new recording to list
    const newRecording: Recording = {
      id: recordings.length + 1,
      name: `Recording ${new Date().toLocaleString()}`,
      duration: formatTime(recordingTime),
      date: 'Just now',
      speakers: 1,
      status: 'processing'
    };
    setRecordings([newRecording, ...recordings]);
  };

  const renderHomeView = () => (
    <div className="space-y-6">
      {/* Welcome Section */}
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-2">Welcome back, {user?.username}!</h1>
        <p className="text-gray-400">Ready to record your next meeting?</p>
      </div>

      {/* Recording Control */}
      <div className="bg-gray-800 p-8 rounded-xl text-center">
        <div className="mb-6">
          {isRecording ? (
            <div className="space-y-4">
              <div className="w-24 h-24 mx-auto bg-red-600 rounded-full flex items-center justify-center animate-pulse">
                <Mic className="h-12 w-12 text-white" />
              </div>
              <div>
                <p className="text-2xl font-bold text-red-400">{formatTime(recordingTime)}</p>
                <p className="text-gray-400">Recording in progress...</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="w-24 h-24 mx-auto bg-blue-600 rounded-full flex items-center justify-center">
                <Mic className="h-12 w-12 text-white" />
              </div>
              <div>
                <p className="text-lg font-medium">Ready to record</p>
                <p className="text-gray-400">Click to start your meeting recording</p>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-center gap-4">
          {!isRecording ? (
            <button
              onClick={handleStartRecording}
              className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors"
            >
              <Mic className="h-5 w-5" />
              Start Recording
            </button>
          ) : (
            <button
              onClick={handleStopRecording}
              className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 rounded-lg font-medium transition-colors"
            >
              <Square className="h-5 w-5" />
              Stop Recording
            </button>
          )}
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 p-4 rounded-lg text-center">
          <FileText className="h-8 w-8 text-blue-400 mx-auto mb-2" />
          <p className="text-2xl font-bold">{recordings.length}</p>
          <p className="text-sm text-gray-400">Total Recordings</p>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg text-center">
          <Clock className="h-8 w-8 text-green-400 mx-auto mb-2" />
          <p className="text-2xl font-bold">2.5h</p>
          <p className="text-sm text-gray-400">This Week</p>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg text-center">
          <Users className="h-8 w-8 text-purple-400 mx-auto mb-2" />
          <p className="text-2xl font-bold">12</p>
          <p className="text-sm text-gray-400">Speakers Identified</p>
        </div>
      </div>
    </div>
  );

  const renderRecordingsView = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">My Recordings</h2>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors">
            <Search className="h-4 w-4" />
            Search
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {recordings.map((recording) => (
          <div key={recording.id} className="bg-gray-800 p-4 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <h3 className="font-medium mb-1">{recording.name}</h3>
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span className="flex items-center gap-1">
                    <Clock className="h-4 w-4" />
                    {recording.duration}
                  </span>
                  <span className="flex items-center gap-1">
                    <Users className="h-4 w-4" />
                    {recording.speakers} speakers
                  </span>
                  <span>{recording.date}</span>
                  <span className={`px-2 py-1 rounded text-xs ${
                    recording.status === 'completed' 
                      ? 'bg-green-900 text-green-400' 
                      : 'bg-yellow-900 text-yellow-400'
                  }`}>
                    {recording.status}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="p-2 hover:bg-gray-700 rounded transition-colors">
                  <Play className="h-4 w-4" />
                </button>
                <button className="p-2 hover:bg-gray-700 rounded transition-colors">
                  <Download className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderSettingsView = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Settings</h2>
      
      <div className="bg-gray-800 p-6 rounded-lg space-y-6">
        <div>
          <label className="block text-sm font-medium mb-2">Audio Input Device</label>
          <select 
            value={audioDevice}
            onChange={(e) => setAudioDevice(e.target.value)}
            className="w-full p-3 bg-gray-700 border border-gray-600 rounded-lg"
          >
            <option value="default">Default Microphone</option>
            <option value="usb">USB Microphone</option>
            <option value="headset">Headset Microphone</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Recording Quality</label>
          <select className="w-full p-3 bg-gray-700 border border-gray-600 rounded-lg">
            <option>High Quality (Recommended)</option>
            <option>Standard Quality</option>
            <option>Low Quality (Saves Space)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Language</label>
          <select className="w-full p-3 bg-gray-700 border border-gray-600 rounded-lg">
            <option>Auto-detect</option>
            <option>English</option>
            <option>Spanish</option>
            <option>French</option>
            <option>German</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input type="checkbox" defaultChecked className="rounded" />
          <label className="text-sm">Enable speaker identification</label>
        </div>

        <div className="flex items-center gap-2">
          <input type="checkbox" defaultChecked className="rounded" />
          <label className="text-sm">Auto-save recordings</label>
        </div>

        <button className="w-full py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors">
          Save Settings
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      {/* Simple Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <h1 className="text-xl font-bold">Meeting Recorder</h1>
          <p className="text-sm text-gray-400">Simple & Easy</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <button
            onClick={() => setCurrentView('home')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'home' 
                ? 'bg-blue-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Home className="h-5 w-5" />
            Home
          </button>
          
          <button
            onClick={() => setCurrentView('recordings')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'recordings' 
                ? 'bg-blue-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Folder className="h-5 w-5" />
            My Recordings
          </button>

          <button
            onClick={() => setCurrentView('settings')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'settings' 
                ? 'bg-blue-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Settings className="h-5 w-5" />
            Settings
          </button>
        </nav>

        {/* User Info */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-3 p-3 bg-gray-700/50 rounded-lg">
            <div className="w-8 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center">
              <span className="text-sm font-bold">{user?.username?.[0]?.toUpperCase()}</span>
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium">{user?.username}</p>
              <p className="text-xs text-gray-400">{user?.role}</p>
            </div>
          </div>
          
          {isAdmin && onSwitchToAdmin && (
            <button
              onClick={onSwitchToAdmin}
              className="w-full mt-2 p-2 text-sm bg-orange-600 hover:bg-orange-700 rounded-lg transition-colors"
            >
              Switch to Admin Panel
            </button>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-auto">
        {currentView === 'home' && renderHomeView()}
        {currentView === 'recordings' && renderRecordingsView()}
        {currentView === 'settings' && renderSettingsView()}
      </main>
    </div>
  );
};