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
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import get_settings
from db.database import init_db
from run_briefing import run as run_pipeline

settings  = get_settings()
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=6, minute=0),
        id      = "morning_briefing",
        replace_existing = True,
    )
    scheduler.start()
    print("SAGE scheduler started — briefing runs at 06:00 daily")
    yield
    scheduler.shutdown()


app = FastAPI(title="SAGE", version="1.0.0", lifespan=lifespan)


@app.get("/")
async def dashboard():
    briefing = await get_latest_briefing()
    if not briefing:
        return HTMLResponse(render_empty())
    return HTMLResponse(render_dashboard(briefing))


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


def render_dashboard(b: dict) -> str:
    actions_html = "".join(
        f"<li>{line.strip()}</li>"
        for line in b.get("actions", "").strip().splitlines()
        if line.strip()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SAGE</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f0f0f; color: #e8e8e8; min-height: 100vh; padding: 2rem; }}
  .container {{ max-width: 720px; margin: 0 auto; }}
  .header {{ border-bottom: 1px solid #2a2a2a; padding-bottom: 1rem; margin-bottom: 2rem; }}
  .header h1 {{ font-size: 1.1rem; font-weight: 600; letter-spacing: 0.12em; color: #888; }}
  .header .date {{ font-size: 0.85rem; color: #555; margin-top: 0.25rem; }}
  .hook {{ font-size: 1.25rem; font-weight: 500; line-height: 1.6;
           color: #f0f0f0; margin-bottom: 2rem; }}
  .section {{ margin-bottom: 1.75rem; }}
  .section h2 {{ font-size: 0.72rem; font-weight: 600; letter-spacing: 0.14em;
                 color: #555; text-transform: uppercase; margin-bottom: 0.75rem; }}
  .section p {{ font-size: 0.95rem; line-height: 1.7; color: #bbb; }}
  .actions li {{ font-size: 0.95rem; line-height: 1.7; color: #bbb;
                 padding: 0.4rem 0; border-bottom: 1px solid #1e1e1e; list-style: none; }}
  .actions li::before {{ content: "→ "; color: #444; }}
  .financial {{ background: #161616; border: 1px solid #2a2a2a;
                border-radius: 8px; padding: 1rem 1.25rem; }}
  .financial p {{ font-size: 0.9rem; color: #aaa; line-height: 1.6; }}
  .close {{ font-size: 0.95rem; color: #666; font-style: italic;
            border-top: 1px solid #1e1e1e; padding-top: 1.5rem; margin-top: 1rem; }}
  .run-btn {{ display: inline-block; margin-top: 2rem; padding: 0.5rem 1.25rem;
              background: #1e1e1e; border: 1px solid #333; border-radius: 6px;
              color: #888; font-size: 0.8rem; cursor: pointer; text-decoration: none; }}
  .run-btn:hover {{ background: #252525; color: #bbb; }}
  .meta {{ font-size: 0.75rem; color: #3a3a3a; margin-top: 0.5rem; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>SAGE</h1>
    <div class="date">{b.get('date', '')} &nbsp;·&nbsp; {b.get('signal_count', 0)} signals</div>
  </div>

  <div class="hook">{b.get('hook', '')}</div>

  <div class="section">
    <h2>Situation</h2>
    <p>{b.get('situation', '')}</p>
  </div>

  <div class="section">
    <h2>Action Items</h2>
    <ul class="actions">{actions_html}</ul>
  </div>

  <div class="section">
    <h2>Financial Pulse</h2>
    <div class="financial"><p>{b.get('financial', '')}</p></div>
  </div>

  <div class="close">{b.get('close', '')}</div>

  <div>
    <a class="run-btn" href="#" onclick="runPipeline()">↻ Run briefing now</a>
    <div class="meta" id="status"></div>
  </div>
</div>
<script>
async function runPipeline() {{
  document.getElementById('status').textContent = 'Running pipeline...';
  const r = await fetch('/api/briefing/run', {{method: 'POST'}});
  const d = await r.json();
  document.getElementById('status').textContent = 'Started at ' + d.time;
  setTimeout(() => location.reload(), 8000);
}}
</script>
</body>
</html>"""


def render_empty() -> str:
    return """<!DOCTYPE html>
<html><head><title>SAGE</title>
<style>body{{background:#0f0f0f;color:#555;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;}}</style>
</head><body>
<div style="text-align:center">
  <div style="font-size:1.1rem;color:#888;margin-bottom:1rem">SAGE</div>
  <div>No briefing yet.</div>
  <div style="margin-top:1rem">
    <a href="#" onclick="run()" style="color:#555;font-size:0.85rem">Run pipeline now →</a>
  </div>
</div>
<script>
async function run() {
  await fetch('/api/briefing/run', {method:'POST'});
  setTimeout(() => location.reload(), 8000);
}
</script>
</body></html>"""


        

        

