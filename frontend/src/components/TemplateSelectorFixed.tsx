import React, { useState, useEffect } from 'react';
import {
  ChevronDown, ChevronUp, Check, Plus, Edit3, Trash2,
  FileText, ListChecks, Clipboard, BarChart3, Flag,
  Presentation, Calendar, Users, Settings,
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

export const TemplateSelectorFixed: React.FC<TemplateSelectorProps> = ({
  selectedTemplates,
  onTemplateToggle,
  onTemplateUpdate,
  availableTemplates,
  className = ''
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateConfig[]>(availableTemplates);

  // Update templates when availableTemplates change
  useEffect(() => {
    setTemplates(availableTemplates);
  }, [availableTemplates]);

  const selectedCount = selectedTemplates.length;

  return (
    <div className={`relative ${className}`}>
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
                  onClick={() => {
                    // Simple create logic - just close for now
                    console.log('Create template clicked');
                  }}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  Custom
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {selectedCount} selected
              </p>
            </div>

            <div className="max-h-64 overflow-y-auto">
              {templates.map(template => {
                const IconComponent = template.icon;
                const isSelected = selectedTemplates.includes(template.id);
                
                return (
                  <div
                    key={template.id}
                    className="flex items-center justify-between p-3 hover:bg-gray-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1">
                      <div className={`w-8 h-8 rounded-lg bg-${template.color}-500/20 flex items-center justify-center`}>
                        {IconComponent && <IconComponent className={`w-4 h-4 text-${template.color}-400`} />}
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
                      </div>
                    </div>

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