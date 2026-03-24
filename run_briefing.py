import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import aiosqlite
from datetime import datetime, timezone
from config import get_settings
from models.signals import RawSignal, SignalSource
from modules.weather import WeatherModule
from brain.scorer import score_and_rank, filter_noise
from brain.narrator import generate_briefing, format_briefing
from db.database import init_db

settings = get_settings()


async def collect_signals() -> list[RawSignal]:
    signals = []

    print("  [1/3] Fetching weather...")
    try:
        weather   = WeatherModule()
        w_signals = await weather.fetch_signals()
        signals.extend(w_signals)
        print(f"        ✓ {len(w_signals)} weather signal")
    except Exception as e:
        print(f"        ✗ Weather failed: {e}")

    print("  [2/3] Fetching Gmail...")
    try:
        from modules.gmail_reader import GmailReader
        gmail     = GmailReader()
        g_signals = await gmail.fetch_signals(hours_back=16)
        signals.extend(g_signals)
        print(f"        ✓ {len(g_signals)} Gmail signals")
    except Exception as e:
        print(f"        ✗ Gmail failed: {e}")

    print("  [3/3] Fetching Calendar...")
    try:
        from modules.calendar_reader import CalendarReader
        calendar  = CalendarReader()
        c_signals = await calendar.fetch_signals()
        signals.extend(c_signals)
        print(f"        ✓ {len(c_signals)} Calendar signals")
    except Exception as e:
        print(f"        ✗ Calendar failed: {e}")

    return signals


async def save_briefing(briefing: dict, signal_ids: list):
    date_str = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO briefings (date, narrative, signals_used, delivered)
            VALUES (?, ?, ?, 0)
            """,
            (date_str, json.dumps(briefing), json.dumps(signal_ids))
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
    print("  SAGE — Morning Briefing Pipeline")
    print("━" * 52)
    print(f"  {datetime.now().strftime('%A, %d %B %Y — %H:%M')}\n")

    await init_db()

    print(" Collecting signals...")
    raw_signals = await collect_signals()

    if not raw_signals:
        print("\n No signals collected. Check your API keys.")
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

    signal_ids = [s.raw.signal_id for s in filtered if s.raw.signal_id]
    await save_signals(filtered)
    await save_briefing(briefing, signal_ids)

    print("\n● Generating voice briefing...")
    try:
        from delivery.voice import generate_voice
        generate_voice(briefing, output_path="data/briefing.mp3")
    except Exception as e:
        print(f"   Voice failed: {e}")

    print("\n" + "━" * 52)
    print(formatted)
    print("━" * 52)
    print("  Pipeline complete.\n")


if __name__ == "__main__":
    asyncio.run(run())