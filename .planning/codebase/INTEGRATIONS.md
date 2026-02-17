# External Integrations

**Analysis Date:** 2026-02-17

## APIs & External Services

**AI / LLM:**
- Ollama (local inference server) - Generates guest responses and extracts structured info from messages
  - SDK/Client: `requests` (raw HTTP via `services/ai_service.py`)
  - Endpoint: `POST {OLLAMA_URL}/api/generate` (non-streaming)
  - Health check: `GET {OLLAMA_URL}/api/tags`
  - Auth: None (local service, no token required)
  - Default model: `mistral:7b-instruct`
  - Config: `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`

**Email:**
- Gmail API (Google Cloud) - Read inbox, send emails, manage threads
  - SDK/Client: `google-api-python-client` + `google-auth-oauthlib` (`services/gmail_service.py`)
  - Auth: OAuth 2.0, credentials stored at `ChatBotAI/credentials.json` (downloaded from Google Cloud Console)
  - Token storage: `instance/gmail_token.json` (auto-refreshed on expiry)
  - Scopes: `gmail.readonly`, `gmail.send`, `gmail.modify`
  - OAuth callback route: `GET /chatbot/gmail/callback`
  - Config: `GMAIL_CREDENTIALS_FILE`, `GMAIL_TOKEN_FILE`

**Short-term Messaging (Planned / Stubbed):**
- WhatsApp - Webhook stub registered at `POST /chatbot/webhook/whatsapp`; no SDK wired
  - Config vars defined: `WHATSAPP_API_URL`, `WHATSAPP_API_TOKEN`
  - Status: TODO (stub returns `{status: received}`)
- Airbnb - Webhook stub at `POST /chatbot/webhook/airbnb`; no SDK wired
  - Config vars defined: `AIRBNB_API_URL`, `AIRBNB_API_TOKEN`
  - Status: TODO (stub returns `{status: received}`)
- Booking.com - Webhook stub at `POST /chatbot/webhook/booking`; no SDK wired
  - Config vars defined: `BOOKING_API_URL`, `BOOKING_API_TOKEN`
  - Status: TODO (stub returns `{status: received}`)

## Data Storage

**Databases:**
- SQLite (development default)
  - Connection: `sqlite:///instance/chatbot.db` (relative to `ChatBotAI/`)
  - Client: Flask-SQLAlchemy ORM (`models.py`)
  - Tables: `guest`, `guest_detail`, `conversation`, `message`, `property`, `ai_settings`
- PostgreSQL (production target, not yet active)
  - Connection: `DATABASE_URL` environment variable
  - Driver: `psycopg2-binary` (commented out in `requirements.txt` - must uncomment for production)
  - Client: Flask-SQLAlchemy (same ORM, transparent switch)

**File Storage:**
- Local filesystem only
  - Gmail OAuth token: `instance/gmail_token.json`
  - Gmail credentials: `ChatBotAI/credentials.json` (must be provided by operator)
  - SQLite database: `instance/chatbot.db`

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- Flask-Login installed but not yet wired into routes (no `@login_required` decorators observed)
- Gmail OAuth 2.0 handled by `services/gmail_service.py` using `google-auth-oauthlib`
  - Authorization URL: `GET /chatbot/gmail/authorize/redirect` (browser redirect)
  - Callback: `GET /chatbot/gmail/callback` (exchanges code for token)
  - Disconnect: `POST /chatbot/gmail/disconnect` (deletes token file)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)

**Logs:**
- Python `logging` module used throughout all services
  - Level: DEBUG in development, INFO in production (set in `app.py:create_app()`)
  - Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
  - Destination: stdout (no file handler configured)

**Health Check:**
- `GET /chatbot/health` - Returns JSON with database status and Ollama connectivity status

## CI/CD & Deployment

**Hosting:**
- Not configured; Flask dev server used via `run.py`

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars for full functionality:**
- `SECRET_KEY` - Must be changed from default for production
- `DATABASE_URL` - Required for PostgreSQL in production; defaults to SQLite in dev
- `OLLAMA_URL` - Ollama server address (default `http://localhost:11434` works locally)
- `OLLAMA_MODEL` - Must match a pulled model in the Ollama instance

**Optional env vars:**
- `GMAIL_CREDENTIALS_FILE` - Path to Google OAuth credentials JSON
- `GMAIL_TOKEN_FILE` - Path to store OAuth tokens
- `WHATSAPP_API_URL`, `WHATSAPP_API_TOKEN` - Not yet functional
- `AIRBNB_API_URL`, `AIRBNB_API_TOKEN` - Not yet functional
- `BOOKING_API_URL`, `BOOKING_API_TOKEN` - Not yet functional

**Secrets location:**
- `.env` file (not committed; `.env.example` is committed as template)
- `ChatBotAI/credentials.json` - Google OAuth client secrets (not committed)
- `instance/gmail_token.json` - OAuth access/refresh token (not committed; auto-generated)

## Webhooks & Callbacks

**Incoming:**
- `POST /chatbot/webhook/gmail` - Gmail push notification receiver (stub only)
- `POST /chatbot/webhook/whatsapp` - WhatsApp message receiver (stub only)
- `POST /chatbot/webhook/airbnb` - Airbnb message receiver (stub only)
- `POST /chatbot/webhook/booking` - Booking.com message receiver (stub only)
- `GET /chatbot/gmail/callback` - Google OAuth redirect callback (active)

**Outgoing:**
- Gmail send: `POST` to Gmail API v1 via `services/gmail_service.py`
- Ollama inference: `POST {OLLAMA_URL}/api/generate` via `services/ai_service.py`

---

*Integration audit: 2026-02-17*
