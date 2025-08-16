import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Plus, 
  Settings, 
  Trash2, 
  Copy, 
  Play,
  Pause,
  Clock,
  Hash,
  User,
  Brain,
  ChevronDown,
  ChevronRight,
  Bot,
  MessageSquare,
  Sparkles,
  Code,
  Zap,
  Target
} from 'lucide-react';
import { config } from '../../config';

interface TemplateSection {
  id: string;
  type: 'executive' | 'actions' | 'decisions' | 'bullets' | 'custom';
  title: string;
  prompt: string;
  order: number;
  isEnabled: boolean;
}

interface MeetingAgent {
  id: string;
  name: string;
  description: string;
  avatar?: string;
  role: 'meeting-analyst' | 'action-tracker' | 'decision-maker' | 'note-taker' | 'custom';
  personality: string; // System prompt for agent personality
  sections: TemplateSection[];
  trigger: 'manual' | 'auto' | 'word_count' | 'time';
  triggerValue?: number; // Words or seconds
  isActive: boolean;
  isDefault?: boolean;
  capabilities: string[]; // List of what this agent can do
  modelPreference?: string; // Preferred AI model
}

const AGENT_ROLES = {
  'meeting-analyst': {
    name: 'Meeting Analyst',
    icon: Brain,
    description: 'Comprehensive meeting analysis and insights',
    defaultPersonality: 'You are an expert meeting analyst. You provide thorough, professional analysis of meetings with keen attention to detail and strategic insights.',
    capabilities: ['Summary Generation', 'Trend Analysis', 'Outcome Assessment', 'Strategic Insights']
  },
  'action-tracker': {
    name: 'Action Tracker',
    icon: Target,
    description: 'Specializes in identifying and tracking action items',
    defaultPersonality: 'You are a meticulous action tracker. You excel at identifying tasks, assigning ownership, and setting deadlines from meeting discussions.',
    capabilities: ['Action Item Extraction', 'Owner Assignment', 'Deadline Tracking', 'Follow-up Reminders']
  },
  'decision-maker': {
    name: 'Decision Maker',
    icon: Zap,
    description: 'Focuses on decisions and resolution tracking',
    defaultPersonality: 'You are a decision analysis expert. You identify key decisions made, their impact, and track resolution status.',
    capabilities: ['Decision Identification', 'Impact Analysis', 'Resolution Tracking', 'Stakeholder Mapping']
  },
  'note-taker': {
    name: 'Note Taker',
    icon: MessageSquare,
    description: 'Detailed note-taking and documentation specialist',
    defaultPersonality: 'You are a professional note-taker. You capture detailed, well-structured meeting notes with perfect organization and clarity.',
    capabilities: ['Detailed Notes', 'Speaker Identification', 'Topic Organization', 'Timestamp Management']
  },
  'custom': {
    name: 'Custom Agent',
    icon: Bot,
    description: 'Custom-configured agent with user-defined capabilities',
    defaultPersonality: 'You are a custom meeting assistant. Follow the user-defined instructions and capabilities provided.',
    capabilities: ['Custom Functions']
  }
};

const SECTION_TYPES = {
  executive: { 
    name: 'Executive Summary', 
    icon: FileText, 
    defaultPrompt: 'Provide a comprehensive executive summary of this meeting, highlighting key topics, outcomes, and overall assessment.'
  },
  actions: { 
    name: 'Action Items', 
    icon: User, 
    defaultPrompt: 'Extract action items from this meeting. Format as JSON array with structure: [{"action": "task description", "owner": "person or TBD", "deadline": "date or TBD"}]'
  },
  decisions: { 
    name: 'Key Decisions', 
    icon: Brain, 
    defaultPrompt: 'List the key decisions made in this meeting. Return as JSON array of decision strings.'
  },
  bullets: { 
    name: 'Key Points', 
    icon: Hash, 
    defaultPrompt: 'Extract key points and highlights from this meeting as a JSON array of bullet point strings.'
  },
  custom: { 
    name: 'Custom Section', 
    icon: Settings, 
    defaultPrompt: 'Analyze this meeting transcript and provide insights based on your custom requirements.'
  }
};

export default function Templates() {
  const [templates, setTemplates] = useState<MeetingTemplate[]>([]);
  const [editingTemplate, setEditingTemplate] = useState<MeetingTemplate | null>(null);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/admin/templates`);
      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      }
    } catch (error) {
      console.error('Failed to load templates:', error);
      // Initialize with default template
      setTemplates([{
        id: 'default',
        name: 'Standard Meeting Summary',
        description: 'Comprehensive meeting analysis with all standard sections',
        sections: [
          {
            id: '1',
            type: 'executive',
            title: 'Executive Summary',
            prompt: SECTION_TYPES.executive.defaultPrompt,
            order: 1,
            isEnabled: true
          },
          {
            id: '2',
            type: 'actions',
            title: 'Action Items',
            prompt: SECTION_TYPES.actions.defaultPrompt,
            order: 2,
            isEnabled: true
          },
          {
            id: '3',
            type: 'decisions',
            title: 'Key Decisions',
            prompt: SECTION_TYPES.decisions.defaultPrompt,
            order: 3,
            isEnabled: true
          },
          {
            id: '4',
            type: 'bullets',
            title: 'Key Points',
            prompt: SECTION_TYPES.bullets.defaultPrompt,
            order: 4,
            isEnabled: true
          }
        ],
        trigger: 'word_count',
        triggerValue: 300,
        isActive: true,
        isDefault: true
      }]);
    }
  };

  const createTemplate = () => {
    const newTemplate: MeetingTemplate = {
      id: Date.now().toString(),
      name: 'New Template',
      description: 'Custom meeting template',
      sections: [
        {
          id: '1',
          type: 'executive',
          title: 'Executive Summary',
          prompt: SECTION_TYPES.executive.defaultPrompt,
          order: 1,
          isEnabled: true
        }
      ],
      trigger: 'word_count',
      triggerValue: 300,
      isActive: false
    };
    setEditingTemplate(newTemplate);
  };

  const addSection = (template: MeetingTemplate, type: keyof typeof SECTION_TYPES) => {
    const newSection: TemplateSection = {
      id: Date.now().toString(),
      type,
      title: SECTION_TYPES[type].name,
      prompt: SECTION_TYPES[type].defaultPrompt,
      order: template.sections.length + 1,
      isEnabled: true
    };
    
    setEditingTemplate({
      ...template,
      sections: [...template.sections, newSection]
    });
  };

  const updateSection = (templateId: string, sectionId: string, updates: Partial<TemplateSection>) => {
    if (!editingTemplate) return;
    
    setEditingTemplate({
      ...editingTemplate,
      sections: editingTemplate.sections.map(section =>
        section.id === sectionId ? { ...section, ...updates } : section
      )
    });
  };

  const removeSection = (sectionId: string) => {
    if (!editingTemplate) return;
    
    setEditingTemplate({
      ...editingTemplate,
      sections: editingTemplate.sections.filter(section => section.id !== sectionId)
    });
  };

  const saveTemplate = async (template: MeetingTemplate) => {
    setLoading(true);
    try {
      const response = await fetch(`${config.apiUrl}/api/admin/templates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(template)
      });

      if (response.ok) {
        const existing = templates.find(t => t.id === template.id);
        if (existing) {
          setTemplates(prev => prev.map(t => t.id === template.id ? template : t));
        } else {
          setTemplates(prev => [...prev, template]);
        }
        setEditingTemplate(null);
      }
    } catch (error) {
      console.error('Failed to save template:', error);
    } finally {
      setLoading(false);
    }
  };

  const setActiveTemplate = async (templateId: string) => {
    const updatedTemplates = templates.map(t => ({
      ...t,
      isActive: t.id === templateId
    }));
    setTemplates(updatedTemplates);

    try {
      await fetch(`${config.apiUrl}/api/admin/templates/active`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ templateId })
      });
    } catch (error) {
      console.error('Failed to set active template:', error);
    }
  };

  const duplicateTemplate = (template: MeetingTemplate) => {
    const duplicate: MeetingTemplate = {
      ...template,
      id: Date.now().toString(),
      name: `${template.name} (Copy)`,
      isActive: false,
      isDefault: false
    };
    setEditingTemplate(duplicate);
  };

  const toggleExpanded = (templateId: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [templateId]: !prev[templateId]
    }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FileText className="w-8 h-8 text-purple-400" />
            Meeting Templates
          </h1>
          <p className="text-zinc-400 mt-2">
            Create and manage AI-powered meeting summary templates
          </p>
        </div>

        {/* Active Template */}
        <div className="mb-8 p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Play className="w-5 h-5 text-green-400" />
            Active Template
          </h2>
          {templates.find(t => t.isActive) ? (
            <div className="p-4 rounded-xl bg-green-500/10 border border-green-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-green-300">
                    {templates.find(t => t.isActive)?.name}
                  </div>
                  <div className="text-sm text-zinc-400 mt-1">
                    {templates.find(t => t.isActive)?.description}
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    Trigger: {templates.find(t => t.isActive)?.trigger === 'word_count' 
                      ? `Every ${templates.find(t => t.isActive)?.triggerValue} words`
                      : templates.find(t => t.isActive)?.trigger === 'time'
                      ? `Every ${templates.find(t => t.isActive)?.triggerValue} seconds`
                      : 'Manual only'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-green-400">
                    {templates.find(t => t.isActive)?.sections.filter(s => s.isEnabled).length} sections
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-zinc-500">
              No active template configured
            </div>
          )}
        </div>

        {/* Templates List */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold">All Templates</h2>
            <button
              onClick={createTemplate}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Create Template
            </button>
          </div>

          <div className="space-y-4">
            {templates.map((template) => (
              <div
                key={template.id}
                className={`rounded-2xl border transition-all ${
                  template.isActive
                    ? 'bg-green-500/5 border-green-500/30'
                    : 'bg-zinc-900/70 border-zinc-800'
                }`}
              >
                {/* Template Header */}
                <div className="p-6 border-b border-zinc-800">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold">{template.name}</h3>
                        {template.isActive && (
                          <span className="px-2 py-1 text-xs bg-green-500/20 text-green-300 rounded-full">
                            Active
                          </span>
                        )}
                        {template.isDefault && (
                          <span className="px-2 py-1 text-xs bg-blue-500/20 text-blue-300 rounded-full">
                            Default
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-zinc-400 mb-2">
                        {template.description}
                      </div>
                      <div className="text-xs text-zinc-500">
                        {template.sections.filter(s => s.isEnabled).length} active sections • 
                        Trigger: {template.trigger === 'word_count' 
                          ? ` ${template.triggerValue} words`
                          : template.trigger === 'time'
                          ? ` ${template.triggerValue}s`
                          : ' Manual'}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleExpanded(template.id)}
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                      >
                        {expandedSections[template.id] ? 
                          <ChevronDown className="w-4 h-4" /> : 
                          <ChevronRight className="w-4 h-4" />
                        }
                      </button>
                      <button
                        onClick={() => duplicateTemplate(template)}
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setEditingTemplate(template)}
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                      >
                        <Settings className="w-4 h-4" />
                      </button>
                      {!template.isActive && (
                        <button
                          onClick={() => setActiveTemplate(template.id)}
                          className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 rounded transition-colors"
                        >
                          Activate
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Template Sections (Expanded) */}
                {expandedSections[template.id] && (
                  <div className="p-6 space-y-3">
                    {template.sections
                      .sort((a, b) => a.order - b.order)
                      .map((section) => {
                        const SectionIcon = SECTION_TYPES[section.type]?.icon || Settings;
                        return (
                          <div
                            key={section.id}
                            className={`p-3 rounded-lg border ${
                              section.isEnabled 
                                ? 'bg-zinc-800/50 border-zinc-700' 
                                : 'bg-zinc-800/20 border-zinc-800 opacity-50'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <SectionIcon className="w-4 h-4 text-purple-400" />
                              <span className="font-medium">{section.title}</span>
                              {!section.isEnabled && (
                                <span className="text-xs text-zinc-500">(Disabled)</span>
                              )}
                            </div>
                            <div className="text-xs text-zinc-400 mt-1 line-clamp-2">
                              {section.prompt}
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Edit Template Modal */}
        {editingTemplate && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-zinc-900 rounded-2xl p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              <h3 className="text-xl font-semibold mb-4">
                {templates.find(t => t.id === editingTemplate.id) ? 'Edit' : 'Create'} Template
              </h3>
              
              <div className="space-y-6">
                {/* Basic Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Template Name</label>
                    <input
                      type="text"
                      value={editingTemplate.name}
                      onChange={(e) => setEditingTemplate(prev => prev ? {...prev, name: e.target.value} : null)}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Trigger</label>
                    <select
                      value={editingTemplate.trigger}
                      onChange={(e) => setEditingTemplate(prev => prev ? {...prev, trigger: e.target.value as any} : null)}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    >
                      <option value="manual">Manual Only</option>
                      <option value="word_count">Word Count</option>
                      <option value="time">Time Interval</option>
                      <option value="auto">Automatic</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Description</label>
                  <textarea
                    value={editingTemplate.description}
                    onChange={(e) => setEditingTemplate(prev => prev ? {...prev, description: e.target.value} : null)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    rows={2}
                  />
                </div>

                {(editingTemplate.trigger === 'word_count' || editingTemplate.trigger === 'time') && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {editingTemplate.trigger === 'word_count' ? 'Words Threshold' : 'Time Interval (seconds)'}
                    </label>
                    <input
                      type="number"
                      value={editingTemplate.triggerValue || 0}
                      onChange={(e) => setEditingTemplate(prev => prev ? {...prev, triggerValue: parseInt(e.target.value)} : null)}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    />
                  </div>
                )}

                {/* Sections */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="text-lg font-medium">Template Sections</h4>
                    <div className="flex gap-2">
                      {Object.entries(SECTION_TYPES).map(([key, type]) => (
                        <button
                          key={key}
                          onClick={() => addSection(editingTemplate, key as keyof typeof SECTION_TYPES)}
                          className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 rounded transition-colors"
                          title={`Add ${type.name}`}
                        >
                          <type.icon className="w-3 h-3" />
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    {editingTemplate.sections
                      .sort((a, b) => a.order - b.order)
                      .map((section) => {
                        const SectionIcon = SECTION_TYPES[section.type]?.icon || Settings;
                        return (
                          <div key={section.id} className="p-4 bg-zinc-800 rounded-lg">
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-3">
                                <SectionIcon className="w-4 h-4 text-purple-400" />
                                <input
                                  type="text"
                                  value={section.title}
                                  onChange={(e) => updateSection(editingTemplate.id, section.id, { title: e.target.value })}
                                  className="bg-transparent border-none outline-none font-medium"
                                />
                              </div>
                              <div className="flex items-center gap-2">
                                <label className="flex items-center gap-2 text-sm">
                                  <input
                                    type="checkbox"
                                    checked={section.isEnabled}
                                    onChange={(e) => updateSection(editingTemplate.id, section.id, { isEnabled: e.target.checked })}
                                    className="rounded"
                                  />
                                  Enabled
                                </label>
                                <button
                                  onClick={() => removeSection(section.id)}
                                  className="p-1 text-red-400 hover:text-red-300"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                            <textarea
                              value={section.prompt}
                              onChange={(e) => updateSection(editingTemplate.id, section.id, { prompt: e.target.value })}
                              className="w-full p-3 bg-zinc-700 border border-zinc-600 rounded focus:border-purple-500 focus:outline-none text-sm"
                              rows={3}
                              placeholder="Enter the AI prompt for this section..."
                            />
                          </div>
                        );
                      })}
                  </div>
                </div>

                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => setEditingTemplate(null)}
                    className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => saveTemplate(editingTemplate)}
                    disabled={loading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loading ? 'Saving...' : 'Save Template'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}