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

    # Exam countdown signals
    # LEARN: We read exam dates from profile.json and generate urgency signals.
    # The closer the exam, the higher the urgency score. This is injected
    # into the pipeline just like any other signal — scorer ranks it naturally.
    print("  [4/5] Loading tasks...")
    try:
        from datetime import date
        today_date = datetime.now(timezone.utc).date()
        profile_path = "data/profile.json"
        import json as _json
        with open(profile_path) as f:
            profile = _json.load(f)

        for exam in profile.get("exams", []):
            exam_date = date.fromisoformat(exam["date"])
            days_left = (exam_date - today_date).days
            if days_left < 0 or days_left > 21:
                continue  # skip past exams and far future ones

            if days_left <= 3:   urgency = 0.98
            elif days_left <= 7: urgency = 0.88
            elif days_left <= 14: urgency = 0.72
            else:                urgency = 0.55

            signals.append(RawSignal(
                source    = SignalSource.ACADEMIC,
                content   = f"Exam in {days_left} days: {exam['subject']} ({exam['code']}) on {exam['date']}.",
                metadata  = {
                    "subject":         f"EXAM in {days_left}d: {exam['subject']}",
                    "urgency_score":   urgency,
                    "sender_weight":   1.0,
                    "sender_category": "exam",
                    "days_left":       days_left,
                    "exam_date":       exam["date"],
                },
                signal_id = f"exam_{exam['code']}_{exam['date']}",
            ))

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


async def run_morning_briefing():
    """
    LEARN: Morning briefing is intentionally lightweight.
    No Groq, no voice, no DB writes — just a quick WhatsApp
    with today's schedule + weather + nearest exam countdown.
    Runs at 8 AM IST so Parisha sees it when she wakes up.
    """
    print("\n── SAGE Morning Briefing ──")
    await init_db()

    from datetime import date
    import json as _json

    today     = datetime.now(timezone.utc).strftime("%A, %d %B")
    today_key = datetime.now(timezone.utc).strftime("%A").lower()

    # Load profile for schedule
    try:
        with open("data/profile.json") as f:
            profile = _json.load(f)
    except Exception:
        profile = {}

    schedule = profile.get("class_schedule", {}).get(today_key, [])
    exams    = profile.get("exams", [])
    today_date = datetime.now(timezone.utc).date()

    # Find nearest upcoming exam
    upcoming = []
    for ex in exams:
        d = date.fromisoformat(ex["date"])
        days = (d - today_date).days
        if 0 <= days <= 21:
            upcoming.append((days, ex["subject"], ex["code"]))
    upcoming.sort()

    # Get weather
    weather_line = ""
    try:
        from modules.weather import WeatherModule
        impact = await WeatherModule().get_impact()
        if impact:
            weather_line = f"🌤 {impact.description.title()}, {impact.temperature_c:.0f}°C. {impact.clothing_advice}."
    except Exception:
        pass

    # Build message
    lines = [f"*SAGE — Good Morning, Parisha* 🌅", f"_{today}_", ""]

    if schedule:
        lines.append("*Today's Classes*")
        for c in schedule:
            lines.append(f"  • {c}")
        lines.append("")
    else:
        lines.append("No classes today — use it well.\n")

    if weather_line:
        lines.append(weather_line)
        lines.append("")

    if upcoming:
        lines.append("*Exam Countdown*")
        for days, subj, code in upcoming[:3]:
            emoji = "🔴" if days <= 3 else "🟡" if days <= 7 else "🟢"
            lines.append(f"  {emoji} {subj} ({code}) — {days} days")
        lines.append("")

    lines.append("_Make today count._")

    message = "\n".join(lines)

    try:
        from delivery.whatsapp_sender import send_whatsapp
        send_whatsapp(message)
        print("  ✓ Morning briefing sent")
    except Exception as e:
        print(f"  ✗ Morning WhatsApp failed: {e}")


async def run_weekly_review():
    """
    LEARN: Every Sunday at 7 PM IST, SAGE sends a weekly performance
    summary via WhatsApp. This is called a "digest" pattern — instead
    of real-time alerts, you batch and summarize a week's worth of data.

    We query the DB for the past 7 days of briefings, signals, and
    feedback to build a personal performance report.
    """
    print("\n── SAGE Weekly Review ──")
    await init_db()

    from datetime import date, timedelta
    import json as _json

    today      = datetime.now(timezone.utc).date()
    week_start = (today - timedelta(days=6)).isoformat()

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count briefings delivered this week
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM briefings WHERE date >= ?", (week_start,)
        ) as cur:
            briefing_count = (await cur.fetchone())["cnt"]

        # Count tasks completed this week
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE done = 1 AND created_at >= ?",
            (week_start,)
        ) as cur:
            tasks_done = (await cur.fetchone())["cnt"]

        # Count pending tasks
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE done = 0"
        ) as cur:
            tasks_pending = (await cur.fetchone())["cnt"]

        # Count signals acted on this week
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM signal_feedback WHERE acted_on = 1 AND date >= ?",
            (week_start,)
        ) as cur:
            acted_on = (await cur.fetchone())["cnt"]

        # Most common signal source this week
        async with db.execute(
            """SELECT source, COUNT(*) as cnt FROM signals
               WHERE received_at >= ? GROUP BY source ORDER BY cnt DESC LIMIT 1""",
            (week_start,)
        ) as cur:
            top_source_row = await cur.fetchone()
            top_source = top_source_row["source"] if top_source_row else "none"

    # Build WhatsApp message
    week_label = f"{(today - timedelta(days=6)).strftime('%d %b')} – {today.strftime('%d %b')}"
    lines = [
        f"*SAGE Weekly Review* 📊",
        f"_{week_label}_",
        "",
        f"*Briefings delivered:* {briefing_count}/7",
        f"*Tasks completed:* {tasks_done}",
        f"*Tasks still pending:* {tasks_pending}",
        f"*Signals acted on:* {acted_on}",
        f"*Top signal source:* {top_source}",
        "",
    ]

    # Motivational close based on performance
    if tasks_done >= 5:
        lines.append("Solid week, Parisha. Keep that momentum.")
    elif tasks_done >= 2:
        lines.append("Decent week. Push harder next one.")
    else:
        lines.append("Rough week. Reset, refocus, go again.")

    message = "\n".join(lines)

    try:
        from delivery.whatsapp_sender import send_whatsapp
        send_whatsapp(message)
        print("  ✓ Weekly review sent")
    except Exception as e:
        print(f"  ✗ Weekly review failed: {e}")
