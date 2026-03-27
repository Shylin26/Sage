import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from datetime import datetime, timezone, timedelta
from groq import Groq
from models.signals import ScoredSignal, SignalSource
from config import get_settings

settings = get_settings()
client   = Groq(api_key=settings.groq_api_key)


def load_profile() -> dict:
    profile_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data/profile.json")
    try:
        with open(profile_path, "r") as f:
            return json.load(f)
    except Exception:
        return {"name": "User", "role": "Student", "tone": "sharp and direct", "goals": []}


def build_persona() -> str:
    """
    LEARN: We call this fresh every time generate_briefing() runs,
    not once at import time. That way the day/schedule is always correct.

    Since the briefing runs at 6 PM, we show TOMORROW's schedule —
    that's what Parisha actually needs to prepare for tonight.
    """
    p = load_profile()

    persona  = f"You are SAGE, a personal AI briefing agent for {p['name']}, a {p['role']}."
    persona += f" Tone: {p['tone']}."
    persona += f" Her goals: {', '.join(p['goals'])}."

    if p.get("location"):
        persona += f" She is based in {p['location']}."

    schedule = p.get("class_schedule", {})
    if schedule:
        tomorrow     = datetime.now(timezone.utc) + timedelta(days=1)
        tomorrow_key = tomorrow.strftime("%A").lower()
        classes      = schedule.get(tomorrow_key, [])

        if classes:
            persona += f" Tomorrow ({tomorrow.strftime('%A')}) she has: {', '.join(classes)}."
        else:
            persona += f" Tomorrow ({tomorrow.strftime('%A')}) she has no classes — free day."

    return persona


def detect_mood(signals: list) -> str:
    """
    LEARN: Mood detection based on signal urgency scores.
    We take the average URR score of all signals and classify
    the day. This changes the narrator's tone automatically —
    high stress day = more supportive, calm day = more analytical.

    This is a simple rule-based classifier. In production systems
    you'd use an ML model, but rules work well for known categories.
    """
    if not signals:
        return "calm"
    avg_urgency = sum(s.urr_score for s in signals) / len(signals)
    high_urgency_count = sum(1 for s in signals if s.urr_score > 0.7)

    if avg_urgency > 0.65 or high_urgency_count >= 3:
        return "stressful"
    elif avg_urgency > 0.4 or high_urgency_count >= 1:
        return "busy"
    else:
        return "calm"


def build_prompts(persona: str) -> dict:
    """Build section prompts fresh with the current persona."""
    return {
        "hook": f"""
{persona}
Write a 1-sentence evening hook — punchy, specific, no generic fluff.
It must reference the single most critical signal from today.
Never say 'Good morning' or 'Good evening'. Never use emojis.
""",
        "situation": f"""
{persona}
Write a 3-4 sentence situation report covering the top signals.
Be direct and specific — name the subjects, amounts, deadlines.
Weather is from Hamirpur, HP — never mention Shimla.
If there are classes tomorrow, mention the most demanding one.
IMPORTANT: Only reference emails personally addressed to Parisha. Ignore newsletters and group emails.
Prioritize by urgency. No filler words.
""",
        "actions": f"""
{persona}
Write 3-5 concrete action items she must do tonight or tomorrow morning.
Format: each action on its own line starting with a verb. No preamble, no intro sentence.
First line must be a real action, not a greeting or filler.
Be specific — not 'check email' but 'Reply to Prof Sharma about the lab submission'.
IMPORTANT: Only suggest actions based on signals directly addressed to Parisha personally.
Do NOT invent tasks from group emails, newsletters, or mailing lists.
If she has a lab tomorrow, include a prep action for it.
""",
        "financial": f"""
{persona}
Write a 2-sentence financial pulse.
Mention any transactions, balances, or anomalies detected.
If no financial signals, write: 'No financial alerts today.'
""",
        "close": f"""
{persona}
Write one closing sentence — motivating but not cringe, aligned with her goals.
Grounded, real, specific to what she is facing today or tomorrow.
Address her by name.
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
    persona      = build_persona()
    mood         = detect_mood(signals)

    # Mood adjusts the tone instruction
    # LEARN: Same data, different framing based on context.
    # This is exactly what good human communicators do too.
    mood_instruction = {
        "stressful": "Today is high-stress. Be warmer, more supportive, and prioritise what matters most. Acknowledge the pressure she's under.",
        "busy":      "Today is busy. Be direct and efficient. Help her focus on the top 3 things.",
        "calm":      "Today is calm. Be analytical and forward-looking. Use this as a planning opportunity.",
    }[mood]

    from brain.memory import get_yesterday_context, format_memory_context
    memory_ctx          = await get_yesterday_context()
    memory_summary      = format_memory_context(memory_ctx)
    persona_with_memory = (
        persona
        + f"\n\nMOOD TODAY: {mood.upper()}. {mood_instruction}"
        + f"\n\nMEMORY FROM YESTERDAY:\n{memory_summary}"
    )

    prompts  = build_prompts(persona_with_memory)
    context  = build_signal_context(signals)
    date_str = datetime.now(timezone.utc).strftime("%A, %d %B %Y")

    loop = asyncio.get_event_loop()
    hook, situation, actions, financial, close = await asyncio.gather(
        loop.run_in_executor(None, call_groq, prompts["hook"],      context, 80),
        loop.run_in_executor(None, call_groq, prompts["situation"], context, 200),
        loop.run_in_executor(None, call_groq, prompts["actions"],   context, 200),
        loop.run_in_executor(None, call_groq, prompts["financial"], context, 100),
        loop.run_in_executor(None, call_groq, prompts["close"],     context, 80),
    )

    return {
        "date":         date_str,
        "hook":         hook,
        "situation":    situation,
        "actions":      actions,
        "financial":    financial,
        "close":        close,
        "signal_count": len(signals),
        "mood":         mood,
    }


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
            content     = "Your interview with Razorpay is confirmed for tomorrow at 10am.",
            metadata    = {"urgency_score": 1.0, "sender_weight": 0.85,
                           "sender_category": "internship", "subject": "Interview Confirmed — Razorpay"},
            received_at = datetime.now(timezone.utc) - timedelta(minutes=30),
            signal_id   = "mock_5",
        ),
        RawSignal(
            source      = SignalSource.GMAIL,
            content     = "The ML assignment submission portal closes tomorrow at 11:59pm.",
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
            content     = "Heavy rain expected in Hamirpur. Commute risk: high. Bring umbrella.",
            metadata    = {"urgency_score": 0.75, "sender_weight": 0.7,
                           "sender_category": "weather", "subject": "Heavy Rain Alert — Hamirpur"},
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
