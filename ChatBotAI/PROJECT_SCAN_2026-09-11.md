# FlaskApp / ChatBotAI project scan

Scanned 2026-09-11. This is a working architecture and maintenance baseline, grounded in the current checkout and read-only database inspection. It is not a penetration test or a live integration certification.

## What this project is

Urlaubsmagie has two connected Flask applications:

- **FlaskApp**: the review portal, with Airbnb/Booking review aggregation, rankings, weekly analytics, apartment problem tracking, Excel exports, and a TV slideshow.
- **ChatBotAI / UMI**: the team's guest communications workspace, registered at `/chatbot`. It combines Smoobu messages, Gmail notification recovery, WhatsApp, guest memory, AI drafting, escalation, knowledge management, reply templates, and team statistics.

The parent is not just a launcher. It contains substantial business logic and imports ChatBotAI's translation service. Changes to shared services can affect both products.

## Repository boundaries and scale

There are **two nested Git repositories**, one at FlaskApp and another at ChatBotAI. The parent also tracks ChatBotAI files. Consequently, a file can be clean in the inner repository and modified in the outer repository.

- ChatBotAI HEAD at scan: `c8498a9` (`feat(inbox+team): cleaner inbox header, team-wide Team-Leistung, Berlin-day stats, one unread count`).
- Inner repository: 265 tracked files, no tracked modifications observed, but many untracked implementation files, tests, migrations, and documents.
- Parent repository: 700 tracked files and existing modifications, including `app.py`, `start_server.bat`, snapshot metadata, and several ChatBotAI files.
- Parent `app.py`: 3,458 lines and 25 route declarations.
- ChatBotAI `routes.py`: 147 route declarations, approximately 5,600 lines.
- ChatBotAI `models.py`: 1,076 lines.
- Services: 24 files, approximately 9,659 lines.
- Frontend: 10 main JavaScript files, approximately 7,563 lines; 16 templates, approximately 6,463 lines.
- Migrations: 27 revision files, ending at `p24_knowledge_is_internal`.

Avoid broad Git operations until the intended repository is explicit. Untracked does not mean disposable: current WhatsApp implementation and numerous migrations/tests are among the untracked files.

## Runtime and startup

### Integrated deployment

`FlaskApp/start_server.bat` starts `python app.py`, the Cloudflare tunnel, and the WhatsApp bridge. Parent `app.py` loads `ChatBotAI/.env`, creates a bare Flask app, and registers `chatbot_bp`. Its main block starts **Waitress on port 80 with 16 threads**. Older notes saying four threads are stale.

Blueprint registration runs `ChatBotAI/__init__.py:on_register()` and `init_chatbot()`:

1. Establish default database/AI configuration.
2. Initialize login, package file logging, database, migrations, defaults, and core services.
3. Restore the saved AI model.
4. Start Smoobu sync, email reconciliation, and keepalive daemon functions.

### Standalone development

`python -m ChatBotAI.run` from the parent calls `ChatBotAI/app.py:create_app()`. This path additionally loads configuration classes, proxy handling, compression, SQLite connection pragmas, FTS verification, debug tracking, and an Ollama connection check.

**These paths are not equivalent.** This is the most consequential architectural fact for future changes: a successful standalone test does not prove production initialization is correct.

### Background work

- Smoobu webhook processing is the main event-driven ingestion path.
- Smoobu daemon: startup pass, then every 600 seconds; recent-thread discovery plus reservation/message sync, multi-account routing, and read-state reconciliation.
- Gmail email reconciliation: every 120 seconds, controlled by its saved setting and Gmail authentication.
- Keepalive: configured public-URL polling, when enabled by app configuration.
- Other work uses process-local threads, locks, caches, and global service instances. This is designed around one Waitress process; adding workers would require reviewing these assumptions.

## Main workflows and code map

| Area | Main files | Responsibility |
|---|---|---|
| HTTP/UI orchestration | `routes.py`, `templates/chatbot/` | Inbox, messages, AI suggestions, settings, knowledge, users, reports, integration endpoints |
| Persistence | `models.py`, `migrations/` | Guests, messages, conversations, properties, settings, knowledge, users, push subscriptions |
| Message lifecycle | `services/message_router.py` | Guest matching, conversation creation, deduplication, storage, unread state, memory extraction, escalation, AI response orchestration |
| Smoobu | `services/smoobu_service.py` | Reservations, properties, account-aware messaging, synchronization, legacy and signed request authentication |
| Gmail recovery | `services/gmail_service.py`, `email_reconcile.py` | OAuth, notification parsing/authenticity checks, conversation matching, missing-message recovery |
| AI | `services/ai_service.py`, `prompt_tier.py`, `prompt_loader.py`, `prompts/` | Ollama calls, rich/compact prompts, extraction, summaries, reply generation, escalation markers |
| Guest memory | `services/memory_service.py`, `guest_matching.py` | Cross-channel identity and atomic remembered facts with source/confidence |
| Knowledge retrieval | `models.py:KnowledgeEntry`, `services/context_filter.py` | Global/street/property scope, internal-only exclusion, relevance scoring, corrections/examples |
| WhatsApp | `whatsapp_bridge/index.js`, `services/whatsapp_service.py` | Node/Baileys linked-device bridge, inbound webhooks, outbound send queue, pairing/status |
| Notion | `services/notion_client.py`, `notion_mapper.py`, `notion_scrubber.py`, `notion_service.py` | Read pages, classify/scrub content, upsert knowledge/templates, remove stale synced rows |
| Frontend | `static/js/{inbox,conversation,knowledge,app,polling,i18n,umi}.js` | Server-rendered pages with browser-side filtering controls, polling, drafts, translation, settings |
| PWA/push | `static/sw.js`, `pwa-install.js`, `services/push_service.py` | Installability and browser notifications; no offline conversation cache |

Typical incoming flow:

`Smoobu / Gmail recovery / WhatsApp -> identify guest and conversation -> deduplicate and store -> timestamps/unread state -> memory/push/escalation -> optional reply generation or draft`

Outgoing delivery is platform-specific. Smoobu replies use a process-local per-conversation lock around duplicate checking, sending, and storage. Failed-message retry is a separate path. The transport can succeed before local persistence succeeds; the code does not have a durable transactional outbox.

### AI behavior that matters

- The database-selected model at scan time is **`kimi-k3:cloud`**. Calls use the Ollama interface, but the selected model is cloud-tagged; the old description of an exclusively local model is inaccurate.
- Saved `master_ai_enabled` is **false**. Manual drafting remains useful independently of unattended replies.
- Rich prompts include recent two-sided history, scoped knowledge, guest context, corrections/examples, and summaries. Compact prompts intentionally restrict knowledge/history.
- Knowledge retrieval has a 45,000-character full-knowledge budget before relevance-based reduction.
- `pending_guest_question()` combines unanswered guest messages; per-message suggestions deliberately target a chosen message instead.
- Internal knowledge rows are filtered from normal guest-reply retrieval. Escalation values are kept out of guest prompts; topic labels/trigger phrases drive escalation.
- Unattended AI/urgency paths have a 48-hour recency gate. Fixed check-in auto-replies have a separate setting and 30-minute gate; they are not governed by the master AI toggle. Their setting was absent, so their default was off at scan time.
- WhatsApp inbound handling requests no automatic AI response. Phone-originated owner messages are now ingested, and bridge-originated echoes are deduplicated.

## Database snapshot

Read directly with SQLite `mode=ro` and query-only mode. Counts can change while the real application is running.

| Entity | Count |
|---|---:|
| Guests | 6,129 |
| Guest details | 28,490 |
| Conversations | 4,218 |
| Messages | 26,131 |
| Properties | 67 |
| Knowledge entries | 114 |
| Users | 9 |
| Email backfill candidates, all statuses | 588 |

Conversation platforms: 4,192 Smoobu, 20 WhatsApp, six playtests. Gmail currently contributes recovered messages rather than a separate population of email-platform conversations.

Knowledge entries: 85 guest-facing and 29 internal; 105 tagged manual and nine tagged AI. No entries were tagged `source='notion'`; that does not rule out manually imported Notion material.

Database validation:

- Revision is `p24_knowledge_is_internal`.
- All model-declared columns are present.
- SQLite `quick_check`: `ok`.
- Foreign-key check: zero violations.
- Duplicate non-null platform message IDs: zero groups.
- FTS row count and message count both equal 26,131. Equal counts do not prove every indexed value is current.
- Journal mode is WAL. This does not establish that every production connection enables foreign-key enforcement or the configured busy timeout.

## Confirmed findings and investigation priorities

### 1. Production configuration bypasses important factory behavior — high priority

Parent `app.py:27` creates a bare Flask app and immediately registers the blueprint. It does not load `Config`/`ProductionConfig`. `__init__.py:126` supplies a hardcoded development secret when the app has none. Loading `.env` alone does not assign its `SECRET_KEY` to Flask configuration.

As written, this startup path bypasses the standalone secret validation and configured secure/SameSite cookie settings. It also bypasses `_setup_sqlite_pragmas()`, `_ensure_fts5_index()`, compression, proxy middleware, and `init_debug_service()`. Prioritize consistent initialization before assuming changes in `config.py` affect production. This conclusion is from source, not inspection of the running process's configuration.

### 2. Logging/send reliability needs a focused follow-up

The package rotating file handler is now installed in both startup paths, so the old statement that production has no handler is obsolete. However, production still lacks debug API-tracker initialization. Alembic logging configuration and live logger state need separate examination before claiming that all production logging works.

`send_message()` returns no useful failure detail to its callers. `_request()` already logs HTTP failures; the open task's claim of absolutely no send-error logging is too broad. Failed sends that later succeed on retry lose their `failed:` marker when `platform_message_id` is replaced. The normal guarded send path stores only successful sends, leaving no durable failure history there.

The reported ~10% failure rate is an older operational report, not independently measured by this scan. Blindly retrying message POSTs could duplicate guest delivery. The duplicate guard catches normalized exact text within two minutes; lightly edited resends can pass.

### 3. Notion sync is implemented but not initialized

`services/notion_service.py:181` defines `init_notion_service()`, but neither startup path calls it. The configured sync route at `routes.py:2248` returns 500 when `get_notion_service()` is `None`. Existing service tests instantiate the service directly, so they do not demonstrate successful application initialization.

Additionally, `sync()` continues after individual page-fetch failures, then deletes synced rows absent from the successful `seen` set (`notion_service.py:161`). A partial upstream failure can therefore delete previously imported content. Review deletion behavior before enabling regular sync. Newly imported entries also need deliberate internal/public classification; the importer does not assign `is_internal`.

### 4. Existing security work is incomplete

- There is a blueprint-wide login gate (`routes.py:122`), so the old audit's blanket missing-decorator finding should not be repeated as an unauthenticated-access conclusion.
- Smoobu webhook verification is conditional on a configured secret; without it, POSTs are accepted (`routes.py:4269`). Live secret configuration was not inspected.
- No explicit CSRF-token mechanism was found in the inspected application code.
- `static/js/app.js:83` inserts toast message text directly into `innerHTML`. This is an unsafe rendering primitive; exploitability requires tracing individual callers and attacker-controlled inputs.
- Setup accepts four-character passwords; there is no visible application-level login rate limiter in the inspected login path.

These are source findings, not proof that a specific attack has occurred. No external security scanning was performed.

### 5. Test isolation is incomplete

`TestingConfig` uses in-memory SQLite, but blueprint startup still treats `DEBUG=False` as production and starts daemons unless explicitly suppressed. Factory construction also checks Ollama and installs logging. Tests need a consistent fixture that isolates services, background work, and filesystem output.

One existing playtest route test writes to `app.instance_path` without a temporary override. During this scan's permitted rerun, it touched **`FlaskApp/instance/playtest_notes.json`**, an existing sidecar. No baseline copy of that sidecar was captured, so this scan cannot claim it remained unchanged. Application source was not edited and the operational chatbot database was opened read-only for inspection.

### 6. Maintainability and unfinished integration edges

- Large route/service files and repeated AI/send paths make behavior drift likely.
- Global services and process-local send/sync locks constrain multi-process deployment.
- Startup automatically runs migrations and column repairs; merely launching the app is not a read-only inspection action.
- WhatsApp retries are in-memory and finite. Media without text/captions is not represented as a message; attachment support is absent.
- The PWA is installable but does not provide offline message access.
- A large existing webhook log was observed in the parent instance directory, alongside ChatBotAI's separate instance directory. File paths depend on whether code uses `app.instance_path` or the package directory.
- Python requirements use lower bounds rather than a lockfile. Installed versions differ from historical audit assumptions. This scan did not check current public vulnerability advisories.
- Older plans and `OPEN_TASKS.md` mix resolved issues with unresolved reports. Use code/tests and current measurements as the baseline.

## Verification performed

- Python AST parsing: **180 files passed**, including parent application/scripts and ChatBotAI source, tests, and migrations.
- JavaScript syntax: **13 files passed**.
- Focused Python selection: 127 passed initially; temporary-directory errors were resolved on rerun.
- Broad Python run: **468 passed**, with one failure and five setup errors in filesystem-dependent playtest tests. Rerunning the two affected modules with filesystem access produced **14 passed**, covering all six affected cases. Thus all 474 collected Python cases passed across these runs, not in a single untouched full-suite invocation.
- The broad run patched startup daemons, file-logger installation, and the Ollama connectivity probe in the test process, and blocked socket connections. It used in-memory test databases. These results validate tested logic, not live service connectivity or production startup parity.
- Both Node test scripts passed: inbox date grouping and translation language markers.
- WhatsApp bridge `selfcheck.js` passed without starting the bridge.
- Approximately 10,000 warnings in the broad suite were mainly repeated `datetime.utcnow()` and legacy SQLAlchemy `Query.get()` deprecations.

No server was started, no account sync was requested, and no guest messages were sent. No implementation fixes were applied. Test-generated filesystem output and this report are the scan's write side effects.

## Broader FlaskApp context

- Review ingestion reads Windows-specific files under `C:\n8n_Docker\Files`, with five-minute caching and JSON snapshots under `FlaskApp/data`.
- `FlaskApp/docs/wohnungsprobleme_pipeline.md` specifies the problem-list data contract and proposed n8n processing steps. The Flask reader expects the nested `message.content.wohnungen` envelope.
- `airbnb-reviews-scraper/` is a separate Node/Apify/Crawlee/Playwright scraping project. Its package has a placeholder test command.
- Root Python scripts handle historical review aggregation, contact enrichment, exports, apartment mappings, backup scheduling, and diagnostics.
- `n8n-new/` contains deployment configuration; `n8n-backup/` contains backup artifacts. Backup contents, credential files, guest message bodies, full datasets, and archived worktrees were not exhaustively read.
- Root README describes an older slideshow-only application and is not a reliable current architecture guide.

## Suggested next work

1. Unify and test the actual production initialization path, including secrets, cookies, logging, and database connection setup.
2. Capture durable send-attempt outcomes and diagnose a real failed send before changing retry policy.
3. Repair Notion initialization and partial-failure deletion behavior before relying on sync.
4. Establish isolated shared test fixtures and clarify the nested-repository workflow.
5. Evaluate reply quality with a fixed set of real, anonymized scenarios covering multiple unanswered questions, rates, reservation context, property/street scope, internal knowledge, and escalation.

This ordering is a proposed starting point, not authorization to implement changes.
