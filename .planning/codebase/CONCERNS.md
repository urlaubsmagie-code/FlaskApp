# Codebase Concerns

**Analysis Date:** 2026-02-17

---

## Tech Debt

**Duplicate guest-finding logic in two services:**
- Issue: `find_or_create_guest()` logic is copy-pasted nearly identically in both `MemoryService` and `MessageRouter`. Any bug fix or change must be applied in two places.
- Files: `services/memory_service.py` (lines 282-385), `services/message_router.py` (lines 267-347)
- Impact: Inconsistency risk; one copy has already diverged slightly (e.g., `MessageRouter` sets `first_contact`/`last_contact` on create, `MemoryService` does not).
- Fix approach: Remove `find_or_create_guest` from `MemoryService` and delegate to `MessageRouter._find_or_create_guest` or extract into a shared utility in `utils/`.

**`MessageRouter` initializes without services, lazy-loads inconsistently:**
- Issue: `MessageRouter.__init__` sets `self.ai_service = None` and `self.memory_service = None`, then lazy-loads via `_get_services()`. However, `get_message_router()` creates a new instance if none exists (bypassing `init_message_router`), so services may not be bound if the router is auto-created before app context is ready.
- Files: `services/message_router.py` (lines 27-36, 504-509)
- Impact: Potential `None` service references for AI and memory on first cold call.
- Fix approach: Either always require explicit `init_message_router()` call or use `current_app` config to initialize lazily but safely.

**`app.py` duplicates initialization done in `__init__.py`:**
- Issue: `create_app()` in `app.py` and `init_chatbot()` in `__init__.py` both call `db.create_all()`, `_populate_default_settings()`, `init_ai_service()`, and `init_memory_service()`. This means different code paths run based on how the app is started.
- Files: `app.py` (lines 37-47), `__init__.py` (lines 24-42)
- Impact: Risk of double initialization; confusing for future contributors.
- Fix approach: Consolidate all initialization into `init_chatbot()` and have `create_app()` call it.

**`AISettings` values are silently ignored at runtime:**
- Issue: Settings like `auto_response_enabled` and `memory_extraction_enabled` are stored in the database (`models.py` lines 342-348) but are never read back at runtime to gate behavior. Only the environment variable config values are used.
- Files: `models.py` (lines 311-329), `services/message_router.py`
- Impact: Settings UI changes have no effect on actual behavior.
- Fix approach: Read `AISettings.get()` values in the message router before performing auto-responses or memory extraction.

**`utils/` directory is empty:**
- Issue: `utils/__init__.py` exists with 3 lines (just a docstring/empty file). No utility functions exist yet.
- Files: `utils/__init__.py`
- Impact: Shared logic (like guest deduplication) ends up duplicated in services instead.
- Fix approach: Move shared helper logic here as it is extracted from services.

---

## Known Bugs

**Duplicate `router` variable in `api_gmail_reply`:**
- Symptoms: In `routes.py` line 803-804, a `router` is obtained via `get_message_router()` for the AI generation path, then a second `router = get_message_router()` is called unconditionally at line 827 for `process_owner_message`. The variable is assigned twice within the same function scope, which is harmless but wasteful and confusing.
- Files: `routes.py` (lines 798-833)
- Trigger: Any call to `POST /api/gmail/reply/<conversation_id>` that goes through AI generation.
- Workaround: None needed; functionally correct but wasteful.

**`health_check` always reports `database: True` without verification:**
- Symptoms: The `/chatbot/health` endpoint returns `"database": True` unconditionally. It never actually queries the database to verify connectivity.
- Files: `routes.py` (lines 296-307)
- Trigger: Database connection failure would not be reported by the health check.
- Workaround: None; health check is misleading in failure scenarios.

**`per_page` is not bounded in conversation pagination:**
- Symptoms: `api_get_conversations` accepts user-supplied `per_page` with no maximum cap. A caller can request `per_page=999999` and receive all records in one response.
- Files: `routes.py` (lines 71-87)
- Trigger: Any `GET /api/conversations?per_page=100000` request.
- Workaround: None.

**`max_results` is not bounded in Gmail email fetch routes:**
- Symptoms: `api_get_emails` and `api_get_unread_emails` accept user-supplied `max_results` with no maximum. Each Gmail result triggers a separate individual API call in `get_recent_emails`, meaning a large `max_results` triggers N+1 Gmail API calls.
- Files: `routes.py` (lines 616, 637), `services/gmail_service.py` (lines 195-209)
- Trigger: Any `GET /api/gmail/emails?max_results=500`.
- Workaround: None.

---

## Security Considerations

**Hardcoded fallback secret key in production path:**
- Risk: `SECRET_KEY` defaults to `'dev-secret-key-change-in-production'` if the env var is not set. If `SECRET_KEY` is never set in a production deployment, sessions are cryptographically weak.
- Files: `config.py` (line 16)
- Current mitigation: Comment in the value warns developer to change it.
- Recommendations: Raise an explicit `RuntimeError` in `ProductionConfig` if `SECRET_KEY` env var is absent. Never provide a fallback default in production config.

**No authentication or authorization on any route:**
- Risk: All API endpoints, settings, guest data, conversation history, and Gmail OAuth flows are publicly accessible. Any user on the network can read all guest PII, send messages, modify AI settings, or trigger email sending.
- Files: `routes.py` (all routes), `__init__.py`
- Current mitigation: `flask-login` is listed in `requirements.txt` but not imported, configured, or used anywhere in the codebase.
- Recommendations: Implement `flask-login` session authentication. Protect all routes with `@login_required`. At minimum, protect all `/api/` and `/gmail/` routes before any production deployment.

**Test/demo routes exposed with no environment guard:**
- Risk: `POST /api/test/create-conversation`, `POST /api/test/simulate-message`, and `POST /api/test/bulk-create` are always registered and allow creation of arbitrary guest and conversation records. These endpoints bypass any real platform validation.
- Files: `routes.py` (lines 334-463)
- Current mitigation: None. Routes are always active regardless of `FLASK_ENV`.
- Recommendations: Guard with `if app.config.get('TESTING') or app.config.get('DEBUG')` at blueprint registration time, or remove from production builds entirely.

**OAuth state parameter not validated on callback:**
- Risk: In `gmail_callback`, the CSRF state stored in the Flask session is retrieved but passed to `handle_oauth_callback` as an optional parameter. The `GmailService.handle_oauth_callback` method accepts state but does not compare it against the stored state before calling `flow.fetch_token`. This means the state check provides no real CSRF protection.
- Files: `routes.py` (lines 563-592), `services/gmail_service.py` (lines 124-153)
- Current mitigation: State is retrieved from session and passed along (but not validated).
- Recommendations: Explicitly verify that the `state` from the callback URL matches the `state` in the session before proceeding.

**Guest PII sent in plain logs:**
- Risk: Guest names, emails, preferences, and allergies are logged at `INFO` level throughout the services. In any environment where logs are stored or forwarded, this creates a PII trail.
- Files: `services/memory_service.py` (line 212), `services/message_router.py` (lines 96, 107)
- Current mitigation: None.
- Recommendations: Log guest IDs only (not names or emails) at INFO level. Reserve PII details for DEBUG level with a note that DEBUG should never be enabled in production.

**Webhook endpoints accept any payload with no verification:**
- Risk: The four webhook endpoints (`/webhook/gmail`, `/webhook/whatsapp`, `/webhook/airbnb`, `/webhook/booking`) are stubs that return `{"status": "received"}` but do no signature verification. When real webhook logic is added, any external actor can send forged payloads.
- Files: `routes.py` (lines 264-289)
- Current mitigation: Stubs do nothing harmful.
- Recommendations: When implementing webhooks, add HMAC signature validation for each platform before processing any payload.

---

## Performance Bottlenecks

**Synchronous AI calls block the request thread:**
- Problem: `ai_service.extract_guest_info()` and `ai_service.generate_guest_response()` are synchronous HTTP calls to Ollama with a 30-second timeout. Each incoming message blocks the Flask worker thread for up to 30 seconds while AI processes.
- Files: `services/ai_service.py` (lines 51-77), `services/memory_service.py` (line 50), `services/message_router.py` (lines 126, 438)
- Cause: Flask runs synchronously; long Ollama calls hold the WSGI worker.
- Improvement path: Offload memory extraction to a task queue (Celery, RQ) or use Flask's async support. AI response generation for auto-reply could be queued and delivered asynchronously.

**N+1 Gmail API calls in `get_recent_emails`:**
- Problem: `get_recent_emails` first fetches a list of message IDs, then calls `get_email_by_id` for each individual message. For 20 emails this is 21 API requests.
- Files: `services/gmail_service.py` (lines 195-209)
- Cause: Gmail list API returns only IDs; full content requires per-message fetch.
- Improvement path: Use Gmail batch API or reduce `max_results` default.

**`get_all_guests` loads all records without pagination:**
- Problem: `api_get_all_guests` loads all `Guest` records with `Guest.query.all()` and serializes them all into a single JSON response.
- Files: `routes.py` (lines 486-493)
- Cause: No pagination applied.
- Improvement path: Apply the same `paginate()` pattern used in `api_get_conversations`.

**`_populate_default_settings` queries DB on every app startup:**
- Problem: `_populate_default_settings` is called inside `create_app` and also inside `init_chatbot`. This runs N queries on every application start or blueprint registration.
- Files: `models.py` (lines 340-355), `app.py` (lines 39-41), `__init__.py` (line 37)
- Cause: No guard prevents double-execution.
- Improvement path: Add a startup migration table or call this only once from a CLI command.

---

## Fragile Areas

**Global service singletons break under test isolation:**
- Files: `services/ai_service.py` (line 336), `services/memory_service.py` (line 471), `services/message_router.py` (line 493), `services/gmail_service.py` (line 490)
- Why fragile: Module-level `_ai_service`, `_memory_service`, `_message_router`, `_gmail_service` globals persist across tests. A test that initializes a service will leave it initialized for subsequent tests, causing state leakage.
- Safe modification: Always call `init_*` functions in test setup and clear globals in teardown. Long-term: replace module globals with Flask `g` or app extensions.
- Test coverage: No tests exist; this issue has not yet been observed.

**`MemoryService.store_detail` commits after every single detail:**
- Files: `services/memory_service.py` (lines 209-210)
- Why fragile: A single message can produce many extracted details. Each `store_detail` call issues a `db.session.commit()`. If one commit fails mid-extraction, partial data is already committed.
- Safe modification: Accumulate all details within a single transaction per message, commit once in `_store_extracted_info`.
- Test coverage: None.

**`Conversation.platform_id` uniqueness constraint can cause silent failures:**
- Files: `models.py` (line 122), `services/message_router.py` (lines 360-376)
- Why fragile: `platform_id` is `unique=True`. `_find_or_create_conversation` queries by `platform_id` then creates. Under concurrent requests for the same `platform_id`, two requests could both find no existing record and both attempt inserts, causing an IntegrityError that surfaces as a 500.
- Safe modification: Add `try/except IntegrityError` around the insert and re-query on conflict.
- Test coverage: None.

**HTML stripping in `_get_email_body` is a naive regex:**
- Files: `services/gmail_service.py` (line 289)
- Why fragile: `re.sub('<[^<]+?>', '', html_body)` does not handle malformed HTML, script tags with embedded content, or HTML entities. AI extraction will receive dirty text with entities like `&amp;` or `&nbsp;` intact.
- Safe modification: Use `html.parser` from the stdlib (`html.unescape` + `HTMLParser`) or `bleach` for robust HTML-to-text conversion.
- Test coverage: None.

---

## Scaling Limits

**SQLite as default database:**
- Current capacity: Suitable for single-process development only.
- Limit: SQLite does not support concurrent writes. Multiple Gunicorn workers will cause database lock errors.
- Scaling path: Switch to PostgreSQL (`psycopg2-binary` already commented out in `requirements.txt`). Set `DATABASE_URL` env var in production.

**Single Ollama instance with no retry or fallback:**
- Current capacity: One local Ollama server, 30-second timeout.
- Limit: If Ollama is slow or restarts, all in-flight requests time out and auto-responses fail silently.
- Scaling path: Add retry logic in `ai_service.generate_response`, implement a circuit-breaker, or support multiple Ollama endpoints.

---

## Dependencies at Risk

**`flask-login` is in requirements but unused:**
- Risk: Listed in `requirements.txt` but never imported or configured. This creates a false sense that auth is implemented, and it adds an unnecessary dependency.
- Files: `requirements.txt` (line 3)
- Impact: Misleading; `flask-login` version drift may cause install conflicts without benefit.
- Migration plan: Either implement authentication using `flask-login` or remove it from `requirements.txt` until auth is actively built.

**No pinned dependency versions (ranges only):**
- Risk: `flask>=3.0.0` and other range-specified deps mean `pip install` on different dates may produce different environments.
- Files: `requirements.txt`
- Impact: Reproducibility issues; a breaking change in a minor version of a dependency could silently break the app.
- Migration plan: Generate a `requirements-lock.txt` with pinned versions via `pip freeze > requirements-lock.txt` and use it in CI/CD.

---

## Missing Critical Features

**No authentication implemented:**
- Problem: The entire application is unauthenticated. All guest data, conversation history, settings, and send-email actions are unprotected.
- Blocks: Any production deployment; any multi-user scenario.

**Webhook handlers are empty stubs:**
- Problem: All four platform webhook handlers (`/webhook/gmail`, `/webhook/whatsapp`, `/webhook/airbnb`, `/webhook/booking`) return `{"status": "received"}` with no processing logic.
- Blocks: Real-time message ingestion from any platform.
- Files: `routes.py` (lines 264-289)

**No background task queue:**
- Problem: AI memory extraction and response generation block HTTP request threads. No async task system exists.
- Blocks: Scalable concurrent message handling.

**No email deduplication for Gmail polling:**
- Problem: `api_process_gmail_emails` processes unread emails and marks them read, but if the same email is processed twice before being marked read (e.g., concurrent polling calls), duplicate messages and guest details will be created.
- Files: `routes.py` (lines 719-774)

---

## Test Coverage Gaps

**No tests exist anywhere:**
- What is not tested: The entire codebase. No test files found under any path.
- Files: All `.py` files
- Risk: Any refactor, bug fix, or new feature can introduce regressions with no automated detection. The most critical untested paths are guest identification (`find_or_create_guest`), memory extraction persistence, and AI response generation.
- Priority: High

**Guest deduplication logic is untested:**
- What is not tested: Email/phone/platform-ID matching priority in `find_or_create_guest`. Duplicate platform IDs across concurrent requests.
- Files: `services/memory_service.py` (lines 282-385), `services/message_router.py` (lines 267-347)
- Risk: Silent guest record duplication could cause memory data to be split across two guest records.
- Priority: High

**Memory extraction is untested:**
- What is not tested: AI JSON parsing in `extract_guest_info`, `_store_extracted_info` deduplication, partial extraction failure handling.
- Files: `services/ai_service.py` (lines 79-140), `services/memory_service.py` (lines 82-155)
- Risk: Corrupted or partial AI output can silently produce wrong guest data (e.g., wrong allergy information stored).
- Priority: High

**OAuth flow is untested:**
- What is not tested: `gmail_authorize`, `gmail_callback`, state validation, token refresh.
- Files: `services/gmail_service.py`, `routes.py` (lines 508-592)
- Risk: OAuth regressions go undetected; token refresh failures could silently disconnect Gmail.
- Priority: Medium

---

*Concerns audit: 2026-02-17*
