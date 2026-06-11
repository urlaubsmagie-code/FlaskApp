# CLAUDE.md — FlaskApp (Urlaubsmagie)

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**Urlaubsmagie** is a production Flask application for vacation rental management. It has two main components:

1. **Bewertungsportal** (Review Portal) — Review analytics, rankings, slideshow display, data processing for 65+ Airbnb/Booking.com properties
2. **ChatBotAI** (Urlaubsmagie Messenger) — Unified guest messaging with AI responses, persistent guest memory, multi-platform inbox (Smoobu/Airbnb/Booking.com/Gmail)

ChatBotAI is a Flask Blueprint registered into the main app. It has its own `CLAUDE.md` with detailed architecture — refer to `ChatBotAI/CLAUDE.md` for ChatBotAI-specific guidance.

## Running the Application

```bash
# Production (from FlaskApp root)
start_server.bat   # Launches Flask (Waitress, port 80) + Cloudflare tunnel

# Development
python app.py      # Direct Flask dev server
```

Access:
- Local: http://127.0.0.1 or http://192.168.178.36
- External: https://umteamsbz.com (via Cloudflare tunnel `umteam-flask`)

## Architecture

### Main App (`app.py`)
Single-file Flask app (~3,450 lines). Handles review loading, translation, analytics, snapshots, and all non-ChatBotAI routes. Registers ChatBotAI blueprint at `/chatbot`.

### Key Routes — Review Portal

**Pages:**
- `/` — Homepage (menu grid)
- `/reviews?category=neuen|allem` — Review listing (new vs all)
- `/slideshow` — Auto-rotating TV display (30s per review, optimized for 55"+ screens)
- `/analytics` — Weekly trends with Chart.js, snapshot-based history
- `/rankings` — Apartment star ratings (all-time)
- `/apartment-issues` — Problem tracking per apartment
- `/reviews/digital-team` — Digital team filtered view

**APIs:**
- `/api/reviews` — All reviews JSON
- `/api/stats` — Statistics
- `/api/translate` — On-the-fly German translation (deep-translator, cached)
- `/api/digital-team/export-excel` — Excel exports (multiple endpoints)
- `/api/snapshots` — Snapshot management
- `/api/analytics-weekly` — Weekly analytics data
- `/api/apartment-issues` — Apartment problems

### ChatBotAI Blueprint (`/chatbot/*`)
See `ChatBotAI/CLAUDE.md` for full details. Key: inbox, conversations, guest profiles, AI settings, knowledge base, statistics, debug dashboard.

### Data Pipeline

```
n8n Docker (C:\n8n_Docker\Files\)
  ├── DatasetScrAN.json (Airbnb reviews)
  ├── DatasetScrBookingAN.json (Booking reviews)
  ├── ID.txt (Airbnb apartment code mapping)
  └── IDB.txt (Booking URL-to-code mapping)
       ↓
app.py load_reviews() → 5-min cache → Routes/APIs
       ↓
Snapshot system (MD5 hash detection → /data/snapshots/)
```

### Key Data Files
- `apartment_config.json` — Maps 45+ apartment IDs to codes (UT, F3, H4, B1, etc.)
- `data/snapshots/` — Timestamped dataset backups (auto-created on data changes)
- `data/DataProblemListing/` — Per-apartment issue JSON files
- `HRFinal.json` — Consolidated historical reviews

### Scrapers & Scripts
- `airbnb_scraper_robust.py` — Playwright-based Airbnb review scraper
- `scripts/` — Utility scripts
- `analyze_*.py`, `export_*.py`, `extract_*.py` — Data processing and export tools

## Deployment

```
Windows PC (192.168.178.36)
├── Flask App (Waitress WSGI, 4 threads, port 80)
│   ├── Review Portal (root routes)
│   └── ChatBotAI Blueprint (/chatbot/*)
├── Cloudflare Tunnel → https://umteamsbz.com
├── Ollama Server (gemma2:9b + qwen3:8b)
├── n8n Docker (data ingestion workflows)
└── SQLite DB (ChatBotAI, instance/ folder)
```

## Configuration

- `apartment_config.json` — Apartment ID mappings
- `C:\n8n_Docker\Files\ID.txt` / `IDB.txt` — Platform-specific ID mappings
- ChatBotAI config: see `ChatBotAI/CLAUDE.md`
- Server: Waitress on port 80 (production), Flask dev server (development)

## Key Design Decisions

1. **Single app.py for review portal** — All review logic in one file with caching. ChatBotAI is the only modularized component (blueprint with services).
2. **Translation on-the-fly** — Reviews translated to German via deep-translator with caching to avoid repeated API calls.
3. **Snapshot system** — MD5 hash comparison detects data changes and auto-creates timestamped backups for historical analytics.
4. **n8n as data source** — Review data comes from n8n Docker workflows, not scraped directly by the Flask app in production.
5. **German-first UI** — All user-facing text in German, English as fallback.

## External Integrations

- **n8n** — Automation workflows for review scraping/data enrichment
- **Cloudflare Tunnel** — External HTTPS access without port forwarding
- **Ollama** — Local LLM for ChatBotAI AI features
- **Smoobu API** — Property management, guest messaging (ChatBotAI)
- **Gmail API** — Email integration (ChatBotAI)
- **deep-translator** — Google Translate for review translation
