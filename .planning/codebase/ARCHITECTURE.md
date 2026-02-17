# Architecture

**Analysis Date:** 2026-02-17

## Pattern Overview

**Overall:** Flask Blueprint with Service Layer

**Key Characteristics:**
- Application Factory pattern (`create_app()`) enables flexible initialization and testing
- Flask Blueprint (`chatbot_bp`) registered at `/chatbot` prefix - allows embedding in larger Flask apps
- Service Layer isolates business logic from HTTP routes; services accessed via global singleton instances
- Persistent memory is the core differentiating feature: every message (guest AND owner) is analyzed by AI for extractable facts stored as atomic `GuestDetail` rows

## Layers

**HTTP Layer:**
- Purpose: Handle HTTP requests, render templates, return JSON responses
- Location: `routes.py`
- Contains: Page routes (HTML), API routes (JSON), webhook stubs, Gmail OAuth routes, test/demo routes
- Depends on: Models (direct DB queries), Services (via `get_*_service()` functions)
- Used by: External clients, browsers

**Service Layer:**
- Purpose: Business logic orchestration and external API integration
- Location: `services/`
- Contains: `AIService`, `MemoryService`, `MessageRouter`, `GmailService`
- Depends on: Models (SQLAlchemy), Ollama HTTP API, Gmail HTTP API
- Used by: Routes

**Data Layer:**
- Purpose: Database schema definition and ORM operations
- Location: `models.py`
- Contains: `Guest`, `GuestDetail`, `Conversation`, `Message`, `Property`, `AISettings`
- Depends on: Flask-SQLAlchemy
- Used by: Services, Routes

**Configuration Layer:**
- Purpose: Environment-specific settings
- Location: `config.py`
- Contains: `Config`, `DevelopmentConfig`, `ProductionConfig`, `TestingConfig`
- Depends on: `os.environ`
- Used by: `app.py` (`create_app`)

## Data Flow

**Incoming Guest Message Flow:**

1. External platform (Gmail webhook, WhatsApp, etc.) or test route POSTs to `/chatbot/api/test/simulate-message` or a webhook endpoint
2. `MessageRouter.process_incoming_message()` is called (`services/message_router.py`)
3. Router calls `_find_or_create_guest()` - matches by email > phone > platform ID
4. Router calls `_find_or_create_conversation()` - matches by `platform_id`
5. Router calls `_store_message()` - persists the `Message` row with `sender_type='guest'`
6. `MemoryService.process_message_for_memory()` is called - AI extracts structured facts, stored as `GuestDetail` rows
7. If `auto_respond=True` and `conversation.ai_enabled=True`, `_generate_ai_response()` is called
8. `AIService.generate_guest_response()` builds prompt from guest profile + conversation history + property info
9. AI response stored as a `Message` row with `sender_type='ai'`
10. Result dict returned to caller

**Outgoing Owner Message Flow:**

1. Owner POSTs message content to `/chatbot/api/conversations/<id>/messages`
2. Route creates `Message` with `sender_type='owner'` and saves to DB
3. `MemoryService.process_message_for_memory()` runs on owner message - owners often mention guest details
4. Response returned to UI

**AI Response Generation (on-demand):**

1. POST to `/chatbot/api/conversations/<id>/ai-response`
2. Route fetches last 10 messages and last guest message
3. `MemoryService.get_guest_profile()` builds complete profile dict from all `GuestDetail` rows
4. `AIService.generate_guest_response()` sends structured prompt to Ollama `/api/generate`
5. AI message stored and returned

**State Management:**
- All state is persisted in SQLite (default) or PostgreSQL (production) via SQLAlchemy ORM
- No in-memory session state for messages or guests; services are stateless singletons
- `ai_enabled` flag is per-Conversation, toggled via `PUT /chatbot/api/conversations/<id>/toggle-ai`

## Key Abstractions

**MessageRouter (`services/message_router.py`):**
- Purpose: Central orchestrator for all message flows; single entry point for processing
- Pattern: Service class with global singleton via `get_message_router()`
- Key method: `process_incoming_message()` coordinates guest identification, message storage, memory extraction, AI response

**AIService (`services/ai_service.py`):**
- Purpose: Wraps Ollama HTTP API; handles prompt construction, response parsing, JSON extraction
- Pattern: Service class with global singleton via `get_ai_service()`
- Key methods: `extract_guest_info()` (returns structured dict), `generate_guest_response()` (returns plain text)

**MemoryService (`services/memory_service.py`):**
- Purpose: Persistent guest memory - extraction, storage, deduplication, retrieval
- Pattern: Service class with global singleton via `get_memory_service()`
- Key methods: `process_message_for_memory()`, `get_guest_profile()`, `store_detail()` (with deduplication)

**GuestDetail (memory atom):**
- Purpose: Single extracted fact about a guest (e.g., `detail_type='allergy'`, `detail_key='food'`, `detail_value='peanuts'`)
- Location: `models.py` (`GuestDetail` class)
- Pattern: Atomic fact with confidence score and source message reference for audit trail
- Confidence defaults: `allergy=0.95`, `family/pet=0.9`, `preference/special_request=0.85`, `interest=0.8`, manual=`1.0`

**Global Service Singletons:**
- Pattern used in `ai_service.py`, `memory_service.py`, `message_router.py`
- Each service module holds a module-level `_service` variable
- `init_*_service()` called at app startup; `get_*_service()` called by routes/other services
- Example: `get_ai_service()` returns `Optional[AIService]` - callers must null-check

## Entry Points

**Development Server:**
- Location: `run.py` and `app.py` (`run_development_server()`)
- Triggers: `python run.py` or `python -m ChatBotAI.run`
- Responsibilities: Creates app via factory, starts Flask dev server on port 5000

**Application Factory:**
- Location: `app.py` (`create_app()`)
- Triggers: Called by `run.py`, tests, or parent Flask apps
- Responsibilities: Configures Flask, initializes DB, initializes services, registers blueprint, adds root redirect

**Blueprint Registration:**
- Location: `__init__.py` (`on_register` hook)
- Triggers: Called when blueprint registers with parent Flask app
- Responsibilities: Sets default config values, calls `init_chatbot()`, ensures `instance/` directory exists

**Main Inbox:**
- Location: `routes.py` (`index()`)
- URL: `GET /chatbot/`
- Responsibilities: Queries all conversations ordered by `updated_at`, renders `inbox.html`

**Primary API Entry Point:**
- Location: `routes.py` (`api_process_gmail_emails()`)
- URL: `POST /chatbot/api/gmail/process`
- Responsibilities: Fetches unread Gmail emails and routes each through `MessageRouter.process_incoming_message()`

## Error Handling

**Strategy:** Try/except with logging; DB rollback on failure; result dicts with `success` and `error` keys

**Patterns:**
- All `MessageRouter` public methods wrap logic in `try/except Exception`, call `db.session.rollback()` on failure, return `{'success': False, 'error': str(e)}`
- Memory extraction failures are non-fatal (`logger.warning`) - message processing continues
- AI service unavailability is handled gracefully; routes return 503 if `get_ai_service()` returns None
- Ollama connection timeout/error logged and returns `None`; callers check for None

## Cross-Cutting Concerns

**Logging:** Python `logging` module; logger created per-module via `logging.getLogger(__name__)`; log level set to DEBUG in development, INFO in production via `app.py`

**Validation:** Minimal - routes check for required JSON keys and return 400 with error message; no schema validation library used

**Authentication:** No user authentication on any routes currently; Gmail OAuth flow implemented for Gmail connection only (`/chatbot/gmail/authorize`, `/chatbot/gmail/callback`); OAuth state stored in Flask session

---

*Architecture analysis: 2026-02-17*
