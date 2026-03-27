import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import get_settings
from db.database import init_db
from run_briefing import run as run_pipeline, run_morning_briefing, run_weekly_review

settings  = get_settings()
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Evening full briefing — 6:00 PM IST = 12:30 UTC
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=12, minute=30, timezone="UTC"),
        id="evening_briefing",
        replace_existing=True,
    )

    # Morning quick briefing — 8:00 AM IST = 2:30 UTC
    scheduler.add_job(
        run_morning_briefing,
        CronTrigger(hour=2, minute=30, timezone="UTC"),
        id="morning_briefing",
        replace_existing=True,
    )

    # Weekly Sunday review — 7:00 PM IST = 13:30 UTC, Sundays only
    scheduler.add_job(
        run_weekly_review,
        CronTrigger(day_of_week="sun", hour=13, minute=30, timezone="UTC"),
        id="weekly_review",
        replace_existing=True,
    )

    scheduler.start()
    print("SAGE scheduler — morning 8AM IST + evening 6PM IST")
    yield
    scheduler.shutdown()


app = FastAPI(title="SAGE", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# ── Pages ──────────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard():
    return FileResponse("frontend/index.html")


# ── Briefing ───────────────────────────────────────────────────────────────

@app.get("/api/briefing/latest")
async def api_latest():
    return await get_latest_briefing() or {"error": "No briefing found"}


@app.get("/api/briefing/history")
async def api_history():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT date, narrative, signals_used FROM briefings ORDER BY date DESC LIMIT 7"
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"date": r["date"], "signals": json.loads(r["signals_used"])} for r in rows]


@app.post("/api/briefing/run")
async def api_run():
    asyncio.create_task(run_pipeline())
    return {"status": "pipeline started", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/morning/run")
async def api_morning():
    asyncio.create_task(run_morning_briefing())
    return {"status": "morning briefing started", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/weekly/run")
async def api_weekly():
    asyncio.create_task(run_weekly_review())
    return {"status": "weekly review started", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/briefing/audio")
async def api_audio():
    # Try file first, fall back to DB
    # LEARN: We store audio as base64 in SQLite so it survives
    # container restarts on Railway (no persistent volume needed)
    import base64
    from fastapi.responses import Response

    if os.path.exists("data/briefing.mp3"):
        return FileResponse("data/briefing.mp3", media_type="audio/mpeg")

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT audio_b64 FROM briefings WHERE audio_b64 != '' ORDER BY date DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row["audio_b64"]:
        raise HTTPException(status_code=404, detail="No audio briefing available yet")

    audio_bytes = base64.b64decode(row["audio_b64"])
    # Also write to file so next request is faster
    with open("data/briefing.mp3", "wb") as f:
        f.write(audio_bytes)

    return Response(content=audio_bytes, media_type="audio/mpeg")


# ── Signals ────────────────────────────────────────────────────────────────

@app.get("/api/signals/today")
async def api_signals():
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT source, content, urgency, urr_score, received_at FROM signals WHERE received_at LIKE ? ORDER BY urr_score DESC",
            (f"{today}%",)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── Status ─────────────────────────────────────────────────────────────────
# LEARN: This is your system health endpoint. Every production app has one.
# It tells you the last time the pipeline ran, how long it took,
# and which modules passed or failed — without reading any logs.

@app.get("/api/status")
async def api_status():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pipeline_runs ORDER BY ran_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return {"status": "no_runs", "message": "Pipeline has never run"}
    return {
        "status":       row["status"],
        "ran_at":       row["ran_at"],
        "duration_sec": row["duration_sec"],
        "modules":      json.loads(row["modules"]),
    }


# ── Tasks ──────────────────────────────────────────────────────────────────
# LEARN: This is a full CRUD API for tasks.
# GET    /api/tasks        → list all pending tasks
# POST   /api/tasks        → create a new task
# PATCH  /api/tasks/{id}   → mark done / update
# DELETE /api/tasks/{id}   → delete

class TaskPayload(BaseModel):
    title:    str
    due_date: str | None = None
    subject:  str        = ""
    priority: str        = "medium"   # low / medium / high


class TaskUpdate(BaseModel):
    done:     bool | None = None
    title:    str  | None = None
    due_date: str  | None = None
    priority: str  | None = None


@app.get("/api/tasks")
async def api_get_tasks():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tasks WHERE done = 0 ORDER BY due_date ASC, priority DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/tasks")
async def api_create_task(payload: TaskPayload):
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute(
            "INSERT INTO tasks (title, due_date, subject, priority) VALUES (?, ?, ?, ?)",
            (payload.title, payload.due_date, payload.subject, payload.priority)
        )
        await db.commit()
        task_id = cursor.lastrowid
    return {"status": "created", "id": task_id}


@app.patch("/api/tasks/{task_id}")
async def api_update_task(task_id: int, payload: TaskUpdate):
    fields, values = [], []
    if payload.done     is not None: fields.append("done = ?");     values.append(int(payload.done))
    if payload.title    is not None: fields.append("title = ?");    values.append(payload.title)
    if payload.due_date is not None: fields.append("due_date = ?"); values.append(payload.due_date)
    if payload.priority is not None: fields.append("priority = ?"); values.append(payload.priority)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")
    values.append(task_id)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
        await db.commit()
    return {"status": "updated"}


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int):
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
    return {"status": "deleted"}


# ── Bank SMS Webhook ───────────────────────────────────────────────────────
# LEARN: This is a webhook — your phone hits this URL whenever it gets
# an SMS. The SMS Forwarder app (Android) can be configured to POST
# every SMS to a URL. We parse it here and store it in the DB so the
# 6 PM pipeline picks it up automatically.

class SMSPayload(BaseModel):
    sender: str
    body:   str
    timestamp: str | None = None   # optional, ISO format


@app.post("/api/sms")
async def api_sms(payload: SMSPayload):
    from modules.bank_sms import parse_sms
    from datetime import datetime, timezone

    received_at = None
    if payload.timestamp:
        try:
            received_at = datetime.fromisoformat(payload.timestamp)
        except Exception:
            pass

    signal = parse_sms(payload.sender, payload.body, received_at)

    if not signal:
        return {"status": "ignored", "reason": "not a bank SMS"}

    # Save directly to DB so it's ready for the next pipeline run
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO signals
                (id, source, content, metadata, urgency, urr_score, summary, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.signal_id,
                signal.source.value,
                signal.content,
                json.dumps(signal.metadata),
                signal.metadata["urgency_score"],
                signal.metadata["urgency_score"],  # urr_score approximated until pipeline runs
                signal.metadata["subject"],
                signal.received_at.isoformat(),
            )
        )
        await db.commit()

    return {
        "status":  "saved",
        "subject": signal.metadata["subject"],
        "urgency": signal.metadata["urgency_score"],
    }


# ── Feedback ───────────────────────────────────────────────────────────────
# LEARN: This is the feedback loop. When you tap 👍 or 👎 on a signal,
# it calls this endpoint. The scorer reads this history and adjusts
# how much weight it gives to each signal source over time.
# This is a simple version of what recommendation systems do.

class FeedbackPayload(BaseModel):
    signal_id: str
    acted_on:  bool   # True = thumbs up, False = thumbs down


@app.post("/api/feedback")
async def api_feedback(payload: FeedbackPayload):
    from brain.scorer import record_feedback
    await record_feedback(payload.signal_id, payload.acted_on)
    return {"status": "recorded", "signal_id": payload.signal_id}


# ── Helpers ────────────────────────────────────────────────────────────────

async def get_latest_briefing() -> dict | None:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM briefings ORDER BY date DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    b = json.loads(row["narrative"])
    b["date_saved"] = row["date"]
    return b
