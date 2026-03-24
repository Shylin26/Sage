import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import json
import asyncio
import aiosqlite
from datetime import datetime, timezone, timedelta
from models.signals import RawSignal, ScoredSignal, SignalSource
from config import get_settings

settings = get_settings()

SOURCE_BASE_RELEVANCE = {
    SignalSource.GMAIL:    0.80,
    SignalSource.WEATHER:  0.70,
    SignalSource.BANK_SMS: 0.95,
    SignalSource.WHATSAPP: 0.60,
    SignalSource.ACADEMIC: 1.00,
}

DECAY_HALFLIFE_HOURS = {
    SignalSource.BANK_SMS: 3.0,
    SignalSource.ACADEMIC: 6.0,
    SignalSource.GMAIL:    8.0,
    SignalSource.WEATHER:  4.0,
    SignalSource.WHATSAPP: 2.0,
}

def exponential_recency(received_at: datetime, source: SignalSource) -> float:
    """
    Exponential decay: score = e^(-λt)
    where λ = ln(2) / half_life
    Models how signal value degrades over time — same math as radioactive decay.
    """
    now       = datetime.now(timezone.utc)
    ts        = received_at.replace(tzinfo=timezone.utc) if received_at.tzinfo is None else received_at
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    half_life = DECAY_HALFLIFE_HOURS.get(source, 8.0)
    lam       = math.log(2) / half_life
    return round(math.exp(-lam * age_hours), 4)

async def get_learned_relevance(source: SignalSource, category: str) -> float:
    """
    Pull learned relevance weight from DB.
    Starts at base value, drifts toward what user actually acts on.
    Returns base value if no history yet.
    """
    base = SOURCE_BASE_RELEVANCE.get(source, 0.5)
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            async with db.execute(
                """
                SELECT
                    SUM(acted_on) * 1.0 / (COUNT(*) + 1e-9) as act_rate,
                    COUNT(*) as total
                FROM signal_feedback
                WHERE signal_id LIKE ?
                """,
                (f"{source.value}%",)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[1] and row[1] >= 5:
                    act_rate = row[0]
                    learned  = 0.3 * base + 0.7 * act_rate
                    return round(max(0.05, min(1.0, learned)), 4)
    except Exception:
        pass
    return base

async def score_signal(raw: RawSignal) -> ScoredSignal:
    urgency_raw  = raw.metadata.get("urgency_score", 0.3)
    sender_w     = raw.metadata.get("sender_weight", 0.5)
    category     = raw.metadata.get("sender_category", "peer")

    urgency      = round(min(1.0, urgency_raw * (0.4 + 0.6 * sender_w)), 4)
    relevance    = await get_learned_relevance(raw.source, category)
    recency      = exponential_recency(raw.received_at, raw.source)

    scored = ScoredSignal(
        raw       = raw,
        urgency   = urgency,
        relevance = relevance,
        recency   = recency,
    )
    scored.compute_urr()
    return scored

async def score_and_rank(signals: list[RawSignal]) -> list[ScoredSignal]:
    scored = await asyncio.gather(*[score_signal(s) for s in signals])
    scored = list(scored)
    scored.sort(key=lambda s: s.urr_score, reverse=True)
    return scored

def filter_noise(scored: list[ScoredSignal], threshold: float = 0.08) -> list[ScoredSignal]:
    return [s for s in scored if s.urr_score >= threshold]

async def record_feedback(signal_id: str, acted_on: bool):
    """
    Call this when user acts on / ignores a briefing item.
    This is what makes SAGE learn over time.
    """
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT INTO signal_feedback (signal_id, acted_on, ignored, date)
            VALUES (?, ?, ?, ?)
            """,
            (signal_id, int(acted_on), int(not acted_on),
             datetime.now(timezone.utc).date().isoformat())
        )
        await db.commit()


async def test():
    mock_signals = [
        RawSignal(
            source      = SignalSource.GMAIL,
            content     = "Your ML assignment is due tomorrow at 11:59pm",
            metadata    = {"urgency_score": 0.8, "sender_weight": 1.0,
                           "sender_category": "faculty", "subject": "ML Assignment Due Tomorrow"},
            received_at = datetime.now(timezone.utc) - timedelta(hours=1),
            signal_id   = "mock_1",
        ),
        RawSignal(
            source      = SignalSource.GMAIL,
            content     = "50% off on Zomato today only",
            metadata    = {"urgency_score": 0.1, "sender_weight": 0.05,
                           "sender_category": "promotion", "subject": "Zomato offer"},
            received_at = datetime.now(timezone.utc) - timedelta(hours=10),
            signal_id   = "mock_2",
        ),
        RawSignal(
            source      = SignalSource.BANK_SMS,
            content     = "UPI payment of Rs.2000 debited from your account",
            metadata    = {"urgency_score": 0.6, "sender_weight": 0.9,
                           "sender_category": "bank", "subject": "UPI Alert"},
            received_at = datetime.now(timezone.utc) - timedelta(hours=2),
            signal_id   = "mock_3",
        ),
        RawSignal(
            source      = SignalSource.WEATHER,
            content     = "Heavy rain expected, commute risk high",
            metadata    = {"urgency_score": 0.75, "sender_weight": 0.7,
                           "sender_category": "weather", "subject": "Weather Alert"},
            received_at = datetime.now(timezone.utc) - timedelta(minutes=15),
            signal_id   = "mock_4",
        ),
        RawSignal(
            source      = SignalSource.ACADEMIC,
            content     = "Internship interview confirmation — tomorrow 10am",
            metadata    = {"urgency_score": 1.0, "sender_weight": 0.85,
                           "sender_category": "internship", "subject": "Interview Confirmed"},
            received_at = datetime.now(timezone.utc) - timedelta(minutes=30),
            signal_id   = "mock_5",
        ),
    ]

    ranked   = await score_and_rank(mock_signals)
    filtered = filter_noise(ranked)

    print(f"\n✓ SAGE URR Scorer — {len(filtered)}/{len(ranked)} signals above noise floor\n")
    print(f"{'#':<3} {'SOURCE':<12} {'CATEGORY':<12} {'URR':>6} {'U':>6} {'R':>6} {'REC':>6}  SUBJECT")
    print("─" * 78)
    for i, s in enumerate(filtered, 1):
        subject  = s.raw.metadata.get("subject", "")[:30]
        category = s.raw.metadata.get("sender_category", "")
        print(
            f"{i:<3} {s.raw.source.value:<12} {category:<12} "
            f"{s.urr_score:>6.3f} {s.urgency:>6.3f} "
            f"{s.relevance:>6.3f} {s.recency:>6.3f}  {subject}"
        )

    print(f"\n  Decay model : exponential (λ = ln2 / half-life per source)")
    print(f"  Relevance   : learned from feedback history (falls back to base)")
    print(f"  Noise floor : URR < 0.08 suppressed\n")

if __name__ == "__main__":
    asyncio.run(test())