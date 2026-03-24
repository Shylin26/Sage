import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from datetime import datetime, timezone
from groq import Groq
from models.signals import ScoredSignal, SignalSource
from config import get_settings

settings = get_settings()
client   = Groq(api_key=settings.groq_api_key)

SECTION_PROMPTS = {
    "hook": """
You are SAGE, a razor-sharp personal AI briefing agent for a B.Tech student.
Write a 1-sentence morning hook — punchy, specific, no generic fluff.
It must reference the single most critical signal from today.
Never say 'Good morning'. Never use emojis.
""",
    "situation": """
You are SAGE. Write a 3-4 sentence situation report covering the top signals.
Be direct and specific — name the subjects, amounts, deadlines.
Prioritize by urgency. No filler words.
""",
    "actions": """
You are SAGE. Write 3-5 concrete action items the student must do today.
Format: each action on its own line starting with a verb.
Be specific — not 'check email' but 'Reply to Prof Sharma's ML assignment email'.
""",
    "financial": """
You are SAGE. Write a 2-sentence financial pulse.
Mention any transactions, balances, or anomalies detected.
If no financial signals, write: 'No financial alerts today.'
""",
    "close": """
You are SAGE. Write one closing sentence — motivating but not cringe.
Grounded, real, specific to what the student is facing today.
""",
}

def build_signal_context(signals: list[ScoredSignal]) -> str:
    lines = []
    for s in signals:
        meta    = s.raw.metadata
        subject = meta.get("subject", "")
        source  = s.raw.source.value
        urr     = s.urr_score
        lines.append(f"[{source.upper()} | URR={urr:.2f}] {subject}\n{s.raw.content[:300]}")
    return "\n\n".join(lines)

def call_groq(system_prompt: str, context: str, max_tokens: int = 200) -> str:
    response = client.chat.completions.create(
        model      = "llama-3.3-70b-versatile",
        max_tokens = max_tokens,
        messages   = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user",   "content": f"Today's signals:\n\n{context}"},
        ],
    )
    return response.choices[0].message.content.strip()

async def generate_briefing(signals: list[ScoredSignal]) -> dict:
    context  = build_signal_context(signals)
    date_str = datetime.now(timezone.utc).strftime("%A, %d %B %Y")

    loop     = asyncio.get_event_loop()

    hook      = await loop.run_in_executor(None, call_groq, SECTION_PROMPTS["hook"],      context, 80)
    situation = await loop.run_in_executor(None, call_groq, SECTION_PROMPTS["situation"], context, 200)
    actions   = await loop.run_in_executor(None, call_groq, SECTION_PROMPTS["actions"],   context, 200)
    financial = await loop.run_in_executor(None, call_groq, SECTION_PROMPTS["financial"], context, 100)
    close     = await loop.run_in_executor(None, call_groq, SECTION_PROMPTS["close"],     context, 80)

    briefing = {
        "date":      date_str,
        "hook":      hook,
        "situation": situation,
        "actions":   actions,
        "financial": financial,
        "close":     close,
        "signal_count": len(signals),
    }

    return briefing

def format_briefing(b: dict) -> str:
    divider = "─" * 52
    return f"""
SAGE DAILY BRIEFING — {b['date']}
{divider}

{b['hook']}

SITUATION
{b['situation']}

ACTION ITEMS
{b['actions']}

FINANCIAL PULSE
{b['financial']}

{divider}
{b['close']}

{b['signal_count']} signals processed.
"""


async def test():
    from datetime import timedelta
    from models.signals import RawSignal, SignalSource

    mock_signals_raw = [
        RawSignal(
            source      = SignalSource.ACADEMIC,
            content     = "Your interview with Razorpay is confirmed for tomorrow at 10am. Please join the Google Meet link.",
            metadata    = {"urgency_score": 1.0, "sender_weight": 0.85,
                           "sender_category": "internship", "subject": "Interview Confirmed — Razorpay"},
            received_at = datetime.now(timezone.utc) - timedelta(minutes=30),
            signal_id   = "mock_5",
        ),
        RawSignal(
            source      = SignalSource.GMAIL,
            content     = "The ML assignment submission portal closes tomorrow at 11:59pm. Late submissions will not be accepted.",
            metadata    = {"urgency_score": 0.8, "sender_weight": 1.0,
                           "sender_category": "faculty", "subject": "ML Assignment Due Tomorrow — Prof Sharma"},
            received_at = datetime.now(timezone.utc) - timedelta(hours=1),
            signal_id   = "mock_1",
        ),
        RawSignal(
            source      = SignalSource.BANK_SMS,
            content     = "UPI payment of Rs.2000 debited. Available balance: Rs.850.",
            metadata    = {"urgency_score": 0.6, "sender_weight": 0.9,
                           "sender_category": "bank", "subject": "UPI Alert — Low Balance"},
            received_at = datetime.now(timezone.utc) - timedelta(hours=2),
            signal_id   = "mock_3",
        ),
        RawSignal(
            source      = SignalSource.WEATHER,
            content     = "Heavy rain expected in Shimla. Commute risk: high. Bring umbrella.",
            metadata    = {"urgency_score": 0.75, "sender_weight": 0.7,
                           "sender_category": "weather", "subject": "Heavy Rain Alert"},
            received_at = datetime.now(timezone.utc) - timedelta(minutes=15),
            signal_id   = "mock_4",
        ),
    ]

    from brain.scorer import score_and_rank, filter_noise
    ranked   = await score_and_rank(mock_signals_raw)
    filtered = filter_noise(ranked)

    print("Generating briefing via Groq...\n")
    briefing  = await generate_briefing(filtered)
    formatted = format_briefing(briefing)
    print(formatted)

if __name__ == "__main__":
    asyncio.run(test())



