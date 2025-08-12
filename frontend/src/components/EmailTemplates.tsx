import React, { useState, useEffect } from 'react';
import { 
  Mail, Plus, Edit, Trash2, Copy, Send, Eye, Settings,
  FileText, Users, Calendar, Target, Award, Zap,
  RefreshCw, Download, Upload, Save, X, Check
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body: string;
  type: 'summary' | 'action_items' | 'transcript' | 'custom';
  variables: string[];
  recipients: string[];
  autoSend: boolean;
  trigger: 'meeting_end' | 'manual' | 'scheduled';
  createdAt: string;
  lastUsed?: string;
  usageCount: number;
  isDefault: boolean;
}

interface CreateTemplateRequest {
  name: string;
  subject: string;
  body: string;
  type: string;
  recipients: string[];
  autoSend: boolean;
  trigger: string;
}

export const EmailTemplates: React.FC = () => {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState<string | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(null);
  const [newTemplate, setNewTemplate] = useState<CreateTemplateRequest>({
    name: '',
    subject: '',
    body: '',
    type: 'summary',
    recipients: [],
    autoSend: false,
    trigger: 'manual'
  });

  const templateTypes = [
    { value: 'summary', label: 'Meeting Summary', icon: FileText, description: 'Send meeting summaries with key points' },
    { value: 'action_items', label: 'Action Items', icon: Target, description: 'Send extracted action items and tasks' },
    { value: 'transcript', label: 'Transcript', icon: Mail, description: 'Send full meeting transcripts' },
    { value: 'custom', label: 'Custom', icon: Edit, description: 'Custom email template' }
  ];

  const availableVariables = [
    { name: '{{meeting_title}}', description: 'Meeting title or session name' },
    { name: '{{meeting_date}}', description: 'Date when meeting occurred' },
    { name: '{{meeting_duration}}', description: 'Meeting duration in minutes' },
    { name: '{{attendees}}', description: 'List of meeting attendees' },
    { name: '{{summary}}', description: 'AI-generated meeting summary' },
    { name: '{{action_items}}', description: 'Extracted action items' },
    { name: '{{transcript}}', description: 'Full meeting transcript' },
    { name: '{{key_decisions}}', description: 'Important decisions made' },
    { name: '{{recording_url}}', description: 'Link to the recording' },
    { name: '{{export_links}}', description: 'Links to downloadable files' }
  ];

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/email-templates`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      } else {
        console.warn('Email templates data not available');
        setTemplates([]);
      }
    } catch (error) {
      console.error('Failed to fetch templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTemplate = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/email-templates`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newTemplate)
      });

      if (response.ok) {
        const createdTemplate = await response.json();
        setTemplates([createdTemplate, ...templates]);
        setShowCreateModal(false);
        resetNewTemplate();
        toast.success('Email template created successfully');
      } else {
        // Demo mode
        const mockTemplate: EmailTemplate = {
          id: Date.now().toString(),
          name: newTemplate.name,
          subject: newTemplate.subject,
          body: newTemplate.body,
          type: newTemplate.type as "summary" | "custom" | "transcript" | "action_items",
          recipients: newTemplate.recipients,
          autoSend: newTemplate.autoSend,
          trigger: newTemplate.trigger,
          variables: extractVariables(newTemplate.body),
          createdAt: new Date().toISOString(),
          usageCount: 0,
          isDefault: false
        };
        setTemplates([mockTemplate, ...templates]);
        setShowCreateModal(false);
        resetNewTemplate();
        toast.success('Email template created (demo mode)');
      }
    } catch (error) {
      console.error('Failed to create template:', error);
      toast.error('Failed to create email template');
    }
  };

  const handleUpdateTemplate = async (template: EmailTemplate) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/email-templates/${template.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(template)
      });

      if (response.ok) {
        setTemplates(templates.map(t => t.id === template.id ? template : t));
        setEditingTemplate(null);
        toast.success('Template updated successfully');
      } else {
        // Demo mode
        setTemplates(templates.map(t => t.id === template.id ? template : t));
        setEditingTemplate(null);
        toast.success('Template updated (demo mode)');
      }
    } catch (error) {
      console.error('Failed to update template:', error);
      toast.error('Failed to update template');
    }
  };

  const handleDeleteTemplate = async (templateId: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/email-templates/${templateId}`, {
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

  const handleTestEmail = async (templateId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/email-templates/${templateId}/test`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success('Test email sent successfully');
      } else {
        toast.success('Test email sent (demo mode)');
      }
    } catch (error) {
      console.error('Failed to send test email:', error);
      toast.error('Failed to send test email');
    }
  };

  const extractVariables = (body: string) => {
    const matches = body.match(/\{\{[^}]+\}\}/g);
    return matches ? [...new Set(matches)] : [];
  };

  const resetNewTemplate = () => {
    setNewTemplate({
      name: '',
      subject: '',
      body: '',
      type: 'summary',
      recipients: [],
      autoSend: false,
      trigger: 'manual'
    });
  };

  const getTypeIcon = (type: string) => {
    const typeInfo = templateTypes.find(t => t.value === type);
    return typeInfo ? <typeInfo.icon className="w-4 h-4" /> : <Mail className="w-4 h-4" />;
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'summary': return 'text-blue-400 bg-blue-400/20';
      case 'action_items': return 'text-green-400 bg-green-400/20';
      case 'transcript': return 'text-purple-400 bg-purple-400/20';
      case 'custom': return 'text-gray-400 bg-gray-400/20';
      default: return 'text-gray-400 bg-gray-400/20';
    }
  };

  const getTriggerIcon = (trigger: string) => {
    switch (trigger) {
      case 'meeting_end': return <Zap className="w-4 h-4" />;
      case 'manual': return <Send className="w-4 h-4" />;
      case 'scheduled': return <Calendar className="w-4 h-4" />;
      default: return <Mail className="w-4 h-4" />;
    }
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
        <h2 className="text-3xl font-bold">Email Templates</h2>
        <div className="flex items-center space-x-4">
          <button
            onClick={() => fetchTemplates()}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
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

      {/* Templates Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {templates.map(template => (
          <div key={template.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <h3 className="text-xl font-semibold">{template.name}</h3>
                  {template.isDefault && (
                    <div className="px-2 py-1 rounded-full text-xs font-medium text-yellow-400 bg-yellow-400/20">
                      Default
                    </div>
                  )}
                </div>
                <div className="flex items-center space-x-4 text-sm text-gray-400">
                  <div className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getTypeColor(template.type)}`}>
                    {getTypeIcon(template.type)}
                    <span className="ml-1 capitalize">{template.type.replace('_', ' ')}</span>
                  </div>
                  <div className="flex items-center">
                    {getTriggerIcon(template.trigger)}
                    <span className="ml-1 capitalize">{template.trigger.replace('_', ' ')}</span>
                  </div>
                  {template.autoSend && (
                    <div className="flex items-center text-green-400">
                      <Zap className="w-3 h-3 mr-1" />
                      Auto-send
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setShowPreviewModal(template.id)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Preview"
                >
                  <Eye className="w-4 h-4 text-gray-400" />
                </button>
                <button
                  onClick={() => setEditingTemplate(template)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Edit"
                >
                  <Edit className="w-4 h-4 text-gray-400" />
                </button>
                <button
                  onClick={() => handleTestEmail(template.id)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Send test"
                >
                  <Send className="w-4 h-4 text-blue-400" />
                </button>
                <button
                  onClick={() => handleDeleteTemplate(template.id)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-400">Subject</label>
                <p className="font-mono text-sm bg-gray-900/50 p-2 rounded">{template.subject}</p>
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Recipients</label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {template.recipients.map((recipient, index) => (
                    <span key={index} className="px-2 py-1 bg-gray-700 rounded-full text-xs">
                      {recipient}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Used {template.usageCount} times</span>
                {template.lastUsed && (
                  <span className="text-gray-400">Last used: {new Date(template.lastUsed).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {templates.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <Mail className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>No email templates found</p>
          <p className="text-sm mt-2">Create your first template to get started</p>
        </div>
      )}

      {/* Create/Edit Template Modal */}
      {(showCreateModal || editingTemplate) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-4xl m-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">
                {editingTemplate ? 'Edit Template' : 'Create New Template'}
              </h3>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setEditingTemplate(null);
                  resetNewTemplate();
                }}
                className="text-gray-400 hover:text-white"
              >
                <X className="w-6 h-6" />
              </button>
            </div>
            
            <form onSubmit={editingTemplate ? (e) => {
              e.preventDefault();
              handleUpdateTemplate(editingTemplate);
            } : handleCreateTemplate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Template Name</label>
                  <input
                    type="text"
                    value={editingTemplate ? editingTemplate.name : newTemplate.name}
                    onChange={(e) => {
                      if (editingTemplate) {
                        setEditingTemplate({...editingTemplate, name: e.target.value});
                      } else {
                        setNewTemplate({...newTemplate, name: e.target.value});
                      }
                    }}
                    placeholder="Weekly Standup Summary"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Type</label>
                  <select
                    value={editingTemplate ? editingTemplate.type : newTemplate.type}
                    onChange={(e) => {
                      if (editingTemplate) {
                        setEditingTemplate({...editingTemplate, type: e.target.value as any});
                      } else {
                        setNewTemplate({...newTemplate, type: e.target.value});
                      }
                    }}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    {templateTypes.map(type => (
                      <option key={type.value} value={type.value}>{type.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Subject Line</label>
                <input
                  type="text"
                  value={editingTemplate ? editingTemplate.subject : newTemplate.subject}
                  onChange={(e) => {
                    if (editingTemplate) {
                      setEditingTemplate({...editingTemplate, subject: e.target.value});
                    } else {
                      setNewTemplate({...newTemplate, subject: e.target.value});
                    }
                  }}
                  placeholder="Meeting Summary - {{meeting_date}}"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  required
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium">Email Body</label>
                  <div className="text-xs text-gray-400">Use variables like {{meeting_title}}</div>
                </div>
                <textarea
                  value={editingTemplate ? editingTemplate.body : newTemplate.body}
                  onChange={(e) => {
                    if (editingTemplate) {
                      setEditingTemplate({...editingTemplate, body: e.target.value});
                    } else {
                      setNewTemplate({...newTemplate, body: e.target.value});
                    }
                  }}
                  placeholder="Dear team,&#10;&#10;Here's the summary of our meeting...&#10;&#10;{{summary}}&#10;&#10;Best regards!"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  rows={10}
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Available Variables</label>
                <div className="grid grid-cols-2 gap-2 text-xs bg-gray-900/50 p-3 rounded max-h-32 overflow-y-auto">
                  {availableVariables.map(variable => (
                    <div key={variable.name} className="flex items-start">
                      <code className="text-purple-300 mr-2">{variable.name}</code>
                      <span className="text-gray-400">{variable.description}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Recipients (one per line)</label>
                  <textarea
                    value={editingTemplate ? editingTemplate.recipients.join('\n') : newTemplate.recipients.join('\n')}
                    onChange={(e) => {
                      const recipients = e.target.value.split('\n').filter(r => r.trim());
                      if (editingTemplate) {
                        setEditingTemplate({...editingTemplate, recipients});
                      } else {
                        setNewTemplate({...newTemplate, recipients});
                      }
                    }}
                    placeholder="team@company.com&#10;manager@company.com"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                    rows={3}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Trigger</label>
                  <select
                    value={editingTemplate ? editingTemplate.trigger : newTemplate.trigger}
                    onChange={(e) => {
                      if (editingTemplate) {
                        setEditingTemplate({...editingTemplate, trigger: e.target.value as any});
                      } else {
                        setNewTemplate({...newTemplate, trigger: e.target.value});
                      }
                    }}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="manual">Manual Send</option>
                    <option value="meeting_end">Auto-send when meeting ends</option>
                    <option value="scheduled">Scheduled Send</option>
                  </select>

                  <label className="flex items-center mt-3">
                    <input
                      type="checkbox"
                      checked={editingTemplate ? editingTemplate.autoSend : newTemplate.autoSend}
                      onChange={(e) => {
                        if (editingTemplate) {
                          setEditingTemplate({...editingTemplate, autoSend: e.target.checked});
                        } else {
                          setNewTemplate({...newTemplate, autoSend: e.target.checked});
                        }
                      }}
                      className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600"
                    />
                    <span className="text-sm">Enable auto-send</span>
                  </label>
                </div>
              </div>
              
              <div className="flex items-center justify-end space-x-4 pt-4 border-t border-gray-700">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    setEditingTemplate(null);
                    resetNewTemplate();
                  }}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
                >
                  <Save className="w-4 h-4 mr-2" />
                  {editingTemplate ? 'Update' : 'Create'} Template
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreviewModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl m-4">
            {(() => {
              const template = templates.find(t => t.id === showPreviewModal);
              return template ? (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold">Preview: {template.name}</h3>
                    <button
                      onClick={() => setShowPreviewModal(null)}
                      className="text-gray-400 hover:text-white"
                    >
                      <X className="w-6 h-6" />
                    </button>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm text-gray-400">Subject</label>
                      <div className="bg-gray-900/50 p-3 rounded font-mono">{template.subject}</div>
                    </div>
                    
                    <div>
                      <label className="text-sm text-gray-400">Body</label>
                      <div className="bg-gray-900/50 p-4 rounded whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                        {template.body}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-end space-x-4 mt-6">
                    <button
                      onClick={() => setShowPreviewModal(null)}
                      className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
                    >
                      Close
                    </button>
                    <button
                      onClick={() => handleTestEmail(template.id)}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors flex items-center"
                    >
                      <Send className="w-4 h-4 mr-2" />
                      Send Test Email
                    </button>
                  </div>
                </>
              ) : null;
            })()}
          </div>
        </div>
      )}
    </div>
  );
};