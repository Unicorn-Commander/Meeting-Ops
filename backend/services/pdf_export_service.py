"""
PDF Export Service for Meeting Transcriptions
Generates professional PDF reports with branding and formatting
"""
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics import renderPDF

logger = logging.getLogger(__name__)

class PDFExportService:
    """Service for generating professional PDF exports of meeting sessions"""
    
    def __init__(self):
        self.page_size = A4
        self.margin = 0.75 * inch
        self.setup_styles()
    
    def setup_styles(self):
        """Set up custom styles for the PDF"""
        self.styles = getSampleStyleSheet()
        
        # Custom brand colors
        self.brand_primary = HexColor('#8B5CF6')  # Purple
        self.brand_secondary = HexColor('#EC4899')  # Pink
        self.brand_accent = HexColor('#10B981')  # Green
        self.text_dark = HexColor('#1F2937')
        self.text_light = HexColor('#6B7280')
        
        # Custom styles
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=self.brand_primary,
            alignment=TA_CENTER,
            spaceAfter=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=self.text_light,
            alignment=TA_CENTER,
            spaceAfter=30
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=self.brand_primary,
            spaceBefore=20,
            spaceAfter=10,
            leftIndent=0
        ))
        
        self.styles.add(ParagraphStyle(
            name='SpeakerName',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=self.brand_secondary,
            fontName='Helvetica-Bold',
            spaceBefore=8,
            spaceAfter=4
        ))
        
        self.styles.add(ParagraphStyle(
            name='TranscriptText',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=self.text_dark,
            leftIndent=20,
            spaceAfter=6,
            alignment=TA_JUSTIFY
        ))
        
        self.styles.add(ParagraphStyle(
            name='MetadataStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self.text_light,
            leftIndent=20,
            spaceAfter=2
        ))
        
        self.styles.add(ParagraphStyle(
            name='Summary',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=self.text_dark,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
            leftIndent=10,
            rightIndent=10
        ))
    
    def create_header_footer(self, canvas, doc):
        """Draw header and footer on each page"""
        canvas.saveState()
        
        # Header
        canvas.setFillColor(self.brand_primary)
        canvas.rect(0, doc.height + doc.topMargin - 30, doc.width + 2*doc.leftMargin, 30, fill=1)
        
        canvas.setFillColor(white)
        canvas.setFont('Helvetica-Bold', 12)
        canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 20, 
                         "🦄 Unicorn Commander: Meeting Ops")
        
        # Footer
        canvas.setFillColor(self.text_light)
        canvas.setFont('Helvetica', 9)
        footer_text = f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        canvas.drawRightString(doc.width + doc.leftMargin, 20, footer_text)
        
        canvas.setFont('Helvetica', 9)
        canvas.drawString(doc.leftMargin, 20, f"Page {canvas.getPageNumber()}")
        
        canvas.restoreState()
    
    def generate_session_pdf(
        self, 
        session_data: Dict[str, Any],
        transcriptions: List[Dict[str, Any]], 
        speakers: List[Dict[str, Any]],
        output_path: str,
        include_summary: bool = True,
        include_speakers: bool = True,
        include_timestamps: bool = True,
        include_confidence: bool = False
    ) -> bool:
        """
        Generate a professional PDF report for a meeting session
        
        Args:
            session_data: Session information
            transcriptions: List of transcription segments
            speakers: List of speaker information
            output_path: Path to save the PDF file
            include_summary: Whether to include AI-generated summary
            include_speakers: Whether to include speaker identification
            include_timestamps: Whether to include timestamps
            include_confidence: Whether to include confidence scores
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=self.page_size,
                rightMargin=self.margin,
                leftMargin=self.margin,
                topMargin=self.margin + 40,  # Extra space for header
                bottomMargin=self.margin + 20  # Extra space for footer
            )
            
            # Build content
            story = []
            
            # Title Page
            story.extend(self._create_title_page(session_data))
            story.append(PageBreak())
            
            # Executive Summary
            if include_summary:
                story.extend(self._create_summary_section(session_data))
                story.append(PageBreak())
            
            # Session Information
            story.extend(self._create_session_info(session_data, speakers))
            
            # Speaker Analysis
            if include_speakers and speakers:
                story.extend(self._create_speaker_analysis(speakers))
            
            # Full Transcript
            story.extend(self._create_transcript_section(
                transcriptions, 
                speakers,
                include_timestamps,
                include_confidence
            ))
            
            # Technical Details
            story.extend(self._create_technical_section(session_data))
            
            # Build PDF with custom page template
            frame = Frame(
                doc.leftMargin, doc.bottomMargin, 
                doc.width, doc.height,
                id='normal'
            )
            
            template = PageTemplate(
                id='main',
                frames=frame,
                onPage=self.create_header_footer
            )
            
            doc.addPageTemplates([template])
            doc.build(story)
            
            logger.info(f"✅ PDF generated successfully: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error generating PDF: {e}")
            return False
    
    def _create_title_page(self, session_data: Dict[str, Any]) -> List:
        """Create the title page"""
        story = []
        
        # Main title
        story.append(Spacer(1, 2*inch))
        story.append(Paragraph(session_data.get('name', 'Meeting Transcript'), 
                              self.styles['CustomTitle']))
        
        # Subtitle with date
        start_time = datetime.fromisoformat(session_data.get('start_time', ''))
        subtitle = f"Meeting held on {start_time.strftime('%A, %B %d, %Y')}"
        story.append(Paragraph(subtitle, self.styles['Subtitle']))
        
        # Meeting metadata table
        meeting_data = [
            ['Meeting Type:', session_data.get('meeting_type', 'General Meeting').title()],
            ['Duration:', self._format_duration(session_data.get('duration_seconds', 0))],
            ['Participants:', f"{session_data.get('total_speakers', 0)} speakers identified"],
            ['NPU Accelerated:', '✅ Yes' if session_data.get('npu_accelerated') else '❌ No'],
            ['Transcription Segments:', str(session_data.get('total_transcriptions', 0))],
        ]
        
        if session_data.get('description'):
            meeting_data.insert(1, ['Description:', session_data['description']])
        
        table = Table(meeting_data, colWidths=[2*inch, 4*inch])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('TEXTCOLOR', (0, 0), (0, -1), self.brand_primary),
            ('TEXTCOLOR', (1, 0), (1, -1), self.text_dark),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(Spacer(1, inch))
        story.append(table)
        story.append(Spacer(1, 2*inch))
        
        # Powered by section
        story.append(Paragraph(
            "Powered by Unicorn Commander Meeting Ops<br/>"
            "NPU-Accelerated AI Transcription & Analysis", 
            self.styles['Subtitle']
        ))
        
        return story
    
    def _create_summary_section(self, session_data: Dict[str, Any]) -> List:
        """Create executive summary section"""
        story = []
        
        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        
        # Placeholder for AI-generated summary
        summary_text = session_data.get('ai_summary', 
            "This meeting covered key discussion points and decisions. "
            "AI-powered summarization will be available in future versions."
        )
        
        story.append(Paragraph(summary_text, self.styles['Summary']))
        story.append(Spacer(1, 20))
        
        # Key metrics
        story.append(Paragraph("Key Metrics", self.styles['SectionHeader']))
        
        metrics_data = [
            ['Total Speaking Time:', self._format_duration(session_data.get('duration_seconds', 0))],
            ['Average Confidence:', f"{session_data.get('avg_confidence', 95):.1f}%"],
            ['Processing Performance:', '2,985x real-time' if session_data.get('npu_accelerated') else '13.6x real-time'],
            ['Words Transcribed:', f"~{session_data.get('total_transcriptions', 0) * 15:,}"],
        ]
        
        metrics_table = Table(metrics_data, colWidths=[2.5*inch, 3*inch])
        metrics_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), self.brand_primary),
            ('TEXTCOLOR', (1, 0), (1, -1), self.text_dark),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(metrics_table)
        return story
    
    def _create_session_info(self, session_data: Dict[str, Any], speakers: List[Dict[str, Any]]) -> List:
        """Create session information section"""
        story = []
        
        story.append(Paragraph("Session Information", self.styles['SectionHeader']))
        
        start_time = datetime.fromisoformat(session_data.get('start_time', ''))
        end_time = None
        if session_data.get('end_time'):
            end_time = datetime.fromisoformat(session_data['end_time'])
        
        info_data = [
            ['Session ID:', session_data.get('session_id', 'Unknown')],
            ['Start Time:', start_time.strftime('%I:%M %p on %B %d, %Y')],
        ]
        
        if end_time:
            info_data.append(['End Time:', end_time.strftime('%I:%M %p on %B %d, %Y')])
        
        info_data.extend([
            ['Status:', session_data.get('status', 'Unknown').title()],
            ['Total Duration:', self._format_duration(session_data.get('duration_seconds', 0))],
        ])
        
        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), self.brand_primary),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 20))
        
        return story
    
    def _create_speaker_analysis(self, speakers: List[Dict[str, Any]]) -> List:
        """Create speaker analysis section"""
        story = []
        
        story.append(Paragraph("Speaker Analysis", self.styles['SectionHeader']))
        
        if not speakers:
            story.append(Paragraph("No speaker information available.", self.styles['Normal']))
            return story
        
        # Create speaker summary table
        speaker_data = [['Speaker ID', 'Speaking Time', 'Segments', 'Participation %']]
        
        total_segments = sum(speaker.get('total_segments', 0) for speaker in speakers)
        
        for speaker in speakers:
            speaker_id = speaker.get('speaker_id', 'Unknown')
            speaking_time = self._format_duration(speaker.get('total_speaking_time', 0))
            segments = speaker.get('total_segments', 0)
            participation = (segments / total_segments * 100) if total_segments > 0 else 0
            
            speaker_data.append([
                speaker_id,
                speaking_time,
                str(segments),
                f"{participation:.1f}%"
            ])
        
        speaker_table = Table(speaker_data, colWidths=[1.5*inch, 1.5*inch, 1*inch, 1.5*inch])
        speaker_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.brand_primary),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, grey),
        ]))
        
        story.append(speaker_table)
        story.append(Spacer(1, 20))
        
        return story
    
    def _create_transcript_section(
        self, 
        transcriptions: List[Dict[str, Any]], 
        speakers: List[Dict[str, Any]],
        include_timestamps: bool,
        include_confidence: bool
    ) -> List:
        """Create the full transcript section"""
        story = []
        
        story.append(Paragraph("Full Transcript", self.styles['SectionHeader']))
        
        if not transcriptions:
            story.append(Paragraph("No transcription data available.", self.styles['Normal']))
            return story
        
        # Create speaker ID mapping
        speaker_map = {speaker.get('speaker_id'): f"Speaker {i+1}" 
                      for i, speaker in enumerate(speakers)}
        
        current_speaker = None
        
        for i, transcript in enumerate(transcriptions):
            speaker_id = transcript.get('speaker_id')
            text = transcript.get('text', '').strip()
            
            if not text:
                continue
            
            # Add speaker name if changed
            if speaker_id != current_speaker:
                current_speaker = speaker_id
                speaker_name = speaker_map.get(speaker_id, speaker_id or "Unknown Speaker")
                story.append(Paragraph(speaker_name, self.styles['SpeakerName']))
            
            # Add transcript text
            story.append(Paragraph(text, self.styles['TranscriptText']))
            
            # Add metadata if requested
            if include_timestamps or include_confidence:
                metadata_parts = []
                
                if include_timestamps and transcript.get('timestamp'):
                    timestamp = datetime.fromisoformat(transcript['timestamp'])
                    metadata_parts.append(f"Time: {timestamp.strftime('%I:%M:%S %p')}")
                
                if include_confidence and transcript.get('confidence'):
                    confidence = transcript['confidence'] * 100
                    metadata_parts.append(f"Confidence: {confidence:.1f}%")
                
                if metadata_parts:
                    metadata_text = " | ".join(metadata_parts)
                    story.append(Paragraph(metadata_text, self.styles['MetadataStyle']))
            
            # Add small spacer between segments
            if i < len(transcriptions) - 1:
                story.append(Spacer(1, 6))
        
        return story
    
    def _create_technical_section(self, session_data: Dict[str, Any]) -> List:
        """Create technical details section"""
        story = []
        
        story.append(PageBreak())
        story.append(Paragraph("Technical Details", self.styles['SectionHeader']))
        
        tech_data = [
            ['Transcription Engine:', 'WhisperX with NPU Acceleration' if session_data.get('npu_accelerated') else 'Whisper CPU'],
            ['Processing Speed:', '2,985x real-time' if session_data.get('npu_accelerated') else '13.6x real-time'],
            ['Speaker Diarization:', 'TitanNet + Spectral Clustering'],
            ['Audio Quality:', '16kHz, 16-bit, Mono'],
            ['Export Format:', 'PDF with embedded metadata'],
            ['Generated By:', 'Unicorn Commander Meeting Ops v1.0'],
        ]
        
        tech_table = Table(tech_data, colWidths=[2.5*inch, 3.5*inch])
        tech_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), self.brand_primary),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(tech_table)
        story.append(Spacer(1, 20))
        
        # Footer note
        story.append(Paragraph(
            "This document was generated using NPU-accelerated AI transcription technology. "
            "For questions about this transcript, please contact your system administrator.",
            self.styles['Normal']
        ))
        
        return story
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"

# Global instance
pdf_export_service = PDFExportService()