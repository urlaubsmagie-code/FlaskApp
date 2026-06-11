# Scan Fix Log — 2026-05-21

Source audit: `SCAN_2026-05-21_MASTER.md` (+ 5 per-domain reports).

## Backup safety net
- Git tag: `backup/pre-scan-2026-05-21` (HEAD before any change)
- Git stash: `stash@{0}` "backup-pre-scan-2026-05-21" (working tree incl. untracked)
- DB snapshot: `instance/chatbot.db.bak-pre-scan-20260521` (14 MB)
- Rollback any single fix via `git revert <sha>`; full rollback: `git reset --hard backup/pre-scan-2026-05-21` + restore DB copy.

## Applied changes (atomic-commitable units)

| # | Wave | Audit ref | Files touched | What changed |
|---|---|---|---|---|
| 1 | A1 | data CRIT #2 | `models.py:276` | `Conversation.updated_at` gains `onupdate=datetime.utcnow` |
| 2 | A2 | backend CRIT #1 | `app.py` background sync | `db.session.remove()` in finally per cycle |
| 3 | A3 | backend CRIT #4 | `app.py` `_reconcile_read_states` | Order by `sent_at, id` desc instead of `MAX(id)` |
| 4 | A4 | backend CRIT #3 | `services/message_router.py` `_generate_ai_response` | AI persist wrapped in try/except → log + escalate on commit fail |
| 5 | A5 | backend CRIT #2 + data | `migrations/versions/p17_guest_dedup_unique.py` (new), `services/smoobu_service.py`, `services/memory_service.py` | Dedupe guests by `smoobu_guest_id`, add partial unique index, IntegrityError fallback in both insert paths |
| 6 | B | security HIGH 1-5 + MED 7 | `routes.py` (18 routes) | `@login_required` on approve/reject/assign/toggle/resolve, push (4), knowledge CRUD (4), guest_profile/statistics/knowledge pages |
| 7 | C | frontend CRIT 1-2 | `static/js/app.js` (helper), `inbox.js`, `conversation.js` | `escapeHtmlAllowMark()` defense for search snippets; AI error banner built via `textContent` |
| 8 | D | deps CVE bumps | `requirements.txt` | flask≥3.1.0, Werkzeug≥3.0.6, Jinja2≥3.1.6 (new pin), requests≥2.32.4, cryptography≥46.0.0, waitress≥3.0.2, flask-wtf≥1.2.1 |
| 9 | E | backend HIGH 6, 9, 7 + ai 5 | `services/smoobu_service.py`, `services/ai_service.py`, `services/message_router.py` | Smoobu 429 retry-after relative-vs-absolute detection; AI semaphore + request share a single deadline; pending-draft delete uses `with_for_update(skip_locked)` + tolerant of races; extraction errors split by type with `exc_info` |
| 10 | F | security HIGH 9, 10 | `config.py`, `app.py` | `SESSION_COOKIE_HTTPONLY/SAMESITE=Lax/SECURE` (Secure off in DevelopmentConfig). Production refuses to start with dev-fallback `SECRET_KEY`. |
| 11 | G | frontend HIGH | `static/js/conversation.js` | `sendInProgress` flag blocks double-click send; cleared in each sender's `.finally()`; 30s safety release |
| 12 | (security MED 8) | webhook signature | `routes.py` Smoobu webhook | Optional HMAC-SHA256 verification gated by `SMOOBU_WEBHOOK_SECRET` env var. Without secret, accepts + logs warning (back-compat). With secret, mismatched signatures → 401. |
| 13 | LOW | sec 12, 13 | `templates/chatbot/conversation.html`, `routes.py:4305` | Playtest clear uses `textContent`; sort_order validated as int in [0,10000] |

## Intentionally deferred

- **Full Flask-WTF CSRF middleware**. Adding `CSRFProtect(app)` would 400 every JS POST/PUT/DELETE until each `fetch()` attaches a token + every form gets `{{ csrf_token() }}`. `SESSION_COOKIE_SAMESITE='Lax'` already blocks cross-site CSRF for non-GET methods, which covers the primary risk. Library is now in requirements; enable when JS is ready to send tokens.
- **Inbox filter listener event delegation** (frontend HIGH). The bindings are top-level — they run once at script load, polling doesn't re-bind them. The audit's "duplication on polling re-renders" did not reproduce in code reading. Marked N/A.
- **Polling.start idempotent guard** (frontend HIGH). Already present at `polling.js:44`. Marked N/A.
- **Migration p16 + p17 application to prod DB**. User-driven. Run with backup, then restart Waitress. Commands below.
- Medium/low items not in the wave list (CSS `!important`, aria-labels, modal focus, reduced-motion polling, cache-busting automation, service worker offline, viewport safe-area).

## Required user actions

1. **Update Python deps**:
   ```
   pip install -U -r requirements.txt
   ```
2. **Set `SECRET_KEY` in environment**. Must be a strong random value before `FLASK_ENV=production` will start. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`.
3. **(Optional but recommended)** set `SMOOBU_WEBHOOK_SECRET` to enable HMAC verification. Configure same secret in Smoobu's webhook setup if they support it; otherwise leave unset and rely on the "warning logged" baseline.
4. **Apply migrations + restart server** (you drive this — `Start_Server.bat` doesn't kill prior processes):
   ```
   flask db upgrade        # applies p16 (cancelled_at) + p17 (guest dedup + unique index)
   # then your normal Start_Server.bat
   ```
   The p17 upgrade will delete duplicate Guest rows (~174 Steven Amaya copies) and reassign their conversations/details to the surviving record before adding the unique index.
5. Smoke-test: open inbox, send a message, trigger AI response, view a guest profile while logged in / logged out (the latter should now redirect to login).

## Notes

- All Python files pass `ast.parse`. All edited JS files pass `new Function()` syntax check.
- No DB schema was touched in this session — only the migration file was added. Schema change happens when you run `flask db upgrade`.
- No dependencies were installed or upgraded automatically; requirements.txt was only edited.
- No server restart was performed.
