<div align="center">

# SAGE
### Personal AI Briefing Agent

*Every evening at 6 PM, SAGE reads your emails, calendar, weather, bank transactions, and pending tasks — scores them by urgency, generates a personalised narrative briefing using an LLM, and delivers it to your WhatsApp and as a voice audio.*

**No app switching. No notification overload. Just one briefing.**

[![Live Demo](https://img.shields.io/badge/Live-sage--production--d82c.up.railway.app-7c6af7?style=flat-square)](https://sage-production-d82c.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![Deployed on Railway](https://img.shields.io/badge/Deployed-Railway-0B0D0E?style=flat-square)](https://railway.app)

</div>

---

## The Problem

I was spending 20–30 minutes every morning checking Gmail, Google Calendar, weather apps, and bank notifications — context-switching between 5 different apps just to understand what my day looked like.

I built SAGE to solve this. One briefing. Every evening. Everything that matters.

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────┐
│                        SIGNAL SOURCES                            │
│                                                                  │
│   Gmail API    Google Calendar    OpenWeatherMap    Bank SMS     │
│   (OAuth2)       (OAuth2)          (REST API)      (Webhook)    │
└─────────────────────────┬────────────────────────────────────────┘
                          │  RawSignal objects
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      SCORING ENGINE                              │
│                                                                  │
│         URR Score  =  Urgency  ×  Relevance  ×  Recency         │
│                                                                  │
│   • Urgency    — keyword + sender weight analysis                │
│   • Relevance  — learned from user feedback over time           │
│   • Recency    — exponential decay (λ = ln2 / half-life)        │
└─────────────────────────┬────────────────────────────────────────┘
                          │  ScoredSignal objects (ranked, noise filtered)
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    NARRATOR  (Groq LLM)                          │
│                                                                  │
│   Mood Detection → Context Memory → Persona Injection           │
│   5 concurrent LLM calls via asyncio.gather()                   │
│   hook / situation / actions / financial / close                │
└─────────────────────────┬────────────────────────────────────────┘
                          │  Structured briefing
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DELIVERY LAYER                              │
│                                                                  │
│        WhatsApp (Twilio)          Voice MP3 (ElevenLabs)        │
│        Morning 8 AM IST           Evening 6 PM IST              │
│        Weekly Sunday Review       Dashboard (FastAPI)           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Features

### Intelligence Layer

**URR Scoring Model**
Every signal gets a composite score before the LLM ever sees it. Signals below the noise floor (URR < 0.08) are discarded entirely.

```python
# Exponential decay — same mathematics as radioactive decay
recency = e^(-λt)    where λ = ln(2) / half_life_per_source

# Source-specific half-lives
DECAY_HALFLIFE_HOURS = {
    SignalSource.BANK_SMS:  3.0,   # financial alerts decay fast
    SignalSource.WEATHER:   4.0,
    SignalSource.ACADEMIC:  6.0,
    SignalSource.GMAIL:     8.0,
}

# Relevance drifts toward what you actually act on
if feedback_count >= 5:
    learned_relevance = 0.3 * base_weight + 0.7 * historical_act_rate
```

**Mood Detection**
Before generating the briefing, SAGE classifies the day based on signal urgency distribution:
- 🔴 **Stressful** — avg URR > 0.65 or 3+ high-urgency signals → warmer, more supportive tone
- 🟡 **Busy** — moderate urgency → direct and efficient
- 🟢 **Calm** — low urgency → analytical and forward-looking

**Context Memory**
SAGE reads yesterday's briefing from the database and injects it into today's prompt. It knows what it told you before. It tracks whether you acted on it.

**Study Streak Tracking**
Counts consecutive days of task completion using the same algorithm as Duolingo. Calls you out if you've been slacking. Acknowledges streaks.

---

### Signal Sources

| Source | What it collects | Urgency logic |
|--------|-----------------|---------------|
| Gmail | Emails from last 16h, classified by sender type | Keyword matching + sender weight |
| Google Calendar | Today's events with times | Always high urgency |
| Weather | Temp, rain probability, commute risk, clothing advice | Rain > 60% or wind > 40km/h → high |
| Bank SMS | Transaction amount, balance, channel (UPI/NEFT/ATM) | Balance < ₹500 → critical |
| Tasks | Pending tasks with deadlines | Overdue = 0.98, due tomorrow = 0.90 |
| Exams | Countdown from profile | < 7 days = 0.88, < 3 days = 0.98 |

---

### Delivery

**Evening Briefing (6 PM IST)**
Full narrative with hook, situation report, action items, financial pulse, and closing line. Delivered as WhatsApp message + voice MP3.

**Morning Briefing (8 AM IST)**
Lightweight WhatsApp — today's class schedule, weather, exam countdown. No LLM, no latency.

**Weekly Review (Sunday 7 PM IST)**
Performance summary — briefings delivered, tasks completed, signals acted on, streak status.

**WhatsApp Commands**
Reply to SAGE directly:
```
status                          → list pending tasks
done 2                          → mark task #2 complete
add task: revise OS by friday   → create a task with deadline
help                            → show all commands
```

---

### Dashboard

PIN-protected web interface served by FastAPI:

- Exam countdown cards with color-coded urgency (green → yellow → red)
- Task manager — add, complete, delete tasks
- Raw signals panel — see every signal SAGE collected, its source, URR score, and timestamp
- Briefing history — last 7 days
- Mood badge — today's day classification
- Study streak badge
- Profile editor — edit goals, tone, exam dates from the UI
- Audio player for voice briefing
- System health bar — green/red dots per module, last run time

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.11, FastAPI | Async-native, fast, clean API design |
| LLM | Groq (LLaMA 3.3 70B) | Fastest inference, free tier |
| Scheduler | APScheduler | Cron-style jobs inside the FastAPI process |
| Database | SQLite + aiosqlite | Zero-config, async, sufficient for personal use |
| Voice | ElevenLabs / gTTS fallback | High quality with automatic fallback |
| Messaging | Twilio WhatsApp API | Reliable delivery, webhook support |
| Email/Calendar | Google APIs (OAuth2) | Official, reliable |
| Weather | OpenWeatherMap | Free tier, accurate |
| Frontend | Vanilla JS + CSS | No framework overhead, full control |
| Deployment | Docker + Railway | One-command deploy, auto-redeploy on push |

---

## Project Structure

```
sage/
├── main.py                  # FastAPI app + all API routes + scheduler
├── run_briefing.py          # Pipeline orchestration (evening + morning + weekly)
├── config.py                # Pydantic settings from .env
│
├── brain/
│   ├── scorer.py            # URR model, exponential decay, feedback learning
│   ├── narrator.py          # LLM briefing generation, mood detection
│   └── memory.py            # Episodic memory, streak tracking
│
├── modules/                 # Signal collectors
│   ├── gmail_reader.py      # Gmail OAuth2, sender classification
│   ├── calendar_reader.py   # Google Calendar events
│   ├── weather.py           # OpenWeatherMap + impact analysis
│   └── bank_sms.py          # Regex SMS parser (amount, balance, channel)
│
├── delivery/
│   ├── voice.py             # ElevenLabs TTS + gTTS Indian English fallback
│   └── whatsapp_sender.py   # Twilio, WhatsApp markdown formatting
│
├── models/
│   └── signals.py           # RawSignal, ScoredSignal dataclasses
│
├── db/
│   ├── database.py          # init_db + safe migrations
│   └── schema.sql           # signals, briefings, tasks, feedback, pipeline_runs
│
├── frontend/
│   ├── index.html
│   ├── app.js               # Fetch, render, CRUD, audio player
│   └── style.css            # Dark theme, CSS custom properties
│
└── data/
    ├── profile.json         # Name, schedule, exams, goals, tone
    └── sage.db              # SQLite database
```

---

## Database Schema

```sql
signals          -- every collected signal with URR scores and metadata
briefings        -- generated briefings + base64 audio (survives restarts)
signal_feedback  -- thumbs up/down per signal (feeds the scorer)
pipeline_runs    -- health tracking: status, duration, per-module results
tasks            -- personal task manager with priorities and due dates
```

---

## Running Locally

```bash
git clone https://github.com/yourusername/sage
cd sage

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your API keys

python -m db.database          # initialise database
python run_briefing.py         # run pipeline once
uvicorn main:app --reload      # start server → localhost:8000
```

**Required environment variables:**

```env
GROQ_API_KEY=
OPENWEATHER_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=
ELEVENLABS_API_KEY=
YOUR_WHATSAPP_NUMBER=
DASHBOARD_PIN=
LAT=
LON=
CITY=
```

---

## Deployment

```bash
git push origin main   # Railway auto-deploys on every push
```

Gmail OAuth tokens are base64-encoded and stored as environment variables — no files committed to git.

```bash
base64 -i data/token.json | tr -d '\n'        # → GMAIL_TOKEN_B64
base64 -i data/credentials.json | tr -d '\n'  # → CREDENTIALS_B64
```

---

## Engineering Decisions Worth Noting

**Why SQLite and not Postgres?**
This is a single-user personal tool. SQLite with aiosqlite gives full async support with zero infrastructure overhead. The entire database is one file.

**Why store audio as base64 in SQLite?**
Railway's free tier has ephemeral storage — files disappear on restart. Storing the MP3 as base64 in the database means voice briefings survive container restarts without needing a persistent volume.

**Why 5 concurrent LLM calls instead of one?**
Each briefing section (hook, situation, actions, financial, close) has a different system prompt and token budget. Running them concurrently with `asyncio.gather()` cuts generation time from ~15s to ~5s.

**Why exponential decay for recency?**
Linear decay would treat a 1-hour-old signal and a 7-hour-old signal as proportionally different. Exponential decay models the real-world intuition that very recent signals are much more valuable, and the value drops off sharply — same mathematics as radioactive decay and memory forgetting curves.

---

## What I Built This With

No tutorials. No boilerplate. Designed the architecture, wrote every module, and iterated through real daily use.

Built as a 2nd year B.Tech CS student at NIT Hamirpur.

---

<div align="center">

*If you're reading this as a recruiter or interviewer — I'm happy to walk through any part of the codebase, explain the scoring model, or discuss the design decisions in detail.*

</div>
