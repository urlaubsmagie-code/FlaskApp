# Technology Stack

**Analysis Date:** 2026-02-17

## Languages

**Primary:**
- Python 3.x - All application logic, services, models, routes

**Secondary:**
- HTML (Jinja2 templates) - Server-side rendered views in `templates/chatbot/`
- CSS - Styling in `static/css/`
- JavaScript - Frontend interactivity in `static/js/`

## Runtime

**Environment:**
- Python (version not pinned; no `.python-version` or `pyproject.toml` found)

**Package Manager:**
- pip - Via `requirements.txt`
- Lockfile: Not present (no `pip.lock` or `poetry.lock`)

## Frameworks

**Core:**
- Flask >= 3.0.0 - Web framework; application factory pattern (`app.py:create_app()`)
- Flask-SQLAlchemy >= 3.1.1 - ORM for all database operations (`models.py`)
- Flask-Login >= 0.6.3 - User session management (installed, not yet wired in routes)
- Werkzeug >= 3.0.0 - WSGI utilities, bundled with Flask

**Build/Dev:**
- python-dotenv >= 1.0.0 - Loads `.env` file into environment at startup (`run.py`)

## Key Dependencies

**Critical:**
- `requests` >= 2.31.0 - HTTP client for all Ollama API calls (`services/ai_service.py`)
- `google-api-python-client` >= 2.100.0 - Gmail REST API access (`services/gmail_service.py`)
- `google-auth-oauthlib` >= 1.1.0 - Google OAuth 2.0 flow for Gmail (`services/gmail_service.py`)
- `google-auth-httplib2` >= 0.1.1 - Google auth transport (`services/gmail_service.py`)

**Infrastructure:**
- SQLite (default) - Local file database at `instance/chatbot.db`; no additional driver needed
- PostgreSQL (optional production) - `psycopg2-binary` commented out in `requirements.txt`

## Configuration

**Environment:**
- `.env` file loaded by `python-dotenv` at startup
- `.env.example` documents all required variables (see `C:\Users\admin\Documents\FlaskApp\ChatBotAI\.env.example`)
- Key environment variables:
  - `FLASK_ENV` - `development` | `production` | `testing`
  - `SECRET_KEY` - Flask session signing key
  - `DATABASE_URL` - Database URI (defaults to SQLite)
  - `OLLAMA_URL` - Ollama server URL (default: `http://localhost:11434`)
  - `OLLAMA_MODEL` - Model name (default: `mistral:7b-instruct`)
  - `OLLAMA_TIMEOUT` - Request timeout seconds (default: `30`)
  - `AI_AUTO_RESPONSE_ENABLED` - Toggle auto AI responses
  - `AI_MEMORY_EXTRACTION_ENABLED` - Toggle memory extraction
  - `AI_RESPONSE_TONE` - AI tone setting
  - `MAX_CONVERSATION_HISTORY` - Messages sent to AI for context

**Configuration Classes** (`config.py`):
- `DevelopmentConfig` - DEBUG=True, SQLALCHEMY_ECHO=True
- `ProductionConfig` - DEBUG=False, expects PostgreSQL via `DATABASE_URL`
- `TestingConfig` - TESTING=True, uses in-memory SQLite

**Build:**
- No build step required; pure Python server-side rendered app
- Static assets served directly by Flask (`static/`)

## Platform Requirements

**Development:**
- Python 3.x installed
- Ollama server running locally at `http://localhost:11434` with `mistral:7b-instruct` pulled
- Optional: Google Cloud credentials JSON at `ChatBotAI/credentials.json` for Gmail

**Production:**
- PostgreSQL database (psycopg2-binary driver needed, currently commented out in `requirements.txt`)
- Ollama server accessible at configured `OLLAMA_URL`
- Public HTTPS URL for Gmail push notification webhooks (optional feature)
- `instance/` directory writable for SQLite or token storage

---

*Stack analysis: 2026-02-17*
