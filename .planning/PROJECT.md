# ChatBotAI - Dashboard UI Completion

## What This Is

A unified messaging dashboard for vacation rental hosts that aggregates guest communications from multiple platforms and uses local AI (Ollama) to provide intelligent, personalized auto-responses with persistent guest memory. This milestone completes the Dashboard UI (Step 7) to make the existing backend features usable through a polished interface.

## Core Value

The system remembers EVERYTHING about every guest permanently — extracting information from ALL messages (guest AND owner) to create truly personalized service for returning guests.

## Requirements

### Validated

<!-- Shipped and confirmed working (Steps 1-6) -->

- ✓ Flask Blueprint integration with parent FlaskApp — existing
- ✓ SQLite database with Guest, GuestDetail, Conversation, Message, Property, AISettings models — existing
- ✓ Ollama AI integration for response generation — existing
- ✓ AI-powered guest info extraction (family, pets, preferences, allergies) — existing
- ✓ Persistent guest memory with deduplication and confidence scores — existing
- ✓ Memory extraction from ALL messages (guest AND owner) — existing
- ✓ Cross-platform guest identification (email > phone > platform ID) — existing
- ✓ Message routing pipeline (incoming → identify → store → extract → respond) — existing
- ✓ Gmail OAuth 2.0 integration with email fetch/send — existing
- ✓ Basic inbox view showing conversations — existing
- ✓ Basic conversation view with message thread — existing
- ✓ Basic guest profile view displaying memories — existing
- ✓ Settings page with AI and Gmail configuration — existing
- ✓ AI toggle per conversation — existing
- ✓ Test endpoints for creating sample conversations — existing

### Active

<!-- Current scope - Step 7 Dashboard UI Completion -->

- [ ] Inbox filtering by platform (Email, WhatsApp, Airbnb, Booking)
- [ ] Inbox filtering by status (Active, Pending, Closed)
- [ ] Inbox filtering by guest
- [ ] Message search across conversations
- [ ] Guest profile editing (add/edit/delete details manually)
- [ ] Real-time inbox updates via polling (10-30 second interval)
- [ ] Real-time conversation updates via polling

### Out of Scope

<!-- Explicit boundaries -->

- Notifications (audio/visual alerts) — defer to future milestone
- Mobile-responsive optimization — defer to future milestone
- WhatsApp Business API integration — Gmail only for now
- Airbnb API integration — Gmail only for now
- Booking.com API integration — Gmail only for now
- WebSocket real-time updates — polling is simpler and sufficient
- Step 8 testing & refinement — separate milestone
- User authentication — single-user system for now

## Context

**Current State:** 75% complete (6/8 steps done). Core services work — AI extraction, memory persistence, Gmail integration all functional. UI exists but lacks filtering, search, editing, and real-time updates.

**Volume:** 10-50 active conversations expected — medium volume, need good organization but not enterprise-scale features.

**Technical Environment:**
- Flask Blueprint at `/chatbot` prefix
- SQLite database at `instance/chatbot.db`
- Ollama at `http://localhost:11434` with `mistral:7b-instruct`
- Existing templates: `base.html`, `inbox.html`, `conversation.html`, `guest_profile.html`, `settings.html`
- Existing CSS (~700 lines) and JS (~400 lines)

## Constraints

- **AI Server**: Must use local Ollama only — no external AI services
- **Platform**: Gmail integration only for v1 — other platforms deferred
- **Database**: SQLite for development — no schema changes to existing models unless necessary
- **Stack**: Flask/Jinja2/vanilla JS — no new frontend frameworks

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling over WebSocket | Simpler implementation, sufficient for 10-50 conversations, works everywhere | — Pending |
| Gmail only for v1 | Reduce scope, Gmail already integrated and working | — Pending |
| Feature complete over polish | Ship working features, polish in future milestone | — Pending |

---
*Last updated: 2026-02-17 after initialization*
