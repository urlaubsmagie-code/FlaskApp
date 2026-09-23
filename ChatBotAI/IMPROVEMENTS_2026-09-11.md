# ChatBotAI improvements — first reliability batch

Implemented 2026-09-11. These changes are on disk; the live Waitress process has not been restarted. No live guest messages, Notion syncs, or database migrations were triggered during implementation.

## Changes

- **Shared startup:** `startup.py` now owns configuration, authentication setup, compression, SQLite pragmas, schema/FTS setup, service initialization, and daemon scheduling. Both blueprint registration in the parent portal and the standalone factory use it. Reinitializing the same app does not duplicate handlers/services/daemons. Background-task failures are independent and logged.
- **Production configuration:** a bare host app remains in production mode even if `.env` says `FLASK_ENV=development`. Environment-backed options are read when the integrated app initializes, while non-default explicit host settings take precedence. Missing/known placeholder session keys are rejected in production, including when `ProductionConfig` is selected without `FLASK_ENV=production`.
- **Private configuration:** replaced the development `SECRET_KEY` in `.env` with a random private key; it is not printed or committed. Set `OLLAMA_TIMEOUT=90` in `.env` to preserve the old integrated startup's effective 90-second timeout when environment configuration starts being honored. The saved database-selected AI model and master AI setting were not changed.
- **Logging:** removed migration-time `logging.config.fileConfig`, which disabled existing application loggers and replaced handlers. Debug/API tracking now initializes in production too. Added optional `CHATBOT_LOG_DIR`; otherwise package logging remains under `ChatBotAI/instance`.
- **Delivery evidence:** `services/delivery_audit.py` records append-only Smoobu attempt events in `instance/delivery_attempts.jsonl`. Each attempt has its own ID, account slot, reservation ID, content hash/length, HTTP status, and outcome. It does not store message bodies, secrets, or upstream response bodies. Rotation retains the current file plus five 10 MB backups. A successful retry does not erase earlier attempts. Accepted means accepted by the API, not confirmed read/delivered to the guest; network/server ambiguity is recorded as `unknown`. Send retry policy is unchanged.
- **Notion initialization and consistency:** service initialization is included in shared startup; the SDK is declared in requirements. All source pages must be fetched successfully before local writes begin. Mapping/database errors roll back the import transaction. Failed syncs return an error to the UI instead of a misleading success. New or changed knowledge entries remain internal until staff reviews them and clears “Nur intern”; unchanged imports preserve the staff's classification. Settings explain this behavior. No actual import was run.
- **Rendering:** toast text is assigned via `textContent`; Notion error text and blocked-page titles are rendered safely.
- **Tests:** testing apps cannot start production daemons, run startup probes, or write application file logs. The shared fixture routes instance output to a temporary folder and blocks live socket connections. Fixed a requests mock that leaked between tests and a translation-cache teardown ordering issue. Added startup, logging, Notion failure/rollback, and delivery-audit regression tests.

## Verification

- Full Python suite: **495 passed**.
- After final Notion error-display changes: **37 targeted tests passed**, including one additional regression case.
- Node inbox-date-grouping and translation-marker tests passed; WhatsApp bridge selfcheck passed.
- Modified Python modules parse; main JavaScript syntax check passed.
- Integrated-style production startup was exercised against an online snapshot of the operational SQLite database in `tmp/production-startup-check`, with network calls blocked and daemons disabled. This checked:
  - existing migration revision `p24_knowledge_is_internal`;
  - SQLite integrity and foreign-key enforcement;
  - Notion/debug initialization;
  - file logging after migrations;
  - authenticated inbox/API returning 200 and anonymous API returning JSON 401.

Test command used (PowerShell, from ChatBotAI):

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest --basetemp=tmp/pytest-improvements-final -q --disable-warnings --tb=short
```

Use a fresh `--basetemp` path for subsequent runs. The suite still emits existing datetime/SQLAlchemy deprecation warnings; it does not verify live provider availability or actual external delivery.

## Applying this batch

1. Keep the verified restore point at `C:\Users\admin\Documents\FlaskApp_Backups\before-improvements_2026-09-11_12-51-28`.
2. Restart the Flask/Waitress process through the usual deployment procedure. Avoid starting a second server or bridge alongside the existing instances.
3. Sign in again: the old development-key sessions will no longer validate. Production cookies now require HTTPS; use `https://umteamsbz.com`. The user confirmed that the team uses the installed phone WebApp through this public HTTPS address. Local HTTP login support is not needed for that workflow. The live server has not yet been restarted.
4. Verify the inbox and debug dashboard. On the next normal Smoobu reply, inspect the new attempt log if delivery fails; do not manufacture a send to a guest merely to test logging.
5. Check any newly synced Notion knowledge before allowing it into guest prompts.

Proxy-header trust is explicitly opt-in with `CHATBOT_TRUST_PROXY_HEADERS=true` and should be enabled only with a correctly configured trusted proxy. Forwarded host and prefix are not trusted. Use an explicit `GMAIL_REDIRECT_URI` when configuring OAuth callbacks.

The cookie/proxy choices follow the [Flask configuration documentation](https://flask.palletsprojects.com/en/stable/config/) and [trusted-proxy guidance](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/).

## UI/UX follow-up

Implemented after the user's UI review approval, without restarting the running server:

- AI suggestions and reply templates open a native, keyboard-accessible preview dialog. Users can cancel, append, or replace the current text. The previous draft remains available for review/restoration; suggestions arriving after typing no longer overwrite the composer. Prompt diagnostics stay in the console.
- The primary AI action is “Antwort entwerfen.” The secondary action is under “Mehr,” is labeled “Zur Freigabe vorbereiten,” and explicitly requests `draft_only: true`. It cannot immediately send through that action. Existing automatic reply settings are retained; a composer hint explains the current global/chat/approval combination after settings load.
- Manual sending keeps the composer and saved draft until the server acknowledges the request. The composer stays locked throughout the request, with a 90-second timeout treated as uncertain delivery. Failed/lost responses do not trigger automatic local fallback or retransmission. A persisted uncertainty marker requires deliberate confirmation before another send, including after reload. Disconnected external channels preserve the draft instead of silently saving it as sent. Local-only chats are explicitly labeled as such. Provider acceptance is not presented as a read receipt.
- Inbox maintenance actions are grouped under “Aktionen.” Statistic filters are native buttons with pressed-state semantics. Search/composer labels and German/English fallback wording are improved.
- Phone message actions have separate 44px targets below the bubble. The composer uses 16px text to avoid small-text input zoom. The preview dialog and secondary menus adapt to narrow screens and the existing dark theme.
- Inbox and conversation polling display offline, reconnecting, and refresh-failure notices. A successful unrelated poll does not conceal another poller's failure. Inbox freshness markers advance only after the full refresh succeeds, allowing recovery after a failed fetch.
- Conversation rendering checks the Smoobu service for that conversation's account, which prevents the new connection guard from incorrectly blocking a configured secondary account.
- Updated asset versions for the changed styles/scripts. Static files may be served by the running application immediately, even without a process restart.

Validation: 54 targeted Python checks passed, followed by 41 checks after final localization/account changes (these groups overlap). All 12 Node test entries passed: nine composer safety cases, one connection-feedback case, and the two existing date-grouping/translation scripts. The conversation rendering test covers the account-aware connection check and preview/status markup. The initial Python run encountered an inaccessible default pytest temporary directory; rerunning with isolated workspace temporary/cache directories passed. Existing dependency deprecation warnings remain.

No live guest messages were sent. No browser connection was available, so visual layout, native dialog behavior, and on-device keyboard/touch verification remain unverified. Draft recovery continues to use this browser's local storage; it is not cross-device storage.

## Remaining backend work

### Screenshot feedback: compact chat controls

The user's first phone screenshot prompted these revisions, superseding the corresponding UI notes above:

- Restored the original small message actions beside each bubble, removing the larger buttons below messages.
- Removed the automation explanation above the composer.
- Removed the “Mehr” menu. Three compact buttons now appear together: “Vorlagen,” “Entwerfen,” and “Zur Freigabe.” The last action still prepares a draft for approval; it does not send immediately.
- Moved the optional previous-draft recovery button below the composer so it does not take a fourth slot in the action row.
- Bumped asset versions. Nine composer regression tests and 23 template/backend checks passed. No server restart or live visual verification was performed.

### Outstanding backend tasks

Final enhancement style adjustment: the dedicated rewriting prompt now encourages fresh wording, sentence structure, and warmth instead of minimal proofreading. Modest expansion is allowed while preserving the staff's purpose, language, certainty, and commitments. The short-closing example now demonstrates a warm rephrasing rather than punctuation changes. Knowledge remains factual reference, and earlier guest questions must not replace the staff's intended message. No server restart performed; actual model wording requires a live check after restart.

Enhancement correction after real user feedback (“Alles gut! Bis bald” generated a fresh guest answer): replaced reuse of the normal guest-answering prompt with a dedicated editing prompt. The staff draft is the only user turn; property knowledge and history are reference data only. Instructions preserve language, intent, and brevity, explicitly keep short farewells short, and forbid answering earlier guest questions. A regression test ensures enhancement never calls the normal reply prompt builder and that the exact staff draft remains the final user message. Actual model wording still needs rechecking after restart; mocked tests establish prompt routing, not model compliance.

Adaptive composer action: the same button offers UMI-Vorschlag for an empty field, Neue Variante for an unchanged generated result, and Mit UMI verbessern for staff-written, pasted, template, or edited text. The enhancement request reuses the conversation/knowledge pipeline and adds a separate editing task that preserves intent and forbids invented facts or commitments. Enhancement variants reuse the original staff input; editing a result establishes a new source. Results go directly into the composer, but never overwrite text changed during the request. Errors retain the draft. No message is saved or delivered by enhancement. On a page reload, restored text is treated as a draft to enhance. English translations and asset versions updated. Mocked tests verify frontend transitions, request contents, knowledge delivery, input validation, prompt separation, and no message writes; actual model wording and on-phone rendering still require user review. No server restart performed.

Suggestion retry follow-up: removed the Previous draft button and its recovery action. After the main UMI suggestion succeeds, its button becomes “Neue Variante” / “New variant.” Another click makes a fresh request through the existing suggestion pipeline and replaces the text only when a valid suggestion arrives. The current draft remains visible during generation and survives errors. Clearing/sending the draft or inserting a template restores the original button label. Repeated clicks during generation are guarded. This reuses the existing prompt/context pipeline; a fresh generation does not guarantee different wording. Eleven composer tests and 23 rendering/translation checks passed. Updated the script asset versions; no restart performed.

Button naming follow-up: restored “UMI-Vorschlag” and “UMI-Antwort erstellen,” including the original English labels. Long labels can wrap within the existing three-button mobile row. This naming change does not change the actions' behavior.

Draft workflow preference: removed the preview dialog. AI suggestions (including per-message suggestions) and templates now insert directly into the text field. “Vorheriger Entwurf” restores the replaced text directly and retains the latest text for recovery too. Sending still requires the Send button; the separate approval-queue action retains its behavior. Ten composer tests and six backend/rendering checks passed; updated the conversation script version.

Desktop screenshot follow-up: anchored the filter panel to the full search/filter row instead of right-aligning it against the small Filter button. Its width is capped to the content row, and filter options wrap when necessary, preventing the panel from extending behind the sidebar. Stylesheet version updated.

The user's second screenshot prompted restoration of the original inbox action row: removed the “Aktionen” dropdown and its positioning styles. All available action buttons are directly visible again, using the existing responsive layout. Updated the stylesheet version to refresh cached styles.

This is not the entire proposed improvement program. Explicit CSRF protection, stronger login throttling/password policy, verified Smoobu webhook authentication, systematic AI-quality evaluation, route-file splitting, and replacing global services/process-local locks remain separate tasks. The delivery audit provides evidence for the reported intermittent send failures; it does not establish their cause or claim to fix the provider failure rate.

The existing nested Git repositories and untracked implementation files are preserved. No commit or automatic restart was made. When packaging these changes, include the new `startup.py`, `services/delivery_audit.py`, `pytest.ini`, and test files as well as modified existing files. Preserve the new private `.env` key during a code-only rollback.
