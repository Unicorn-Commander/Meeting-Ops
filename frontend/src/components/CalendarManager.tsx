import { useState, useEffect } from 'react';
import { Calendar, Clock, Users, MapPin, CheckCircle, AlertCircle, Plus, Settings } from 'lucide-react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { useAuth } from '../contexts/AuthContext';
import { getErrorMessage } from '../utils/errorHandling';

interface CalendarStatus {
  microsoft365: {
    configured: boolean;
    authenticated: boolean;
  };
  google: {
    configured: boolean;
    authenticated: boolean;
  };
  room_configured: boolean;
  room_locations: any;
}

interface Meeting {
  id: string;
  title: string;
  start_time: string;
  end_time: string;
  attendees: string[];
  location: string;
  status: string;
}

interface RoomStatus {
  current_time: string;
  device_location: string;
  room_info: any;
  is_available: boolean;
  current_meeting: Meeting | null;
  next_meeting: Meeting | null;
  calendar_integration: string;
}

export function CalendarManager() {
  const { isAuthenticated } = useAuth();
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus>({
    microsoft365: { configured: false, authenticated: false },
    google: { configured: false, authenticated: false },
    room_configured: false,
    room_locations: {}
  });
  
  const [roomStatus, setRoomStatus] = useState<RoomStatus>({
    current_time: new Date().toISOString(),
    device_location: 'Not configured',
    room_info: {},
    is_available: true,
    current_meeting: null,
    next_meeting: null,
    calendar_integration: 'not_configured'
  });

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [newMeeting, setNewMeeting] = useState({
    title: '',
    start_time: '',
    end_time: '',
    attendees: '',
    location: '',
    description: ''
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      const loadData = async () => {
        setIsLoading(true);
        setError(null);
        try {
          await Promise.all([
            fetchCalendarStatus(),
            fetchRoomStatus()
          ]);
        } catch (err) {
          console.error('Failed to load calendar data:', err);
          setError('Failed to load calendar data. Please check your authentication.');
        } finally {
          setIsLoading(false);
        }
      };
      loadData();
    } else {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  const fetchCalendarStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/calendar/status', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setCalendarStatus(data);
    } catch (error) {
      console.error('Failed to fetch calendar status:', error);
      throw error;
    }
  };

  const fetchRoomStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/calendar/room/status', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setRoomStatus(data);
    } catch (error) {
      console.error('Failed to fetch room status:', error);
      throw error;
    }
  };

  const scheduleMeeting = async () => {
    try {
      const attendeesList = newMeeting.attendees.split(',').map(email => email.trim()).filter(email => email);
      
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/calendar/meeting/schedule', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          title: newMeeting.title,
          start_time: newMeeting.start_time,
          end_time: newMeeting.end_time,
          attendees: attendeesList,
          location: newMeeting.location,
          description: newMeeting.description
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === 'success') {
          alert('✅ Meeting scheduled successfully!');
          setShowScheduleForm(false);
          setNewMeeting({
            title: '',
            start_time: '',
            end_time: '',
            attendees: '',
            location: '',
            description: ''
          });
          fetchRoomStatus(); // Refresh room status
        } else if (result.status === 'conflict') {
          alert(`❌ Meeting conflicts detected:\n${result.conflicts.map(c => 
            `${c.attendee}: ${c.conflicting_event} (${new Date(c.start_time).toLocaleString()})`
          ).join('\n')}`);
        }
      } else {
        const error = await response.text();
        alert(`❌ Failed to schedule meeting: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      console.error('Failed to schedule meeting:', error);
      alert(`❌ Failed to schedule meeting: ${getErrorMessage(error)}`);
    }
  };

  const getStatusIcon = (configured: boolean, authenticated: boolean) => {
    if (configured && authenticated) return <CheckCircle className="w-5 h-5 text-green-400" />;
    if (configured && !authenticated) return <AlertCircle className="w-5 h-5 text-yellow-400" />;
    return <AlertCircle className="w-5 h-5 text-red-400" />;
  };

  const getStatusText = (configured: boolean, authenticated: boolean) => {
    if (configured && authenticated) return 'Connected';
    if (configured && !authenticated) return 'Authentication Failed';
    return 'Not Configured';
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Calendar Management</h2>
        <div className="flex gap-3">
          <Button
            onClick={() => setShowScheduleForm(!showScheduleForm)}
            className="bg-blue-600 hover:bg-blue-700 flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Schedule Meeting
          </Button>
        </div>
      </div>

      {/* Integration Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            Integration Status
          </h3>
          
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Microsoft 365</span>
              <div className="flex items-center gap-2">
                {getStatusIcon(calendarStatus.microsoft365.configured, calendarStatus.microsoft365.authenticated)}
                <span className="text-sm text-gray-400">
                  {getStatusText(calendarStatus.microsoft365.configured, calendarStatus.microsoft365.authenticated)}
                </span>
              </div>
            </div>
            
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Google Workspace</span>
              <div className="flex items-center gap-2">
                {getStatusIcon(calendarStatus.google.configured, calendarStatus.google.authenticated)}
                <span className="text-sm text-gray-400">
                  {getStatusText(calendarStatus.google.configured, calendarStatus.google.authenticated)}
                </span>
              </div>
            </div>
          </div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <MapPin className="w-5 h-5" />
            Room Status
          </h3>
          
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Location</span>
              <span className="text-white">{roomStatus.device_location}</span>
            </div>
            
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Available</span>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${roomStatus.is_available ? 'bg-green-400' : 'bg-red-400'}`} />
                <span className="text-white">{roomStatus.is_available ? 'Yes' : 'No'}</span>
              </div>
            </div>
            
            {roomStatus.current_meeting && (
              <div className="mt-3 p-3 bg-gray-700/50 rounded">
                <div className="text-sm text-gray-400 mb-1">Current Meeting</div>
                <div className="text-white font-medium">{roomStatus.current_meeting.title}</div>
                <div className="text-xs text-gray-400">
                  {new Date(roomStatus.current_meeting.start_time).toLocaleTimeString()} - 
                  {new Date(roomStatus.current_meeting.end_time).toLocaleTimeString()}
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Schedule Meeting Form */}
      {showScheduleForm && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Schedule New Meeting</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Meeting Title</label>
              <input
                type="text"
                value={newMeeting.title}
                onChange={(e) => setNewMeeting({...newMeeting, title: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="Enter meeting title..."
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Location</label>
              <input
                type="text"
                value={newMeeting.location}
                onChange={(e) => setNewMeeting({...newMeeting, location: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="Meeting location..."
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Start Time</label>
              <input
                type="datetime-local"
                value={newMeeting.start_time}
                onChange={(e) => setNewMeeting({...newMeeting, start_time: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">End Time</label>
              <input
                type="datetime-local"
                value={newMeeting.end_time}
                onChange={(e) => setNewMeeting({...newMeeting, end_time: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              />
            </div>
            
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-2">Attendees (comma-separated emails)</label>
              <input
                type="text"
                value={newMeeting.attendees}
                onChange={(e) => setNewMeeting({...newMeeting, attendees: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="user1@company.com, user2@company.com..."
              />
            </div>
            
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
              <textarea
                value={newMeeting.description}
                onChange={(e) => setNewMeeting({...newMeeting, description: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white h-20"
                placeholder="Meeting description..."
              />
            </div>
          </div>
          
          <div className="flex gap-4 mt-6">
            <Button
              onClick={scheduleMeeting}
              className="bg-green-600 hover:bg-green-700"
              disabled={!newMeeting.title || !newMeeting.start_time || !newMeeting.end_time}
            >
              Schedule Meeting
            </Button>
            <Button
              onClick={() => setShowScheduleForm(false)}
              className="bg-gray-600 hover:bg-gray-700"
            >
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-red-400" />
            <div>
              <h3 className="text-lg font-semibold text-white">Error Loading Calendar Data</h3>
              <p className="text-gray-300 mt-1">{error}</p>
              <Button
                onClick={() => window.location.reload()}
                className="mt-3 bg-blue-600 hover:bg-blue-700"
              >
                Refresh Page
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Main Content */}
      {!isLoading && !error && (
        <>
          {/* Configuration Notice */}
          {calendarStatus.calendar_integration === 'not_configured' && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-yellow-400" />
            <div>
              <h3 className="text-lg font-semibold text-white">Calendar Integration Not Configured</h3>
              <p className="text-gray-300 mt-1">
                Configure Microsoft 365 or Google Workspace integration in Settings → Calendar Integration to enable meeting scheduling and room management.
              </p>
            </div>
          </div>
        </Card>
      )}
        </>
      )}
    </div>
  );
}