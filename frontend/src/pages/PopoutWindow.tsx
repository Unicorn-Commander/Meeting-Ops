import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MeetingIntelligenceV2 } from '../components/MeetingIntelligenceV2';
import { LiveTranscriptionEnhanced } from '../components/LiveTranscriptionEnhanced';
import { useRecording } from '../contexts/RecordingContext';
import { X, Maximize2 } from 'lucide-react';

interface PopoutWindowProps {}

export const PopoutWindow: React.FC<PopoutWindowProps> = () => {
  const [searchParams] = useSearchParams();
  const { 
    isRecording: globalIsRecording, 
    transcriptions: globalTranscriptions,
    activeSession 
  } = useRecording();
  
  const type = window.location.pathname.split('/').pop(); // intelligence, transcription, etc.
  const sessionId = searchParams.get('sessionId') || '';
  
  const [isMaximized, setIsMaximized] = useState(false);

  // Update window title
  useEffect(() => {
    const titles = {
      intelligence: 'Meeting Intelligence',
      transcription: 'Live Transcription',
      analytics: 'Meeting Analytics'
    };
    document.title = titles[type as keyof typeof titles] || 'Meeting Ops - Popout';
  }, [type]);

  const toggleMaximize = () => {
    if (isMaximized) {
      window.resizeTo(1200, 800);
      setIsMaximized(false);
    } else {
      window.resizeTo(window.screen.availWidth, window.screen.availHeight);
      window.moveTo(0, 0);
      setIsMaximized(true);
    }
  };

  const closeWindow = () => {
    window.close();
  };

  return (
    <div className="h-screen bg-gray-950 text-white flex flex-col">
      {/* Window Controls */}
      <div className="flex items-center justify-between p-3 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <span className="ml-4 text-sm font-medium">
            {type === 'intelligence' && 'Meeting Intelligence'}
            {type === 'transcription' && 'Live Transcription'}
            {type === 'analytics' && 'Meeting Analytics'}
            {sessionId && ` - Session ${sessionId.slice(-6)}`}
          </span>
        </div>
        
        <div className="flex items-center gap-1">
          <button
            onClick={toggleMaximize}
            className="p-1.5 rounded hover:bg-gray-800 transition-colors"
            title={isMaximized ? 'Restore' : 'Maximize'}
          >
            <Maximize2 className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={closeWindow}
            className="p-1.5 rounded hover:bg-gray-800 transition-colors"
            title="Close"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-4">
        {type === 'intelligence' && (
          <MeetingIntelligenceV2
            sessionId={sessionId}
            isRecording={globalIsRecording}
            transcript={globalTranscriptions.map(t => t.text).join(' ')}
            onSummaryUpdate={(summary) => {
              console.log('[Popout Intelligence] Summary updated:', summary);
            }}
            className="h-full"
          />
        )}
        
        {type === 'transcription' && (
          <LiveTranscriptionEnhanced
            sessionId={sessionId}
            isRecording={globalIsRecording}
            onTranscriptionUpdate={(text) => {
              console.log('[Popout Transcription] New text:', text);
            }}
            className="h-full"
          />
        )}
        
        {type === 'analytics' && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">📊</span>
              </div>
              <h3 className="text-lg font-medium text-gray-300 mb-2">Analytics Dashboard</h3>
              <p className="text-gray-500">Advanced analytics coming soon...</p>
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="border-t border-gray-800 px-4 py-2 bg-gray-900 text-xs text-gray-500">
        <div className="flex items-center justify-between">
          <span>
            {globalIsRecording ? (
              <span className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
                Recording Active
              </span>
            ) : (
              'Standby'
            )}
          </span>
          <span>Meeting Ops v2.0.0</span>
        </div>
      </div>
    </div>
  );
};