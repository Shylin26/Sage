import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import time
import aiosqlite
from datetime import datetime, timezone
from config import get_settings
from models.signals import RawSignal, SignalSource
from modules.weather import WeatherModule
from brain.scorer import score_and_rank, filter_noise
from brain.narrator import generate_briefing, format_briefing
from db.database import init_db

settings = get_settings()


async def collect_signals() -> tuple[list[RawSignal], dict]:
    """Returns (signals, module_health).
    
    LEARN: We return a tuple now — the signals AND a health dict.
    Each module records "ok" or "failed: <reason>" so we can show
    this in the dashboard and debug without reading logs.
    """
    signals = []
    health  = {}

    print("  [1/3] Fetching weather...")
    try:
        w_signals = await WeatherModule().fetch_signals()
        signals.extend(w_signals)
        health["weather"] = "ok"
        print(f"        ✓ {len(w_signals)} weather signal")
    except Exception as e:
        health["weather"] = f"failed: {e}"
        print(f"        ✗ Weather failed: {e}")

    print("  [2/3] Fetching Gmail...")
    try:
        from modules.gmail_reader import GmailReader
        g_signals = await GmailReader().fetch_signals(hours_back=16)
        signals.extend(g_signals)
        health["gmail"] = "ok"
        print(f"        ✓ {len(g_signals)} Gmail signals")
    except Exception as e:
        health["gmail"] = f"failed: {e}"
        print(f"        ✗ Gmail failed: {e}")

    print("  [3/3] Fetching Calendar...")
    try:
        from modules.calendar_reader import CalendarReader
        c_signals = await CalendarReader().fetch_signals()
        signals.extend(c_signals)
        health["calendar"] = "ok"
        print(f"        ✓ {len(c_signals)} Calendar signals")
    except Exception as e:
        health["calendar"] = f"failed: {e}"
        print(f"        ✗ Calendar failed: {e}")

    # Pull pending tasks from DB and convert to signals
    # LEARN: Tasks with due dates get urgency based on how close the deadline is.
    # Due today = 0.95, due tomorrow = 0.85, due in 3 days = 0.65, etc.
    print("  [4/5] Loading tasks...")
    try:
        from datetime import date, timedelta
        today_date = datetime.now(timezone.utc).date()
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE done = 0 ORDER BY due_date ASC"
            ) as cursor:
                task_rows = await cursor.fetchall()

        for t in task_rows:
            due      = t["due_date"]
            days_left = None
            urgency  = 0.5

            if due:
                due_date  = date.fromisoformat(due)
                days_left = (due_date - today_date).days
                if days_left <= 0:   urgency = 0.98   # overdue
                elif days_left == 1: urgency = 0.90   # due tomorrow
                elif days_left <= 3: urgency = 0.75
                elif days_left <= 7: urgency = 0.55
                else:                urgency = 0.35

            label   = f"TASK DUE {'TODAY' if days_left == 0 else 'TOMORROW' if days_left == 1 else f'in {days_left}d' if days_left else 'no deadline'}"
            subject = f"{label}: {t['title']}"
            if t["subject"]:
                subject += f" ({t['subject']})"

            signals.append(RawSignal(
                source    = SignalSource.ACADEMIC,
                content   = f"Pending task: {t['title']}. Subject: {t['subject'] or 'General'}. Due: {due or 'no deadline'}. Priority: {t['priority']}.",
                metadata  = {
                    "subject":         subject,
                    "urgency_score":   urgency,
                    "sender_weight":   1.0,
                    "sender_category": "task",
                    "task_id":         t["id"],
                    "due_date":        due,
                    "days_left":       days_left,
                },
                signal_id = f"task_{t['id']}",
            ))

        health["tasks"] = "ok"
        print(f"        ✓ {len(task_rows)} pending tasks")
    except Exception as e:
        health["tasks"] = f"failed: {e}"
        print(f"        ✗ Tasks failed: {e}")

    # Bank SMS signals arrive via webhook and are already in the DB.
    print("  [5/5] Loading Bank SMS from DB...")
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM signals WHERE source = 'bank_sms' AND received_at LIKE ? ORDER BY received_at DESC",
                (f"{today}%",)
            ) as cursor:
                rows = await cursor.fetchall()

        from models.signals import SignalSource
        import json as _json
        for row in rows:
            meta = _json.loads(row["metadata"])
            signals.append(RawSignal(
                source      = SignalSource.BANK_SMS,
                content     = row["content"],
                metadata    = meta,
                received_at = datetime.fromisoformat(row["received_at"]),
                signal_id   = row["id"],
            ))
        health["bank_sms"] = "ok"
        print(f"        ✓ {len(rows)} bank SMS signals")
    except Exception as e:
        health["bank_sms"] = f"failed: {e}"
        print(f"        ✗ Bank SMS failed: {e}")

    return signals, health


async def save_pipeline_run(health: dict, duration: float, signal_count: int):
    """
    LEARN: Every run gets recorded — when it ran, how long it took,
    which modules passed/failed. This is called 'observability' in
    production systems. You can't fix what you can't see.
    """
    failed = [k for k, v in health.items() if v != "ok"]
    if len(failed) == len(health):
        status = "failed"
    elif failed:
        status = "partial"
    else:
        status = "ok"

    health["signal_count"] = signal_count

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT INTO pipeline_runs (ran_at, duration_sec, status, modules)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                round(duration, 2),
                status,
                json.dumps(health),
            )
        )
        await db.commit()
    print(f"  ✓ Run recorded — status: {status} ({duration:.1f}s)")


async def save_briefing(briefing: dict, signal_ids: list, audio_path: str = ""):
    date_str = datetime.now(timezone.utc).date().isoformat()
    
    # Read MP3 and store as base64 in DB so it survives container restarts
    audio_b64 = ""
    if audio_path and os.path.exists(audio_path):
        import base64
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        print(f"  ✓ Audio stored in DB ({len(audio_b64)//1024} KB)")

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO briefings (date, narrative, signals_used, delivered, audio_b64)
            VALUES (?, ?, ?, 0, ?)
            """,
            (date_str, json.dumps(briefing), json.dumps(signal_ids), audio_b64)
        )
        await db.commit()
    print(f"  ✓ Briefing saved to DB for {date_str}")


async def save_signals(signals):
    async with aiosqlite.connect(settings.db_path) as db:
        for s in signals:
            await db.execute(
                """
                INSERT OR IGNORE INTO signals
                    (id, source, content, metadata, urgency, urr_score, summary, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.raw.signal_id or f"{s.raw.source.value}_{datetime.now().timestamp()}",
                    s.raw.source.value,
                    s.raw.content,
                    json.dumps(s.raw.metadata),
                    s.urgency,
                    s.urr_score,
                    s.summary,
                    s.raw.received_at.isoformat(),
                )
            )
        await db.commit()
    print(f"  ✓ {len(signals)} signals saved to DB")


async def run():
    print("\n" + "━" * 52)
    print("  SAGE — Evening Briefing Pipeline")
    print("━" * 52)
    print(f"  {datetime.now().strftime('%A, %d %B %Y — %H:%M')}\n")

    await init_db()
    start_time = time.time()

    print("● Collecting signals...")
    raw_signals, health = await collect_signals()

    if not raw_signals:
        await save_pipeline_run(health, time.time() - start_time, 0)
        print("\n  No signals collected. Check your API keys.")
        return

    print(f"\n● Scoring {len(raw_signals)} signals...")
    ranked   = await score_and_rank(raw_signals)
    filtered = filter_noise(ranked)
    print(f"  {len(filtered)} signals above noise floor\n")

    for s in filtered:
        subject = s.raw.metadata.get("subject", s.raw.content[:50])
        print(f"  {s.urr_score:.3f}  [{s.raw.source.value}]  {subject}")

    print(f"\n● Generating briefing via Groq...")
    briefing  = await generate_briefing(filtered)
    formatted = format_briefing(briefing)

    print("\n● Generating voice briefing...")
    audio_path = "data/briefing.mp3"
    try:
        from delivery.voice import generate_voice
        generate_voice(briefing, output_path=audio_path)
        health["voice"] = "ok"
    except Exception as e:
        health["voice"] = f"failed: {e}"
        audio_path = ""
        print(f"   Voice failed: {e}")

    signal_ids = [s.raw.signal_id for s in filtered if s.raw.signal_id]
    await save_signals(filtered)
    await save_briefing(briefing, signal_ids, audio_path)

    print("\n● Sending WhatsApp briefing...")
    try:
        from delivery.whatsapp_sender import send_whatsapp
        send_whatsapp(formatted)
        health["whatsapp"] = "ok"
    except Exception as e:
        health["whatsapp"] = f"failed: {e}"
        print(f"   WhatsApp failed: {e}")

    await save_pipeline_run(health, time.time() - start_time, len(filtered))

    print("\n" + "━" * 52)
    print(formatted)
    print("━" * 52)
    print("  Pipeline complete.\n")


if __name__ == "__main__":
    asyncio.run(run())
