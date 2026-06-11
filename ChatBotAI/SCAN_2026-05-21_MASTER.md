# Deep Scan — Master Log
**Date:** 2026-05-21
**Scope:** ChatBotAI Flask app (security, backend, frontend, data layer, dependencies)
**Mode:** Read-only audit. No source files were modified.

Five parallel subagents investigated. Per-domain reports linked below; this master log consolidates findings into a single decision-ready triage.

## Reports
- [Security](SCAN_2026-05-21_security.md) — 15 findings
- [Backend / services](SCAN_2026-05-21_backend.md) — 27 findings
- [Frontend / templates / JS](SCAN_2026-05-21_frontend.md) — 17 findings
- [Data / DB / migrations](SCAN_2026-05-21_data.md) — 16 findings
- [Dependencies (Context7 / PyPI)](SCAN_2026-05-21_dependencies.md) — CVE list + freshness

## Severity rollup
| Domain | CRIT | HIGH | MED | LOW | INFO | Total |
|---|---|---|---|---|---|---|
| Security | 0 | 5 | 7 | 3 | 0 | 15 |
| Backend | 4 | 8 | 9 | 4 | 2 | 27 |
| Frontend | 2 | 4 | 6 | 4 | 1 | 17 |
| Data | 2 | 0 | 8 | 6 | 0 | 16 |
| Deps | — | 4 CVEs | 5 stale | — | — | — |
| **Total** | **8** | **21** | **35** | **17** | **3** | **~84** |

---

## Top-of-stack — fix-now candidates

These are the items most likely to bite production. Ordered by blast radius, not by domain.

### 1. CRITICAL — Migration p16 not applied to prod DB → Smoobu webhook will crash
- Source: data, backend
- `cancelled_at` referenced in models.py:250 and routes.py; column missing on prod SQLite.
- **Action:** `flask db upgrade` after a backup. Restart Waitress. (Already noted in MEMORY.md; still open.)

### 2. CRITICAL — Background daemon leaks SQLAlchemy sessions
- Source: backend (app.py background sync)
- Reuses app_context indefinitely without `db.session.remove()` → connection-pool exhaustion after minutes.
- **Action:** Wrap each sync cycle in fresh app_context + `db.session.remove()` in `finally`.

### 3. CRITICAL — Unread reconciliation uses MAX(id), not MAX(sent_at)
- Source: backend (app.py `_reconcile_read_states`)
- Out-of-order Smoobu imports can wrongly mark unread convos read.
- **Action:** Order by `sent_at` (already the project's source of truth).

### 4. CRITICAL — AI response save can fail silently
- Source: backend (`_generate_ai_response`)
- Commit failures aren't propagated → guest gets no reply, no error surfaced.
- **Action:** Wrap AI persist in its own tx; raise/log + escalation on failure.

### 5. CRITICAL — Guest dedup race (the known "175 Steven Amaya")
- Source: backend, data
- No compound unique constraint covering `(smoobu_guest_id, email, phone)`; check-then-insert race under webhook replay.
- **Action:** Add unique constraint or upsert pattern. (Plan a one-off dedupe migration too.)

### 6. CRITICAL — Two innerHTML XSS sinks
- Source: frontend
- inbox.js:522 (search snippets), conversation.js:482 (AI error banner).
- **Action:** `escapeHtml()` defensively even if backend sanitizes.

### 7. CRITICAL — Conversation.updated_at missing onupdate
- Source: data (models.py:276)
- Code manually bumps in 4 places; any missed path causes inbox sort drift.
- **Action:** Add `onupdate=datetime.utcnow`.

### 8. CRITICAL — Multiple unauthenticated state-changing API routes
- Source: security
- routes.py: approval (2054), rejection (2120), conversation reassign/toggle (1988/2013/2025), push subscription endpoints (2609/2646/2665/2746), knowledge CRUD (4183/4220/4267/4312).
- **Action:** Apply `@login_required` (and `@admin_required` where appropriate) across all of them.

---

## HIGH — second wave (within 1–2 weeks)

**Security**
- Smoobu webhook signature not verified — forged-webhook injection risk.
- SECRET_KEY default fallback in config.py:16.
- Session cookies missing HttpOnly / Secure / SameSite.
- No CSRF (Flask-WTF not installed) across 49 mutating endpoints.

**Backend**
- Smoobu retry-after parsing treats relative seconds as absolute timestamps → retry storm.
- Webhook handlers spawn daemon threads without proper app_context isolation.
- AI semaphore uses wall-clock timeout → zombie threads.
- Manual sync button can hang indefinitely if daemon stalls (sync lock holding).
- Pending draft deletion lacks row-level locking — approved drafts can be wiped by concurrent regen.
- 53+ `except Exception:` blocks — silent failures hide bugs.

**Frontend**
- Filter-button listener duplication on polling re-renders (memory leak).
- `PollingManager.start()` missing idempotent guard → interval stacking on visibility flips.
- Send-message double-click race (ms-unique tempId + finally re-enable).

**Dependencies (CVEs)**
- `cryptography` floor allows 4+ CVEs → bump to ≥46.
- `Werkzeug` allows CVE-2024-34069 / CVE-2024-49767 → bump to ≥3.0.6.
- `waitress` allows CVE-2024-49768 (request smuggling, **relevant — fronts prod**) → bump to ≥3.0.2.
- `requests` CVE-2024-35195 → bump to ≥2.32.4.
- Jinja2 unpinned (CVE-2024-56326 / CVE-2025-27516 reachable) → pin ≥3.1.6.

---

## MEDIUM — backlog (when scheduled)

Security: protect page routes (/knowledge, /statistics, /guest/<id>); add rate-limiting on AI + login endpoints.

Backend: mixed naive/aware datetimes in a few spots; bare `except:` cleanup; Smoobu pagination idempotency window only ~2h; logger vs print consistency.

Frontend: !important overuse; aria-labels missing on icon buttons; modal focus management; reduced-motion polling; i18n for loading states.

Data: missing composite index on `(sender_type, conversation_id)`; User.last_seen unindexed (acceptable for current scale); WAL file size monitoring; UPSERT for message dedup under load.

Deps: minor staleness (flask 3.0→3.1, flask-migrate 4.0→4.1, pywebpush 2.0→2.3, etc.).

---

## LOW / INFO
See per-domain reports. Includes service-worker offline caching, cache-busting automation, safe-area-inset, viewport notch handling, and the Ollama improvement of using `format: 'json'` for extraction calls instead of regex stripping.

---

## Suggested order of attack (not yet executed)

1. **Wave A — prod-safety, do first**: items 1–5 + 7 above (DB / data integrity). All can be done in one focused session with backup.
2. **Wave B — auth lockdown**: item 8 (auth decorators) — large but mechanical patch across routes.py.
3. **Wave C — XSS sinks**: item 6 — two small JS edits + CSP header.
4. **Wave D — dependency CVE bumps**: pin cryptography / Werkzeug / waitress / requests / Jinja2; run app smoke test.
5. **Wave E — HIGH backend hardening**: Smoobu retry parsing, AI semaphore deadline, webhook signature, session leak under threads.
6. **Wave F — CSRF + secure cookies + session hygiene**: requires Flask-WTF and a coordinated JS change.
7. **Wave G — Frontend polish**: polling guard, listener delegation, double-click flag.
8. **Backlog**: MEDIUM/LOW items as time permits.

---

## What I did NOT do
- No source files were modified.
- No migrations were applied.
- No dependencies were upgraded.
- No commits.

**Awaiting your call on which waves to execute and in what order.**
