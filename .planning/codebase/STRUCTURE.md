# Codebase Structure

**Analysis Date:** 2026-02-17

## Directory Layout

```
ChatBotAI/                        # Package root (Python package)
├── __init__.py                   # Blueprint definition, init_chatbot(), on_register hook
├── app.py                        # Application factory (create_app, run_development_server)
├── config.py                     # Config classes (Development, Production, Testing)
├── models.py                     # SQLAlchemy models (Guest, GuestDetail, Conversation, Message, Property, AISettings)
├── routes.py                     # All URL routes (page, API, webhook, Gmail, test)
├── run.py                        # Development server entry point
├── requirements.txt              # Python dependencies
├── CLAUDE.md                     # Project instructions for Claude Code
├── .env                          # Local environment variables (do not commit)
├── .env.example                  # Template for environment variables
├── services/                     # Business logic services
│   ├── __init__.py               # Empty package marker
│   ├── ai_service.py             # Ollama AI integration (AIService class + singleton)
│   ├── memory_service.py         # Guest memory extraction/storage (MemoryService class + singleton)
│   ├── message_router.py         # Message orchestration (MessageRouter class + singleton)
│   └── gmail_service.py          # Gmail API OAuth2 integration (GmailService class + singleton)
├── templates/                    # Jinja2 HTML templates
│   └── chatbot/                  # Namespaced under chatbot/ (matches blueprint name)
│       ├── base.html             # Base layout template
│       ├── inbox.html            # Conversation list / dashboard
│       ├── conversation.html     # Single conversation thread view
│       ├── guest_profile.html    # Guest profile with memory details
│       ├── settings.html         # AI settings configuration
│       └── gmail_error.html      # Gmail OAuth error page
├── static/                       # Frontend static assets
│   ├── css/
│   │   └── style.css             # Application stylesheet
│   └── js/
│       └── app.js                # Frontend JavaScript (AJAX, UI interactions)
├── utils/                        # Shared utilities
│   └── __init__.py               # Currently empty; reserved for utility functions
└── instance/                     # Runtime data (not committed)
    └── chatbot.db                # SQLite database file (auto-created)
```

## Directory Purposes

**`services/`:**
- Purpose: All business logic - AI, memory, message routing, platform integrations
- Contains: One class per service with a global singleton pattern (`init_*` + `get_*` functions)
- Key files: `message_router.py` (central orchestrator), `ai_service.py` (Ollama), `memory_service.py` (guest memory), `gmail_service.py` (Gmail OAuth)

**`templates/chatbot/`:**
- Purpose: Server-rendered HTML pages using Jinja2
- Contains: One template per page view; all extend `base.html`
- Note: Namespaced under `chatbot/` subdirectory to avoid conflicts when embedded in larger Flask apps

**`static/`:**
- Purpose: Browser-served assets (CSS, JS)
- Contains: Single CSS file, single JS file
- URL path: `/chatbot/static/` (set by blueprint `static_url_path`)

**`utils/`:**
- Purpose: Reserved for shared helper functions (currently empty)
- Contains: `__init__.py` only

**`instance/`:**
- Purpose: Runtime files not committed to version control
- Contains: `chatbot.db` (SQLite), `gmail_token.json` (OAuth token after Gmail connection)
- Generated: Yes
- Committed: No (in `.gitignore`)

## Key File Locations

**Entry Points:**
- `run.py`: CLI entry point, calls `run_development_server()` from `app.py`
- `app.py`: `create_app()` factory, `run_development_server()` function
- `__init__.py`: Blueprint object `chatbot_bp`, `init_chatbot()`, `on_register` hook

**Configuration:**
- `config.py`: All config classes; `get_config()` selects class based on `FLASK_ENV`
- `.env.example`: Documents all required environment variables
- `__init__.py` (`on_register`): Sets SQLAlchemy, Ollama defaults via `app.config.setdefault()`

**Core Logic:**
- `services/message_router.py`: `MessageRouter.process_incoming_message()` - main message pipeline
- `services/memory_service.py`: `MemoryService.process_message_for_memory()`, `get_guest_profile()`
- `services/ai_service.py`: `AIService.extract_guest_info()`, `generate_guest_response()`
- `services/gmail_service.py`: OAuth2 flow, email fetch, send, thread management

**Database:**
- `models.py`: All SQLAlchemy models; `db = SQLAlchemy()` instance; `_populate_default_settings()`
- `instance/chatbot.db`: SQLite DB (auto-created by `db.create_all()` in `create_app`)

**Routes:**
- `routes.py`: All endpoints registered on `chatbot_bp`; imported at end of `__init__.py`

**Templates:**
- `templates/chatbot/base.html`: Master layout; all other templates extend this
- `templates/chatbot/inbox.html`: Main dashboard
- `templates/chatbot/conversation.html`: Message thread view
- `templates/chatbot/guest_profile.html`: Guest memory display

## Naming Conventions

**Files:**
- Snake_case for all Python files: `ai_service.py`, `memory_service.py`, `message_router.py`
- Descriptive suffixes: `*_service.py` for service classes, `*_router.py` for router
- Templates use snake_case: `guest_profile.html`, `inbox.html`

**Directories:**
- Lowercase, no hyphens: `services/`, `templates/`, `static/`, `utils/`
- Templates namespaced under `chatbot/` subdirectory

**Classes:**
- PascalCase: `AIService`, `MemoryService`, `MessageRouter`, `GmailService`
- Model classes match table intent: `Guest`, `GuestDetail`, `Conversation`, `Message`

**Functions:**
- Service init pattern: `init_<name>_service()` / `get_<name>_service()`
- Route functions: snake_case matching action: `api_get_conversations()`, `api_send_message()`
- Private helpers: leading underscore `_find_or_create_guest()`, `_store_message()`

**Global Variables:**
- Service singletons: `_ai_service`, `_memory_service`, `_message_router` (underscore prefix = private)

## Where to Add New Code

**New Platform Integration (e.g., SMS, Telegram):**
- Implementation: `services/<platform>_service.py` (follow `gmail_service.py` pattern)
- Webhook route: add to `routes.py` under `# WEBHOOK ROUTES` section
- Platform API routes: add to `routes.py` under a new section for that platform
- Config vars: add to `config.py` `Config` class with `os.environ.get()` defaults

**New Service:**
- Implementation: `services/<name>_service.py`
- Pattern: Create class, module-level `_<name>_service = None`, `init_<name>_service()`, `get_<name>_service()`
- Initialize: Call `init_<name>_service()` in `app.py` `create_app()` within app context

**New API Endpoint:**
- Location: `routes.py`, within appropriate section comment block
- Use `@chatbot_bp.route('/api/...')` decorator
- Return `jsonify(...)` for success, `jsonify({'error': '...'}), <code>` for errors

**New Page View:**
- Route: `routes.py` (use `render_template('chatbot/<name>.html', ...)`)
- Template: `templates/chatbot/<name>.html` (extend `base.html`)

**New Model:**
- Location: `models.py`
- Add `to_dict()` method on all models
- Register in `db.create_all()` (automatic via SQLAlchemy)

**Utility Functions:**
- Shared helpers: `utils/__init__.py` or a new file under `utils/`

## Special Directories

**`instance/`:**
- Purpose: Runtime-generated files (database, OAuth tokens)
- Generated: Yes - `instance/` dir created by `__init__.py` `on_register` hook
- Committed: No

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No (in `.gitignore`)

**`.planning/`:**
- Purpose: GSD planning documents - architecture analysis, implementation plans
- Generated: Yes (by GSD tools)
- Committed: No (should be in `.gitignore`)

---

*Structure analysis: 2026-02-17*
