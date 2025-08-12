import React, { useEffect, useRef } from 'react';
import { MessageCircle, Loader2, Mic, MicOff } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: string;
  speaker?: string | null;
  confidence?: number;
  isComplete?: boolean;
}

interface LiveTranscriptionChatProps {
  transcriptions: TranscriptionSegment[];
  isRecording: boolean;
  currentSegment?: string;
  className?: string;
}

export const LiveTranscriptionChat: React.FC<LiveTranscriptionChatProps> = ({
  transcriptions,
  isRecording,
  currentSegment,
  className = ''
}) => {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new transcriptions arrive
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcriptions, currentSegment]);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: '2-digit',
      second: '2-digit' 
    });
  };

  return (
    <div className={`flex flex-col h-full bg-gradient-to-b from-gray-900 to-gray-950 rounded-xl shadow-2xl border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-800 bg-gray-900/50 backdrop-blur rounded-t-xl">
        <div className="flex items-center gap-3">
          <div className="relative">
            <MessageCircle className="w-6 h-6 text-purple-400" />
            {isRecording && (
              <div className="absolute -top-1 -right-1 w-3 h-3">
                <div className="w-full h-full bg-green-500 rounded-full animate-pulse"></div>
                <div className="absolute inset-0 bg-green-400 rounded-full animate-ping"></div>
              </div>
            )}
          </div>
          <div>
            <h3 className="text-white font-semibold">Live Transcript</h3>
            <p className="text-xs text-gray-400">
              {isRecording ? 'Listening...' : 'Ready to record'}
            </p>
          </div>
        </div>
        
        {/* Status indicator */}
        <div className="flex items-center gap-2">
          {isRecording ? (
            <div className="flex items-center gap-2 px-3 py-1 bg-green-500/20 rounded-full">
              <Mic className="w-4 h-4 text-green-400" />
              <span className="text-xs text-green-400 font-medium">Recording</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1 bg-gray-700/50 rounded-full">
              <MicOff className="w-4 h-4 text-gray-400" />
              <span className="text-xs text-gray-400">Idle</span>
            </div>
          )}
        </div>
      </div>

      {/* Chat-style transcript area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {!isRecording && transcriptions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-12">
            <div className="w-20 h-20 mb-4 rounded-full bg-purple-500/10 flex items-center justify-center">
              <MicOff className="w-10 h-10 text-purple-400" />
            </div>
            <p className="text-gray-400 text-center">
              Start recording to see live transcription
            </p>
            <p className="text-xs text-gray-500 mt-2">
              Updates appear every 4 seconds
            </p>
          </div>
        ) : transcriptions.length === 0 && !currentSegment ? (
          <div className="flex flex-col items-center justify-center h-full py-12">
            <Loader2 className="w-8 h-8 text-purple-400 animate-spin mb-4" />
            <p className="text-gray-300">Waiting for speech...</p>
            <p className="text-xs text-gray-500 mt-1">Speak clearly into the microphone</p>
            <div className="mt-4 p-3 bg-gray-800 rounded text-xs text-gray-400">
              Debug: {transcriptions.length} transcriptions loaded
              {isRecording && <div>Recording is active</div>}
            </div>
          </div>
        ) : (
          <>
            {/* Enhanced continuous transcript */}
            <div className="p-6 space-y-4">
              {transcriptions.map((segment, index) => (
                <div
                  key={segment.id}
                  className="bg-gray-800/30 backdrop-blur-sm rounded-lg p-4 border-l-4 border-purple-500 shadow-lg animate-fade-in-up"
                  style={{ animationDelay: `${index * 0.1}s` }}
                >
                  <div className="text-white text-xl leading-relaxed font-medium">
                    {segment.text}
                  </div>
                  {segment.confidence && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="text-xs text-gray-400">Confidence:</div>
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map((level) => (
                          <div
                            key={level}
                            className={`w-2 h-2 rounded-full ${
                              segment.confidence! >= level * 0.2
                                ? 'bg-green-400'
                                : 'bg-gray-600'
                            }`}
                          />
                        ))}
                      </div>
                      <span className="text-xs text-gray-400">
                        {Math.round((segment.confidence || 0) * 100)}%
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
        
        {/* Auto-scroll anchor */}
        <div ref={endRef} />
      </div>

      {/* Footer with stats */}
      {isRecording && (
        <div className="p-3 border-t border-gray-800 bg-gray-900/30 backdrop-blur rounded-b-xl">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">
              {transcriptions.length} segments captured
            </span>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-gray-400">Live transcription active</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};