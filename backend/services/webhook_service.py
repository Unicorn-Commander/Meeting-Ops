"""
Webhook Service for Meeting Event Notifications
Sends real-time notifications to external systems about meeting events
"""

import asyncio
import json
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import httpx
from dataclasses import dataclass, asdict
import aiofiles

logger = logging.getLogger(__name__)

@dataclass
class WebhookEvent:
    """Webhook event data structure"""
    event_type: str
    event_id: str
    timestamp: datetime
    session_id: str
    data: Dict[str, Any]
    source: str = "unicorn-commander"
    version: str = "1.0"

@dataclass
class WebhookEndpoint:
    """Webhook endpoint configuration"""
    id: str
    name: str
    url: str
    secret: Optional[str] = None
    events: List[str] = None  # None means all events
    active: bool = True
    headers: Dict[str, str] = None
    retry_count: int = 3
    timeout: int = 30
    
class WebhookService:
    """Service for managing and sending webhook notifications"""
    
    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self.event_log: List[WebhookEvent] = []
        self.max_log_size = 1000
        
        # Supported event types
        self.EVENT_TYPES = {
            'session.created': 'Meeting session created',
            'session.started': 'Meeting recording started',
            'session.paused': 'Meeting recording paused',
            'session.resumed': 'Meeting recording resumed',
            'session.stopped': 'Meeting recording stopped',
            'session.completed': 'Meeting session completed',
            'session.deleted': 'Meeting session deleted',
            'transcription.completed': 'Transcription processing completed',
            'speaker.identified': 'New speaker identified',
            'summary.generated': 'Meeting summary generated',
            'calendar.meeting_scheduled': 'Calendar meeting scheduled',
            'calendar.conflict_detected': 'Calendar conflict detected',
            'wyoming.satellite_connected': 'Wyoming satellite connected',
            'wyoming.wake_word_detected': 'Wake word detected',
            'system.error': 'System error occurred',
            'system.startup': 'System started up',
            'system.shutdown': 'System shutting down'
        }
    
    def add_endpoint(self, endpoint: WebhookEndpoint) -> bool:
        """Add a new webhook endpoint"""
        try:
            self.endpoints[endpoint.id] = endpoint
            logger.info(f"✅ Webhook endpoint added: {endpoint.name} ({endpoint.url})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add webhook endpoint: {e}")
            return False
    
    def remove_endpoint(self, endpoint_id: str) -> bool:
        """Remove a webhook endpoint"""
        try:
            if endpoint_id in self.endpoints:
                endpoint = self.endpoints.pop(endpoint_id)
                logger.info(f"🗑️ Webhook endpoint removed: {endpoint.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to remove webhook endpoint: {e}")
            return False
    
    def update_endpoint(self, endpoint_id: str, updates: Dict[str, Any]) -> bool:
        """Update webhook endpoint configuration"""
        try:
            if endpoint_id not in self.endpoints:
                return False
            
            endpoint = self.endpoints[endpoint_id]
            for key, value in updates.items():
                if hasattr(endpoint, key):
                    setattr(endpoint, key, value)
            
            logger.info(f"📝 Webhook endpoint updated: {endpoint.name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update webhook endpoint: {e}")
            return False
    
    def get_endpoints(self) -> List[WebhookEndpoint]:
        """Get all webhook endpoints"""
        return list(self.endpoints.values())
    
    def get_endpoint(self, endpoint_id: str) -> Optional[WebhookEndpoint]:
        """Get specific webhook endpoint"""
        return self.endpoints.get(endpoint_id)
    
    async def send_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """Send event to all relevant webhook endpoints"""
        results = {}
        
        # Add to event log
        self.event_log.append(event)
        if len(self.event_log) > self.max_log_size:
            self.event_log.pop(0)
        
        # Send to all matching endpoints concurrently
        tasks = []
        for endpoint in self.endpoints.values():
            if self._should_send_to_endpoint(endpoint, event):
                tasks.append(self._send_to_endpoint(endpoint, event))
        
        if tasks:
            endpoint_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(endpoint_results):
                endpoint_id = list(self.endpoints.keys())[i]
                results[endpoint_id] = result
        
        return results
    
    def _should_send_to_endpoint(self, endpoint: WebhookEndpoint, event: WebhookEvent) -> bool:
        """Check if event should be sent to specific endpoint"""
        if not endpoint.active:
            return False
        
        # If no specific events configured, send all
        if not endpoint.events:
            return True
        
        # Check if event type is in endpoint's filter
        return event.event_type in endpoint.events
    
    async def _send_to_endpoint(self, endpoint: WebhookEndpoint, event: WebhookEvent) -> Dict[str, Any]:
        """Send event to specific webhook endpoint"""
        result = {
            'endpoint_id': endpoint.id,
            'endpoint_name': endpoint.name,
            'url': endpoint.url,
            'success': False,
            'status_code': None,
            'response': None,
            'error': None,
            'attempts': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Prepare payload
        payload = {
            'event': asdict(event),
            'timestamp': event.timestamp.isoformat(),
            'signature': None
        }
        
        # Add signature if secret is configured
        if endpoint.secret:
            payload['signature'] = self._generate_signature(payload, endpoint.secret)
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Unicorn-Commander-Webhook/1.0',
            'X-UC-Event-Type': event.event_type,
            'X-UC-Event-ID': event.event_id,
            'X-UC-Timestamp': event.timestamp.isoformat()
        }
        
        if endpoint.headers:
            headers.update(endpoint.headers)
        
        # Retry logic
        for attempt in range(endpoint.retry_count):
            result['attempts'] = attempt + 1
            
            try:
                async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                    response = await client.post(
                        endpoint.url,
                        json=payload,
                        headers=headers
                    )
                    
                    result['status_code'] = response.status_code
                    result['response'] = response.text[:500]  # Limit response size
                    
                    if response.status_code < 400:
                        result['success'] = True
                        logger.info(f"✅ Webhook sent successfully to {endpoint.name}: {event.event_type}")
                        break
                    else:
                        logger.warning(f"⚠️ Webhook failed to {endpoint.name}: HTTP {response.status_code}")
                        
            except asyncio.TimeoutError:
                error_msg = f"Timeout after {endpoint.timeout}s"
                result['error'] = error_msg
                logger.warning(f"⏰ Webhook timeout to {endpoint.name}: {error_msg}")
                
            except Exception as e:
                error_msg = str(e)
                result['error'] = error_msg
                logger.error(f"❌ Webhook error to {endpoint.name}: {error_msg}")
            
            # Wait before retry (exponential backoff)
            if attempt < endpoint.retry_count - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        return result
    
    def _generate_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """Generate HMAC signature for webhook payload"""
        try:
            # Remove signature field if present to avoid circular reference
            payload_copy = payload.copy()
            payload_copy.pop('signature', None)
            
            # Create canonical string
            canonical_string = json.dumps(payload_copy, sort_keys=True, separators=(',', ':'))
            
            # Generate HMAC-SHA256 signature
            signature = hmac.new(
                secret.encode('utf-8'),
                canonical_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return f"sha256={signature}"
            
        except Exception as e:
            logger.error(f"Failed to generate webhook signature: {e}")
            return ""
    
    def verify_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Verify webhook signature (for receiving webhooks)"""
        try:
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            expected_sig_header = f"sha256={expected_signature}"
            return hmac.compare_digest(signature, expected_sig_header)
            
        except Exception as e:
            logger.error(f"Failed to verify webhook signature: {e}")
            return False
    
    async def send_session_event(self, event_type: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send session-related webhook event"""
        event = WebhookEvent(
            event_type=event_type,
            event_id=f"{event_type}_{session_data.get('id', 'unknown')}_{int(datetime.now().timestamp())}",
            timestamp=datetime.now(),
            session_id=str(session_data.get('id', 'unknown')),
            data=session_data
        )
        
        return await self.send_event(event)
    
    async def send_transcription_event(self, session_id: str, transcription_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send transcription-related webhook event"""
        event = WebhookEvent(
            event_type='transcription.completed',
            event_id=f"transcription_{session_id}_{int(datetime.now().timestamp())}",
            timestamp=datetime.now(),
            session_id=session_id,
            data=transcription_data
        )
        
        return await self.send_event(event)
    
    async def send_calendar_event(self, event_type: str, calendar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send calendar-related webhook event"""
        event = WebhookEvent(
            event_type=f"calendar.{event_type}",
            event_id=f"calendar_{event_type}_{int(datetime.now().timestamp())}",
            timestamp=datetime.now(),
            session_id=calendar_data.get('session_id', 'unknown'),
            data=calendar_data
        )
        
        return await self.send_event(event)
    
    async def send_system_event(self, event_type: str, system_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send system-related webhook event"""
        event = WebhookEvent(
            event_type=f"system.{event_type}",
            event_id=f"system_{event_type}_{int(datetime.now().timestamp())}",
            timestamp=datetime.now(),
            session_id='system',
            data=system_data
        )
        
        return await self.send_event(event)
    
    def get_event_log(self, limit: int = 100, event_type: Optional[str] = None) -> List[WebhookEvent]:
        """Get recent webhook events"""
        events = self.event_log[-limit:] if limit else self.event_log
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events
    
    def get_endpoint_stats(self, endpoint_id: str) -> Dict[str, Any]:
        """Get statistics for specific endpoint"""
        if endpoint_id not in self.endpoints:
            return {}
        
        endpoint = self.endpoints[endpoint_id]
        
        # Count events sent to this endpoint (simplified)
        total_events = len([e for e in self.event_log 
                           if self._should_send_to_endpoint(endpoint, e)])
        
        return {
            'endpoint_id': endpoint_id,
            'name': endpoint.name,
            'url': endpoint.url,
            'active': endpoint.active,
            'total_events_sent': total_events,
            'event_types': endpoint.events or list(self.EVENT_TYPES.keys()),
            'last_event': self.event_log[-1].timestamp.isoformat() if self.event_log else None
        }
    
    async def test_endpoint(self, endpoint_id: str) -> Dict[str, Any]:
        """Test webhook endpoint with a test event"""
        if endpoint_id not in self.endpoints:
            return {'success': False, 'error': 'Endpoint not found'}
        
        test_event = WebhookEvent(
            event_type='system.test',
            event_id=f"test_{endpoint_id}_{int(datetime.now().timestamp())}",
            timestamp=datetime.now(),
            session_id='test',
            data={
                'message': 'This is a test webhook from Unicorn Commander',
                'test': True,
                'endpoint_id': endpoint_id
            }
        )
        
        endpoint = self.endpoints[endpoint_id]
        result = await self._send_to_endpoint(endpoint, test_event)
        
        return result

# Global webhook service instance
webhook_service = WebhookService()

# Event helper functions for easy integration
async def notify_session_created(session_data: Dict[str, Any]):
    """Notify that a new session was created"""
    return await webhook_service.send_session_event('session.created', session_data)

async def notify_session_started(session_data: Dict[str, Any]):
    """Notify that session recording started"""
    return await webhook_service.send_session_event('session.started', session_data)

async def notify_session_stopped(session_data: Dict[str, Any]):
    """Notify that session recording stopped"""
    return await webhook_service.send_session_event('session.stopped', session_data)

async def notify_transcription_completed(session_id: str, transcription_data: Dict[str, Any]):
    """Notify that transcription was completed"""
    return await webhook_service.send_transcription_event(session_id, transcription_data)

async def notify_meeting_scheduled(meeting_data: Dict[str, Any]):
    """Notify that a meeting was scheduled"""
    return await webhook_service.send_calendar_event('meeting_scheduled', meeting_data)

async def notify_wake_word_detected(wake_word_data: Dict[str, Any]):
    """Notify that wake word was detected"""
    event = WebhookEvent(
        event_type='wyoming.wake_word_detected',
        event_id=f"wake_word_{int(datetime.now().timestamp())}",
        timestamp=datetime.now(),
        session_id='wyoming',
        data=wake_word_data
    )
    return await webhook_service.send_event(event)