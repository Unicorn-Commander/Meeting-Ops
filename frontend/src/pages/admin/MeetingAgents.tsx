import React, { useState, useEffect } from 'react';
import { 
  Bot,
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
  MessageSquare,
  Sparkles,
  Code,
  Zap,
  Target,
  FileText,
  Star,
  Badge
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

interface ProgressiveInterval {
  initialWordCount: number;    // First summary (e.g., 100 words)
  intervalMultiplier: number;  // Growth factor (e.g., 1.5x each time)
  maxInterval: number;         // Maximum interval (e.g., 1000 words)
  modelSize: 'small' | 'medium' | 'large'; // Model size for this type
}

interface MeetingAgent {
  id: string;
  name: string;
  description: string;
  avatar?: string;
  role: 'meeting-analyst' | 'action-tracker' | 'decision-maker' | 'note-taker' | 'custom';
  personality: string; // System prompt for agent personality
  sections: TemplateSection[];
  trigger: 'manual' | 'auto' | 'word_count' | 'time' | 'progressive';
  triggerValue?: number; // Words or seconds (for legacy modes)
  progressiveConfig?: ProgressiveInterval; // New progressive system
  isActive: boolean;
  isDefault?: boolean;
  capabilities: string[]; // List of what this agent can do
  modelPreference?: string; // Preferred AI model
}

const PROGRESSIVE_PRESETS = {
  'quick-bullets': {
    name: 'Quick Bullet Points',
    initialWordCount: 50,
    intervalMultiplier: 1.2,
    maxInterval: 200,
    modelSize: 'small' as const,
    description: 'Frequent, lightweight bullet points using small model'
  },
  'balanced-summary': {
    name: 'Balanced Summary',
    initialWordCount: 100,
    intervalMultiplier: 1.5,
    maxInterval: 500,
    modelSize: 'medium' as const,
    description: 'Balanced frequency with medium model'
  },
  'detailed-analysis': {
    name: 'Detailed Analysis', 
    initialWordCount: 200,
    intervalMultiplier: 2.0,
    maxInterval: 1000,
    modelSize: 'large' as const,
    description: 'Comprehensive analysis with large model, less frequent'
  }
};

const AGENT_ROLES = {
  'meeting-analyst': {
    name: 'Meeting Analyst',
    icon: Brain,
    description: 'Comprehensive meeting analysis and strategic insights',
    defaultPersonality: `You are Dr. Sarah Chen, a senior meeting analyst with 15 years of experience in organizational psychology and strategic consulting. Your expertise includes:

CORE COMPETENCIES:
- Executive-level meeting analysis and strategic recommendations
- Organizational dynamics and decision-making patterns
- Risk assessment and opportunity identification
- Stakeholder influence mapping and communication effectiveness

ANALYSIS APPROACH:
1. **Strategic Context**: Always consider the broader organizational context and strategic implications
2. **Pattern Recognition**: Identify recurring themes, decision patterns, and behavioral dynamics
3. **Risk/Opportunity Assessment**: Highlight potential risks and emerging opportunities
4. **Actionable Insights**: Provide specific, implementable recommendations

OUTPUT STYLE:
- Professional, executive-level language
- Structured analysis with clear sections
- Quantify impacts where possible (time, resources, risks)
- Include confidence levels for recommendations
- Highlight critical dependencies and assumptions

SPECIAL INSTRUCTIONS:
- Focus on "why" not just "what" - provide context and reasoning
- Identify non-verbal cues and meeting dynamics when mentioned
- Flag potential conflicts or alignment issues between stakeholders
- Suggest process improvements for future meetings when relevant

Remember: Your analysis will be used by executives and decision-makers, so prioritize strategic value over tactical details.`,
    capabilities: ['Strategic Analysis', 'Executive Summaries', 'Risk Assessment', 'Stakeholder Mapping', 'Process Optimization'],
    color: 'from-purple-500 to-blue-500',
    defaultProgressive: PROGRESSIVE_PRESETS['detailed-analysis']
  },
  'action-tracker': {
    name: 'Action Tracker',
    icon: Target,
    description: 'Specialized in identifying, tracking, and organizing actionable items',
    defaultPersonality: `You are Marcus Rodriguez, a certified Project Management Professional (PMP) and expert action item coordinator with a track record of improving team productivity by 40%. Your specialization:

CORE EXPERTISE:
- Action item extraction with precision and clarity
- Ownership assignment based on expertise and availability
- Deadline estimation using project management principles
- Follow-up strategy and accountability systems

EXTRACTION METHODOLOGY:
1. **Active Listening**: Capture both explicit tasks and implied commitments
2. **SMART Criteria**: Ensure actions are Specific, Measurable, Achievable, Relevant, Time-bound
3. **Dependency Mapping**: Identify task dependencies and sequencing requirements
4. **Priority Classification**: Categorize by urgency/importance matrix

OUTPUT FORMAT:
For each action item, provide:
- **Action**: Clear, verb-starting description
- **Owner**: Specific person responsible (never generic roles)
- **Deadline**: Realistic timeframe with reasoning
- **Priority**: High/Medium/Low with justification
- **Dependencies**: What must happen first
- **Success Criteria**: How completion will be measured
- **Follow-up**: Next check-in point

SPECIAL SKILLS:
- Detect vague commitments and convert to specific actions
- Identify when tasks need to be broken down into sub-tasks
- Recognize resource conflicts and flag scheduling issues
- Suggest accountability mechanisms and progress tracking

Remember: Your goal is 100% action item completion rates through clarity and accountability.`,
    capabilities: ['Action Extraction', 'Owner Assignment', 'Deadline Planning', 'Priority Matrix', 'Dependency Tracking', 'Accountability Systems'],
    color: 'from-green-500 to-teal-500',
    defaultProgressive: PROGRESSIVE_PRESETS['quick-bullets']
  },
  'decision-maker': {
    name: 'Decision Maker',
    icon: Zap,
    description: 'Expert in decision analysis, consensus building, and resolution tracking',
    defaultPersonality: `You are Dr. Amara Okafor, a decision science expert and former McKinsey consultant specializing in organizational decision-making processes. Your expertise:

DECISION ANALYSIS FRAMEWORK:
- **Decision Identification**: Distinguish between decisions made, deferred, and avoided
- **Stakeholder Impact**: Map who is affected and how decisions change their work/outcomes
- **Implementation Requirements**: What resources, approvals, or changes are needed
- **Risk Assessment**: Potential downsides and mitigation strategies

DECISION CATEGORIES YOU TRACK:
1. **Strategic Decisions**: Long-term direction, resource allocation, market positioning
2. **Operational Decisions**: Process changes, tool selections, workflow modifications
3. **Personnel Decisions**: Role changes, hiring, team structure
4. **Financial Decisions**: Budget allocations, cost approvals, investment priorities
5. **Policy Decisions**: Rule changes, compliance requirements, governance updates

OUTPUT STRUCTURE:
For each decision:
- **Decision**: What exactly was decided (precise language)
- **Rationale**: Why this choice was made
- **Alternatives Considered**: What options were discussed but rejected
- **Implementation Plan**: Next steps to execute the decision
- **Success Metrics**: How to measure if the decision was correct
- **Review Date**: When to reassess the decision's effectiveness
- **Stakeholder Impact**: Who is affected and how they should be notified

SPECIAL CAPABILITIES:
- Identify implicit decisions and unstated assumptions
- Detect consensus vs. compliance (true buy-in vs. reluctant agreement)
- Flag decisions that may need legal, HR, or compliance review
- Recognize when decisions are made without proper authority or information

Remember: Great decisions require clarity, commitment, and follow-through. Your analysis ensures nothing falls through the cracks.`,
    capabilities: ['Decision Identification', 'Consensus Analysis', 'Impact Assessment', 'Implementation Planning', 'Risk Evaluation', 'Stakeholder Communication'],
    color: 'from-yellow-500 to-orange-500',
    defaultProgressive: PROGRESSIVE_PRESETS['balanced-summary']
  },
  'note-taker': {
    name: 'Note Taker',
    icon: MessageSquare,
    description: 'Professional documentation specialist with executive assistant expertise',
    defaultPersonality: `You are Jennifer Kim, an executive assistant and documentation specialist with 12 years of experience supporting C-level executives at Fortune 500 companies. Your documentation philosophy:

DOCUMENTATION STANDARDS:
- **Accuracy**: Capture exact quotes for critical statements and decisions
- **Clarity**: Use clear, professional language that can be understood by all stakeholders
- **Completeness**: Include context, reasoning, and non-verbal cues when relevant
- **Structure**: Organize information in logical, scannable formats
- **Actionability**: Make it easy for readers to find what they need to act on

NOTE-TAKING METHODOLOGY:
1. **Real-Time Capture**: Record key points as they happen, noting timestamps for important moments
2. **Speaker Attribution**: Clearly identify who said what, including roles/titles when relevant
3. **Topic Threading**: Track how topics evolve and connect throughout the discussion
4. **Sentiment Tracking**: Note agreement levels, concerns, enthusiasm, or resistance

OUTPUT ORGANIZATION:
- **Meeting Header**: Date, time, attendees (with roles), meeting purpose
- **Executive Summary**: 2-3 sentences capturing the most critical outcomes
- **Key Discussions**: Organized by topic with speaker attribution
- **Decisions Made**: Clear list with context and reasoning
- **Action Items**: Extracted separately for easy tracking
- **Parking Lot**: Items that were mentioned but not resolved
- **Next Steps**: What happens before the next meeting

SPECIAL SKILLS:
- Convert technical jargon into business-friendly language
- Identify when clarification is needed (note gaps or ambiguities)
- Recognize important tangential discussions that should be captured
- Balance detail with brevity based on audience needs
- Create meeting minutes that serve as historical record

FORMATTING EXPERTISE:
- Use bullet points, headers, and white space effectively
- Create scannable documents that executives can quickly review
- Include relevant links, references, or attachments mentioned
- Maintain consistent formatting and terminology throughout

Remember: Your notes may be referenced weeks or months later, so they must be self-contained and professional.`,
    capabilities: ['Executive Documentation', 'Real-time Capture', 'Speaker Attribution', 'Topic Threading', 'Professional Formatting', 'Historical Record Keeping'],
    color: 'from-blue-500 to-cyan-500',
    defaultProgressive: PROGRESSIVE_PRESETS['quick-bullets']
  },
  'custom': {
    name: 'Custom Agent',
    icon: Bot,
    description: 'Fully customizable agent with user-defined capabilities and behavior',
    defaultPersonality: `You are a custom meeting assistant designed to meet specific organizational needs. Your behavior, expertise, and output format are completely customizable based on user requirements.

DEFAULT MODE (until configured):
- Professional, neutral tone
- Comprehensive analysis across multiple dimensions
- Structured output with clear sections
- Focus on actionable insights and clear documentation

CUSTOMIZATION PARAMETERS:
- **Expertise Domain**: Can be configured for specific industries, functions, or use cases
- **Analysis Depth**: From high-level summaries to detailed technical analysis  
- **Output Format**: Flexible formatting based on organizational preferences
- **Focus Areas**: Emphasize specific aspects (compliance, innovation, efficiency, etc.)
- **Tone & Style**: Formal, casual, technical, or executive-focused language

ADVANCED CAPABILITIES:
- Industry-specific terminology and analysis frameworks
- Compliance and regulatory awareness for specific sectors
- Custom scoring/rating systems for meetings
- Integration with organizational metrics and KPIs
- Multi-language support and cultural considerations

CONFIGURATION OPTIONS:
- Custom prompts and instructions
- Specific analysis frameworks (SWOT, RACI, OKRs, etc.)
- Company-specific terminology and abbreviations
- Role-based output variations for different stakeholders
- Integration with existing workflows and systems

Remember: This agent adapts to your organization's specific needs and preferences. Configure it to match your meeting culture and requirements.`,
    capabilities: ['Full Customization', 'Industry Adaptation', 'Flexible Formatting', 'Multi-Framework Analysis', 'Cultural Adaptation'],
    color: 'from-pink-500 to-rose-500',
    defaultProgressive: PROGRESSIVE_PRESETS['balanced-summary']
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

export default function MeetingAgents() {
  const [agents, setAgents] = useState<MeetingAgent[]>([]);
  const [editingAgent, setEditingAgent] = useState<MeetingAgent | null>(null);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<keyof typeof AGENT_ROLES | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      setBackendError(null);
      const response = await fetch(`${config.apiUrl}/api/advanced/agents`);
      if (response.ok) {
        const data = await response.json();
        setAgents(data);
        return;
      } else {
        throw new Error(`Backend returned ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to load agents from backend:', error);
      setBackendError('Cannot connect to Meeting-Ops backend. Please check that the backend service is running.');
      setAgents([]);
    }
  };


  const createAgent = (role?: keyof typeof AGENT_ROLES) => {
    const roleData = role ? AGENT_ROLES[role] : AGENT_ROLES['custom'];
    const newAgent: MeetingAgent = {
      id: Date.now().toString(),
      name: `New ${roleData.name}`,
      description: roleData.description,
      role: role || 'custom',
      personality: roleData.defaultPersonality,
      capabilities: [...roleData.capabilities],
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
      trigger: 'progressive',
      progressiveConfig: { ...roleData.defaultProgressive },
      isActive: false
    };
    setEditingAgent(newAgent);
    setSelectedRole(null);
  };

  const addSection = (agent: MeetingAgent, type: keyof typeof SECTION_TYPES) => {
    const newSection: TemplateSection = {
      id: Date.now().toString(),
      type,
      title: SECTION_TYPES[type].name,
      prompt: SECTION_TYPES[type].defaultPrompt,
      order: agent.sections.length + 1,
      isEnabled: true
    };
    
    setEditingAgent({
      ...agent,
      sections: [...agent.sections, newSection]
    });
  };

  const updateSection = (agentId: string, sectionId: string, updates: Partial<TemplateSection>) => {
    if (!editingAgent) return;
    
    setEditingAgent({
      ...editingAgent,
      sections: editingAgent.sections.map(section =>
        section.id === sectionId ? { ...section, ...updates } : section
      )
    });
  };

  const removeSection = (sectionId: string) => {
    if (!editingAgent) return;
    
    setEditingAgent({
      ...editingAgent,
      sections: editingAgent.sections.filter(section => section.id !== sectionId)
    });
  };

  const saveAgent = async (agent: MeetingAgent) => {
    setLoading(true);
    try {
      const response = await fetch(`${config.apiUrl}/api/advanced/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agent)
      });

      if (response.ok) {
        updateAgentsList(agent);
        setEditingAgent(null);
      } else {
        alert('Failed to save agent. Backend returned error.');
      }
    } catch (error) {
      console.error('Failed to save agent:', error);
      alert('Failed to save agent. Please check backend connection.');
    } finally {
      setLoading(false);
    }
  };

  const updateAgentsList = (agent: MeetingAgent) => {
    const existing = agents.find(a => a.id === agent.id);
    if (existing) {
      setAgents(prev => prev.map(a => a.id === agent.id ? agent : a));
    } else {
      setAgents(prev => [...prev, agent]);
    }
  };

  const setActiveAgent = async (agentId: string) => {
    // Update all agents to set only the selected one as active
    const updatedAgents = agents.map(a => ({
      ...a,
      isActive: a.id === agentId
    }));
    setAgents(updatedAgents);

    try {
      // Update the selected agent to be active in backend
      const response = await fetch(`${config.apiUrl}/api/advanced/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...updatedAgents.find(a => a.id === agentId),
          isActive: true
        })
      });
      
      // Also update other agents to be inactive
      const inactiveAgents = updatedAgents.filter(a => a.id !== agentId);
      for (const agent of inactiveAgents) {
        await fetch(`${config.apiUrl}/api/advanced/agents`, {
          method: 'POST', 
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...agent,
            isActive: false
          })
        });
      }
      
      if (!response.ok) {
        alert('Failed to set active agent. Backend returned error.');
      }
    } catch (error) {
      console.error('Failed to set active agent:', error);
      alert('Failed to set active agent. Please check backend connection.');
    }
  };

  const duplicateAgent = (agent: MeetingAgent) => {
    const duplicate: MeetingAgent = {
      ...agent,
      id: Date.now().toString(),
      name: `${agent.name} (Copy)`,
      isActive: false,
      isDefault: false
    };
    setEditingAgent(duplicate);
  };

  const toggleExpanded = (agentId: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [agentId]: !prev[agentId]
    }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Bot className="w-8 h-8 text-purple-400" />
            Meeting Agents
          </h1>
          <p className="text-zinc-400 mt-2">
            Create and manage AI agents for intelligent meeting analysis (inspired by Open WebUI)
          </p>
        </div>

        {/* Backend Error */}
        {backendError && (
          <div className="mb-8 p-6 rounded-2xl bg-red-900/20 border border-red-500/30">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
              <h2 className="text-xl font-semibold text-red-300">Backend Connection Error</h2>
            </div>
            <p className="text-red-200 mb-4">{backendError}</p>
            <button
              onClick={loadAgents}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Active Agent */}
        <div className="mb-8 p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Play className="w-5 h-5 text-green-400" />
            Active Agent
          </h2>
          {agents.find(a => a.isActive) ? (() => {
            const activeAgent = agents.find(a => a.isActive)!;
            const roleData = AGENT_ROLES[activeAgent.role];
            const RoleIcon = roleData.icon;
            return (
              <div className="p-4 rounded-xl bg-green-500/10 border border-green-500/30">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-full bg-gradient-to-br ${roleData.color} flex items-center justify-center`}>
                      <RoleIcon className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <div className="font-medium text-green-300">{activeAgent.name}</div>
                      <div className="text-sm text-zinc-400 mt-1">{activeAgent.description}</div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {activeAgent.capabilities.map(cap => (
                          <span key={cap} className="px-2 py-0.5 text-xs bg-green-500/20 text-green-400 rounded-full">
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-green-400">
                      {activeAgent.sections.filter(s => s.isEnabled).length} sections
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      Trigger: {activeAgent.trigger === 'word_count' 
                        ? `Every ${activeAgent.triggerValue} words`
                        : activeAgent.trigger === 'time'
                        ? `Every ${activeAgent.triggerValue} seconds`
                        : 'Manual only'}
                    </div>
                  </div>
                </div>
              </div>
            );
          })() : (
            <div className="text-center py-8 text-zinc-500">
              No active agent configured
            </div>
          )}
        </div>

        {/* Agent Creation Menu */}
        {selectedRole && (
          <div className="mb-8 p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
            <h2 className="text-xl font-semibold mb-4">Choose Agent Type</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(AGENT_ROLES).map(([key, role]) => {
                const RoleIcon = role.icon;
                return (
                  <button
                    key={key}
                    onClick={() => createAgent(key as keyof typeof AGENT_ROLES)}
                    className={`p-4 rounded-xl border-2 border-zinc-700 hover:border-purple-500 transition-all bg-gradient-to-br ${role.color}/10 hover:${role.color}/20`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${role.color} flex items-center justify-center`}>
                        <RoleIcon className="w-4 h-4 text-white" />
                      </div>
                      <span className="font-medium">{role.name}</span>
                    </div>
                    <p className="text-sm text-zinc-400 text-left">{role.description}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {role.capabilities.slice(0, 2).map(cap => (
                        <span key={cap} className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-300 rounded-full">
                          {cap}
                        </span>
                      ))}
                      {role.capabilities.length > 2 && (
                        <span className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-300 rounded-full">
                          +{role.capabilities.length - 2}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Agents List */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold">All Agents</h2>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedRole('create')}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Create Agent
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {agents.map((agent) => {
              const roleData = AGENT_ROLES[agent.role];
              const RoleIcon = roleData.icon;
              return (
                <div
                  key={agent.id}
                  className={`rounded-2xl border transition-all ${
                    agent.isActive
                      ? 'bg-green-500/5 border-green-500/30'
                      : 'bg-zinc-900/70 border-zinc-800'
                  }`}
                >
                  {/* Agent Header */}
                  <div className="p-6 border-b border-zinc-800">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`w-12 h-12 rounded-full bg-gradient-to-br ${roleData.color} flex items-center justify-center`}>
                          <RoleIcon className="w-6 h-6 text-white" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="font-semibold">{agent.name}</h3>
                            {agent.isActive && (
                              <span className="px-2 py-1 text-xs bg-green-500/20 text-green-300 rounded-full">
                                Active
                              </span>
                            )}
                            {agent.isDefault && (
                              <span className="px-2 py-1 text-xs bg-blue-500/20 text-blue-300 rounded-full">
                                Default
                              </span>
                            )}
                            <Badge className={`text-xs bg-gradient-to-r ${roleData.color} text-white`}>
                              {roleData.name}
                            </Badge>
                          </div>
                          <div className="text-sm text-zinc-400 mb-2">
                            {agent.description}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {agent.capabilities.map(cap => (
                              <span key={cap} className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-300 rounded-full">
                                {cap}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleExpanded(agent.id)}
                          className="p-2 text-zinc-400 hover:text-white transition-colors"
                        >
                          {expandedSections[agent.id] ? 
                            <ChevronDown className="w-4 h-4" /> : 
                            <ChevronRight className="w-4 h-4" />
                          }
                        </button>
                        <button
                          onClick={() => duplicateAgent(agent)}
                          className="p-2 text-zinc-400 hover:text-white transition-colors"
                        >
                          <Copy className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setEditingAgent(agent)}
                          className="p-2 text-zinc-400 hover:text-white transition-colors"
                        >
                          <Settings className="w-4 h-4" />
                        </button>
                        {!agent.isActive && (
                          <button
                            onClick={() => setActiveAgent(agent.id)}
                            className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 rounded transition-colors"
                          >
                            Activate
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Agent Details (Expanded) */}
                  {expandedSections[agent.id] && (
                    <div className="p-6">
                      <div className="mb-4">
                        <h4 className="font-medium mb-2">Agent Personality</h4>
                        <p className="text-sm text-zinc-400 bg-zinc-800/50 p-3 rounded-lg">
                          {agent.personality}
                        </p>
                      </div>
                      
                      <div>
                        <h4 className="font-medium mb-3">Active Sections ({agent.sections.filter(s => s.isEnabled).length})</h4>
                        <div className="space-y-2">
                          {agent.sections
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
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Edit Agent Modal */}
        {editingAgent && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-zinc-900 rounded-2xl p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              <h3 className="text-xl font-semibold mb-4">
                {agents.find(a => a.id === editingAgent.id) ? 'Edit' : 'Create'} Agent
              </h3>
              
              <div className="space-y-6">
                {/* Basic Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Agent Name</label>
                    <input
                      type="text"
                      value={editingAgent.name}
                      onChange={(e) => setEditingAgent(prev => prev ? {...prev, name: e.target.value} : null)}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Agent Role</label>
                    <select
                      value={editingAgent.role}
                      onChange={(e) => {
                        const role = e.target.value as keyof typeof AGENT_ROLES;
                        const roleData = AGENT_ROLES[role];
                        setEditingAgent(prev => prev ? {
                          ...prev, 
                          role,
                          personality: roleData.defaultPersonality,
                          capabilities: [...roleData.capabilities]
                        } : null);
                      }}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    >
                      {Object.entries(AGENT_ROLES).map(([key, role]) => (
                        <option key={key} value={key}>{role.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Description</label>
                  <textarea
                    value={editingAgent.description}
                    onChange={(e) => setEditingAgent(prev => prev ? {...prev, description: e.target.value} : null)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    rows={2}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Agent Personality (System Prompt)</label>
                  <textarea
                    value={editingAgent.personality}
                    onChange={(e) => setEditingAgent(prev => prev ? {...prev, personality: e.target.value} : null)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    rows={3}
                    placeholder="Define how this agent should behave and respond..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Capabilities</label>
                  <div className="flex flex-wrap gap-2 p-3 bg-zinc-800 border border-zinc-700 rounded-lg">
                    {editingAgent.capabilities.map((cap, index) => (
                      <span key={index} className="px-2 py-1 text-xs bg-purple-500/20 text-purple-300 rounded-full flex items-center gap-1">
                        {cap}
                        <button
                          onClick={() => setEditingAgent(prev => prev ? {
                            ...prev,
                            capabilities: prev.capabilities.filter((_, i) => i !== index)
                          } : null)}
                          className="text-red-400 hover:text-red-300"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    <input
                      type="text"
                      placeholder="Add capability..."
                      onKeyPress={(e) => {
                        if (e.key === 'Enter' && e.currentTarget.value.trim()) {
                          setEditingAgent(prev => prev ? {
                            ...prev,
                            capabilities: [...prev.capabilities, e.currentTarget.value.trim()]
                          } : null);
                          e.currentTarget.value = '';
                        }
                      }}
                      className="text-xs bg-transparent border-none outline-none placeholder-zinc-500"
                    />
                  </div>
                </div>

                {/* Progressive Interval Configuration */}
                <div>
                  <label className="block text-sm font-medium mb-2">Trigger Configuration</label>
                  <div className="space-y-4">
                    <div>
                      <select
                        value={editingAgent.trigger}
                        onChange={(e) => {
                          const trigger = e.target.value as MeetingAgent['trigger'];
                          setEditingAgent(prev => prev ? {
                            ...prev,
                            trigger,
                            progressiveConfig: trigger === 'progressive' ? 
                              PROGRESSIVE_PRESETS['balanced-summary'] : undefined
                          } : null);
                        }}
                        className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                      >
                        <option value="progressive">Progressive Intervals (Recommended)</option>
                        <option value="word_count">Fixed Word Count</option>
                        <option value="time">Fixed Time Interval</option>
                        <option value="manual">Manual Only</option>
                      </select>
                    </div>

                    {editingAgent.trigger === 'progressive' && editingAgent.progressiveConfig && (
                      <div className="p-4 bg-zinc-800/50 rounded-lg space-y-3">
                        <h4 className="font-medium text-purple-300">Progressive Interval Settings</h4>
                        
                        {/* Preset Selection */}
                        <div>
                          <label className="block text-xs text-zinc-400 mb-2">Quick Presets</label>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            {Object.entries(PROGRESSIVE_PRESETS).map(([key, preset]) => (
                              <button
                                key={key}
                                onClick={() => setEditingAgent(prev => prev ? {
                                  ...prev,
                                  progressiveConfig: { ...preset }
                                } : null)}
                                className="p-2 text-left bg-zinc-700 hover:bg-zinc-600 rounded text-xs transition-colors"
                              >
                                <div className="font-medium">{preset.name}</div>
                                <div className="text-zinc-400 text-xs">{preset.description}</div>
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Manual Configuration */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div>
                            <label className="block text-xs text-zinc-400 mb-1">Initial Words</label>
                            <input
                              type="number"
                              value={editingAgent.progressiveConfig.initialWordCount}
                              onChange={(e) => setEditingAgent(prev => prev ? {
                                ...prev,
                                progressiveConfig: {
                                  ...prev.progressiveConfig!,
                                  initialWordCount: parseInt(e.target.value) || 50
                                }
                              } : null)}
                              className="w-full p-2 bg-zinc-700 border border-zinc-600 rounded text-sm focus:border-purple-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-zinc-400 mb-1">Growth Factor</label>
                            <input
                              type="number"
                              step="0.1"
                              value={editingAgent.progressiveConfig.intervalMultiplier}
                              onChange={(e) => setEditingAgent(prev => prev ? {
                                ...prev,
                                progressiveConfig: {
                                  ...prev.progressiveConfig!,
                                  intervalMultiplier: parseFloat(e.target.value) || 1.5
                                }
                              } : null)}
                              className="w-full p-2 bg-zinc-700 border border-zinc-600 rounded text-sm focus:border-purple-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-zinc-400 mb-1">Max Interval</label>
                            <input
                              type="number"
                              value={editingAgent.progressiveConfig.maxInterval}
                              onChange={(e) => setEditingAgent(prev => prev ? {
                                ...prev,
                                progressiveConfig: {
                                  ...prev.progressiveConfig!,
                                  maxInterval: parseInt(e.target.value) || 1000
                                }
                              } : null)}
                              className="w-full p-2 bg-zinc-700 border border-zinc-600 rounded text-sm focus:border-purple-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-zinc-400 mb-1">Model Size</label>
                            <select
                              value={editingAgent.progressiveConfig.modelSize}
                              onChange={(e) => setEditingAgent(prev => prev ? {
                                ...prev,
                                progressiveConfig: {
                                  ...prev.progressiveConfig!,
                                  modelSize: e.target.value as 'small' | 'medium' | 'large'
                                }
                              } : null)}
                              className="w-full p-2 bg-zinc-700 border border-zinc-600 rounded text-sm focus:border-purple-500 focus:outline-none"
                            >
                              <option value="small">Small (Fast)</option>
                              <option value="medium">Medium</option>
                              <option value="large">Large (Detailed)</option>
                            </select>
                          </div>
                        </div>

                        {/* Preview */}
                        <div className="text-xs text-zinc-400 bg-zinc-900/50 p-2 rounded">
                          <strong>Preview:</strong> First summary at {editingAgent.progressiveConfig.initialWordCount} words, 
                          then increasing by {editingAgent.progressiveConfig.intervalMultiplier}x each time, 
                          up to maximum {editingAgent.progressiveConfig.maxInterval} words using {editingAgent.progressiveConfig.modelSize} model.
                        </div>
                      </div>
                    )}

                    {editingAgent.trigger === 'word_count' && (
                      <div>
                        <label className="block text-xs text-zinc-400 mb-1">Word Count Trigger</label>
                        <input
                          type="number"
                          value={editingAgent.triggerValue || 300}
                          onChange={(e) => setEditingAgent(prev => prev ? {
                            ...prev,
                            triggerValue: parseInt(e.target.value) || 300
                          } : null)}
                          className="w-full p-2 bg-zinc-800 border border-zinc-700 rounded focus:border-purple-500 focus:outline-none"
                        />
                      </div>
                    )}

                    {editingAgent.trigger === 'time' && (
                      <div>
                        <label className="block text-xs text-zinc-400 mb-1">Time Interval (seconds)</label>
                        <input
                          type="number"
                          value={editingAgent.triggerValue || 60}
                          onChange={(e) => setEditingAgent(prev => prev ? {
                            ...prev,
                            triggerValue: parseInt(e.target.value) || 60
                          } : null)}
                          className="w-full p-2 bg-zinc-800 border border-zinc-700 rounded focus:border-purple-500 focus:outline-none"
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* Sections */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="text-lg font-medium">Agent Sections</h4>
                    <div className="flex gap-2">
                      {Object.entries(SECTION_TYPES).map(([key, type]) => (
                        <button
                          key={key}
                          onClick={() => addSection(editingAgent, key as keyof typeof SECTION_TYPES)}
                          className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 rounded transition-colors"
                          title={`Add ${type.name}`}
                        >
                          <type.icon className="w-3 h-3" />
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    {editingAgent.sections
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
                                  onChange={(e) => updateSection(editingAgent.id, section.id, { title: e.target.value })}
                                  className="bg-transparent border-none outline-none font-medium"
                                />
                              </div>
                              <div className="flex items-center gap-2">
                                <label className="flex items-center gap-2 text-sm">
                                  <input
                                    type="checkbox"
                                    checked={section.isEnabled}
                                    onChange={(e) => updateSection(editingAgent.id, section.id, { isEnabled: e.target.checked })}
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
                              onChange={(e) => updateSection(editingAgent.id, section.id, { prompt: e.target.value })}
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
                    onClick={() => setEditingAgent(null)}
                    className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => saveAgent(editingAgent)}
                    disabled={loading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loading ? 'Saving...' : 'Save Agent'}
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