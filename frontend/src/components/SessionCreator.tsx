import React, { useState, useRef } from 'react';
import {
  Plus, Upload, FileAudio,
  X, Loader2, Trash2,
  Mic
} from 'lucide-react';
import { config } from '../config';

interface SessionCreatorProps {
  onClose: () => void;
  onSessionCreated: (sessionId: string) => void;
  className?: string;
}

export const SessionCreator: React.FC<SessionCreatorProps> = ({
  onClose,
  onSessionCreated,
  className = ''
}) => {
  const [sessionName, setSessionName] = useState('');
  const [description, setDescription] = useState('');
  const [participants, setParticipants] = useState<string[]>(['']);
  const [tags, setTags] = useState<string[]>(['']);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [sessionType, setSessionType] = useState<'live' | 'upload'>('live');
  const [creating, setCreating] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const audioInputRef = useRef<HTMLInputElement>(null);

  const colorClasses: Record<string, { border: string; bg: string; text: string }> = {
    purple: { border: 'border-purple-500', bg: 'bg-purple-500/10', text: 'text-purple-400' },
    blue: { border: 'border-blue-500', bg: 'bg-blue-500/10', text: 'text-blue-400' },
  };

  const sessionTypes = [
    {
      id: 'live',
      name: 'Live Recording',
      description: 'Record meeting live with microphone',
      icon: Mic,
      color: 'purple'
    },
    {
      id: 'upload',
      name: 'Upload Audio',
      description: 'Upload existing audio file for transcription',
      icon: Upload,
      color: 'blue'
    }
  ];

  const addParticipant = () => {
    setParticipants([...participants, '']);
  };

  const updateParticipant = (index: number, value: string) => {
    const newParticipants = [...participants];
    newParticipants[index] = value;
    setParticipants(newParticipants);
  };

  const removeParticipant = (index: number) => {
    setParticipants(participants.filter((_, i) => i !== index));
  };

  const addTag = () => {
    setTags([...tags, '']);
  };

  const updateTag = (index: number, value: string) => {
    const newTags = [...tags];
    newTags[index] = value;
    setTags(newTags);
  };

  const removeTag = (index: number) => {
    setTags(tags.filter((_, i) => i !== index));
  };

  const handleAudioUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // Validate audio file
      const validTypes = ['audio/wav', 'audio/mp3', 'audio/m4a', 'audio/ogg', 'audio/flac'];
      if (!validTypes.includes(file.type)) {
        alert('Please select a valid audio file (WAV, MP3, M4A, OGG, FLAC)');
        return;
      }
      
      // Check file size (max 500MB)
      if (file.size > 500 * 1024 * 1024) {
        alert('Audio file is too large. Please select a file under 500MB.');
        return;
      }
      
      setAudioFile(file);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const createSession = async () => {
    if (!sessionName.trim()) {
      alert('Please enter a session name');
      return;
    }

    if (sessionType === 'upload' && !audioFile) {
      alert('Please select an audio file to upload');
      return;
    }

    setCreating(true);
    setUploadProgress(0);

    try {
      // Create session
      const sessionData = {
        name: sessionName,
        description: description.trim() || undefined,
        participants: participants.filter(p => p.trim()),
        tags: tags.filter(t => t.trim()),
        session_type: sessionType
      };

      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(sessionData)
      });

      if (!response.ok) {
        throw new Error('Failed to create session');
      }

      const session = await response.json();
      console.log('[SessionCreator] Session created:', session.id);

      // Upload audio file if provided
      if (audioFile) {
        console.log('[SessionCreator] Uploading audio file...');
        const formData = new FormData();
        formData.append('audio', audioFile);

        const uploadResponse = await fetch(
          `${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/upload-audio`, 
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: formData
          }
        );

        if (!uploadResponse.ok) {
          throw new Error('Failed to upload audio file');
        }
        setUploadProgress(50);
      }

      setUploadProgress(100);
      console.log('[SessionCreator] Session created successfully:', session.id);
      
      // Auto-start transcription if audio was uploaded
      if (audioFile) {
        try {
          const startResponse = await fetch(
            `${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/start`,
            {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
              }
            }
          );
          
          if (startResponse.ok) {
            console.log('[SessionCreator] Auto-started transcription for uploaded audio');
          }
        } catch (error) {
          console.warn('[SessionCreator] Failed to auto-start transcription:', error);
        }
      }

      onSessionCreated(session.id);
    } catch (error) {
      console.error('[SessionCreator] Failed to create session:', error);
      alert('Failed to create session. Please try again.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className={`bg-gray-950 rounded-xl border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-3">
              <Plus className="w-6 h-6 text-purple-400" />
              Create New Session
            </h2>
            <p className="text-gray-400 mt-1">
              Start a live recording or upload existing audio for transcription
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Session Type Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-3">
            Session Type
          </label>
          <div className="grid grid-cols-2 gap-4">
            {sessionTypes.map(type => {
              const Icon = type.icon;
              const isSelected = sessionType === type.id;
              return (
                <button
                  key={type.id}
                  onClick={() => setSessionType(type.id as 'live' | 'upload')}
                  className={`p-4 rounded-lg border-2 text-left transition-all ${
                    isSelected
                      ? `${colorClasses[type.color]?.border} ${colorClasses[type.color]?.bg}`
                      : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <Icon className={`w-5 h-5 ${
                      isSelected ? colorClasses[type.color]?.text || 'text-gray-400' : 'text-gray-400'
                    }`} />
                    <h3 className={`font-semibold ${
                      isSelected ? 'text-white' : 'text-gray-300'
                    }`}>
                      {type.name}
                    </h3>
                  </div>
                  <p className="text-sm text-gray-400">{type.description}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Basic Info */}
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Session Name *
            </label>
            <input
              type="text"
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              placeholder="Enter session name..."
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description..."
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
            />
          </div>
        </div>

        {/* Participants */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm font-medium text-gray-300">
              Participants
            </label>
            <button
              onClick={addParticipant}
              className="flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300"
            >
              <Plus className="w-3 h-3" />
              Add
            </button>
          </div>
          <div className="space-y-2">
            {participants.map((participant, index) => (
              <div key={index} className="flex gap-2">
                <input
                  type="text"
                  value={participant}
                  onChange={(e) => updateParticipant(index, e.target.value)}
                  placeholder="Participant name..."
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
                />
                {participants.length > 1 && (
                  <button
                    onClick={() => removeParticipant(index)}
                    className="p-2 text-red-400 hover:text-red-300"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Tags */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm font-medium text-gray-300">
              Tags
            </label>
            <button
              onClick={addTag}
              className="flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300"
            >
              <Plus className="w-3 h-3" />
              Add
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {tags.map((tag, index) => (
              <div key={index} className="flex gap-2">
                <input
                  type="text"
                  value={tag}
                  onChange={(e) => updateTag(index, e.target.value)}
                  placeholder="Tag..."
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 text-sm"
                />
                {tags.length > 1 && (
                  <button
                    onClick={() => removeTag(index)}
                    className="p-2 text-red-400 hover:text-red-300"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Audio Upload (for upload type) */}
        {sessionType === 'upload' && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-3">
              Audio File *
            </label>
            <div className="border-2 border-dashed border-gray-700 rounded-lg p-6">
              {!audioFile ? (
                <div className="text-center">
                  <FileAudio className="w-12 h-12 text-gray-500 mx-auto mb-4" />
                  <p className="text-gray-400 mb-2">Select an audio file to upload</p>
                  <p className="text-xs text-gray-500 mb-4">
                    Supports WAV, MP3, M4A, OGG, FLAC (max 500MB)
                  </p>
                  <button
                    onClick={() => audioInputRef.current?.click()}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                  >
                    Choose File
                  </button>
                  <input
                    ref={audioInputRef}
                    type="file"
                    accept="audio/*"
                    onChange={handleAudioUpload}
                    className="hidden"
                  />
                </div>
              ) : (
                <div className="flex items-center gap-4">
                  <FileAudio className="w-8 h-8 text-blue-400" />
                  <div className="flex-1">
                    <p className="text-white font-medium">{audioFile.name}</p>
                    <p className="text-xs text-gray-400">{formatFileSize(audioFile.size)}</p>
                  </div>
                  <button
                    onClick={() => setAudioFile(null)}
                    className="p-2 text-red-400 hover:text-red-300"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Upload Progress */}
        {creating && uploadProgress > 0 && (
          <div>
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-gray-300">Upload Progress</span>
              <span className="text-gray-400">{uploadProgress}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-800">
          <button
            onClick={onClose}
            disabled={creating}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={createSession}
            disabled={creating || !sessionName.trim() || (sessionType === 'upload' && !audioFile)}
            className={`flex items-center gap-2 px-6 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              sessionType === 'live'
                ? 'bg-purple-600 hover:bg-purple-700 text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {creating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                {sessionType === 'live' ? <Mic className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
                {sessionType === 'live' ? 'Start Live Session' : 'Upload & Process'}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};