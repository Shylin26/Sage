# SAGE — Student AI for Guidance and Execution

> A production-grade personal intelligence agent that reads your Gmail, weather, and financial signals every morning — scores them with an adaptive ML ranking engine — and delivers a structured voice briefing. Built with Go, Python, LLaMA 3.3 70B, and ElevenLabs.

## What it actually does

SAGE wakes up at 6am, pulls signals from every channel that matters to you, scores each one using an exponential decay model with learned relevance weights, fuses cross-signal context, generates a structured narrative via a Groq/LLaMA prompt chain, and delivers it as a voice MP3 and live web dashboard.

It doesn't just tell you what happened. It tells you what matters — and why, right now.

## What makes this different

**Exponential temporal decay** — signal value degrades as e^(-λt) where λ = ln(2) / half_life. Each source has its own half-life: bank SMS decays in 3 hours, Gmail in 8. A 6-hour-old fraud alert scores near zero. A fresh assignment email scores near one.

**Online relevance learning** — SAGE tracks which briefing items you act on vs ignore. Relevance weights update via 0.3 × base + 0.7 × act_rate after 5+ samples. It gets smarter the more you use it.

**Cross-signal correlation** — signals are fused across sources before narration. Rain + important meeting = proactive commute alert. Low balance + upcoming deadline = financial advisory.

**Structured prompt chain** — the briefing is 6 sequential prompts with distinct system instructions: hook, situation, action items, financial pulse, weather advisory, motivational close. Each runs in a thread pool executor.

**Polyglot architecture** — Go handles HTTP, scheduling, and SQLite reads at sub-millisecond latency. Python handles AI workloads. They share only the database file.

## Signal scoring
```
URR = Urgency × Relevance × Recency

Urgency   = keyword_score × (0.4 + 0.6 × sender_weight)
Relevance = 0.3 × base + 0.7 × historical_act_rate
Recency   = e^(−ln(2)/half_life × age_hours)
```

## Tech stack

| Layer | Technology |
|---|---|
| HTTP server | Go · Gin |
| Scheduler | robfig/cron |
| AI inference | Groq · LLaMA 3.3 70B |
| Voice synthesis | ElevenLabs Turbo v2 |
| Email ingestion | Gmail API · OAuth 2.0 |
| Weather | OpenWeatherMap |
| Storage | SQLite · aiosqlite |
| Async pipeline | Python asyncio |

## Setup
```bash
git clone https://github.com/Shylin26/Sage.git
cd Sage
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:
```env
GROQ_API_KEY=
OPENWEATHER_API_KEY=
ELEVENLABS_API_KEY=
LAT=31.1048
LON=77.1734
CITY=Shimla
DB_PATH=data/sage.db
```
```bash
python3 -m db.database
python3 run_briefing.py
```

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Live dashboard |
| GET | `/api/briefing/latest` | Latest briefing JSON |
| POST | `/api/briefing/run` | Trigger pipeline manually |
| GET | `/api/signals/today` | Today's ranked signals |
| GET | `/api/health` | Health check |

