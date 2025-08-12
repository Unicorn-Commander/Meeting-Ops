import React from 'react';

export interface TemplateConfig {
  id: string;
  name: string;
  icon: React.ElementType;
  description: string;
  color: string;
  auto: boolean;
  keywords: string[];
  custom?: boolean;
  fields?: any[];
}

interface TemplateSelectorProps {
  selectedTemplates: string[];
  onTemplateToggle: (templateId: string) => void;
  onTemplateUpdate: (templates: TemplateConfig[]) => void;
  availableTemplates: TemplateConfig[];
  className?: string;
}

export const TemplateSelectorSimple: React.FC<TemplateSelectorProps> = ({
  selectedTemplates,
  onTemplateToggle,
  availableTemplates,
  className = ''
}) => {
  return (
    <div className={`bg-gray-800 rounded-lg p-4 ${className}`}>
      <h4 className="text-white mb-3">Template Selection (Simple)</h4>
      <div className="space-y-2">
        {availableTemplates.map(template => (
          <button
            key={template.id}
            onClick={() => onTemplateToggle(template.id)}
            className={`block w-full text-left px-3 py-2 rounded transition-colors ${
              selectedTemplates.includes(template.id)
                ? 'bg-purple-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {template.name}
          </button>
        ))}
      </div>
    </div>
  );
};