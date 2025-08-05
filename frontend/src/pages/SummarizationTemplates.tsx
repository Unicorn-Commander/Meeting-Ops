import React, { useState, useEffect } from 'react';
import { 
  FileText, Plus, Edit2, Trash2, Copy, Save, X, 
  Briefcase, Users, Calendar, Code, Heart, School,
  DollarSign, Mic, Brain, Zap, Settings, ChevronRight
} from 'lucide-react';

interface SummarizationTemplate {
  id: string;
  name: string;
  category: string;
  description: string;
  icon: string;
  prompt: string;
  outputFormat: string;
  extractFields: string[];
  maxLength: number;
  temperature: number;
  model: 'whisper-large-v3' | 'llama3' | 'gemma2' | 'gpt-4' | 'claude-3';
  isDefault: boolean;
  usageCount: number;
  lastUsed: string | null;
}

const DEFAULT_TEMPLATES: SummarizationTemplate[] = [
  {
    id: 'business-meeting',
    name: 'Business Meeting',
    category: 'Business',
    description: 'Standard business meeting with action items and decisions',
    icon: 'Briefcase',
    prompt: `Analyze this business meeting transcript and provide:
1. Meeting Overview (2-3 sentences)
2. Key Discussion Points (bullet list)
3. Decisions Made (numbered list)
4. Action Items with Owners and Deadlines
5. Next Steps
6. Risks or Concerns Raised

Format the output professionally with clear sections.`,
    outputFormat: 'markdown',
    extractFields: ['action_items', 'decisions', 'attendees', 'next_meeting'],
    maxLength: 1500,
    temperature: 0.3,
    model: 'llama3',
    isDefault: true,
    usageCount: 0,
    lastUsed: null
  },
  {
    id: 'sales-call',
    name: 'Sales Call',
    category: 'Sales',
    description: 'Sales calls with customer needs and follow-ups',
    icon: 'DollarSign',
    prompt: `Analyze this sales call transcript and extract:
1. Customer Information (name, company, role)
2. Pain Points and Challenges
3. Product/Service Interest Level (1-10)
4. Budget Discussion
5. Decision Timeline
6. Competitors Mentioned
7. Follow-up Actions Required
8. Probability of Close (percentage)

Include specific quotes that indicate buying signals or objections.`,
    outputFormat: 'json',
    extractFields: ['customer_info', 'pain_points', 'budget', 'timeline', 'next_steps'],
    maxLength: 2000,
    temperature: 0.2,
    model: 'llama3',
    isDefault: false,
    usageCount: 0,
    lastUsed: null
  },
  {
    id: 'medical-consultation',
    name: 'Medical Consultation',
    category: 'Healthcare',
    description: 'Patient consultations with symptoms and treatment plans',
    icon: 'Heart',
    prompt: `Summarize this medical consultation:
1. Chief Complaint
2. History of Present Illness
3. Symptoms Discussed
4. Physical Examination Findings
5. Assessment/Diagnosis
6. Treatment Plan
7. Medications Prescribed
8. Follow-up Instructions
9. Patient Questions and Concerns

Maintain HIPAA compliance and use medical terminology appropriately.`,
    outputFormat: 'structured',
    extractFields: ['diagnosis', 'medications', 'follow_up', 'symptoms'],
    maxLength: 2500,
    temperature: 0.1,
    model: 'claude-3',
    isDefault: false,
    usageCount: 0,
    lastUsed: null
  },
  {
    id: 'team-standup',
    name: 'Daily Standup',
    category: 'Agile',
    description: 'Daily team standup with progress and blockers',
    icon: 'Users',
    prompt: `Extract from this standup meeting:
For each participant:
- What they completed yesterday
- What they're working on today
- Any blockers or dependencies

Also note:
- Team velocity/progress
- Cross-team dependencies
- Risks to sprint goals`,
    outputFormat: 'bullet_list',
    extractFields: ['completed', 'in_progress', 'blockers', 'dependencies'],
    maxLength: 1000,
    temperature: 0.3,
    model: 'gemma2',
    isDefault: false,
    usageCount: 0,
    lastUsed: null
  },
  {
    id: 'interview',
    name: 'Job Interview',
    category: 'HR',
    description: 'Candidate interviews with skills assessment',
    icon: 'Mic',
    prompt: `Evaluate this job interview:
1. Candidate Overview
2. Technical Skills Demonstrated
3. Soft Skills Observed
4. Experience Relevance (1-10)
5. Cultural Fit Assessment
6. Strengths
7. Areas of Concern
8. Questions Asked by Candidate
9. Recommended Next Steps
10. Overall Rating (1-10)

Provide specific examples from the conversation.`,
    outputFormat: 'structured',
    extractFields: ['skills', 'experience', 'culture_fit', 'recommendation'],
    maxLength: 2000,
    temperature: 0.4,
    model: 'gpt-4',
    isDefault: false,
    usageCount: 0,
    lastUsed: null
  },
  {
    id: 'lecture',
    name: 'Academic Lecture',
    category: 'Education',
    description: 'Educational lectures with key concepts and examples',
    icon: 'School',
    prompt: `Summarize this lecture:
1. Main Topic and Learning Objectives
2. Key Concepts Explained (with definitions)
3. Examples and Case Studies
4. Important Formulas or Theories
5. Student Questions and Answers
6. Homework or Assignments Given
7. Recommended Reading
8. Key Takeaways (bullet points)`,
    outputFormat: 'markdown',
    extractFields: ['concepts', 'examples', 'assignments', 'questions'],
    maxLength: 3000,
    temperature: 0.3,
    model: 'claude-3',
    isDefault: false,
    usageCount: 0,
    lastUsed: null
  }
];

export const SummarizationTemplates: React.FC = () => {
  const [templates, setTemplates] = useState<SummarizationTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<SummarizationTemplate | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<Partial<SummarizationTemplate>>({});
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await fetch('/api/summarization-templates', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setTemplates(data.length > 0 ? data : DEFAULT_TEMPLATES);
      } else {
        // Use default templates if API fails
        setTemplates(DEFAULT_TEMPLATES);
      }
    } catch (error) {
      console.error('Failed to load templates:', error);
      setTemplates(DEFAULT_TEMPLATES);
    }
  };

  const saveTemplate = async () => {
    try {
      const endpoint = isCreating 
        ? '/api/summarization-templates'
        : `/api/summarization-templates/${editingTemplate.id}`;
      
      const method = isCreating ? 'POST' : 'PUT';
      
      const response = await fetch(endpoint, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(editingTemplate)
      });

      if (response.ok) {
        await loadTemplates();
        setIsEditing(false);
        setIsCreating(false);
        setEditingTemplate({});
      }
    } catch (error) {
      console.error('Failed to save template:', error);
    }
  };

  const deleteTemplate = async (id: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return;

    try {
      await fetch(`/api/summarization-templates/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      await loadTemplates();
    } catch (error) {
      console.error('Failed to delete template:', error);
    }
  };

  const duplicateTemplate = (template: SummarizationTemplate) => {
    setEditingTemplate({
      ...template,
      id: undefined,
      name: `${template.name} (Copy)`,
      isDefault: false
    });
    setIsCreating(true);
    setIsEditing(true);
  };

  const getIconComponent = (iconName: string) => {
    const icons: { [key: string]: any } = {
      Briefcase, Users, Calendar, Code, Heart, School, DollarSign, Mic, Brain
    };
    const Icon = icons[iconName] || FileText;
    return <Icon className="w-5 h-5" />;
  };

  const categories = ['all', ...Array.from(new Set(templates.map(t => t.category)))];
  const filteredTemplates = selectedCategory === 'all' 
    ? templates 
    : templates.filter(t => t.category === selectedCategory);

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-white">Summarization Templates</h1>
            <button
              onClick={() => {
                setEditingTemplate({
                  name: '',
                  category: 'Custom',
                  description: '',
                  prompt: '',
                  outputFormat: 'markdown',
                  extractFields: [],
                  maxLength: 1500,
                  temperature: 0.3,
                  model: 'llama3'
                });
                setIsCreating(true);
                setIsEditing(true);
              }}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2"
            >
              <Plus className="w-5 h-5" />
              New Template
            </button>
          </div>

          {/* Category Filter */}
          <div className="flex gap-2">
            {categories.map(category => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg capitalize ${
                  selectedCategory === category
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {category}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Templates List */}
          <div className="space-y-4">
            {filteredTemplates.map(template => (
              <div
                key={template.id}
                onClick={() => setSelectedTemplate(template)}
                className={`bg-gray-800 rounded-lg p-4 cursor-pointer transition-all ${
                  selectedTemplate?.id === template.id ? 'ring-2 ring-purple-500' : 'hover:bg-gray-750'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-gray-700 rounded-lg">
                      {getIconComponent(template.icon)}
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        {template.name}
                        {template.isDefault && (
                          <span className="px-2 py-1 bg-blue-900/50 text-blue-400 text-xs rounded-full">
                            Default
                          </span>
                        )}
                      </h3>
                      <p className="text-sm text-gray-400">{template.category}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        duplicateTemplate(template);
                      }}
                      className="p-1 hover:bg-gray-700 rounded"
                    >
                      <Copy className="w-4 h-4 text-gray-400" />
                    </button>
                    {!template.isDefault && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTemplate(template);
                            setIsEditing(true);
                            setIsCreating(false);
                          }}
                          className="p-1 hover:bg-gray-700 rounded"
                        >
                          <Edit2 className="w-4 h-4 text-gray-400" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteTemplate(template.id);
                          }}
                          className="p-1 hover:bg-gray-700 rounded"
                        >
                          <Trash2 className="w-4 h-4 text-red-400" />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <p className="text-sm text-gray-300 mb-3">{template.description}</p>

                <div className="flex items-center gap-4 text-xs text-gray-400">
                  <span className="flex items-center gap-1">
                    <Brain className="w-3 h-3" />
                    {template.model}
                  </span>
                  <span>Max {template.maxLength} words</span>
                  {template.usageCount > 0 && (
                    <span>Used {template.usageCount} times</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Template Details/Editor */}
          <div className="bg-gray-800 rounded-lg p-6">
            {isEditing ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-semibold text-white">
                    {isCreating ? 'Create Template' : 'Edit Template'}
                  </h2>
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setIsCreating(false);
                      setEditingTemplate({});
                    }}
                    className="p-2 hover:bg-gray-700 rounded-lg"
                  >
                    <X className="w-5 h-5 text-gray-400" />
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
                  <input
                    type="text"
                    value={editingTemplate.name || ''}
                    onChange={(e) => setEditingTemplate({ ...editingTemplate, name: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Category</label>
                  <input
                    type="text"
                    value={editingTemplate.category || ''}
                    onChange={(e) => setEditingTemplate({ ...editingTemplate, category: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
                  <input
                    type="text"
                    value={editingTemplate.description || ''}
                    onChange={(e) => setEditingTemplate({ ...editingTemplate, description: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Prompt</label>
                  <textarea
                    value={editingTemplate.prompt || ''}
                    onChange={(e) => setEditingTemplate({ ...editingTemplate, prompt: e.target.value })}
                    rows={8}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white font-mono text-sm"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Model</label>
                    <select
                      value={editingTemplate.model || 'llama3'}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, model: e.target.value as any })}
                      className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                    >
                      <option value="whisper-large-v3">Whisper Large v3 (NPU)</option>
                      <option value="llama3">LLaMA 3 (Local)</option>
                      <option value="gemma2">Gemma 2 (Local)</option>
                      <option value="gpt-4">GPT-4 (API)</option>
                      <option value="claude-3">Claude 3 (API)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Output Format</label>
                    <select
                      value={editingTemplate.outputFormat || 'markdown'}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, outputFormat: e.target.value })}
                      className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                    >
                      <option value="markdown">Markdown</option>
                      <option value="json">JSON</option>
                      <option value="structured">Structured</option>
                      <option value="bullet_list">Bullet List</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Max Length</label>
                    <input
                      type="number"
                      value={editingTemplate.maxLength || 1500}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, maxLength: parseInt(e.target.value) })}
                      className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Temperature</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="1"
                      value={editingTemplate.temperature || 0.3}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, temperature: parseFloat(e.target.value) })}
                      className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                    />
                  </div>
                </div>

                <button
                  onClick={saveTemplate}
                  className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center justify-center gap-2"
                >
                  <Save className="w-5 h-5" />
                  Save Template
                </button>
              </div>
            ) : selectedTemplate ? (
              <div>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-2xl font-semibold text-white mb-2">{selectedTemplate.name}</h2>
                    <p className="text-gray-400">{selectedTemplate.description}</p>
                  </div>
                  <div className="p-3 bg-gray-700 rounded-lg">
                    {getIconComponent(selectedTemplate.icon)}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="p-4 bg-gray-700 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-300 mb-2">Prompt Template</h3>
                    <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono">
                      {selectedTemplate.prompt}
                    </pre>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-3 bg-gray-700 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">AI Model</div>
                      <div className="text-white flex items-center gap-2">
                        <Brain className="w-4 h-4 text-purple-400" />
                        {selectedTemplate.model}
                        {selectedTemplate.model === 'whisper-large-v3' && (
                          <span className="px-2 py-1 bg-green-900/50 text-green-400 text-xs rounded-full flex items-center gap-1">
                            <Zap className="w-3 h-3" />
                            NPU
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="p-3 bg-gray-700 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">Output Format</div>
                      <div className="text-white">{selectedTemplate.outputFormat}</div>
                    </div>

                    <div className="p-3 bg-gray-700 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">Max Length</div>
                      <div className="text-white">{selectedTemplate.maxLength} words</div>
                    </div>

                    <div className="p-3 bg-gray-700 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">Temperature</div>
                      <div className="text-white">{selectedTemplate.temperature}</div>
                    </div>
                  </div>

                  {selectedTemplate.extractFields.length > 0 && (
                    <div className="p-4 bg-gray-700 rounded-lg">
                      <h3 className="text-sm font-medium text-gray-300 mb-2">Extracted Fields</h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedTemplate.extractFields.map(field => (
                          <span key={field} className="px-3 py-1 bg-gray-600 text-gray-200 text-sm rounded-full">
                            {field}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {selectedTemplate.usageCount > 0 && (
                    <div className="flex items-center justify-between text-sm text-gray-400">
                      <span>Used {selectedTemplate.usageCount} times</span>
                      {selectedTemplate.lastUsed && (
                        <span>Last used: {new Date(selectedTemplate.lastUsed).toLocaleDateString()}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <FileText className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400">Select a template to view details</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};