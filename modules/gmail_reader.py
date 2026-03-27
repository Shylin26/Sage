import asyncio
import base64
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

SENDER_WEIGHT = {
    "faculty":    1.0,
    "bank":       0.90,
    "internship": 0.85,
    "peer":       0.55,
    "promotion":  0.05,
}

URGENCY_KEYWORDS = {
    5: ["urgent", "deadline today", "final warning", "fraud", "suspended", "immediate action"],
    4: ["due tomorrow", "your submission", "interview confirmed", "offer letter", "payment failed"],
    3: ["reminder", "please respond", "your meeting", "your assignment", "action required"],
    2: ["fyi", "heads up", "when you get a chance", "newsletter", "digest"],
}

class GmailReader:
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
        self.service = build("gmail", "v1", credentials=creds)

    def _classify_sender(self, sender: str) -> tuple:
        s = sender.lower()
        if any(d in s for d in [".edu", "ac.in", "university", "college", "institute", "nit", "iit"]):
            return "faculty", SENDER_WEIGHT["faculty"]
        if any(d in s for d in ["sbi", "hdfc", "icici", "axis", "kotak", "paytm", "razorpay", "upi"]):
            return "bank", SENDER_WEIGHT["bank"]
        if any(d in s for d in ["noreply", "no-reply", "newsletter", "marketing", "promo"]):
            return "promotion", SENDER_WEIGHT["promotion"]
        if any(d in s for d in ["internship", "hiring", "recruit", "hr@", "talent"]):
            return "internship", SENDER_WEIGHT["internship"]
        return "peer", SENDER_WEIGHT["peer"]

    def _score_urgency(self, subject: str, body_preview: str) -> float:
        text = (subject + " " + body_preview).lower()
        for score, keywords in URGENCY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return score / 5.0
        return 0.3

    def _extract_body(self, payload: dict) -> str:
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result
        return ""

    def _parse_message(self, msg: dict) -> Optional[RawSignal]:
        try:
            headers      = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject      = headers.get("Subject", "(no subject)")
            sender       = headers.get("From", "")
            date_str     = headers.get("Date", "")
            body         = self._extract_body(msg["payload"])[:800]
            sender_category, sender_weight = self._classify_sender(sender)
            urgency_score = self._score_urgency(subject, body)
            return RawSignal(
                source    = SignalSource.GMAIL,
                content   = f"Subject: {subject}\nFrom: {sender}\n\n{body}",
                metadata  = {
                    "subject":         subject,
                    "sender":          sender,
                    "sender_category": sender_category,
                    "sender_weight":   sender_weight,
                    "urgency_score":   urgency_score,
                    "date":            date_str,
                },
                signal_id = msg["id"],
            )
        except Exception as e:
            print(f"Parse error: {e}")
            return None

    def _fetch_messages_sync(self, query: str, max_results: int) -> list:
        result = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        message_ids = result.get("messages", [])
        messages = []
        for item in message_ids:
            msg = self.service.users().messages().get(
                userId="me", id=item["id"], format="full"
            ).execute()
            messages.append(msg)
        return messages

    async def fetch_signals(self, hours_back: int = 16, max_results: int = 30) -> list:
        if not self.service:
            self.authenticate()
        after_ts = int(
            (datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp()
        )
        query = f"after:{after_ts} -category:promotions -category:social"
        loop = asyncio.get_event_loop()
        raw_messages = await loop.run_in_executor(
            None, self._fetch_messages_sync, query, max_results
        )
        signals = []
        for msg in raw_messages:
            signal = self._parse_message(msg)
            if signal:
                signals.append(signal)
        return signals


async def test():
    reader  = GmailReader()
    signals = await reader.fetch_signals(hours_back=24)
    print(f"\n✓ Fetched {len(signals)} Gmail signals\n")
    for s in signals[:5]:
        print(f"  [{s.metadata['sender_category'].upper()}] urgency={s.metadata['urgency_score']:.1f}")
        print(f"  {s.metadata['subject'][:70]}")
        print()

if __name__ == "__main__":
    asyncio.run(test())