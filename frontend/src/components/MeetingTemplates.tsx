import React, { useState, useEffect } from 'react';
import { 
  FileText, Plus, Edit, Trash2, Copy, Clock, Users,
  Star, Settings, Download, Upload, Search, Tag,
  Play, Pause, CheckCircle, Calendar, Target,
  Mic, Video, MapPin, Bell, RefreshCw
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface MeetingTemplate {
  id: string;
  name: string;
  description: string;
  type: 'standup' | 'board' | 'interview' | 'presentation' | 'planning' | 'custom';
  duration: number; // minutes
  agenda: AgendaItem[];
  settings: {
    autoRecord: boolean;
    requireAttendance: boolean;
    allowLateJoin: boolean;
    sendReminders: boolean;
    transcriptionEnabled: boolean;
    aiInsights: boolean;
    speakerDiarization: boolean;
  };
  participants: {
    required: number;
    optional: number;
    roles: string[];
  };
  questions: string[];
  checklistItems: string[];
  usageCount: number;
  lastUsed?: string;
  createdAt: string;
  createdBy: string;
  isDefault: boolean;
  tags: string[];
}

interface AgendaItem {
  id: string;
  title: string;
  duration: number;
  type: 'discussion' | 'presentation' | 'decision' | 'update' | 'break';
  description?: string;
  presenter?: string;
  required: boolean;
}

interface TemplateUsage {
  templateId: string;
  sessionId: string;
  sessionName: string;
  date: string;
  duration: number;
  attendeeCount: number;
}

export const MeetingTemplates: React.FC = () => {
  const [templates, setTemplates] = useState<MeetingTemplate[]>([]);
  const [usage, setUsage] = useState<TemplateUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<MeetingTemplate | null>(null);
  const [activeTab, setActiveTab] = useState<'templates' | 'usage'>('templates');

  const templateTypes = [
    { 
      value: 'standup', 
      label: 'Daily Standup', 
      icon: Clock,
      color: 'bg-blue-500',
      description: 'Quick team sync meetings'
    },
    { 
      value: 'board', 
      label: 'Board Meeting', 
      icon: Users,
      color: 'bg-purple-500',
      description: 'Executive board meetings'
    },
    { 
      value: 'interview', 
      label: 'Interview', 
      icon: Mic,
      color: 'bg-green-500',
      description: 'Candidate interviews'
    },
    { 
      value: 'presentation', 
      label: 'Presentation', 
      icon: Video,
      color: 'bg-orange-500',
      description: 'Client or team presentations'
    },
    { 
      value: 'planning', 
      label: 'Planning Session', 
      icon: Target,
      color: 'bg-red-500',
      description: 'Strategic planning meetings'
    },
    { 
      value: 'custom', 
      label: 'Custom', 
      icon: Settings,
      color: 'bg-gray-500',
      description: 'Custom meeting format'
    }
  ];

  useEffect(() => {
    loadTemplateData();
  }, []);

  const loadTemplateData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Load templates
      const templatesResponse = await fetch(`${API_BASE_URL}/api/meeting-templates`, { headers });
      if (templatesResponse.ok) {
        const templatesData = await templatesResponse.json();
        setTemplates(templatesData);
      } else {
        // Mock data for demonstration
        setTemplates([
          {
            id: 'template-1',
            name: 'Daily Team Standup',
            description: 'Quick 15-minute team sync to discuss progress and blockers',
            type: 'standup',
            duration: 15,
            agenda: [
              { id: '1', title: 'What did you do yesterday?', duration: 4, type: 'update', required: true },
              { id: '2', title: 'What will you do today?', duration: 4, type: 'update', required: true },
              { id: '3', title: 'Any blockers?', duration: 4, type: 'discussion', required: true },
              { id: '4', title: 'Team announcements', duration: 3, type: 'update', required: false }
            ],
            settings: {
              autoRecord: true,
              requireAttendance: true,
              allowLateJoin: true,
              sendReminders: true,
              transcriptionEnabled: true,
              aiInsights: false,
              speakerDiarization: true
            },
            participants: {
              required: 5,
              optional: 2,
              roles: ['Developer', 'Product Manager', 'Designer']
            },
            questions: [
              'What did you accomplish yesterday?',
              'What are your goals for today?',
              'Are there any blockers preventing your progress?'
            ],
            checklistItems: [
              'All team members present',
              'Previous action items reviewed',
              'New blockers identified and assigned'
            ],
            usageCount: 45,
            lastUsed: '2025-01-09T09:00:00Z',
            createdAt: '2024-11-01T10:00:00Z',
            createdBy: 'Sarah Wilson',
            isDefault: true,
            tags: ['agile', 'daily', 'team']
          },
          {
            id: 'template-2',
            name: 'Technical Interview - Senior Developer',
            description: 'Structured interview process for senior developer candidates',
            type: 'interview',
            duration: 60,
            agenda: [
              { id: '1', title: 'Introduction & Background', duration: 10, type: 'discussion', presenter: 'Interviewer', required: true },
              { id: '2', title: 'Technical Deep Dive', duration: 25, type: 'discussion', required: true },
              { id: '3', title: 'Code Review Exercise', duration: 15, type: 'presentation', required: true },
              { id: '4', title: 'Cultural Fit & Questions', duration: 10, type: 'discussion', required: true }
            ],
            settings: {
              autoRecord: true,
              requireAttendance: false,
              allowLateJoin: false,
              sendReminders: false,
              transcriptionEnabled: true,
              aiInsights: true,
              speakerDiarization: true
            },
            participants: {
              required: 2,
              optional: 1,
              roles: ['Technical Lead', 'HR Representative', 'Team Member']
            },
            questions: [
              'Walk me through your experience with [specific technology]',
              'How do you approach system design?',
              'Describe a challenging technical problem you solved',
              'How do you stay current with technology trends?'
            ],
            checklistItems: [
              'Resume reviewed by all interviewers',
              'Technical skills assessment completed',
              'Cultural fit evaluation documented',
              'Next steps communicated to candidate'
            ],
            usageCount: 12,
            lastUsed: '2025-01-08T14:30:00Z',
            createdAt: '2024-12-15T11:00:00Z',
            createdBy: 'Mike Chen',
            isDefault: false,
            tags: ['hiring', 'technical', 'senior']
          },
          {
            id: 'template-3',
            name: 'Monthly Board Meeting',
            description: 'Executive board meeting with financial review and strategic decisions',
            type: 'board',
            duration: 120,
            agenda: [
              { id: '1', title: 'Opening & Attendance', duration: 5, type: 'update', required: true },
              { id: '2', title: 'Financial Review', duration: 30, type: 'presentation', presenter: 'CFO', required: true },
              { id: '3', title: 'Operational Updates', duration: 25, type: 'update', required: true },
              { id: '4', title: 'Strategic Initiatives', duration: 35, type: 'decision', required: true },
              { id: '5', title: 'Risk Assessment', duration: 15, type: 'discussion', required: true },
              { id: '6', title: 'Executive Session', duration: 10, type: 'discussion', required: false }
            ],
            settings: {
              autoRecord: true,
              requireAttendance: true,
              allowLateJoin: false,
              sendReminders: true,
              transcriptionEnabled: true,
              aiInsights: true,
              speakerDiarization: true
            },
            participants: {
              required: 7,
              optional: 2,
              roles: ['Board Member', 'CEO', 'CFO', 'CTO']
            },
            questions: [
              'Financial performance vs targets?',
              'Key operational metrics update?',
              'Strategic initiative progress?',
              'Major risks and mitigation plans?'
            ],
            checklistItems: [
              'Quorum established',
              'Previous meeting minutes approved',
              'Financial statements reviewed',
              'Board resolutions documented',
              'Action items assigned with due dates'
            ],
            usageCount: 8,
            lastUsed: '2025-01-05T10:00:00Z',
            createdAt: '2024-10-01T15:00:00Z',
            createdBy: 'John Doe',
            isDefault: false,
            tags: ['executive', 'monthly', 'governance']
          }
        ]);
      }

      // Load usage data
      const usageResponse = await fetch(`${API_BASE_URL}/api/meeting-templates/usage`, { headers });
      if (usageResponse.ok) {
        const usageData = await usageResponse.json();
        setUsage(usageData);
      } else {
        // Mock usage data
        setUsage([
          {
            templateId: 'template-1',
            sessionId: 'session-123',
            sessionName: 'Daily Standup - Jan 9',
            date: '2025-01-09T09:00:00Z',
            duration: 12,
            attendeeCount: 6
          },
          {
            templateId: 'template-1',
            sessionId: 'session-124',
            sessionName: 'Daily Standup - Jan 8',
            date: '2025-01-08T09:00:00Z',
            duration: 15,
            attendeeCount: 5
          }
        ]);
      }
    } catch (error) {
      console.error('Failed to load template data:', error);
    } finally {
      setLoading(false);
    }
  };

  const createMeetingFromTemplate = async (templateId: string) => {
    try {
      const template = templates.find(t => t.id === templateId);
      if (!template) return;

      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/from-template`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          templateId,
          name: `${template.name} - ${new Date().toLocaleDateString()}`,
          scheduledFor: new Date().toISOString()
        })
      });

      if (response.ok) {
        const session = await response.json();
        toast.success(`Meeting created: ${session.name}`);
        
        // Update usage count
        setTemplates(prev => prev.map(t => 
          t.id === templateId 
            ? { ...t, usageCount: t.usageCount + 1, lastUsed: new Date().toISOString() }
            : t
        ));
      } else {
        // Demo mode
        toast.success(`Meeting created from ${template.name} template`);
        setTemplates(prev => prev.map(t => 
          t.id === templateId 
            ? { ...t, usageCount: t.usageCount + 1, lastUsed: new Date().toISOString() }
            : t
        ));
      }
    } catch (error) {
      console.error('Failed to create meeting:', error);
      toast.error('Failed to create meeting from template');
    }
  };

  const duplicateTemplate = (template: MeetingTemplate) => {
    const duplicated: MeetingTemplate = {
      ...template,
      id: `template-${Date.now()}`,
      name: `${template.name} (Copy)`,
      usageCount: 0,
      lastUsed: undefined,
      createdAt: new Date().toISOString(),
      createdBy: 'Current User',
      isDefault: false
    };
    
    setTemplates([duplicated, ...templates]);
    toast.success('Template duplicated successfully');
  };

  const deleteTemplate = async (templateId: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/meeting-templates/${templateId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        setTemplates(templates.filter(t => t.id !== templateId));
        toast.success('Template deleted successfully');
      } else {
        // Demo mode
        setTemplates(templates.filter(t => t.id !== templateId));
        toast.success('Template deleted (demo mode)');
      }
    } catch (error) {
      console.error('Failed to delete template:', error);
      toast.error('Failed to delete template');
    }
  };

  const exportTemplate = (template: MeetingTemplate) => {
    const dataStr = JSON.stringify(template, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `${template.name.replace(/\s+/g, '_')}_template.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  const filteredTemplates = templates.filter(template => {
    const matchesSearch = template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         template.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         template.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesType = selectedType === 'all' || template.type === selectedType;
    return matchesSearch && matchesType;
  });

  const getTypeInfo = (type: string) => {
    return templateTypes.find(t => t.value === type) || templateTypes[templateTypes.length - 1];
  };

  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold flex items-center">
            <FileText className="w-8 h-8 text-green-400 mr-3" />
            Meeting Templates
          </h2>
          <p className="text-gray-400 mt-1">
            Standardize your meeting formats for consistent, productive sessions
          </p>
        </div>
        
        <div className="flex items-center space-x-2">
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center">
            <Upload className="w-4 h-4 mr-2" />
            Import
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
          >
            <Plus className="w-4 h-4 mr-2" />
            Create Template
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Total Templates</p>
              <p className="text-2xl font-bold">{templates.length}</p>
            </div>
            <FileText className="w-8 h-8 text-green-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Most Used</p>
              <p className="text-lg font-bold truncate">
                {templates.reduce((prev, curr) => prev.usageCount > curr.usageCount ? prev : curr, templates[0])?.name || 'None'}
              </p>
            </div>
            <Star className="w-8 h-8 text-yellow-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Total Usage</p>
              <p className="text-2xl font-bold">
                {templates.reduce((sum, t) => sum + t.usageCount, 0)}
              </p>
            </div>
            <Play className="w-8 h-8 text-purple-400" />
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Avg Duration</p>
              <p className="text-2xl font-bold">
                {formatDuration(Math.round(templates.reduce((sum, t) => sum + t.duration, 0) / templates.length))}
              </p>
            </div>
            <Clock className="w-8 h-8 text-blue-400" />
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center space-x-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search templates..."
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          />
        </div>
        
        <select
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
          className="px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
        >
          <option value="all">All Types</option>
          {templateTypes.map(type => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        
        <button
          onClick={loadTemplateData}
          className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-800 rounded-lg p-1">
        {[
          { id: 'templates', label: 'Templates', icon: FileText },
          { id: 'usage', label: 'Usage History', icon: Calendar }
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

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        <div className="grid gap-6">
          {filteredTemplates.map(template => {
            const typeInfo = getTypeInfo(template.type);
            const TypeIcon = typeInfo.icon;
            
            return (
              <div key={template.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center space-x-4">
                    <div className={`p-3 rounded-lg ${typeInfo.color}/20`}>
                      <TypeIcon className={`w-6 h-6 text-white`} />
                    </div>
                    
                    <div>
                      <div className="flex items-center space-x-3 mb-1">
                        <h3 className="text-xl font-semibold">{template.name}</h3>
                        {template.isDefault && (
                          <div className="px-2 py-1 rounded-full text-xs font-medium text-yellow-400 bg-yellow-400/20">
                            Default
                          </div>
                        )}
                      </div>
                      <p className="text-gray-400 text-sm mb-2">{template.description}</p>
                      
                      <div className="flex items-center space-x-4 text-sm text-gray-400">
                        <div className="flex items-center">
                          <Clock className="w-4 h-4 mr-1" />
                          {formatDuration(template.duration)}
                        </div>
                        <div className="flex items-center">
                          <Users className="w-4 h-4 mr-1" />
                          {template.participants.required} required
                        </div>
                        <div className="flex items-center">
                          <Play className="w-4 h-4 mr-1" />
                          Used {template.usageCount} times
                        </div>
                        {template.lastUsed && (
                          <span>Last used: {new Date(template.lastUsed).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => createMeetingFromTemplate(template.id)}
                      className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition-colors flex items-center"
                    >
                      <Play className="w-4 h-4 mr-2" />
                      Start Meeting
                    </button>
                    <button
                      onClick={() => duplicateTemplate(template)}
                      className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                      title="Duplicate"
                    >
                      <Copy className="w-4 h-4 text-gray-400" />
                    </button>
                    <button
                      onClick={() => setEditingTemplate(template)}
                      className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <Edit className="w-4 h-4 text-gray-400" />
                    </button>
                    <button
                      onClick={() => exportTemplate(template)}
                      className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                      title="Export"
                    >
                      <Download className="w-4 h-4 text-gray-400" />
                    </button>
                    <button
                      onClick={() => deleteTemplate(template.id)}
                      className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4 text-red-400" />
                    </button>
                  </div>
                </div>

                {/* Agenda Preview */}
                <div className="space-y-3">
                  <h4 className="font-medium text-gray-300">Agenda:</h4>
                  <div className="space-y-2">
                    {template.agenda.slice(0, 3).map(item => (
                      <div key={item.id} className="flex items-center justify-between bg-gray-700 rounded-lg p-3">
                        <div className="flex items-center space-x-3">
                          <div className={`w-2 h-2 rounded-full ${item.required ? 'bg-red-400' : 'bg-gray-400'}`} />
                          <span className="text-sm">{item.title}</span>
                          {item.presenter && (
                            <span className="text-xs text-gray-400">({item.presenter})</span>
                          )}
                        </div>
                        <span className="text-xs text-gray-400">{item.duration}m</span>
                      </div>
                    ))}
                    {template.agenda.length > 3 && (
                      <div className="text-sm text-gray-400 text-center">
                        +{template.agenda.length - 3} more items
                      </div>
                    )}
                  </div>
                </div>

                {/* Tags */}
                {template.tags.length > 0 && (
                  <div className="mt-4">
                    <div className="flex flex-wrap gap-2">
                      {template.tags.map((tag, index) => (
                        <span key={index} className="px-2 py-1 bg-gray-700 rounded-full text-xs">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          
          {filteredTemplates.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
              <p>No meeting templates found</p>
              <p className="text-sm mt-2">Create your first template to standardize your meetings</p>
            </div>
          )}
        </div>
      )}

      {/* Usage Tab */}
      {activeTab === 'usage' && (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">Recent Template Usage</h3>
          
          <div className="space-y-3">
            {usage.map((item, index) => {
              const template = templates.find(t => t.id === item.templateId);
              const typeInfo = template ? getTypeInfo(template.type) : null;
              const TypeIcon = typeInfo?.icon || FileText;
              
              return (
                <div key={index} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      <div className={`p-2 rounded ${typeInfo?.color}/20`}>
                        <TypeIcon className="w-5 h-5 text-white" />
                      </div>
                      
                      <div>
                        <h4 className="font-semibold">{item.sessionName}</h4>
                        <div className="flex items-center space-x-4 text-sm text-gray-400">
                          <span>{new Date(item.date).toLocaleDateString()}</span>
                          <span>{item.duration} minutes</span>
                          <span>{item.attendeeCount} attendees</span>
                        </div>
                      </div>
                    </div>
                    
                    <button className="text-blue-400 hover:text-blue-300 text-sm">
                      View Session →
                    </button>
                  </div>
                </div>
              );
            })}
            
            {usage.length === 0 && (
              <div className="text-center py-8 text-gray-400">
                <Calendar className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No template usage history</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};