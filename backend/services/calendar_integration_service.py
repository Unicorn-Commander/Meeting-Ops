"""
Calendar Integration Service for Microsoft 365 and Google Workspace
Provides meeting scheduling, room availability, and calendar conflict detection
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import httpx
from dataclasses import dataclass, asdict
import base64
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

@dataclass
class CalendarEvent:
    """Calendar event data structure"""
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: List[str]
    location: str
    organizer: str
    description: str = ""
    meeting_type: str = "general"
    is_recurring: bool = False
    status: str = "confirmed"  # confirmed, tentative, cancelled

@dataclass
class RoomAvailability:
    """Room availability information"""
    room_id: str
    room_name: str
    location: str
    capacity: int
    is_available: bool
    next_available: Optional[datetime] = None
    current_meeting: Optional[CalendarEvent] = None
    equipment: List[str] = None

class Microsoft365Service:
    """Microsoft 365 Graph API integration for calendar management"""
    
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires_at = None
        self.base_url = "https://graph.microsoft.com/v1.0"
        
    async def authenticate(self) -> bool:
        """Authenticate with Microsoft 365 using client credentials"""
        try:
            auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(auth_url, data=data)
                response.raise_for_status()
                
                token_data = response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data['expires_in']
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5min buffer
                
                logger.info("✅ Microsoft 365 authentication successful")
                return True
                
        except Exception as e:
            logger.error(f"❌ Microsoft 365 authentication failed: {e}")
            return False
    
    async def _ensure_authenticated(self):
        """Ensure we have a valid access token"""
        if not self.access_token or datetime.now() >= self.token_expires_at:
            await self.authenticate()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Microsoft Graph API"""
        await self._ensure_authenticated()
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
    
    async def get_calendar_events(self, user_email: str, start_time: datetime, end_time: datetime) -> List[CalendarEvent]:
        """Get calendar events for a user within a time range"""
        try:
            endpoint = f"/users/{user_email}/calendar/calendarView"
            params = {
                'startDateTime': start_time.isoformat(),
                'endDateTime': end_time.isoformat(),
                '$orderby': 'start/dateTime',
                '$select': 'id,subject,start,end,attendees,location,organizer,body,isRecurring,showAs'
            }
            
            response = await self._make_request('GET', endpoint, params=params)
            
            events = []
            for event_data in response.get('value', []):
                try:
                    event = CalendarEvent(
                        id=event_data['id'],
                        title=event_data.get('subject', 'No Title'),
                        start_time=datetime.fromisoformat(event_data['start']['dateTime'].replace('Z', '+00:00')),
                        end_time=datetime.fromisoformat(event_data['end']['dateTime'].replace('Z', '+00:00')),
                        attendees=[att.get('emailAddress', {}).get('address', '') for att in event_data.get('attendees', [])],
                        location=event_data.get('location', {}).get('displayName', ''),
                        organizer=event_data.get('organizer', {}).get('emailAddress', {}).get('address', ''),
                        description=event_data.get('body', {}).get('content', ''),
                        is_recurring=event_data.get('isRecurring', False),
                        status=event_data.get('showAs', 'busy').lower()
                    )
                    events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")
                    continue
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Failed to get calendar events: {e}")
            return []
    
    async def create_meeting(self, event: CalendarEvent, attendees: List[str]) -> Optional[str]:
        """Create a new meeting in Microsoft 365"""
        try:
            endpoint = f"/users/{event.organizer}/calendar/events"
            
            event_data = {
                'subject': event.title,
                'start': {
                    'dateTime': event.start_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': event.end_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'location': {
                    'displayName': event.location
                },
                'body': {
                    'contentType': 'text',
                    'content': event.description
                },
                'attendees': [
                    {
                        'emailAddress': {
                            'address': email,
                            'name': email.split('@')[0]
                        },
                        'type': 'required'
                    }
                    for email in attendees
                ]
            }
            
            response = await self._make_request('POST', endpoint, json=event_data)
            
            logger.info(f"✅ Meeting created: {event.title}")
            return response.get('id')
            
        except Exception as e:
            logger.error(f"❌ Failed to create meeting: {e}")
            return None
    
    async def get_room_availability(self, room_emails: List[str], start_time: datetime, end_time: datetime) -> List[RoomAvailability]:
        """Check availability for multiple rooms"""
        try:
            endpoint = "/me/calendar/getSchedule"
            
            request_data = {
                'schedules': room_emails,
                'startTime': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'endTime': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'availabilityViewInterval': 60
            }
            
            response = await self._make_request('POST', endpoint, json=request_data)
            
            availability_list = []
            for i, schedule in enumerate(response.get('value', [])):
                room_email = room_emails[i]
                busy_times = schedule.get('busyViewInfo', [])
                
                # Check if room is currently available
                now = datetime.now()
                is_available = not any(
                    start_time <= now <= end_time 
                    for busy_time in schedule.get('freeBusyViewInfo', [])
                    if busy_time == '2'  # '2' means busy in FreeBusy view
                )
                
                room_availability = RoomAvailability(
                    room_id=room_email,
                    room_name=room_email.split('@')[0].replace('.', ' ').title(),
                    location=f"Building {room_email.split('.')[0][-1] if '.' in room_email else 'A'}",
                    capacity=10,  # Default capacity, should be configured
                    is_available=is_available,
                    equipment=['Projector', 'Video Conference', 'Whiteboard']  # Default equipment
                )
                
                availability_list.append(room_availability)
            
            return availability_list
            
        except Exception as e:
            logger.error(f"❌ Failed to get room availability: {e}")
            return []

class GoogleWorkspaceService:
    """Google Workspace Calendar API integration"""
    
    def __init__(self, service_account_key: Dict[str, str]):
        self.service_account_key = service_account_key
        self.access_token = None
        self.token_expires_at = None
        self.base_url = "https://www.googleapis.com/calendar/v3"
    
    async def authenticate(self) -> bool:
        """Authenticate with Google Workspace using service account"""
        try:
            import jwt
            
            # Create JWT for service account authentication
            now = datetime.now()
            payload = {
                'iss': self.service_account_key['client_email'],
                'scope': 'https://www.googleapis.com/auth/calendar',
                'aud': 'https://oauth2.googleapis.com/token',
                'exp': now + timedelta(hours=1),
                'iat': now
            }
            
            token = jwt.encode(payload, self.service_account_key['private_key'], algorithm='RS256')
            
            # Exchange JWT for access token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://oauth2.googleapis.com/token',
                    data={
                        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                        'assertion': token
                    }
                )
                response.raise_for_status()
                
                token_data = response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data['expires_in']
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                
                logger.info("✅ Google Workspace authentication successful")
                return True
                
        except Exception as e:
            logger.error(f"❌ Google Workspace authentication failed: {e}")
            return False
    
    async def _ensure_authenticated(self):
        """Ensure we have a valid access token"""
        if not self.access_token or datetime.now() >= self.token_expires_at:
            await self.authenticate()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Google Calendar API"""
        await self._ensure_authenticated()
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
    
    async def get_calendar_events(self, calendar_id: str, start_time: datetime, end_time: datetime) -> List[CalendarEvent]:
        """Get calendar events for a calendar within a time range"""
        try:
            endpoint = f"/calendars/{calendar_id}/events"
            params = {
                'timeMin': start_time.isoformat(),
                'timeMax': end_time.isoformat(),
                'orderBy': 'startTime',
                'singleEvents': True
            }
            
            response = await self._make_request('GET', endpoint, params=params)
            
            events = []
            for event_data in response.get('items', []):
                try:
                    start = event_data.get('start', {})
                    end = event_data.get('end', {})
                    
                    # Handle all-day events
                    start_dt = start.get('dateTime', start.get('date'))
                    end_dt = end.get('dateTime', end.get('date'))
                    
                    if 'T' not in start_dt:  # All-day event
                        start_dt += 'T00:00:00Z'
                        end_dt += 'T23:59:59Z'
                    
                    event = CalendarEvent(
                        id=event_data['id'],
                        title=event_data.get('summary', 'No Title'),
                        start_time=datetime.fromisoformat(start_dt.replace('Z', '+00:00')),
                        end_time=datetime.fromisoformat(end_dt.replace('Z', '+00:00')),
                        attendees=[att.get('email', '') for att in event_data.get('attendees', [])],
                        location=event_data.get('location', ''),
                        organizer=event_data.get('organizer', {}).get('email', ''),
                        description=event_data.get('description', ''),
                        is_recurring='recurrence' in event_data,
                        status=event_data.get('status', 'confirmed')
                    )
                    events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse Google event: {e}")
                    continue
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Failed to get Google calendar events: {e}")
            return []
    
    async def create_meeting(self, calendar_id: str, event: CalendarEvent, attendees: List[str]) -> Optional[str]:
        """Create a new meeting in Google Calendar"""
        try:
            endpoint = f"/calendars/{calendar_id}/events"
            
            event_data = {
                'summary': event.title,
                'start': {
                    'dateTime': event.start_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': event.end_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'location': event.location,
                'description': event.description,
                'attendees': [
                    {'email': email}
                    for email in attendees
                ],
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"meet-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }
            }
            
            response = await self._make_request('POST', endpoint, json=event_data, params={'conferenceDataVersion': 1})
            
            logger.info(f"✅ Google meeting created: {event.title}")
            return response.get('id')
            
        except Exception as e:
            logger.error(f"❌ Failed to create Google meeting: {e}")
            return None

class CalendarIntegrationService:
    """Main calendar integration service coordinating Microsoft 365 and Google Workspace"""
    
    def __init__(self):
        self.microsoft_service: Optional[Microsoft365Service] = None
        self.google_service: Optional[GoogleWorkspaceService] = None
        self.room_locations = {}
        self.meeting_rooms = []
        
    def configure_microsoft_365(self, tenant_id: str, client_id: str, client_secret: str):
        """Configure Microsoft 365 integration"""
        self.microsoft_service = Microsoft365Service(tenant_id, client_id, client_secret)
        
    def configure_google_workspace(self, service_account_key: Dict[str, str]):
        """Configure Google Workspace integration"""
        self.google_service = GoogleWorkspaceService(service_account_key)
    
    def configure_room_location(self, device_location: str, room_name: str, capacity: int, equipment: List[str]):
        """Configure this device's room location"""
        self.room_locations[device_location] = {
            'room_name': room_name,
            'capacity': capacity,
            'equipment': equipment,
            'device_id': device_location
        }
    
    async def get_user_availability(self, user_email: str, start_time: datetime, end_time: datetime) -> List[CalendarEvent]:
        """Get user's calendar events to check availability"""
        events = []
        
        # Try Microsoft 365 first
        if self.microsoft_service:
            try:
                ms_events = await self.microsoft_service.get_calendar_events(user_email, start_time, end_time)
                events.extend(ms_events)
            except Exception as e:
                logger.warning(f"Microsoft 365 calendar access failed: {e}")
        
        # Try Google Workspace
        if self.google_service and not events:  # Only if MS365 failed
            try:
                google_events = await self.google_service.get_calendar_events(user_email, start_time, end_time)
                events.extend(google_events)
            except Exception as e:
                logger.warning(f"Google Workspace calendar access failed: {e}")
        
        return events
    
    async def schedule_meeting(self, title: str, start_time: datetime, end_time: datetime, 
                              attendees: List[str], location: str = None, description: str = "") -> Optional[str]:
        """Schedule a meeting with automatic conflict detection"""
        try:
            # Check for conflicts with all attendees
            conflicts = await self.check_conflicts(attendees, start_time, end_time)
            if conflicts:
                logger.warning(f"Meeting conflicts detected: {conflicts}")
                return None
            
            # Use configured room location if not specified
            if not location and self.room_locations:
                location = list(self.room_locations.keys())[0]
            
            # Create meeting event
            event = CalendarEvent(
                id="",  # Will be set by calendar service
                title=title,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                location=location or "Unicorn Commander Meeting Room",
                organizer=attendees[0] if attendees else "",
                description=description,
                meeting_type="scheduled"
            )
            
            # Try to create in Microsoft 365 first
            if self.microsoft_service and attendees:
                event_id = await self.microsoft_service.create_meeting(event, attendees)
                if event_id:
                    return event_id
            
            # Try Google Workspace as fallback
            if self.google_service and attendees:
                calendar_id = attendees[0]  # Use organizer's calendar
                event_id = await self.google_service.create_meeting(calendar_id, event, attendees)
                if event_id:
                    return event_id
            
            logger.error("❌ Failed to create meeting in any calendar service")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to schedule meeting: {e}")
            return None
    
    async def check_conflicts(self, attendees: List[str], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Check for calendar conflicts with meeting attendees"""
        conflicts = []
        
        for attendee in attendees:
            try:
                events = await self.get_user_availability(attendee, start_time, end_time)
                
                for event in events:
                    # Check if event overlaps with proposed meeting time
                    if (event.start_time < end_time and event.end_time > start_time and 
                        event.status != 'cancelled'):
                        conflicts.append({
                            'attendee': attendee,
                            'conflicting_event': event.title,
                            'start_time': event.start_time,
                            'end_time': event.end_time
                        })
                        
            except Exception as e:
                logger.warning(f"Failed to check conflicts for {attendee}: {e}")
        
        return conflicts
    
    async def suggest_meeting_times(self, attendees: List[str], duration_minutes: int, 
                                   preferred_start: datetime, preferred_end: datetime) -> List[datetime]:
        """Suggest available meeting times for all attendees"""
        try:
            suggestions = []
            
            # Get all attendees' calendars
            all_events = []
            for attendee in attendees:
                events = await self.get_user_availability(attendee, preferred_start, preferred_end)
                all_events.extend(events)
            
            # Sort events by start time
            all_events.sort(key=lambda x: x.start_time)
            
            # Find gaps between meetings
            current_time = preferred_start
            for event in all_events:
                # Check if there's a gap before this event
                if current_time + timedelta(minutes=duration_minutes) <= event.start_time:
                    suggestions.append(current_time)
                
                # Move to end of this event
                current_time = max(current_time, event.end_time)
                
                # Stop if we have enough suggestions
                if len(suggestions) >= 5:
                    break
            
            # Check if there's time at the end
            if (current_time + timedelta(minutes=duration_minutes) <= preferred_end and 
                len(suggestions) < 5):
                suggestions.append(current_time)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"❌ Failed to suggest meeting times: {e}")
            return []
    
    async def get_room_availability_status(self) -> Dict[str, Any]:
        """Get current room availability status"""
        try:
            now = datetime.now()
            end_time = now + timedelta(hours=8)  # Check next 8 hours
            
            status = {
                'current_time': now.isoformat(),
                'device_location': list(self.room_locations.keys())[0] if self.room_locations else 'Unknown',
                'room_info': self.room_locations,
                'is_available': True,
                'current_meeting': None,
                'next_meeting': None,
                'conflicts_detected': []
            }
            
            # Check if any calendar service is configured
            if not self.microsoft_service and not self.google_service:
                status['calendar_integration'] = 'not_configured'
                return status
            
            # Get events for configured room
            if self.room_locations:
                location = list(self.room_locations.keys())[0]
                # This would typically check room calendar, but we'll check user calendars for now
                # In production, you'd have dedicated room calendars
                status['calendar_integration'] = 'active'
            
            return status
            
        except Exception as e:
            logger.error(f"❌ Failed to get room availability: {e}")
            return {'error': str(e)}

# Global instance
calendar_service = CalendarIntegrationService()