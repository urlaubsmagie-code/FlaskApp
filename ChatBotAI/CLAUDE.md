# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChatBotAI is a Flask-based unified guest messaging system for vacation rental hosts. It integrates with multiple communication platforms (Email/Gmail, WhatsApp, Airbnb, Booking.com) and uses Ollama AI to generate personalized responses while maintaining persistent guest memory.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (from parent directory)
python -m ChatBotAI.run

# Or run directly
python ChatBotAI/run.py
```

The server runs at http://localhost:5000 by default. All routes are under the `/chatbot` prefix.

## Architecture

### Application Factory Pattern
- `app.py`: Contains `create_app()` factory function and `run_development_server()`
- `config.py`: Configuration classes (Development, Production, Testing) with environment variable support
- `__init__.py`: Blueprint registration and `init_chatbot()` for integration with larger Flask apps

### Core Services (services/)

**AIService** (`ai_service.py`):
- Interfaces with Ollama API at `http://localhost:11434`
- `extract_guest_info()`: Extracts structured data (family, pets, preferences, allergies) from messages
- `generate_guest_response()`: Creates personalized responses using guest profile and conversation history

**MemoryService** (`memory_service.py`):
- Persistent guest memory storage - the key differentiating feature
- `process_message_for_memory()`: Extracts and stores guest details from both guest AND owner messages
- `get_guest_profile()`: Retrieves complete guest profile for AI context
- `find_or_create_guest()`: Smart guest identification across platforms (email > phone > platform ID)

**MessageRouter** (`message_router.py`):
- Central orchestrator for all message flow
- `process_incoming_message()`: Main entry point - identifies guest, manages conversation, stores message, extracts memory, generates AI response
- `process_owner_message()`: Handles outgoing messages with memory extraction

**GmailService** (`gmail_service.py`):
- Gmail API integration with OAuth 2.0
- Requires `credentials.json` from Google Cloud Console in ChatBotAI folder
- Token stored in `instance/gmail_token.json`

### Database Models (models.py)

- **Guest**: Central record with platform identifiers (email, phone, whatsapp_id, airbnb_id, booking_id)
- **GuestDetail**: Extracted memory items (family, pet, preference, allergy, interest, special_request) with AI confidence scores
- **Conversation**: Platform threads with AI toggle per conversation
- **Message**: Individual messages with `sender_type` (guest, owner, ai) and processing status
- **Property**: Rental property details for AI context
- **AISettings**: Key-value store for AI configuration

### Routes (routes.py)

Page routes render Jinja2 templates from `templates/chatbot/`:
- `/chatbot/` - Inbox view
- `/chatbot/conversation/<id>` - Single conversation thread
- `/chatbot/guest/<id>` - Guest profile with memories
- `/chatbot/settings` - AI configuration

API routes (`/api/*`) return JSON for AJAX operations.

Test routes (`/api/test/*`) allow creating sample conversations without real platform integrations.

## Configuration

Key environment variables:
- `FLASK_ENV`: development/production/testing
- `OLLAMA_URL`: Ollama server URL (default: http://localhost:11434)
- `OLLAMA_MODEL`: Model name (default: mistral:7b-instruct)
- `SECRET_KEY`: Flask secret key
- `DATABASE_URL`: Database URI (default: SQLite in instance folder)

## Key Design Decisions

1. **Memory extraction runs on ALL messages** (guest and owner) because hosts often mention guest details in their responses

2. **GuestDetail stores atomic facts** with confidence scores and source message references for audit

3. **Guest identification priority**: email (most reliable) > phone > platform-specific ID

4. **Services use global instances** initialized at app startup, retrieved via `get_*_service()` functions

5. **AI responses include full context**: guest profile, property info, and recent conversation history

## Open Audits / Pending Triage

### Deep Scan — 2026-05-21 (read-only, no code changed)
Five parallel subagents audited security, backend, frontend, data layer, and dependencies. Findings logged for later triage; user reviews before any fix is applied.

**Reports (in ChatBotAI/ root):**
- `SCAN_2026-05-21_MASTER.md` — consolidated triage, severity rollup, suggested wave order
- `SCAN_2026-05-21_security.md` — 15 findings (HIGH: missing @login_required on ~10 API routes, no CSRF, Smoobu webhook unverified, weak session cookies, SECRET_KEY fallback)
- `SCAN_2026-05-21_backend.md` — 27 findings (CRITICAL: session leak in background daemon, guest-dedup race, unread reconciliation orders by id not sent_at, silent AI commit failures)
- `SCAN_2026-05-21_frontend.md` — 17 findings (CRITICAL: 2 innerHTML XSS sinks in inbox.js:522 + conversation.js:482; HIGH: polling listener leaks, send double-click race)
- `SCAN_2026-05-21_data.md` — 16 findings (CRITICAL: migration p16 cancelled_at not applied to prod DB, Conversation.updated_at missing onupdate)
- `SCAN_2026-05-21_dependencies.md` — actionable CVEs in cryptography (<46), Werkzeug (<3.0.6), waitress (<3.0.2), requests (<2.32.4), Jinja2 unpinned

**Totals:** ~84 findings — CRIT 8 / HIGH 21 / MED 35 / LOW 17 / INFO 3.

**Suggested wave order (not yet executed):**
- Wave A — prod-safety/data integrity (items 1–5, 7 in MASTER)
- Wave B — auth decorators across routes.py (item 8)
- Wave C — XSS sinks + CSP (item 6)
- Wave D — CVE bumps (cryptography / Werkzeug / waitress / Jinja2)
- Wave E — backend hardening (Smoobu retry parsing, AI semaphore deadline, webhook sig)
- Wave F — CSRF + secure cookies (Flask-WTF integration)
- Wave G — frontend polish (polling guard, listener delegation, send-flag)

**Status:** awaiting user decision on which waves to execute. Do NOT auto-fix; user wants to drive selection from the MASTER log.
