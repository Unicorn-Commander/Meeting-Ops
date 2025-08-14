import { useState, useEffect } from 'react';
import { Webhook, Plus, TestTube, Edit, Trash2, Activity, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { getErrorMessage } from '../utils/errorHandling';

interface WebhookEndpoint {
  id: string;
  name: string;
  url: string;
  events: string[] | null;
  active: boolean;
  retry_count: number;
  timeout: number;
}

interface WebhookEvent {
  event_type: string;
  event_id: string;
  timestamp: string;
  session_id: string;
  data: any;
}

interface WebhookStats {
  total_endpoints: number;
  active_endpoints: number;
  total_events_sent: number;
  recent_events: number;
  event_types: string[];
  endpoint_stats: any[];
}

export function WebhookManager() {
  const { isAuthenticated } = useAuthentikAuth();
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [stats, setStats] = useState<WebhookStats>({
    total_endpoints: 0,
    active_endpoints: 0,
    total_events_sent: 0,
    recent_events: 0,
    event_types: [],
    endpoint_stats: []
  });
  
  const [availableEvents, setAvailableEvents] = useState<string[]>([]);
  const [eventDescriptions, setEventDescriptions] = useState<{[key: string]: string}>({});
  
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingEndpoint, setEditingEndpoint] = useState<WebhookEndpoint | null>(null);
  const [newEndpoint, setNewEndpoint] = useState({
    name: '',
    url: '',
    secret: '',
    events: [] as string[],
    active: true,
    retry_count: 3,
    timeout: 30
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
            fetchEndpoints(),
            fetchEvents(),
            fetchStats()
          ]);
        } catch (err) {
          console.error('Failed to load webhook data:', err);
          setError('Failed to load webhook data. Please check your authentication.');
        } finally {
          setIsLoading(false);
        }
      };
      loadData();
    } else {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  const fetchEndpoints = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/webhooks', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setEndpoints(data.endpoints || []);
      setAvailableEvents(data.available_events || []);
      setEventDescriptions(data.event_descriptions || {});
    } catch (error) {
      console.error('Failed to fetch webhooks:', error);
      throw error;
    }
  };

  const fetchEvents = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/webhooks/events/log?limit=50', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setEvents(data.events || []);
    } catch (error) {
      console.error('Failed to fetch webhook events:', error);
      throw error;
    }
  };

  const fetchStats = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/webhooks/stats', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch webhook stats:', error);
      throw error;
    }
  };

  const createEndpoint = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/webhooks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          ...newEndpoint,
          events: newEndpoint.events.length > 0 ? newEndpoint.events : null
        }),
      });

      if (response.ok) {
        alert('✅ Webhook endpoint created successfully!');
        setShowAddForm(false);
        resetForm();
        fetchEndpoints();
        fetchStats();
      } else {
        const error = await response.text();
        alert(`❌ Failed to create webhook: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      console.error('Failed to create webhook:', error);
      alert(`❌ Failed to create webhook: ${getErrorMessage(error)}`);
    }
  };

  const updateEndpoint = async () => {
    if (!editingEndpoint) return;
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/webhooks/${editingEndpoint.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          ...newEndpoint,
          events: newEndpoint.events.length > 0 ? newEndpoint.events : null
        }),
      });

      if (response.ok) {
        alert('✅ Webhook endpoint updated successfully!');
        setEditingEndpoint(null);
        resetForm();
        fetchEndpoints();
        fetchStats();
      } else {
        const error = await response.text();
        alert(`❌ Failed to update webhook: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      console.error('Failed to update webhook:', error);
      alert(`❌ Failed to update webhook: ${getErrorMessage(error)}`);
    }
  };

  const deleteEndpoint = async (id: string) => {
    if (!confirm('Are you sure you want to delete this webhook endpoint?')) return;
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/webhooks/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        alert('✅ Webhook endpoint deleted successfully!');
        fetchEndpoints();
        fetchStats();
      } else {
        const error = await response.text();
        alert(`❌ Failed to delete webhook: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      console.error('Failed to delete webhook:', error);
      alert(`❌ Failed to delete webhook: ${getErrorMessage(error)}`);
    }
  };

  const testEndpoint = async (id: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/webhooks/${id}/test`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const result = await response.json();
      if (result.success) {
        alert('✅ Test webhook sent successfully!');
      } else {
        alert(`❌ Test webhook failed: ${result.test_result?.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to test webhook:', error);
      alert(`❌ Failed to test webhook: ${getErrorMessage(error)}`);
    }
  };

  const startEdit = (endpoint: WebhookEndpoint) => {
    setEditingEndpoint(endpoint);
    setNewEndpoint({
      name: endpoint.name,
      url: endpoint.url,
      secret: '',
      events: endpoint.events || [],
      active: endpoint.active,
      retry_count: endpoint.retry_count,
      timeout: endpoint.timeout
    });
    setShowAddForm(true);
  };

  const resetForm = () => {
    setNewEndpoint({
      name: '',
      url: '',
      secret: '',
      events: [],
      active: true,
      retry_count: 3,
      timeout: 30
    });
  };

  const toggleEventSelection = (eventType: string) => {
    setNewEndpoint(prev => ({
      ...prev,
      events: prev.events.includes(eventType)
        ? prev.events.filter(e => e !== eventType)
        : [...prev.events, eventType]
    }));
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">Error Loading Webhooks</h3>
          <p className="text-gray-400">{error}</p>
          <Button
            onClick={() => window.location.reload()}
            className="mt-4 bg-blue-600 hover:bg-blue-700"
          >
            Refresh Page
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Webhook Management</h2>
        <div className="flex gap-3">
          <Button
            onClick={() => {
              setShowAddForm(!showAddForm);
              setEditingEndpoint(null);
              resetForm();
            }}
            className="bg-blue-600 hover:bg-blue-700 flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add Webhook
          </Button>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Webhook className="w-5 h-5 text-blue-400" />
            <span className="text-xs text-gray-400">Endpoints</span>
          </div>
          <div className="text-2xl font-bold text-white">{stats.total_endpoints}</div>
          <div className="text-xs text-gray-400 mt-1">{stats.active_endpoints} active</div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Activity className="w-5 h-5 text-green-400" />
            <span className="text-xs text-gray-400">Events</span>
          </div>
          <div className="text-2xl font-bold text-white">{stats.total_events_sent}</div>
          <div className="text-xs text-gray-400 mt-1">total sent</div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <Clock className="w-5 h-5 text-yellow-400" />
            <span className="text-xs text-gray-400">Recent</span>
          </div>
          <div className="text-2xl font-bold text-white">{stats.recent_events}</div>
          <div className="text-xs text-gray-400 mt-1">last hour</div>
        </Card>

        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <CheckCircle className="w-5 h-5 text-purple-400" />
            <span className="text-xs text-gray-400">Types</span>
          </div>
          <div className="text-2xl font-bold text-white">{stats.event_types.length}</div>
          <div className="text-xs text-gray-400 mt-1">event types</div>
        </Card>
      </div>

      {/* Add/Edit Webhook Form */}
      {showAddForm && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4">
            {editingEndpoint ? 'Edit Webhook Endpoint' : 'Add New Webhook Endpoint'}
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
              <input
                type="text"
                value={newEndpoint.name}
                onChange={(e) => setNewEndpoint({...newEndpoint, name: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="My App Webhook"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">URL</label>
              <input
                type="url"
                value={newEndpoint.url}
                onChange={(e) => setNewEndpoint({...newEndpoint, url: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="https://api.myapp.com/webhooks"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Secret (optional)</label>
              <input
                type="password"
                value={newEndpoint.secret}
                onChange={(e) => setNewEndpoint({...newEndpoint, secret: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                placeholder="Webhook secret for HMAC verification"
              />
            </div>
            
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-300 mb-2">Retry Count</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={newEndpoint.retry_count}
                  onChange={(e) => setNewEndpoint({...newEndpoint, retry_count: parseInt(e.target.value) || 3})}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
              
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-300 mb-2">Timeout (s)</label>
                <input
                  type="number"
                  min="5"
                  max="120"
                  value={newEndpoint.timeout}
                  onChange={(e) => setNewEndpoint({...newEndpoint, timeout: parseInt(e.target.value) || 30})}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>
          </div>
          
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Event Types (leave empty for all events)
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-40 overflow-y-auto">
              {availableEvents.map(eventType => (
                <label key={eventType} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={newEndpoint.events.includes(eventType)}
                    onChange={() => toggleEventSelection(eventType)}
                    className="w-4 h-4"
                  />
                  <span className="text-gray-300">{eventType}</span>
                </label>
              ))}
            </div>
          </div>
          
          <div className="flex items-center gap-3 mt-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={newEndpoint.active}
                onChange={(e) => setNewEndpoint({...newEndpoint, active: e.target.checked})}
                className="w-4 h-4"
              />
              <span className="text-gray-300">Active</span>
            </label>
          </div>
          
          <div className="flex gap-4 mt-6">
            <Button
              onClick={editingEndpoint ? updateEndpoint : createEndpoint}
              className="bg-green-600 hover:bg-green-700"
              disabled={!newEndpoint.name || !newEndpoint.url}
            >
              {editingEndpoint ? 'Update' : 'Create'} Webhook
            </Button>
            <Button
              onClick={() => {
                setShowAddForm(false);
                setEditingEndpoint(null);
                resetForm();
              }}
              className="bg-gray-600 hover:bg-gray-700"
            >
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {/* Webhook Endpoints List */}
      {endpoints.length > 0 && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Webhook Endpoints</h3>
          
          <div className="space-y-4">
            {endpoints.map(endpoint => (
              <div key={endpoint.id} className="border border-gray-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${endpoint.active ? 'bg-green-400' : 'bg-gray-400'}`} />
                    <h4 className="font-medium text-white">{endpoint.name}</h4>
                  </div>
                  
                  <div className="flex gap-2">
                    <Button
                      onClick={() => testEndpoint(endpoint.id)}
                      className="bg-blue-600 hover:bg-blue-700 px-3 py-1 text-xs flex items-center gap-1"
                    >
                      <TestTube className="w-3 h-3" />
                      Test
                    </Button>
                    <Button
                      onClick={() => startEdit(endpoint)}
                      className="bg-yellow-600 hover:bg-yellow-700 px-3 py-1 text-xs flex items-center gap-1"
                    >
                      <Edit className="w-3 h-3" />
                      Edit
                    </Button>
                    <Button
                      onClick={() => deleteEndpoint(endpoint.id)}
                      className="bg-red-600 hover:bg-red-700 px-3 py-1 text-xs flex items-center gap-1"
                    >
                      <Trash2 className="w-3 h-3" />
                      Delete
                    </Button>
                  </div>
                </div>
                
                <div className="text-sm text-gray-400 mb-2">{endpoint.url}</div>
                
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="bg-gray-700 px-2 py-1 rounded">
                    {endpoint.events?.length || 'All'} events
                  </span>
                  <span className="bg-gray-700 px-2 py-1 rounded">
                    {endpoint.retry_count} retries
                  </span>
                  <span className="bg-gray-700 px-2 py-1 rounded">
                    {endpoint.timeout}s timeout
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Recent Events */}
      {events.length > 0 && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Recent Events</h3>
          
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {events.slice(0, 20).map((event, index) => (
              <div key={index} className="flex items-center justify-between p-2 bg-gray-700/50 rounded">
                <div className="flex items-center gap-3">
                  <span className="text-xs bg-blue-600 px-2 py-1 rounded text-white">
                    {event.event_type}
                  </span>
                  <span className="text-sm text-gray-300">
                    Session: {event.session_id}
                  </span>
                </div>
                <span className="text-xs text-gray-400">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Empty State */}
      {endpoints.length === 0 && (
        <Card className="bg-gray-800 border-gray-700 p-6">
          <div className="text-center py-8">
            <Webhook className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">No Webhook Endpoints</h3>
            <p className="text-gray-400 mb-4">
              Create your first webhook endpoint to receive real-time notifications about meeting events.
            </p>
            <Button
              onClick={() => setShowAddForm(true)}
              className="bg-blue-600 hover:bg-blue-700"
            >
              Add First Webhook
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}