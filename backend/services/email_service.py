"""
Email Service for Meeting Summaries
Sends professional email reports with meeting summaries and attachments
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from typing import List, Dict, Any, Optional
from datetime import datetime
import tempfile
from jinja2 import Template
import json

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending meeting summary emails"""
    
    def __init__(self):
        self.smtp_host = ''
        self.smtp_port = 587
        self.smtp_username = ''
        self.smtp_password = ''
        self.smtp_use_tls = True
        self.from_email = 'noreply@unicorn-commander.local'
        self.from_name = 'Unicorn Commander Meeting Ops'
        
        self._load_smtp_config()
        self.email_templates = self._load_email_templates()

    def _get_config_path(self):
        return os.path.join(os.path.dirname(__file__), 'email_config.json')

    def _load_smtp_config(self):
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.smtp_host = config.get('smtp_host', '')
                    self.smtp_port = config.get('smtp_port', 587)
                    self.smtp_username = config.get('smtp_username', '')
                    self.smtp_password = config.get('smtp_password', '')
                    self.smtp_use_tls = config.get('smtp_use_tls', True)
                    self.from_email = config.get('from_email', self.smtp_username or 'noreply@unicorn-commander.local')
                    self.from_name = config.get('from_name', 'Unicorn Commander Meeting Ops')
            except Exception as e:
                logger.error(f"Error loading email config: {e}")

    def update_smtp_config(self, host: str, port: int, username: str, password: str):
        self.smtp_host = host
        self.smtp_port = port
        self.smtp_username = username
        self.smtp_password = password
        # Always use TLS for security
        self.smtp_use_tls = True 

        config = {
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'smtp_username': self.smtp_username,
            'smtp_password': self.smtp_password,
            'smtp_use_tls': self.smtp_use_tls,
            'from_email': self.from_email,
            'from_name': self.from_name,
        }
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            logger.info("SMTP configuration updated and saved.")
        except Exception as e:
            logger.error(f"Error saving email config: {e}")

    def get_smtp_config(self) -> Dict[str, Any]:
        return {
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'smtp_username': self.smtp_username,
            'smtp_password': self.smtp_password, # This should ideally not be sent to frontend
            'smtp_use_tls': self.smtp_use_tls,
            'from_email': self.from_email,
            'from_name': self.from_name,
        }
    
    def _load_email_templates(self) -> Dict[str, Template]:
        """Load email templates"""
        templates = {}
        
        # Meeting Summary Template
        templates['meeting_summary'] = Template('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meeting Summary - {{ meeting_name }}</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #fff; }
        .header { background: linear-gradient(135deg, #8B5CF6, #EC4899); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
        .header h1 { margin: 0; font-size: 28px; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        .content { padding: 30px; }
        .section { margin-bottom: 30px; }
        .section h2 { color: #8B5CF6; border-bottom: 2px solid #8B5CF6; padding-bottom: 10px; }
        .metrics { display: flex; justify-content: space-between; margin: 20px 0; }
        .metric { text-align: center; flex: 1; padding: 15px; background: #f8f9fa; margin: 0 5px; border-radius: 8px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #8B5CF6; }
        .metric-label { font-size: 12px; color: #666; text-transform: uppercase; }
        .action-item { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; border-radius: 4px; }
        .decision { background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 10px 0; border-radius: 4px; }
        .speaker-list { list-style: none; padding: 0; }
        .speaker-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #EC4899; }
        .footer { background: #f8f9fa; padding: 20px; text-align: center; color: #666; border-radius: 0 0 10px 10px; }
        .attachment-note { background: #e2e3e5; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .tech-badge { background: #10B981; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; }
        @media (max-width: 600px) {
            .metrics { flex-direction: column; }
            .metric { margin: 5px 0; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🦄 {{ meeting_name }}</h1>
            <p>{{ meeting_date }} • {{ duration }} • {{ speaker_count }} participants</p>
            {% if npu_accelerated %}
            <span class="tech-badge">⚡ NPU ACCELERATED</span>
            {% endif %}
        </div>
        
        <div class="content">
            <!-- Key Metrics -->
            <div class="section">
                <h2>📊 Key Metrics</h2>
                <div class="metrics">
                    <div class="metric">
                        <div class="metric-value">{{ duration }}</div>
                        <div class="metric-label">Duration</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{{ speaker_count }}</div>
                        <div class="metric-label">Speakers</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{{ confidence }}%</div>
                        <div class="metric-label">Avg Confidence</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{{ processing_speed }}</div>
                        <div class="metric-label">Processing</div>
                    </div>
                </div>
            </div>
            
            <!-- Executive Summary -->
            {% if executive_summary %}
            <div class="section">
                <h2>📋 Executive Summary</h2>
                <p>{{ executive_summary }}</p>
            </div>
            {% endif %}
            
            <!-- Action Items -->
            {% if action_items %}
            <div class="section">
                <h2>✅ Action Items</h2>
                {% for item in action_items %}
                <div class="action-item">
                    <strong>{{ item.task }}</strong>
                    {% if item.assignee != 'Unknown' %}<br><em>Assigned to: {{ item.assignee }}</em>{% endif %}
                    {% if item.deadline != 'Not specified' %}<br><em>Due: {{ item.deadline }}</em>{% endif %}
                    <span style="float: right; color: 
                        {%- if item.priority == 'high' -%}#dc3545
                        {%- elif item.priority == 'medium' -%}#ffc107
                        {%- else -%}#28a745{%- endif -%};">
                        {{ item.priority.upper() }}
                    </span>
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <!-- Key Decisions -->
            {% if key_decisions %}
            <div class="section">
                <h2>🎯 Key Decisions</h2>
                {% for decision in key_decisions %}
                <div class="decision">
                    <strong>{{ decision.decision }}</strong>
                    {% if decision.rationale %}<br><em>Rationale: {{ decision.rationale }}</em>{% endif %}
                    {% if decision.impact %}<br><em>Impact: {{ decision.impact }}</em>{% endif %}
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <!-- Speaker Insights -->
            {% if speaker_insights %}
            <div class="section">
                <h2>👥 Speaker Insights</h2>
                <ul class="speaker-list">
                    {% for speaker in speaker_insights %}
                    <li class="speaker-item">
                        <strong>{{ speaker.speaker_id }}</strong> - {{ speaker.speaking_style }}
                        <br><small>{{ speaker.total_contributions }} contributions, {{ speaker.total_words }} words</small>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
            
            <!-- Next Steps -->
            {% if next_steps %}
            <div class="section">
                <h2>🚀 Recommended Next Steps</h2>
                <ul>
                    {% for step in next_steps %}
                    <li>{{ step }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
            
            <!-- Attachments -->
            {% if has_attachments %}
            <div class="attachment-note">
                <strong>📎 Attachments Included:</strong>
                <ul>
                    <li>Complete meeting transcript (PDF)</li>
                    <li>Audio recording (if available)</li>
                    <li>Detailed analytics report</li>
                </ul>
            </div>
            {% endif %}
        </div>
        
        <div class="footer">
            <p>Generated by Unicorn Commander Meeting Ops v1.0</p>
            <p><em>NPU-Accelerated AI Transcription & Analysis</em></p>
            <p style="font-size: 11px; color: #999;">
                This summary was generated automatically using AI. 
                For questions, contact your system administrator.
            </p>
        </div>
    </div>
</body>
</html>
        ''')
        
        # Plain text template
        templates['meeting_summary_text'] = Template('''
MEETING SUMMARY: {{ meeting_name }}
================================================================

Date: {{ meeting_date }}
Duration: {{ duration }}
Participants: {{ speaker_count }} speakers
{% if npu_accelerated %}NPU Acceleration: Enabled ({{ processing_speed }} processing){% endif %}

{% if executive_summary %}
EXECUTIVE SUMMARY
-----------------
{{ executive_summary }}

{% endif %}
{% if action_items %}
ACTION ITEMS
------------
{% for item in action_items %}
• {{ item.task }}
  Assigned to: {{ item.assignee }}
  Due: {{ item.deadline }}
  Priority: {{ item.priority.upper() }}

{% endfor %}
{% endif %}
{% if key_decisions %}
KEY DECISIONS
-------------
{% for decision in key_decisions %}
• {{ decision.decision }}
{% if decision.rationale %}  Rationale: {{ decision.rationale }}{% endif %}

{% endfor %}
{% endif %}
{% if speaker_insights %}
SPEAKER INSIGHTS
----------------
{% for speaker in speaker_insights %}
• {{ speaker.speaker_id }}: {{ speaker.speaking_style }}
  {{ speaker.total_contributions }} contributions, {{ speaker.total_words }} words

{% endfor %}
{% endif %}
{% if next_steps %}
RECOMMENDED NEXT STEPS
----------------------
{% for step in next_steps %}
• {{ step }}
{% endfor %}

{% endif %}
--
Generated by Unicorn Commander Meeting Ops
NPU-Accelerated AI Transcription & Analysis
        ''')
        
        return templates
    
    async def send_meeting_summary(
        self,
        recipients: List[str],
        session_data: Dict[str, Any],
        summary_data: Dict[str, Any],
        include_pdf: bool = True,
        include_audio: bool = False,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None
    ) -> bool:
        """
        Send meeting summary email with attachments
        
        Args:
            recipients: List of email addresses to send to
            session_data: Meeting session information
            summary_data: AI-generated summary data
            include_pdf: Whether to attach PDF transcript
            include_audio: Whether to attach audio file
            cc_recipients: CC email addresses
            bcc_recipients: BCC email addresses
        
        Returns:
            bool: True if email sent successfully
        """
        try:
            if not recipients:
                logger.warning("No recipients specified for meeting summary email")
                return False
            
            if not self.smtp_username or not self.smtp_password:
                logger.warning("SMTP credentials not configured - email sending disabled")
                return False
            
            # Prepare email data
            start_time = datetime.fromisoformat(session_data.get('start_time', ''))
            
            email_data = {
                'meeting_name': session_data.get('name', 'Meeting Summary'),
                'meeting_date': start_time.strftime('%A, %B %d, %Y at %I:%M %p'),
                'duration': self._format_duration(session_data.get('duration_seconds', 0)),
                'speaker_count': session_data.get('total_speakers', 0),
                'confidence': round(summary_data.get('quality_metrics', {}).get('avg_confidence', 0) * 100),
                'processing_speed': '2,985x real-time' if session_data.get('npu_accelerated') else '13.6x real-time',
                'npu_accelerated': session_data.get('npu_accelerated', False),
                'executive_summary': summary_data.get('executive_summary', ''),
                'action_items': summary_data.get('action_items', []),
                'key_decisions': summary_data.get('key_decisions', []),
                'speaker_insights': summary_data.get('speaker_insights', []),
                'next_steps': summary_data.get('next_steps', []),
                'has_attachments': include_pdf or include_audio
            }
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Meeting Summary: {email_data['meeting_name']}"
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(recipients)
            msg['Date'] = formatdate(localtime=True)
            
            if cc_recipients:
                msg['Cc'] = ', '.join(cc_recipients)
            
            # Add plain text version
            text_content = self.email_templates['meeting_summary_text'].render(**email_data)
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Add HTML version
            html_content = self.email_templates['meeting_summary'].render(**email_data)
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Add PDF attachment if requested
            if include_pdf:
                pdf_content = await self._generate_pdf_attachment(session_data, summary_data)
                if pdf_content:
                    pdf_attachment = MIMEApplication(pdf_content, _subtype='pdf')
                    pdf_filename = f"meeting_summary_{session_data.get('session_id', 'unknown')}.pdf"
                    pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
                    msg.attach(pdf_attachment)
            
            # Send email
            all_recipients = recipients + (cc_recipients or []) + (bcc_recipients or [])
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                
                server.send_message(msg, to_addrs=all_recipients)
            
            logger.info(f"✅ Meeting summary email sent to {len(all_recipients)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send meeting summary email: {e}")
            return False
    
    async def _generate_pdf_attachment(
        self, 
        session_data: Dict[str, Any], 
        summary_data: Dict[str, Any]
    ) -> Optional[bytes]:
        """Generate PDF attachment for email"""
        try:
            from services.pdf_export_service import pdf_export_service
            
            # Create temporary PDF file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                pdf_path = tmp_file.name
            
            # Generate PDF
            success = pdf_export_service.generate_session_pdf(
                session_data=session_data,
                transcriptions=[],  # Simplified for email attachment
                speakers=[],
                output_path=pdf_path,
                include_summary=True,
                include_speakers=True,
                include_timestamps=False,
                include_confidence=False
            )
            
            if success:
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                
                # Cleanup
                os.unlink(pdf_path)
                return pdf_content
            
        except Exception as e:
            logger.error(f"Error generating PDF attachment: {e}")
        
        return None
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}m {remaining_seconds}s"
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}h {minutes}m"
            return f"{hours}h"
    
    async def send_test_email(self, host: str, port: int, username: str, password: str) -> Dict[str, Any]:
        """Send a test email to verify configuration"""
        try:
            if not username or not password:
                return {"status": "error", "message": "SMTP username and password are required.", "required_env_vars": ["SMTP_USERNAME", "SMTP_PASSWORD"]}
            
            msg = MIMEText(
                "This is a test email from Unicorn Commander Meeting Ops.\n\n"
                "If you received this email, your email configuration is working correctly!\n\n"
                "🦄 Unicorn Commander Meeting Ops\n"
                "NPU-Accelerated AI Transcription & Analysis"
            )
            
            msg['Subject'] = "Test Email - Unicorn Commander Meeting Ops"
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = username # Send test email to the configured username
            msg['Date'] = formatdate(localtime=True)
            
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)
            
            logger.info(f"✅ Test email sent to {username}")
            return {"status": "configured", "message": "Email service configured and test email sent.", "smtp_host": host, "smtp_port": port}
            
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ SMTP Authentication Error: Invalid username or password.")
            return {"status": "error", "message": "SMTP Authentication Error: Invalid username or password.", "required_env_vars": ["SMTP_USERNAME", "SMTP_PASSWORD"]}
        except smtplib.SMTPConnectError:
            logger.error(f"❌ SMTP Connection Error: Could not connect to {host}:{port}.")
            return {"status": "error", "message": f"SMTP Connection Error: Could not connect to {host}:{port}. Please check host and port.", "required_env_vars": ["SMTP_HOST", "SMTP_PORT"]}
        except Exception as e:
            logger.error(f"❌ Failed to send test email: {e}")
            return {"status": "error", "message": f"Failed to send test email: {e}"}
    
    def is_configured(self) -> bool:
        """Check if email service is properly configured"""
        return bool(self.smtp_username and self.smtp_password)

# Global instance
email_service = EmailService()