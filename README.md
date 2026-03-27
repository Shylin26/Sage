# SAGE — Personal AI Briefing Agent

> A fully autonomous personal intelligence system that collects signals from your digital life, scores them by urgency, and delivers a personalised daily briefing via WhatsApp and voice — every day at 6 PM.

**Live:** [sage-production-d82c.up.railway.app](https://sage-production-d82c.up.railway.app)

---

## What is SAGE?

SAGE (Signal Aggregation and Guided Execution) is a personal AI agent I built to replace the mental overhead of checking multiple apps every day. Instead of manually scanning Gmail, weather, calendar, and bank notifications — SAGE collects everything, scores it by urgency using a custom algorithm, generates a narrative briefing using an LLM, and delivers it as a WhatsApp message and voice audio every evening.

It runs 24/7 on a cloud server. I don't touch it. It just works.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Signal Sources                       │
│  Gmail  │  Google Calendar  │  Weather API  │  Bank SMS  │
└────────────────────┬────────────────────────────────────┘
                     │ RawSignal objects
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    Scoring Engine                        │
│         URR Score = Urgency × Relevance × Recency        │
│    Exponential decay · Learned weights from feedback     │
└────────────────────┬────────────────────────────────────┘
                     │ ScoredSignal objects (ranked)
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Narrator (Groq LLM)                     │
│   Mood detection · Context memory · Persona injection    │
│   5 concurrent Groq calls → hook/situation/actions/...   │
└────────────────────┬────────────────────────────────────┘
                     │ Structured briefing dict
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     Delivery Layer                       │
│        WhatsApp (Twilio)  │  Voice MP3 (ElevenLabs)      │
└─────────────────────────────────────────────────────────┘
```

---

## Features

### Signal Collection
- **Gmail** — reads emails from the last 16 hours, classifies senders (faculty, bank, internship, peer, promotion), scores urgency using keyword matching
- **Google Calendar** — fetches today's events and converts them to signals
- **Weather** — OpenWeatherMap API with commute risk and clothing advice for Hamirpur, HP
- **Bank SMS** — regex-based parser that extracts transaction amounts, balances, and channels (UPI/NEFT/ATM) from SMS forwarded via webhook
- **Tasks** — pending tasks with deadlines become signals; urgency increases as due date approaches
- **Exam countdown** — reads exam schedule from profile, generates high-urgency signals as exams approach

### Scoring Engine (`brain/scorer.py`)
Custom URR (Urgency × Relevance × Recency) scoring model:

```python
# Exponential decay — same math as radioactive decay
recency = e^(-λt)  where λ = ln(2) / half_life_per_source

# Relevance learned from feedback history
if feedback_count >= 5:
    learned_relevance = 0.3 * base + 0.7 * act_rate
```

- Each signal source has a different decay half-life (bank SMS: 3h, weather: 4h, Gmail: 8h)
- Relevance weights drift toward what the user actually acts on over time
- Signals below URR threshold 0.08 are filtered as noise

### Narrator (`brain/narrator.py`)
- Powered by **Groq (LLaMA 3.3 70B)**
- 5 sections generated concurrently via `asyncio.gather()` — hook, situation, actions, financial, close
- **Mood detection** — classifies the day as calm/busy/stressful based on signal urgency distribution, adjusts tone automatically
- **Context memory** — reads yesterday's briefing from DB, injects it into the prompt so SAGE can reference what it told you before
- **Study streak tracking** — counts consecutive days of task completion, calls you out or celebrates you

### Delivery
- **WhatsApp** via Twilio — formatted with bold headers and bullet points, auto-splits messages over 1500 chars
- **Voice** via ElevenLabs TTS (falls back to gTTS Indian English accent)
- **Morning briefing** at 8 AM IST — lightweight WhatsApp with today's schedule, weather, exam countdown
- **Evening briefing** at 6 PM IST — full narrative briefing + voice MP3
- **Weekly review** every Sunday — task completion rate, signals acted on, streak summary

### Dashboard
- Dark-themed web UI served by FastAPI
- PIN-protected (HTTP Basic Auth)
- Exam countdown widget with color-coded urgency
- Task manager with add/complete/delete
- Raw signals panel — see exactly what SAGE collected and why
- Briefing history — last 7 days
- Mood badge — shows day classification
- Study streak badge
- Profile editor — edit goals, tone, exam dates from the UI
- Audio player for voice briefing
- One-click pipeline trigger

### WhatsApp Commands
Reply to SAGE on WhatsApp:
```
status          → list pending tasks
done 2          → mark task #2 complete
add task: <title> by <day>  → create a task
help            → show all commands
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, APScheduler |
| LLM | Groq API (LLaMA 3.3 70B) |
| Database | SQLite via aiosqlite (async) |
| Voice | ElevenLabs TTS / gTTS fallback |
| Messaging | Twilio WhatsApp API |
| Email/Calendar | Google Gmail + Calendar API (OAuth2) |
| Weather | OpenWeatherMap API |
| Frontend | Vanilla JS, CSS custom properties |
| Deployment | Docker, Railway |

---

## Project Structure

```
sage/
├── main.py                 # FastAPI app, scheduler, all API routes
├── run_briefing.py         # Pipeline orchestration
├── config.py               # Pydantic settings
│
├── modules/                # Signal collectors
│   ├── gmail_reader.py
│   ├── calendar_reader.py
│   ├── weather.py
│   ├── bank_sms.py         # Regex SMS parser
│   └── whatsapp.py
│
├── brain/                  # Intelligence layer
│   ├── scorer.py           # URR scoring + exponential decay
│   ├── narrator.py         # LLM briefing generation
│   ├── memory.py           # Episodic memory + streak tracking
│   └── correlator.py
│
├── delivery/
│   ├── voice.py            # ElevenLabs + gTTS
│   └── whatsapp_sender.py
│
├── models/
│   ├── signals.py          # RawSignal, ScoredSignal dataclasses
│   └── briefing.py
│
├── db/
│   ├── database.py         # init + migrations
│   └── schema.sql
│
├── frontend/               # Dashboard UI
│   ├── index.html
│   ├── app.js
│   └── style.css
│
└── data/
    ├── profile.json        # Personal config (name, schedule, exams, goals)
    └── sage.db             # SQLite database
```

---

## Database Schema

```sql
signals         -- all collected signals with URR scores
briefings       -- generated briefings + audio (base64)
signal_feedback -- thumbs up/down per signal (feeds scorer)
pipeline_runs   -- health tracking per run
tasks           -- personal task manager
```

---

## Running Locally

```bash
git clone https://github.com/yourusername/sage
cd sage
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
python run_briefing.py  # run pipeline once
uvicorn main:app --reload  # start server
```

**Required API keys:**
- `GROQ_API_KEY` — [console.groq.com](https://console.groq.com)
- `OPENWEATHER_API_KEY` — [openweathermap.org](https://openweathermap.org/api)
- `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` — [twilio.com](https://twilio.com)
- `ELEVENLABS_API_KEY` — [elevenlabs.io](https://elevenlabs.io)
- Google OAuth credentials — [console.cloud.google.com](https://console.cloud.google.com)

---

## Deployment (Railway)

```bash
git push origin main  # Railway auto-deploys on push
```

Set environment variables in Railway dashboard. For Gmail OAuth tokens:
```bash
base64 -i data/token.json | tr -d '\n'       # → GMAIL_TOKEN_B64
base64 -i data/credentials.json | tr -d '\n' # → CREDENTIALS_B64
```

---

## What I Learned Building This

- **Async Python** — entire pipeline is async with `asyncio.gather()` for concurrent LLM calls
- **Signal processing** — designing a scoring model with exponential decay and learned weights
- **LLM prompt engineering** — mood-aware prompts, persona injection, memory context
- **OAuth2 flow** — Google API authentication with token refresh
- **Webhook patterns** — receiving real-time data from Twilio and SMS forwarder
- **Production deployment** — Docker, Railway, environment variable management, health checks
- **SQLite migrations** — safe schema evolution on a live database

---

## Author

**Parisha** — B.Tech CS, NIT Hamirpur (2nd Year)

Built entirely from scratch as a personal productivity tool. Every module, scoring algorithm, and prompt was designed and iterated on through real daily use.
