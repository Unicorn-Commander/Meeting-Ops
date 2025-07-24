import React, { useState, useEffect } from 'react';
import { FileText, Clock, Users, Target, ChevronRight, CheckCircle } from 'lucide-react';

interface MeetingTemplate {
  id: string;
  name: string;
  description: string;
  typical_duration: string;
  sections: string[];
  focus_areas: string[];
  icon?: string;
}

interface MeetingTemplateSelectorProps {
  onTemplateSelect: (templateId: string) => void;
  selectedTemplate?: string;
  compact?: boolean;
}

export const MeetingTemplateSelector: React.FC<MeetingTemplateSelectorProps> = ({
  onTemplateSelect,
  selectedTemplate,
  compact = false
}) => {
  const [templates, setTemplates] = useState<MeetingTemplate[]>([]);
  const [expandedTemplate, setExpandedTemplate] = useState<string | null>(null);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/templates', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setTemplates(data.templates || []);
      }
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const getTemplateIcon = (templateId: string) => {
    const icons: { [key: string]: React.ReactElement } = {
      standup: <Users className="h-5 w-5" />,
      retrospective: <Target className="h-5 w-5" />,
      planning: <FileText className="h-5 w-5" />,
      one_on_one: <Users className="h-5 w-5" />,
      brainstorming: <Target className="h-5 w-5" />,
      all_hands: <Users className="h-5 w-5" />,
      client: <Users className="h-5 w-5" />,
      design_review: <FileText className="h-5 w-5" />,
      interview: <Users className="h-5 w-5" />,
      board: <Target className="h-5 w-5" />
    };
    return icons[templateId] || <FileText className="h-5 w-5" />;
  };

  const getTemplateColor = (templateId: string) => {
    const colors: { [key: string]: string } = {
      standup: 'bg-blue-100 text-blue-700 border-blue-200',
      retrospective: 'bg-purple-100 text-purple-700 border-purple-200',
      planning: 'bg-green-100 text-green-700 border-green-200',
      one_on_one: 'bg-yellow-100 text-yellow-700 border-yellow-200',
      brainstorming: 'bg-pink-100 text-pink-700 border-pink-200',
      all_hands: 'bg-indigo-100 text-indigo-700 border-indigo-200',
      client: 'bg-orange-100 text-orange-700 border-orange-200',
      design_review: 'bg-teal-100 text-teal-700 border-teal-200',
      interview: 'bg-red-100 text-red-700 border-red-200',
      board: 'bg-gray-100 text-gray-700 border-gray-200'
    };
    return colors[templateId] || 'bg-gray-100 text-gray-700 border-gray-200';
  };

  if (compact) {
    return (
      <div className="relative">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Meeting Template
        </label>
        <select
          value={selectedTemplate || ''}
          onChange={(e) => onTemplateSelect(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">No template (General meeting)</option>
          {templates.map(template => (
            <option key={template.id} value={template.id}>
              {template.name} - {template.typical_duration}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <FileText className="h-5 w-5" />
        Select Meeting Template
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {templates.map(template => {
          const isSelected = selectedTemplate === template.id;
          const isExpanded = expandedTemplate === template.id;
          
          return (
            <div
              key={template.id}
              className={`
                rounded-lg border-2 transition-all cursor-pointer
                ${isSelected 
                  ? 'border-blue-500 shadow-lg' 
                  : 'border-gray-200 hover:border-gray-300 hover:shadow-md'
                }
              `}
              onClick={() => onTemplateSelect(template.id)}
            >
              <div className={`p-4 rounded-t-lg ${getTemplateColor(template.id)}`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {getTemplateIcon(template.id)}
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium flex items-center gap-2">
                        {template.name}
                        {isSelected && <CheckCircle className="h-4 w-4" />}
                      </h4>
                      <p className="text-sm mt-1 opacity-90">{template.description}</p>
                      <div className="flex items-center gap-2 mt-2 text-xs opacity-75">
                        <Clock className="h-3 w-3" />
                        <span>{template.typical_duration}</span>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedTemplate(isExpanded ? null : template.id);
                    }}
                    className="p-1 hover:bg-white/20 rounded transition-transform"
                    style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="p-4 bg-white border-t">
                  <div className="space-y-3 text-sm">
                    <div>
                      <h5 className="font-medium text-gray-700 mb-1">Sections:</h5>
                      <ul className="list-disc list-inside text-gray-600 space-y-1">
                        {template.sections.map((section, idx) => (
                          <li key={idx}>{section}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h5 className="font-medium text-gray-700 mb-1">Focus Areas:</h5>
                      <div className="flex flex-wrap gap-2">
                        {template.focus_areas.map((area, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs"
                          >
                            {area}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* No Template Option */}
        <div
          className={`
            rounded-lg border-2 transition-all cursor-pointer
            ${!selectedTemplate 
              ? 'border-blue-500 shadow-lg' 
              : 'border-gray-200 hover:border-gray-300 hover:shadow-md'
            }
          `}
          onClick={() => onTemplateSelect('')}
        >
          <div className="p-4 rounded-t-lg bg-gray-100 text-gray-700 border-gray-200">
            <div className="flex items-start gap-3">
              <FileText className="h-5 w-5 mt-0.5" />
              <div className="flex-1">
                <h4 className="font-medium flex items-center gap-2">
                  General Meeting
                  {!selectedTemplate && <CheckCircle className="h-4 w-4" />}
                </h4>
                <p className="text-sm mt-1 opacity-90">
                  No specific template - flexible format for any meeting type
                </p>
                <div className="flex items-center gap-2 mt-2 text-xs opacity-75">
                  <Clock className="h-3 w-3" />
                  <span>Any duration</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};