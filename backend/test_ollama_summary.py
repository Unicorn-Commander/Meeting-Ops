#!/usr/bin/env python3
"""
Test script to demonstrate Ollama summarization working with meeting transcripts
"""
import asyncio
from services.llm_summarization_service import llm_summarization_service

async def test_ollama_summarization():
    # Sample meeting data
    session_data = {
        'meeting_type': 'Team Standup',
        'duration_seconds': 900,  # 15 minutes
        'speakers': [
            {'speaker_id': 'speaker_1'},
            {'speaker_id': 'speaker_2'},
            {'speaker_id': 'speaker_3'}
        ]
    }
    
    # Sample transcriptions with speaker labels
    transcriptions = [
        {'speaker_id': 'speaker_1', 'text': "Good morning everyone. Let's start with our daily standup. I'll go first.", 'confidence': 0.95},
        {'speaker_id': 'speaker_1', 'text': "Yesterday I completed the API integration for the payment gateway.", 'confidence': 0.92},
        {'speaker_id': 'speaker_1', 'text': "Today I'm working on the error handling and retry logic.", 'confidence': 0.94},
        {'speaker_id': 'speaker_1', 'text': "No blockers on my end.", 'confidence': 0.96},
        
        {'speaker_id': 'speaker_2', 'text': "Thanks. I'll go next.", 'confidence': 0.93},
        {'speaker_id': 'speaker_2', 'text': "Yesterday I finished the UI mockups for the dashboard redesign.", 'confidence': 0.91},
        {'speaker_id': 'speaker_2', 'text': "Today I'm starting on the React components implementation.", 'confidence': 0.94},
        {'speaker_id': 'speaker_2', 'text': "I might need help with the state management part later.", 'confidence': 0.89},
        
        {'speaker_id': 'speaker_3', 'text': "I can help with that. My update:", 'confidence': 0.95},
        {'speaker_id': 'speaker_3', 'text': "Yesterday I deployed the latest build to staging and fixed two critical bugs.", 'confidence': 0.93},
        {'speaker_id': 'speaker_3', 'text': "Today I'm working on performance optimization for the search feature.", 'confidence': 0.92},
        {'speaker_id': 'speaker_3', 'text': "We should discuss the database indexing strategy in our next meeting.", 'confidence': 0.90},
        
        {'speaker_id': 'speaker_1', 'text': "Great, let's schedule that for tomorrow. Any other updates?", 'confidence': 0.94},
        {'speaker_id': 'speaker_2', 'text': "Just a reminder that the client demo is on Friday.", 'confidence': 0.96},
        {'speaker_id': 'speaker_3', 'text': "Right, we should do a dry run on Thursday.", 'confidence': 0.93},
        {'speaker_id': 'speaker_1', 'text': "Agreed. Let's wrap up. Have a productive day everyone!", 'confidence': 0.95}
    ]
    
    speakers = session_data['speakers']
    
    print("🚀 Testing Ollama Summarization Service")
    print(f"📊 Session: {session_data['meeting_type']} ({session_data['duration_seconds']//60} minutes)")
    print(f"👥 Participants: {len(speakers)}")
    print(f"💬 Transcript segments: {len(transcriptions)}")
    print("\n" + "="*60 + "\n")
    
    # Test LLM status
    status = llm_summarization_service.get_status()
    print("🔍 LLM Service Status:")
    print(f"  - Ollama Available: {status['ollama_available']}")
    print(f"  - Ollama URL: {status['ollama_url']}")
    print(f"  - Ollama Model: {status['ollama_model']}")
    print(f"  - Available Providers: {status['available_providers']}")
    
    if not status['ollama_available']:
        print("❌ Ollama is not available. Please ensure Ollama is running on port 11434")
        return
    
    print("\n" + "="*60 + "\n")
    print("🤖 Generating comprehensive summary with Ollama (gemma3n:latest)...")
    
    # Generate comprehensive summary
    try:
        summary = await llm_summarization_service.generate_comprehensive_summary(
            session_data=session_data,
            transcriptions=transcriptions,
            speakers=speakers,
            summary_style='executive',
            focus_areas=['action_items', 'decisions', 'blockers']
        )
        
        print("\n✅ Summary generated successfully!\n")
        print("="*60)
        
        # Display results
        print("\n📝 EXECUTIVE SUMMARY:")
        print("-" * 40)
        print(summary.get('executive_summary', 'No summary available'))
        
        print("\n📌 ACTION ITEMS:")
        print("-" * 40)
        for item in summary.get('action_items', []):
            print(f"• [{item.get('priority', 'medium')}] {item.get('task', 'Unknown task')}")
            if item.get('assignee') != 'Unknown':
                print(f"  Assigned to: {item.get('assignee')}")
            if item.get('deadline') != 'Not specified':
                print(f"  Due: {item.get('deadline')}")
        
        print("\n🎯 KEY DECISIONS:")
        print("-" * 40)
        for decision in summary.get('key_decisions', []):
            print(f"• {decision.get('decision', 'Unknown decision')}")
            if decision.get('rationale'):
                print(f"  Reason: {decision.get('rationale')}")
        
        print("\n💭 DISCUSSION TOPICS:")
        print("-" * 40)
        for topic in summary.get('topics', []):
            print(f"• {topic.get('topic', 'Unknown topic')} ({topic.get('time_percent', 0)}% of meeting)")
            print(f"  Status: {topic.get('status', 'unknown')}")
        
        print("\n📊 MEETING METRICS:")
        print("-" * 40)
        metrics = summary.get('quality_metrics', {})
        print(f"• Duration: {metrics.get('duration_minutes', 0)} minutes")
        print(f"• Participants: {metrics.get('total_speakers', 0)}")
        print(f"• Participation Balance: {metrics.get('speaker_participation_balance', 0)*100:.0f}%")
        print(f"• Average Confidence: {metrics.get('avg_confidence', 0)*100:.0f}%")
        
        print("\n🎭 SENTIMENT ANALYSIS:")
        print("-" * 40)
        sentiment = summary.get('sentiment', {})
        print(f"• Overall Tone: {sentiment.get('overall_tone', 'neutral')}")
        print(f"• Energy Level: {sentiment.get('energy_level', 'medium')}")
        print(f"• Collaboration: {sentiment.get('collaboration', 'good')}")
        print(f"• Engagement: {sentiment.get('engagement', 'medium')}")
        
        print("\n➡️ NEXT STEPS:")
        print("-" * 40)
        for step in summary.get('next_steps', []):
            print(f"• {step}")
            
    except Exception as e:
        print(f"❌ Error generating summary: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🦄 Unicorn Commander - Ollama Summarization Test")
    print("=" * 60)
    asyncio.run(test_ollama_summarization())