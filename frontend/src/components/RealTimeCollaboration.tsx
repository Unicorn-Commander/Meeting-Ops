import React, { useState, useEffect } from 'react';
import { 
  Users, MessageSquare, Edit3, Share2, Bell, Eye,
  Send, Clock, Mic, MicOff, Video, VideoOff,
  Star, ThumbsUp, Flag, Download, Settings,
  UserCheck, UserX, Activity, Zap
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ActiveUser {
  id: string;
  name: string;
  role: string;
  avatar?: string;
  status: 'online' | 'away' | 'busy';
  lastSeen: string;
  isRecording: boolean;
  isSpeaking: boolean;
  permissions: string[];
}

interface LiveAnnotation {
  id: string;
  userId: string;
  userName: string;
  timestamp: number;
  text: string;
  type: 'note' | 'question' | 'action' | 'decision';
  reactions: Array<{
    userId: string;
    type: 'like' | 'important' | 'agree' | 'disagree';
  }>;
  createdAt: string;
}

interface ChatMessage {
  id: string;
  userId: string;
  userName: string;
  message: string;
  timestamp: string;
  type: 'message' | 'system' | 'announcement';
  mentions?: string[];
}

interface CollaborativeSession {
  id: string;
  name: string;
  status: 'active' | 'paused' | 'ended';
  startTime: string;
  duration: number;
  activeUsers: ActiveUser[];
  annotations: LiveAnnotation[];
  chatMessages: ChatMessage[];
  sharedNotes: string;
  permissions: {
    canAnnotate: boolean;
    canChat: boolean;
    canEdit: boolean;
    canControl: boolean;
  };
}

export const RealTimeCollaboration: React.FC = () => {
  const [session, setSession] = useState<CollaborativeSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'users' | 'annotations' | 'chat' | 'notes'>('users');
  const [newMessage, setNewMessage] = useState('');
  const [newAnnotation, setNewAnnotation] = useState('');
  const [annotationType, setAnnotationType] = useState<'note' | 'question' | 'action' | 'decision'>('note');
  const [sharedNotes, setSharedNotes] = useState('');
  const [isTyping, setIsTyping] = useState<string[]>([]);

  useEffect(() => {
    loadCollaborationData();
    
    // Simulate real-time updates
    const interval = setInterval(() => {
      updateUserActivity();
    }, 5000);
    
    return () => clearInterval(interval);
  }, []);

  const loadCollaborationData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/collaboration/session`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setSession(data);
      } else {
        // Mock data for demonstration
        setSession({
          id: 'collab-session-1',
          name: 'Weekly Strategy Meeting - Live Session',
          status: 'active',
          startTime: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
          duration: 45,
          activeUsers: [
            {
              id: 'user-1',
              name: 'John Doe',
              role: 'Manager',
              status: 'online',
              lastSeen: new Date().toISOString(),
              isRecording: false,
              isSpeaking: true,
              permissions: ['annotate', 'chat', 'edit']
            },
            {
              id: 'user-2',
              name: 'Sarah Wilson',
              role: 'Team Lead',
              status: 'online',
              lastSeen: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
              isRecording: true,
              isSpeaking: false,
              permissions: ['annotate', 'chat', 'control']
            },
            {
              id: 'user-3',
              name: 'Mike Chen',
              role: 'Developer',
              status: 'away',
              lastSeen: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
              isRecording: false,
              isSpeaking: false,
              permissions: ['annotate', 'chat']
            }
          ],
          annotations: [
            {
              id: 'ann-1',
              userId: 'user-2',
              userName: 'Sarah Wilson',
              timestamp: 2730, // 45:30
              text: 'This metric shows significant improvement over Q3',
              type: 'note',
              reactions: [
                { userId: 'user-1', type: 'like' },
                { userId: 'user-3', type: 'important' }
              ],
              createdAt: new Date(Date.now() - 15 * 60 * 1000).toISOString()
            },
            {
              id: 'ann-2',
              userId: 'user-1',
              userName: 'John Doe',
              timestamp: 2850, // 47:30
              text: 'ACTION: Schedule follow-up meeting with engineering team',
              type: 'action',
              reactions: [
                { userId: 'user-2', type: 'agree' }
              ],
              createdAt: new Date(Date.now() - 10 * 60 * 1000).toISOString()
            }
          ],
          chatMessages: [
            {
              id: 'msg-1',
              userId: 'user-3',
              userName: 'Mike Chen',
              message: 'Can we get the slides shared after the meeting?',
              timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
              type: 'message'
            },
            {
              id: 'msg-2',
              userId: 'system',
              userName: 'System',
              message: 'Sarah Wilson started recording',
              timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
              type: 'system'
            },
            {
              id: 'msg-3',
              userId: 'user-2',
              userName: 'Sarah Wilson',
              message: '@Mike Chen Yes, I\'ll email them out right after we finish',
              timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
              type: 'message',
              mentions: ['user-3']
            }
          ],
          sharedNotes: `# Weekly Strategy Meeting Notes
## Agenda:
1. Q4 Performance Review
2. 2025 Planning
3. Resource Allocation

## Key Points:
- Revenue up 23% from Q3
- Need to expand engineering team
- New product launch planned for Q2 2025

## Action Items:
- [ ] Schedule engineering team meeting (John)
- [ ] Prepare 2025 budget proposal (Sarah)
- [ ] Review competitor analysis (Mike)`,
          permissions: {
            canAnnotate: true,
            canChat: true,
            canEdit: true,
            canControl: false
          }
        });
      }
    } catch (error) {
      console.error('Failed to load collaboration data:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateUserActivity = () => {
    if (!session) return;
    
    // Simulate real-time user activity updates
    setSession(prev => ({
      ...prev!,
      activeUsers: prev!.activeUsers.map(user => ({
        ...user,
        isSpeaking: Math.random() > 0.7, // Randomly update speaking status
        lastSeen: user.status === 'online' ? new Date().toISOString() : user.lastSeen
      }))
    }));
  };

  const sendChatMessage = async () => {
    if (!newMessage.trim() || !session) return;

    const message: ChatMessage = {
      id: `msg-${Date.now()}`,
      userId: 'current-user',
      userName: 'You',
      message: newMessage,
      timestamp: new Date().toISOString(),
      type: 'message'
    };

    setSession(prev => ({
      ...prev!,
      chatMessages: [...prev!.chatMessages, message]
    }));

    setNewMessage('');
    toast.success('Message sent');
  };

  const addAnnotation = async () => {
    if (!newAnnotation.trim() || !session) return;

    const annotation: LiveAnnotation = {
      id: `ann-${Date.now()}`,
      userId: 'current-user',
      userName: 'You',
      timestamp: session.duration * 60, // Current timestamp in seconds
      text: newAnnotation,
      type: annotationType,
      reactions: [],
      createdAt: new Date().toISOString()
    };

    setSession(prev => ({
      ...prev!,
      annotations: [...prev!.annotations, annotation]
    }));

    setNewAnnotation('');
    toast.success('Annotation added');
  };

  const addReaction = (annotationId: string, reactionType: 'like' | 'important' | 'agree' | 'disagree') => {
    setSession(prev => ({
      ...prev!,
      annotations: prev!.annotations.map(ann => 
        ann.id === annotationId
          ? {
              ...ann,
              reactions: [...ann.reactions, { userId: 'current-user', type: reactionType }]
            }
          : ann
      )
    }));
  };

  const updateSharedNotes = (notes: string) => {
    setSharedNotes(notes);
    // Simulate real-time sync
    setTimeout(() => {
      setSession(prev => ({ ...prev!, sharedNotes: notes }));
    }, 500);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'bg-green-400';
      case 'away': return 'bg-yellow-400';
      case 'busy': return 'bg-red-400';
      default: return 'bg-gray-400';
    }
  };

  const getAnnotationColor = (type: string) => {
    switch (type) {
      case 'note': return 'border-l-blue-400 bg-blue-400/10';
      case 'question': return 'border-l-yellow-400 bg-yellow-400/10';
      case 'action': return 'border-l-green-400 bg-green-400/10';
      case 'decision': return 'border-l-purple-400 bg-purple-400/10';
      default: return 'border-l-gray-400 bg-gray-400/10';
    }
  };

  const formatTimestamp = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="text-center py-12 text-gray-400">
        <Users className="w-16 h-16 mx-auto mb-4 opacity-50" />
        <p>No active collaboration session</p>
        <button className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
          Start Collaboration Session
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold flex items-center">
            <Users className="w-8 h-8 text-purple-400 mr-3" />
            Real-time Collaboration
          </h2>
          <div className="flex items-center space-x-4 mt-2">
            <div className={`px-3 py-1 rounded-full text-sm ${
              session.status === 'active' ? 'bg-green-400/20 text-green-400' : 'bg-gray-400/20 text-gray-400'
            }`}>
              {session.status === 'active' ? 'Live' : session.status}
            </div>
            <span className="text-gray-400">
              Duration: {Math.floor(session.duration / 60)}:{(session.duration % 60).toString().padStart(2, '0')}
            </span>
            <span className="text-gray-400">
              {session.activeUsers.filter(u => u.status === 'online').length} online
            </span>
          </div>
        </div>
        
        <div className="flex items-center space-x-2">
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center">
            <Share2 className="w-4 h-4 mr-2" />
            Share Session
          </button>
          <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center">
            <Settings className="w-4 h-4 mr-2" />
            Settings
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-800 rounded-lg p-1">
        {[
          { id: 'users', label: 'Active Users', icon: Users },
          { id: 'annotations', label: 'Live Notes', icon: Edit3 },
          { id: 'chat', label: 'Chat', icon: MessageSquare },
          { id: 'notes', label: 'Shared Notes', icon: Edit3 }
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors flex-1 ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
              {tab.id === 'chat' && session.chatMessages.length > 0 && (
                <span className="bg-purple-500 text-white text-xs px-1 rounded-full">
                  {session.chatMessages.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Active Users Tab */}
      {activeTab === 'users' && (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">Active Participants</h3>
          
          <div className="grid gap-4">
            {session.activeUsers.map(user => (
              <div key={user.id} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="relative">
                      <div className="w-10 h-10 bg-gray-600 rounded-full flex items-center justify-center">
                        <Users className="w-5 h-5" />
                      </div>
                      <div className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-gray-800 ${getStatusColor(user.status)}`} />
                    </div>
                    
                    <div>
                      <h4 className="font-semibold">{user.name}</h4>
                      <div className="flex items-center space-x-2 text-sm text-gray-400">
                        <span>{user.role}</span>
                        <span>•</span>
                        <span className="capitalize">{user.status}</span>
                        {user.isSpeaking && (
                          <>
                            <span>•</span>
                            <span className="text-green-400 flex items-center">
                              <Mic className="w-3 h-3 mr-1" />
                              Speaking
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    {user.isRecording && (
                      <div className="px-2 py-1 bg-red-400/20 text-red-400 rounded text-xs flex items-center">
                        <Activity className="w-3 h-3 mr-1" />
                        Recording
                      </div>
                    )}
                    
                    <div className="flex items-center space-x-1 text-xs text-gray-400">
                      {user.permissions.includes('control') && <Settings className="w-3 h-3" />}
                      {user.permissions.includes('edit') && <Edit3 className="w-3 h-3" />}
                      {user.permissions.includes('annotate') && <Star className="w-3 h-3" />}
                    </div>
                    
                    <button className="p-2 hover:bg-gray-700 rounded transition-colors">
                      <Eye className="w-4 h-4 text-gray-400" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Annotations Tab */}
      {activeTab === 'annotations' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-bold">Live Annotations</h3>
            {session.permissions.canAnnotate && (
              <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center">
                <Edit3 className="w-4 h-4 mr-2" />
                Add Note
              </button>
            )}
          </div>
          
          {session.permissions.canAnnotate && (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="space-y-3">
                <div className="flex items-center space-x-4">
                  <select 
                    value={annotationType}
                    onChange={(e) => setAnnotationType(e.target.value as any)}
                    className="px-3 py-1 bg-gray-700 border border-gray-600 rounded text-sm"
                  >
                    <option value="note">📝 Note</option>
                    <option value="question">❓ Question</option>
                    <option value="action">✅ Action Item</option>
                    <option value="decision">🎯 Decision</option>
                  </select>
                  <span className="text-sm text-gray-400">at {formatTimestamp(session.duration * 60)}</span>
                </div>
                
                <textarea
                  value={newAnnotation}
                  onChange={(e) => setNewAnnotation(e.target.value)}
                  placeholder="Add annotation at current timestamp..."
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg resize-none"
                  rows={2}
                />
                
                <button
                  onClick={addAnnotation}
                  disabled={!newAnnotation.trim()}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg transition-colors"
                >
                  Add Annotation
                </button>
              </div>
            </div>
          )}
          
          <div className="space-y-3">
            {session.annotations.map(annotation => (
              <div key={annotation.id} className={`border-l-4 rounded-lg p-4 ${getAnnotationColor(annotation.type)}`}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">{annotation.userName}</span>
                    <span className="text-sm text-gray-400">@{formatTimestamp(annotation.timestamp)}</span>
                    <span className="text-xs px-2 py-1 bg-gray-700 rounded capitalize">{annotation.type}</span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(annotation.createdAt).toLocaleTimeString()}
                  </span>
                </div>
                
                <p className="mb-3">{annotation.text}</p>
                
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => addReaction(annotation.id, 'like')}
                    className="flex items-center space-x-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition-colors"
                  >
                    <ThumbsUp className="w-3 h-3" />
                    <span>{annotation.reactions.filter(r => r.type === 'like').length}</span>
                  </button>
                  <button
                    onClick={() => addReaction(annotation.id, 'important')}
                    className="flex items-center space-x-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition-colors"
                  >
                    <Star className="w-3 h-3" />
                    <span>{annotation.reactions.filter(r => r.type === 'important').length}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat Tab */}
      {activeTab === 'chat' && (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">Live Chat</h3>
          
          <div className="bg-gray-800 rounded-lg border border-gray-700 h-96 flex flex-col">
            <div className="flex-1 p-4 overflow-y-auto space-y-3">
              {session.chatMessages.map(message => (
                <div key={message.id} className={`${
                  message.type === 'system' ? 'text-center text-gray-400 text-sm' : ''
                }`}>
                  {message.type === 'system' ? (
                    <p>{message.message}</p>
                  ) : (
                    <div className="flex items-start space-x-2">
                      <div className="w-8 h-8 bg-gray-600 rounded-full flex items-center justify-center flex-shrink-0">
                        <Users className="w-4 h-4" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-sm">{message.userName}</span>
                          <span className="text-xs text-gray-400">
                            {new Date(message.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <p className="text-sm mt-1">{message.message}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            {session.permissions.canChat && (
              <div className="border-t border-gray-700 p-4">
                <div className="flex items-center space-x-2">
                  <input
                    type="text"
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && sendChatMessage()}
                    placeholder="Type a message..."
                    className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg"
                  />
                  <button
                    onClick={sendChatMessage}
                    disabled={!newMessage.trim()}
                    className="p-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Shared Notes Tab */}
      {activeTab === 'notes' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-bold">Shared Notes</h3>
            <div className="flex items-center space-x-2">
              <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center">
                <Download className="w-4 h-4 mr-2" />
                Export
              </button>
              {isTyping.length > 0 && (
                <span className="text-sm text-gray-400">
                  {isTyping.join(', ')} typing...
                </span>
              )}
            </div>
          </div>
          
          <div className="bg-gray-800 rounded-lg border border-gray-700">
            {session.permissions.canEdit ? (
              <textarea
                value={sharedNotes || session.sharedNotes}
                onChange={(e) => updateSharedNotes(e.target.value)}
                placeholder="Collaborative notes - everyone can edit..."
                className="w-full h-96 p-4 bg-transparent border-0 resize-none focus:outline-none"
              />
            ) : (
              <div className="p-4 h-96 overflow-y-auto">
                <pre className="whitespace-pre-wrap font-mono text-sm">
                  {session.sharedNotes}
                </pre>
              </div>
            )}
          </div>
          
          {!session.permissions.canEdit && (
            <p className="text-sm text-gray-400 text-center">
              You don't have permission to edit shared notes
            </p>
          )}
        </div>
      )}
    </div>
  );
};