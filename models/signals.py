from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class SignalSource(str, Enum):
    GMAIL     = "gmail"
    WHATSAPP  = "whatsapp"
    BANK_SMS  = "bank_sms"
    WEATHER   = "weather"
    ACADEMIC  = "academic"

class UrgencyLevel(int, Enum):
    CRITICAL = 5
    HIGH     = 4
    MEDIUM   = 3
    LOW      = 2
    NOISE    = 1

@dataclass
class RawSignal:
    source:      SignalSource
    content:     str
    metadata:    dict          = field(default_factory=dict)
    received_at: datetime      = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_id:   Optional[str] = None

@dataclass
class ScoredSignal:
    raw:       RawSignal
    urgency:   float  = 0.5   # 0-1
    relevance: float  = 0.5   # 0-1, learned over time
    recency:   float  = 1.0   # 0-1, decays with age
    urr_score: float  = 0.0   # urgency × relevance × recency
    summary:   str    = ""

    def compute_urr(self):
        self.urr_score = self.urgency * self.relevance * self.recency
        return self.urr_score