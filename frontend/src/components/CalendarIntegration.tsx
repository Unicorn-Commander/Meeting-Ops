import React, { useState, useEffect } from 'react';
import {
  Calendar,
  Clock,
  Users,
  MapPin,
  Settings,
  RefreshCw,
  Plus,
  Eye,
  AlertCircle,
  CheckCircle,
  ExternalLink,
  Building,
  Mail,
  Phone,
  Video,
  Trash2,
  Edit3
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface CalendarProvider {
  id: string;
  name: string;
  type: 'microsoft365' | 'google';
  enabled: boolean;
  configured: boolean;
  last_sync?: string;
  sync_status: 'success' | 'error' | 'syncing';
  error_message?: string;
}

interface Meeting {
  id: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  attendees: Array<{
    email: string;
    name?: string;
    response_status: 'accepted' | 'declined' | 'tentative' | 'none';
  }>;
  location?: string;
  meeting_url?: string;
  organizer: {
    email: string;
    name?: string;
  };
  recording_enabled: boolean;
  recording_session_id?: string;
  status: 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
}

interface RoomConfiguration {
  id: string;
  name: string;
  location: string;
  capacity: number;
  equipment: string[];
  calendar_integration: boolean;
  auto_recording: boolean;
}

export const CalendarIntegration: React.FC = () => {
  const [providers, setProviders] = useState<CalendarProvider[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [roomConfig, setRoomConfig] = useState<RoomConfiguration | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [showRoomConfig, setShowRoomConfig] = useState(false);
  const [activeTab, setActiveTab] = useState<'meetings' | 'providers' | 'room'>('meetings');

  useEffect(() => {
    loadCalendarData();
    
    // Auto-refresh every 5 minutes
    const interval = setInterval(loadCalendarData, 300000);
    return () => clearInterval(interval);
  }, []);

  const loadCalendarData = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Load calendar providers
      const providersResponse = await fetch(`${API_BASE_URL}/api/calendar/providers`, { headers });
      if (providersResponse.ok) {
        const providersData = await providersResponse.json();
        setProviders(providersData);
      } else {
        // Mock data for testing
        setProviders([
          {
            id: 'microsoft365',
            name: 'Microsoft 365',
            type: 'microsoft365',
            enabled: true,
            configured: true,
            last_sync: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
            sync_status: 'success'
          },
          {
            id: 'google',
            name: 'Google Workspace',
            type: 'google',
            enabled: false,
            configured: false,
            sync_status: 'error',
            error_message: 'Authentication required'
          }
        ]);
      }

      // Load meetings
      const meetingsResponse = await fetch(`${API_BASE_URL}/api/calendar/meetings`, { headers });
      if (meetingsResponse.ok) {
        const meetingsData = await meetingsResponse.json();
        setMeetings(meetingsData);
      } else {
        // Mock data for testing
        setMeetings([
          {
            id: 'meeting-1',
            title: 'Weekly Team Standup',
            description: 'Weekly sync meeting for project updates',
            start_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
            end_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
            attendees: [
              { email: 'john@company.com', name: 'John Doe', response_status: 'accepted' },
              { email: 'jane@company.com', name: 'Jane Smith', response_status: 'tentative' },
              { email: 'bob@company.com', name: 'Bob Wilson', response_status: 'accepted' }
            ],
            location: 'Conference Room A',
            organizer: { email: 'admin@company.com', name: 'Admin User' },
            recording_enabled: true,
            status: 'scheduled'
          },
          {
            id: 'meeting-2',
            title: 'Client Presentation',
            start_time: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
            end_time: new Date(Date.now() + 25 * 60 * 60 * 1000).toISOString(),
            attendees: [
              { email: 'client@external.com', name: 'Client Representative', response_status: 'accepted' }
            ],
            meeting_url: 'https://teams.microsoft.com/l/meetup-join/...',
            organizer: { email: 'admin@company.com', name: 'Admin User' },
            recording_enabled: false,
            status: 'scheduled'
          },
          {
            id: 'meeting-3',
            title: 'Project Review Meeting',
            start_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            end_time: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
            attendees: [
              { email: 'team@company.com', name: 'Development Team', response_status: 'accepted' }
            ],
            location: 'Conference Room B',
            organizer: { email: 'admin@company.com', name: 'Admin User' },
            recording_enabled: true,
            recording_session_id: 'session-123',
            status: 'completed'
          }
        ]);
      }

      // Load room configuration
      const roomResponse = await fetch(`${API_BASE_URL}/api/calendar/room/config`, { headers });
      if (roomResponse.ok) {
        const roomData = await roomResponse.json();
        setRoomConfig(roomData);
      } else {
        // Mock data for testing
        setRoomConfig({
          id: 'room-1',
          name: 'Main Conference Room',
          location: 'Building A, Floor 2, Room 201',
          capacity: 12,
          equipment: ['Microphone Array', '4K Camera', 'NPU Processing Unit', 'Whiteboard'],
          calendar_integration: true,
          auto_recording: true
        });
      }
    } catch (error) {
      console.error('Failed to load calendar data:', error);
    } finally {
      setLoading(false);
    }
  };

  const syncProvider = async (providerId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/calendar/providers/${providerId}/sync`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        // Update provider status
        setProviders(prev => prev.map(p => 
          p.id === providerId 
            ? { ...p, sync_status: 'syncing', last_sync: new Date().toISOString() }
            : p
        ));
        
        // Reload data after a delay
        setTimeout(loadCalendarData, 3000);
      }
    } catch (error) {
      console.error('Sync failed:', error);
    }
  };

  const toggleRecording = async (meetingId: string, enabled: boolean) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/calendar/meetings/${meetingId}/recording`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ recording_enabled: enabled })
      });
      
      if (response.ok) {
        setMeetings(prev => prev.map(m => 
          m.id === meetingId ? { ...m, recording_enabled: enabled } : m
        ));
      }
    } catch (error) {
      console.error('Failed to toggle recording:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'scheduled':
        return 'text-blue-400 bg-blue-900/20';
      case 'in_progress':
        return 'text-green-400 bg-green-900/20';
      case 'completed':
        return 'text-gray-400 bg-gray-900/20';
      case 'cancelled':
        return 'text-red-400 bg-red-900/20';
      default:
        return 'text-gray-400 bg-gray-900/20';
    }
  };

  const getResponseColor = (status: string) => {
    switch (status) {
      case 'accepted':
        return 'text-green-400';
      case 'declined':
        return 'text-red-400';
      case 'tentative':
        return 'text-yellow-400';
      default:
        return 'text-gray-400';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Calendar className="w-8 h-8 text-blue-400" />
            Calendar Integration
          </h1>
          <p className="text-gray-400">Meeting scheduling & room management</p>
        </div>
        <button
          onClick={loadCalendarData}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-800 rounded-lg p-1">
        {[
          { id: 'meetings', label: 'Meetings', icon: Calendar },
          { id: 'providers', label: 'Providers', icon: Settings },
          { id: 'room', label: 'Room Config', icon: Building }
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
            </button>
          );
        })}
      </div>

      {/* Meetings Tab */}
      {activeTab === 'meetings' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">Upcoming & Recent Meetings</h2>
            <button className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded transition-colors">
              <Plus className="w-4 h-4" />
              Schedule Meeting
            </button>
          </div>

          <div className="grid gap-4">
            {meetings.map((meeting) => (
              <div key={meeting.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-lg font-semibold">{meeting.title}</h3>
                      <span className={`px-2 py-1 rounded text-xs ${getStatusColor(meeting.status)}`}>
                        {meeting.status.replace('_', ' ')}
                      </span>
                      {meeting.recording_enabled && (
                        <span className="px-2 py-1 bg-red-900/20 text-red-400 rounded text-xs">
                          Recording Enabled
                        </span>
                      )}
                    </div>
                    
                    <div className="flex items-center gap-4 text-sm text-gray-400 mb-2">
                      <div className="flex items-center gap-1">
                        <Clock className="w-4 h-4" />
                        <span>
                          {new Date(meeting.start_time).toLocaleDateString()} •{' '}
                          {new Date(meeting.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                          {new Date(meeting.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-1">
                        <Users className="w-4 h-4" />
                        <span>{meeting.attendees.length} attendees</span>
                      </div>
                    </div>

                    {meeting.location && (
                      <div className="flex items-center gap-1 text-sm text-gray-400 mb-2">
                        <MapPin className="w-4 h-4" />
                        <span>{meeting.location}</span>
                      </div>
                    )}

                    {meeting.meeting_url && (
                      <div className="flex items-center gap-1 text-sm text-gray-400 mb-2">
                        <Video className="w-4 h-4" />
                        <a 
                          href={meeting.meeting_url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 flex items-center gap-1"
                        >
                          Join Meeting <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    )}

                    {meeting.description && (
                      <p className="text-sm text-gray-300 mt-2">{meeting.description}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setSelectedMeeting(meeting)}
                      className="p-2 text-gray-400 hover:text-white transition-colors"
                      title="View Details"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    
                    <button
                      onClick={() => toggleRecording(meeting.id, !meeting.recording_enabled)}
                      className={`p-2 rounded transition-colors ${
                        meeting.recording_enabled 
                          ? 'text-red-400 hover:bg-red-900/20' 
                          : 'text-gray-400 hover:bg-gray-700'
                      }`}
                      title={meeting.recording_enabled ? 'Disable Recording' : 'Enable Recording'}
                    >
                      <Settings className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Attendees */}
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-400">Attendees:</span>
                  <div className="flex flex-wrap gap-2">
                    {meeting.attendees.slice(0, 3).map((attendee, index) => (
                      <span
                        key={index}
                        className={`text-xs px-2 py-1 rounded ${getResponseColor(attendee.response_status)} bg-gray-700`}
                      >
                        {attendee.name || attendee.email}
                      </span>
                    ))}
                    {meeting.attendees.length > 3 && (
                      <span className="text-xs px-2 py-1 rounded bg-gray-700 text-gray-400">
                        +{meeting.attendees.length - 3} more
                      </span>
                    )}
                  </div>
                </div>

                {meeting.recording_session_id && (
                  <div className="mt-3 p-3 bg-gray-700 rounded-lg">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-400">Recording Session:</span>
                      <button className="text-blue-400 hover:text-blue-300 text-sm">
                        View Recording →
                      </button>
                    </div>
                    <span className="text-xs font-mono text-gray-500">{meeting.recording_session_id}</span>
                  </div>
                )}
              </div>
            ))}
          </div>

          {meetings.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Calendar className="w-16 h-16 mx-auto mb-4 opacity-50" />
              <p>No meetings found</p>
              <p className="text-sm">Configure a calendar provider to sync meetings</p>
            </div>
          )}
        </div>
      )}

      {/* Providers Tab */}
      {activeTab === 'providers' && (
        <div className="space-y-6">
          <h2 className="text-xl font-bold">Calendar Providers</h2>
          
          <div className="grid gap-4">
            {providers.map((provider) => (
              <div key={provider.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-lg ${
                      provider.type === 'microsoft365' ? 'bg-blue-900/20' : 'bg-red-900/20'
                    }`}>
                      {provider.type === 'microsoft365' ? (
                        <Building className="w-6 h-6 text-blue-400" />
                      ) : (
                        <Mail className="w-6 h-6 text-red-400" />
                      )}
                    </div>
                    
                    <div>
                      <h3 className="text-lg font-semibold">{provider.name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        {provider.sync_status === 'success' && (
                          <CheckCircle className="w-4 h-4 text-green-400" />
                        )}
                        {provider.sync_status === 'error' && (
                          <AlertCircle className="w-4 h-4 text-red-400" />
                        )}
                        {provider.sync_status === 'syncing' && (
                          <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
                        )}
                        
                        <span className={`text-sm ${
                          provider.sync_status === 'success' ? 'text-green-400' :
                          provider.sync_status === 'error' ? 'text-red-400' :
                          'text-blue-400'
                        }`}>
                          {provider.sync_status === 'success' ? 'Connected' :
                           provider.sync_status === 'error' ? 'Error' :
                           'Syncing...'}
                        </span>
                        
                        {provider.last_sync && (
                          <>
                            <span className="text-gray-400">•</span>
                            <span className="text-sm text-gray-400">
                              Last sync: {new Date(provider.last_sync).toLocaleString()}
                            </span>
                          </>
                        )}
                      </div>
                      
                      {provider.error_message && (
                        <p className="text-sm text-red-400 mt-1">{provider.error_message}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => syncProvider(provider.id)}
                      disabled={provider.sync_status === 'syncing'}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded transition-colors"
                    >
                      {provider.sync_status === 'syncing' ? 'Syncing...' : 'Sync Now'}
                    </button>
                    
                    <button
                      className={`w-12 h-6 rounded-full transition-colors ${
                        provider.enabled ? 'bg-green-600' : 'bg-gray-600'
                      }`}
                    >
                      <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                        provider.enabled ? 'translate-x-6' : 'translate-x-0.5'
                      }`} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-lg font-semibold mb-4">Add New Provider</h3>
            <div className="grid grid-cols-2 gap-4">
              <button className="flex items-center gap-3 p-4 border border-gray-600 rounded-lg hover:border-blue-500 transition-colors">
                <Building className="w-6 h-6 text-blue-400" />
                <div className="text-left">
                  <p className="font-medium">Microsoft 365</p>
                  <p className="text-sm text-gray-400">Connect to Office 365 / Outlook</p>
                </div>
              </button>
              
              <button className="flex items-center gap-3 p-4 border border-gray-600 rounded-lg hover:border-red-500 transition-colors">
                <Mail className="w-6 h-6 text-red-400" />
                <div className="text-left">
                  <p className="font-medium">Google Workspace</p>
                  <p className="text-sm text-gray-400">Connect to Google Calendar</p>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Room Configuration Tab */}
      {activeTab === 'room' && roomConfig && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">Room Configuration</h2>
            <button
              onClick={() => setShowRoomConfig(!showRoomConfig)}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
            >
              <Edit3 className="w-4 h-4" />
              Edit Configuration
            </button>
          </div>

          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400">Room Name</label>
                  <p className="text-lg font-medium">{roomConfig.name}</p>
                </div>
                
                <div>
                  <label className="text-sm text-gray-400">Location</label>
                  <p className="text-lg font-medium flex items-center gap-2">
                    <MapPin className="w-4 h-4" />
                    {roomConfig.location}
                  </p>
                </div>
                
                <div>
                  <label className="text-sm text-gray-400">Capacity</label>
                  <p className="text-lg font-medium flex items-center gap-2">
                    <Users className="w-4 h-4" />
                    {roomConfig.capacity} people
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 mb-2 block">Equipment</label>
                  <div className="flex flex-wrap gap-2">
                    {roomConfig.equipment.map((item, index) => (
                      <span
                        key={index}
                        className="px-3 py-1 bg-gray-700 rounded-full text-sm"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm text-gray-400">Calendar Integration</label>
                    <div className={`w-12 h-6 rounded-full ${
                      roomConfig.calendar_integration ? 'bg-green-600' : 'bg-gray-600'
                    }`}>
                      <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                        roomConfig.calendar_integration ? 'translate-x-6' : 'translate-x-0.5'
                      } mt-0.5`} />
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <label className="text-sm text-gray-400">Auto Recording</label>
                    <div className={`w-12 h-6 rounded-full ${
                      roomConfig.auto_recording ? 'bg-green-600' : 'bg-gray-600'
                    }`}>
                      <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                        roomConfig.auto_recording ? 'translate-x-6' : 'translate-x-0.5'
                      } mt-0.5`} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-lg font-semibold mb-4">Room Status</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-400">Available</div>
                <div className="text-sm text-gray-400">Current Status</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold">3</div>
                <div className="text-sm text-gray-400">Meetings Today</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold">Next: 2:00 PM</div>
                <div className="text-sm text-gray-400">Next Meeting</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};