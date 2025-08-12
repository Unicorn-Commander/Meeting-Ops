import React, { useState, useEffect } from 'react';
import {
  ChevronDown, ChevronUp, Check, Plus, Edit3, Trash2,
  FileText, ListChecks, Clipboard, BarChart3, Flag,
  Presentation, Calendar, Users, Globe, Settings,
  Eye, EyeOff, Save, X
} from 'lucide-react';

export interface TemplateConfig {
  id: string;
  name: string;
  icon: React.ElementType;
  description: string;
  color: string;
  auto: boolean;
  keywords: string[];
  custom?: boolean;
  fields?: TemplateField[];
}

export interface TemplateField {
  id: string;
  name: string;
  type: 'text' | 'list' | 'number' | 'date' | 'boolean';
  required: boolean;
  placeholder?: string;
}

interface TemplateSelectorProps {
  selectedTemplates: string[];
  onTemplateToggle: (templateId: string) => void;
  onTemplateUpdate: (templates: TemplateConfig[]) => void;
  availableTemplates: TemplateConfig[];
  className?: string;
}

export const TemplateSelector: React.FC<TemplateSelectorProps> = ({
  selectedTemplates,
  onTemplateToggle,
  onTemplateUpdate,
  availableTemplates,
  className = ''
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateConfig[]>(availableTemplates);
  const [isCreating, setIsCreating] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<TemplateConfig | null>(null);

  // Default template icons
  const defaultIcons = {
    FileText, ListChecks, Clipboard, BarChart3, Flag,
    Presentation, Calendar, Users, Globe, Settings
  };

  // Update templates when availableTemplates change
  useEffect(() => {
    setTemplates(availableTemplates);
  }, [availableTemplates]);

  const handleTemplateCreate = () => {
    const newTemplate: TemplateConfig = {
      id: `custom_${Date.now()}`,
      name: 'New Template',
      icon: FileText,
      description: 'Custom template',
      color: 'blue',
      auto: false,
      keywords: [],
      custom: true,
      fields: []
    };
    setEditingTemplate(newTemplate);
    setIsCreating(true);
  };

  const handleTemplateSave = () => {
    if (!editingTemplate) return;

    const updatedTemplates = isCreating
      ? [...templates, editingTemplate]
      : templates.map(t => t.id === editingTemplate.id ? editingTemplate : t);

    setTemplates(updatedTemplates);
    onTemplateUpdate(updatedTemplates);
    setEditingTemplate(null);
    setIsCreating(false);
  };

  const handleTemplateDelete = (templateId: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return;

    const updatedTemplates = templates.filter(t => t.id !== templateId);
    setTemplates(updatedTemplates);
    onTemplateUpdate(updatedTemplates);
  };

  const addTemplateField = () => {
    if (!editingTemplate) return;

    const newField: TemplateField = {
      id: `field_${Date.now()}`,
      name: 'New Field',
      type: 'text',
      required: false,
      placeholder: 'Enter value...'
    };

    setEditingTemplate({
      ...editingTemplate,
      fields: [...(editingTemplate.fields || []), newField]
    });
  };

  const updateTemplateField = (fieldId: string, updates: Partial<TemplateField>) => {
    if (!editingTemplate) return;

    setEditingTemplate({
      ...editingTemplate,
      fields: editingTemplate.fields?.map(f =>
        f.id === fieldId ? { ...f, ...updates } : f
      ) || []
    });
  };

  const removeTemplateField = (fieldId: string) => {
    if (!editingTemplate) return;

    setEditingTemplate({
      ...editingTemplate,
      fields: editingTemplate.fields?.filter(f => f.id !== fieldId) || []
    });
  };

  const selectedCount = selectedTemplates.length;
  const autoSelectedCount = templates.filter(t => t.auto && selectedTemplates.includes(t.id)).length;

  return (
    <div className={`relative ${className}`}>
      {/* Template Editor Modal */}
      {editingTemplate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-700">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white">
                  {isCreating ? 'Create Template' : 'Edit Template'}
                </h3>
                <button
                  onClick={() => {
                    setEditingTemplate(null);
                    setIsCreating(false);
                  }}
                  className="p-2 hover:bg-gray-800 rounded transition-colors text-gray-400"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Template Name
                  </label>
                  <input
                    type="text"
                    value={editingTemplate.name}
                    onChange={(e) => setEditingTemplate({
                      ...editingTemplate,
                      name: e.target.value
                    })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                    placeholder="Enter template name..."
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Color
                  </label>
                  <select
                    value={editingTemplate.color}
                    onChange={(e) => setEditingTemplate({
                      ...editingTemplate,
                      color: e.target.value
                    })}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="blue">Blue</option>
                    <option value="green">Green</option>
                    <option value="purple">Purple</option>
                    <option value="orange">Orange</option>
                    <option value="red">Red</option>
                    <option value="indigo">Indigo</option>
                    <option value="yellow">Yellow</option>
                    <option value="pink">Pink</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description
                </label>
                <input
                  type="text"
                  value={editingTemplate.description}
                  onChange={(e) => setEditingTemplate({
                    ...editingTemplate,
                    description: e.target.value
                  })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                  placeholder="Describe what this template captures..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Auto-detection Keywords
                </label>
                <input
                  type="text"
                  value={editingTemplate.keywords.join(', ')}
                  onChange={(e) => setEditingTemplate({
                    ...editingTemplate,
                    keywords: e.target.value.split(',').map(k => k.trim()).filter(Boolean)
                  })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                  placeholder="keyword1, keyword2, keyword3..."
                />
                <p className="text-xs text-gray-500 mt-1">
                  Keywords that trigger automatic template selection
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="auto-detection"
                  checked={editingTemplate.auto}
                  onChange={(e) => setEditingTemplate({
                    ...editingTemplate,
                    auto: e.target.checked
                  })}
                  className="rounded border-gray-600 bg-gray-800 text-purple-500 focus:ring-purple-500"
                />
                <label htmlFor="auto-detection" className="text-sm text-gray-300">
                  Enable auto-detection
                </label>
              </div>

              {/* Template Fields */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="text-sm font-medium text-gray-300">
                    Custom Fields
                  </label>
                  <button
                    onClick={addTemplateField}
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    Add Field
                  </button>
                </div>

                <div className="space-y-3">
                  {editingTemplate.fields?.map(field => (
                    <div key={field.id} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                      <div className="grid grid-cols-3 gap-3">
                        <input
                          type="text"
                          value={field.name}
                          onChange={(e) => updateTemplateField(field.id, { name: e.target.value })}
                          placeholder="Field name"
                          className="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-purple-500"
                        />
                        <select
                          value={field.type}
                          onChange={(e) => updateTemplateField(field.id, { type: e.target.value as any })}
                          className="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-purple-500"
                        >
                          <option value="text">Text</option>
                          <option value="list">List</option>
                          <option value="number">Number</option>
                          <option value="date">Date</option>
                          <option value="boolean">Boolean</option>
                        </select>
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-1 text-xs text-gray-400">
                            <input
                              type="checkbox"
                              checked={field.required}
                              onChange={(e) => updateTemplateField(field.id, { required: e.target.checked })}
                              className="rounded border-gray-600 bg-gray-700"
                            />
                            Required
                          </label>
                          <button
                            onClick={() => removeTemplateField(field.id)}
                            className="p-1 text-red-400 hover:text-red-300"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                      <input
                        type="text"
                        value={field.placeholder || ''}
                        onChange={(e) => updateTemplateField(field.id, { placeholder: e.target.value })}
                        placeholder="Field placeholder text"
                        className="mt-2 w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-purple-500"
                      />
                    </div>
                  ))}
                  
                  {(!editingTemplate.fields || editingTemplate.fields.length === 0) && (
                    <div className="text-center py-4 text-gray-500 text-sm">
                      No custom fields added yet. Click "Add Field" to get started.
                    </div>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-700">
                <button
                  onClick={() => {
                    setEditingTemplate(null);
                    setIsCreating(false);
                  }}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleTemplateSave}
                  className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                >
                  <Save className="w-4 h-4" />
                  {isCreating ? 'Create' : 'Update'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dropdown Button */}
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center justify-between gap-3 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors border border-gray-700 min-w-[200px]"
        >
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            <span className="text-sm">
              Templates ({selectedCount})
            </span>
          </div>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {/* Dropdown Content */}
        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-2 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
            <div className="p-3 border-b border-gray-700">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-300">
                  Select Templates
                </span>
                <button
                  onClick={handleTemplateCreate}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  Custom
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {autoSelectedCount} auto-selected
              </p>
            </div>

            <div className="max-h-64 overflow-y-auto">
              {templates.map(template => {
                const Icon = template.icon;
                const isSelected = selectedTemplates.includes(template.id);
                
                return (
                  <div
                    key={template.id}
                    className="flex items-center justify-between p-3 hover:bg-gray-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1">
                      <div
                        className={`w-8 h-8 rounded-lg bg-${template.color}-500/20 flex items-center justify-center`}
                      >
                        <Icon className={`w-4 h-4 text-${template.color}-400`} />
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">
                            {template.name}
                          </span>
                          {template.auto && (
                            <Eye className="w-3 h-3 text-green-400" />
                          )}
                          {template.custom && (
                            <span className="px-1 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded">
                              Custom
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-400">{template.description}</p>
                        {template.keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {template.keywords.slice(0, 3).map(keyword => (
                              <span key={keyword} className="px-1 py-0.5 bg-gray-700 text-gray-300 text-xs rounded">
                                {keyword}
                              </span>
                            ))}
                            {template.keywords.length > 3 && (
                              <span className="text-xs text-gray-500">+{template.keywords.length - 3}</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {template.custom && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingTemplate(template);
                            }}
                            className="p-1 hover:bg-gray-700 rounded transition-colors text-gray-400"
                          >
                            <Edit3 className="w-3 h-3" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleTemplateDelete(template.id);
                            }}
                            className="p-1 hover:bg-gray-700 rounded transition-colors text-red-400"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </>
                      )}
                      
                      <button
                        onClick={() => onTemplateToggle(template.id)}
                        className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                          isSelected
                            ? `border-${template.color}-500 bg-${template.color}-500`
                            : 'border-gray-600 hover:border-gray-500'
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="p-3 border-t border-gray-700 text-center">
              <button
                onClick={() => setIsOpen(false)}
                className="text-xs text-gray-400 hover:text-gray-300"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};