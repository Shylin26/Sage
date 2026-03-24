import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from models.signals import RawSignal, SignalSource
from config import get_settings

settings = get_settings()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly"
]

class CalendarReader:
    def __init__(self):
        self.credentials_path = "data/credentials.json"
        self.token_path       = "data/token.json"
        self.service          = None

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        self.service = build("calendar", "v3", credentials=creds)

    def _fetch_events_sync(self, time_min: str, time_max: str) -> list:
        events_result = self.service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    async def fetch_signals(self) -> list[RawSignal]:
        if not self.service:
            self.authenticate()

        # Fetch events for today (from midnight to midnight of next day)
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(
            None, self._fetch_events_sync, start_of_day.isoformat(), end_of_day.isoformat()
        )

        signals = []
        for event in events:
            # Skip full-day events if they don't have a specific dateTime
            if 'dateTime' not in event.get('start', {}):
                continue
                
            start = event['start']['dateTime']
            end   = event['end']['dateTime']
            summary = event.get('summary', 'Untitled Event')
            description = event.get('description', '')
            
            # Format nicely
            start_dt = datetime.fromisoformat(start)
            start_str = start_dt.strftime("%I:%M %p")
            
            content = f"Calendar Event: {summary}\nTime: {start_str}\nDetails: {description}"
            signals.append(RawSignal(
                source    = SignalSource.ACADEMIC,
                content   = content,
                metadata  = {
                    "subject": f"SCHEDULE: {summary} at {start_str}",
                    "sender_category": "calendar",
                    "sender_weight": 0.95,
                    "urgency_score": 0.85, # Calendar events are usually highly urgent for the given day
                },
                signal_id = event['id']
            ))
            
        return signals

async def test():
    reader  = CalendarReader()
    signals = await reader.fetch_signals()
    print(f"\n✓ Fetched {len(signals)} Calendar events for today\n")
    for s in signals:
        print(f"  {s.metadata['subject']} (urgency={s.metadata['urgency_score']:.1f})")
        print()

if __name__ == "__main__":
    asyncio.run(test())
