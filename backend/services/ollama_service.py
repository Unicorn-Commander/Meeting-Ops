"""
Ollama service for LLM operations (summarization, insights, etc.)
"""
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434"):
        """Initialize Ollama service"""
        self.base_url = base_url
        self.default_model = "gemma3n:latest"
        
    def list_models(self) -> List[str]:
        """List available models in Ollama"""
        try:
            url = f"{self.base_url}/api/tags"
            request = urllib.request.Request(url)
            
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
                models = data.get("models", [])
                return [m["name"] for m in models]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []
    
    def generate(self, prompt: str, model: Optional[str] = None, stream: bool = False) -> str:
        """Generate text using Ollama"""
        try:
            model = model or self.default_model
            url = f"{self.base_url}/api/generate"
            
            data = {
                "model": model,
                "prompt": prompt,
                "stream": stream
            }
            
            request = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode())
                return result.get("response", "")
                
        except Exception as e:
            logger.error(f"Failed to generate with Ollama: {e}")
            return ""
    
    def summarize_meeting(self, transcript: str, template: Optional[Dict] = None) -> Dict:
        """Generate meeting summary using Ollama"""
        
        # Default template if none provided
        if not template:
            template = {
                "name": "Standard Meeting Summary",
                "sections": [
                    "Key Discussion Points",
                    "Decisions Made",
                    "Action Items",
                    "Next Steps"
                ]
            }
        
        # Build prompt
        sections_text = "\n".join([f"- {s}" for s in template.get("sections", [])])
        
        prompt = f"""Please analyze the following meeting transcript and provide a comprehensive summary.

Meeting Transcript:
{transcript[:8000]}  # Limit to avoid token limits

Please provide a summary with the following sections:
{sections_text}

Format the response in a clear, professional manner with bullet points for each section.
Be concise but comprehensive. Focus on actionable insights."""
        
        # Generate summary
        summary_text = self.generate(prompt)
        
        # Parse into sections (basic parsing)
        sections = {}
        current_section = None
        current_content = []
        
        for line in summary_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Check if this is a section header
            is_header = False
            for section in template.get("sections", []):
                if section.lower() in line.lower():
                    # Save previous section
                    if current_section:
                        sections[current_section] = '\n'.join(current_content)
                    # Start new section
                    current_section = section
                    current_content = []
                    is_header = True
                    break
            
            if not is_header and current_section:
                current_content.append(line)
        
        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content)
        
        return {
            "summary": summary_text,
            "sections": sections,
            "model": self.default_model,
            "template": template["name"]
        }
    
    def generate_meeting_title(self, transcript: str) -> str:
        """Generate a concise meeting title based on transcript"""
        
        prompt = f"""Based on the following meeting transcript, generate a concise, professional meeting title.
The title should be 5-10 words and capture the main topic or purpose of the meeting.

Transcript excerpt:
{transcript[:2000]}

Provide ONLY the title, nothing else. No quotes, no explanation."""
        
        title = self.generate(prompt).strip()
        
        # Clean up the title
        title = title.replace('"', '').replace("'", '')
        if not title or len(title) > 100:
            title = "Team Meeting"
        
        return title
    
    def extract_action_items(self, transcript: str) -> List[Dict]:
        """Extract action items from meeting transcript"""
        
        prompt = f"""Analyze the following meeting transcript and extract all action items.

Transcript:
{transcript[:6000]}

For each action item, identify:
1. The task/action to be done
2. Who is responsible (if mentioned)
3. Due date/timeline (if mentioned)

Format as a list with each item on a new line starting with a dash (-)
Include responsible person in [brackets] and timeline in (parentheses) if available.

Example:
- Complete the report [John] (by Friday)
- Schedule follow-up meeting [Sarah]
- Review budget proposal"""
        
        response = self.generate(prompt)
        
        # Parse action items
        action_items = []
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                # Parse the action item
                item_text = line[1:].strip()
                
                # Extract assignee if present
                assignee = None
                if '[' in item_text and ']' in item_text:
                    start = item_text.index('[')
                    end = item_text.index(']')
                    assignee = item_text[start+1:end]
                    item_text = item_text[:start] + item_text[end+1:]
                
                # Extract due date if present
                due_date = None
                if '(' in item_text and ')' in item_text:
                    start = item_text.rindex('(')
                    end = item_text.rindex(')')
                    due_date = item_text[start+1:end]
                    item_text = item_text[:start] + item_text[end+1:]
                
                action_items.append({
                    "task": item_text.strip(),
                    "assignee": assignee,
                    "due_date": due_date
                })
        
        return action_items
    
    def analyze_sentiment(self, transcript: str) -> Dict:
        """Analyze meeting sentiment and dynamics"""
        
        prompt = f"""Analyze the sentiment and dynamics of this meeting transcript.

Transcript excerpt:
{transcript[:3000]}

Provide:
1. Overall sentiment (positive/neutral/negative)
2. Meeting effectiveness (1-10 scale)
3. Key concerns raised
4. Positive highlights
5. Suggested improvements

Be concise and professional."""
        
        response = self.generate(prompt)
        
        return {
            "analysis": response,
            "model": self.default_model
        }

# Global instance
ollama_service = OllamaService()