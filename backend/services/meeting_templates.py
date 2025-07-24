"""
Meeting Note Templates System
Provides structured templates for different meeting types
"""
from typing import Dict, List, Any
import json

class MeetingTemplates:
    """Predefined templates for different meeting types"""
    
    TEMPLATES = {
        "standup": {
            "name": "Daily Standup",
            "description": "Quick team sync on progress and blockers",
            "system_prompt": """You are analyzing a daily standup meeting. Focus on:
1. What each person accomplished yesterday
2. What they plan to work on today
3. Any blockers or issues they're facing
4. Team collaboration needs

Format the output with clear sections for each team member.""",
            "output_structure": {
                "sections": ["Team Updates", "Blockers", "Action Items", "Collaboration Needs"],
                "per_speaker": True,
                "extract_dates": True
            },
            "focus_areas": ["progress", "blockers", "commitments"],
            "typical_duration": "15-30 minutes"
        },
        
        "retrospective": {
            "name": "Sprint Retrospective",
            "description": "Team reflection on what went well and what to improve",
            "system_prompt": """You are analyzing a retrospective meeting. Organize feedback into:
1. What went well (positives)
2. What didn't go well (challenges)
3. What to improve (action items)
4. Team sentiment and morale

Capture specific examples and ensure action items have clear owners.""",
            "output_structure": {
                "sections": ["Went Well", "Challenges", "Improvements", "Action Items", "Team Morale"],
                "sentiment_analysis": True,
                "action_tracking": True
            },
            "focus_areas": ["feedback", "improvements", "team_dynamics"],
            "typical_duration": "60-90 minutes"
        },
        
        "planning": {
            "name": "Sprint Planning",
            "description": "Planning upcoming work and setting goals",
            "system_prompt": """You are analyzing a planning meeting. Extract:
1. Sprint/Period goals
2. User stories or tasks discussed
3. Effort estimates mentioned
4. Dependencies identified
5. Commitments made by team members

Include any risks or concerns raised.""",
            "output_structure": {
                "sections": ["Goals", "Planned Work", "Estimates", "Dependencies", "Risks", "Commitments"],
                "extract_numbers": True,
                "track_assignments": True
            },
            "focus_areas": ["goals", "tasks", "estimates", "assignments"],
            "typical_duration": "60-120 minutes"
        },
        
        "one_on_one": {
            "name": "1:1 Meeting",
            "description": "Manager-employee or peer discussion",
            "system_prompt": """You are analyzing a 1:1 meeting. Focus on:
1. Topics discussed
2. Feedback exchanged
3. Career development topics
4. Action items for both parties
5. Follow-up items

Maintain confidentiality markers for sensitive topics.""",
            "output_structure": {
                "sections": ["Discussion Topics", "Feedback", "Development", "Action Items", "Follow-ups"],
                "confidentiality": True,
                "bilateral_actions": True
            },
            "focus_areas": ["feedback", "development", "concerns"],
            "typical_duration": "30-60 minutes"
        },
        
        "brainstorming": {
            "name": "Brainstorming Session",
            "description": "Creative ideation and problem solving",
            "system_prompt": """You are analyzing a brainstorming session. Capture:
1. Problem or challenge being addressed
2. All ideas proposed (even incomplete ones)
3. Ideas that gained traction
4. Next steps for promising ideas
5. Parking lot items

Group related ideas and note enthusiasm levels.""",
            "output_structure": {
                "sections": ["Challenge", "Ideas Proposed", "Top Ideas", "Next Steps", "Parking Lot"],
                "idea_grouping": True,
                "enthusiasm_tracking": True
            },
            "focus_areas": ["ideas", "solutions", "creativity"],
            "typical_duration": "45-90 minutes"
        },
        
        "all_hands": {
            "name": "All Hands Meeting",
            "description": "Company or department-wide meeting",
            "system_prompt": """You are analyzing an all-hands meeting. Structure the summary as:
1. Key announcements
2. Business updates and metrics
3. Team/Individual recognition
4. Q&A highlights
5. Important dates and deadlines

Emphasize company-wide impact items.""",
            "output_structure": {
                "sections": ["Announcements", "Business Updates", "Recognition", "Q&A", "Important Dates"],
                "highlight_metrics": True,
                "extract_dates": True
            },
            "focus_areas": ["announcements", "metrics", "recognition"],
            "typical_duration": "30-60 minutes"
        },
        
        "client_meeting": {
            "name": "Client Meeting",
            "description": "External client or customer discussion",
            "system_prompt": """You are analyzing a client meeting. Focus on:
1. Client needs and requirements
2. Our commitments and proposals
3. Timeline discussions
4. Budget or pricing topics
5. Next steps and follow-ups

Clearly distinguish client requests from internal discussions.""",
            "output_structure": {
                "sections": ["Client Requirements", "Our Proposals", "Timeline", "Commercial", "Next Steps"],
                "client_focus": True,
                "commitment_tracking": True
            },
            "focus_areas": ["requirements", "commitments", "timeline", "commercial"],
            "typical_duration": "30-90 minutes"
        },
        
        "design_review": {
            "name": "Design Review",
            "description": "Technical or design review session",
            "system_prompt": """You are analyzing a design review. Extract:
1. Design decisions discussed
2. Technical feedback and concerns
3. Alternative approaches suggested
4. Approval status and conditions
5. Required changes or iterations

Include specific technical details mentioned.""",
            "output_structure": {
                "sections": ["Design Overview", "Feedback", "Alternatives", "Decisions", "Required Changes"],
                "technical_detail": True,
                "decision_tracking": True
            },
            "focus_areas": ["technical_details", "feedback", "decisions"],
            "typical_duration": "45-90 minutes"
        },
        
        "interview": {
            "name": "Interview",
            "description": "Job interview or evaluation",
            "system_prompt": """You are analyzing an interview. Summarize:
1. Key qualifications discussed
2. Experience highlights
3. Technical assessments
4. Cultural fit indicators
5. Next steps in process

Maintain objectivity and avoid bias.""",
            "output_structure": {
                "sections": ["Qualifications", "Experience", "Technical Skills", "Cultural Fit", "Next Steps"],
                "objective_tone": True,
                "competency_mapping": True
            },
            "focus_areas": ["qualifications", "experience", "fit"],
            "typical_duration": "30-60 minutes"
        },
        
        "board_meeting": {
            "name": "Board Meeting",
            "description": "Executive or board-level discussion",
            "system_prompt": """You are analyzing a board meeting. Structure as:
1. Strategic decisions made
2. Financial reviews and approvals
3. Risk discussions
4. Governance matters
5. Action items with owners and deadlines

Focus on high-level strategic matters.""",
            "output_structure": {
                "sections": ["Strategic Decisions", "Financial Review", "Risk Assessment", "Governance", "Board Actions"],
                "executive_summary": True,
                "formal_tone": True
            },
            "focus_areas": ["strategy", "finances", "governance", "risk"],
            "typical_duration": "60-180 minutes"
        }
    }
    
    @classmethod
    def get_template(cls, template_type: str) -> Dict[str, Any]:
        """Get a specific template by type"""
        return cls.TEMPLATES.get(template_type, cls.TEMPLATES["standup"])
    
    @classmethod
    def list_templates(cls) -> List[Dict[str, str]]:
        """List all available templates with basic info"""
        return [
            {
                "id": key,
                "name": value["name"],
                "description": value["description"],
                "typical_duration": value.get("typical_duration", "Varies")
            }
            for key, value in cls.TEMPLATES.items()
        ]
    
    @classmethod
    def build_prompt(cls, template_type: str, custom_instructions: str = "") -> str:
        """Build a complete prompt combining template and custom instructions"""
        template = cls.get_template(template_type)
        base_prompt = template["system_prompt"]
        
        if custom_instructions:
            return f"{base_prompt}\n\nAdditional instructions:\n{custom_instructions}"
        
        return base_prompt
    
    @classmethod
    def format_speaker_context(cls, transcriptions: List[Dict], speakers: List[Dict]) -> str:
        """Format transcriptions with clear speaker labels for LLM context"""
        speaker_map = {
            speaker.get('speaker_id'): speaker.get('name', f"Speaker {i+1}")
            for i, speaker in enumerate(speakers)
        }
        
        formatted_lines = []
        current_speaker = None
        
        for transcript in transcriptions:
            speaker_id = transcript.get('speaker_id')
            speaker_name = speaker_map.get(speaker_id, "Unknown Speaker")
            text = transcript.get('text', '').strip()
            
            if not text:
                continue
            
            # Add speaker label when speaker changes
            if speaker_id != current_speaker:
                current_speaker = speaker_id
                formatted_lines.append(f"\n[{speaker_name}]:")
            
            formatted_lines.append(text)
        
        return " ".join(formatted_lines)
    
    @classmethod
    def create_custom_template(cls, name: str, description: str, 
                             system_prompt: str, sections: List[str],
                             focus_areas: List[str]) -> Dict[str, Any]:
        """Create a custom template"""
        return {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "output_structure": {
                "sections": sections,
                "custom": True
            },
            "focus_areas": focus_areas,
            "typical_duration": "Custom"
        }