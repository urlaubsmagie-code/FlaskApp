# Background Smoobu Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically sync new guest messages from Smoobu every 2 minutes so messages appear in the app without manual sync.

**Architecture:** A daemon thread started at the end of `create_app()` that loops every 120 seconds, calling the existing `sync_messages()` inside a Flask app context. A threading lock prevents concurrent syncs with manual triggers.

**Tech Stack:** Python stdlib `threading` (no new dependencies)

---

### Task 1: Add `_start_background_sync()` to `app.py`

**Files:**
- Modify: `app.py:1-10` (imports)
- Modify: `app.py:206-322` (create_app function)

- [ ] **Step 1: Add threading import to `app.py`**

At the top of `app.py`, add `threading` to the imports:

```python
import os
import logging
import threading
from pathlib import Path
```

- [ ] **Step 2: Add the `_start_background_sync()` function**

Add this function in `app.py` after the `_ensure_fts5_index()` function (after line 203) and before `create_app()`:

```python
def _start_background_sync(app):
    """Start a daemon thread that syncs Smoobu messages every 2 minutes.

    Only starts if Smoobu is configured with an API key. The thread runs
    inside an app context so it can access the database. A lock prevents
    overlap with manual syncs or slow cycles.
    """
    logger = logging.getLogger(__name__)
    sync_lock = threading.Lock()

    SYNC_INTERVAL = 120  # seconds
    INITIAL_DELAY = 30   # seconds — let app fully boot first

    def _sync_loop():
        import time
        time.sleep(INITIAL_DELAY)
        logger.info("Background Smoobu sync started (every %ds)", SYNC_INTERVAL)

        while True:
            try:
                if sync_lock.acquire(blocking=False):
                    try:
                        with app.app_context():
                            from .services.smoobu_service import get_smoobu_service
                            smoobu = get_smoobu_service()
                            if smoobu and smoobu.is_configured():
                                result = smoobu.sync_messages()
                                imported = result.get('imported', 0)
                                if imported > 0:
                                    logger.info("Background sync: imported %d new messages", imported)
                                else:
                                    logger.debug("Background sync: no new messages")
                            else:
                                logger.debug("Background sync: Smoobu not configured, skipping")
                    finally:
                        sync_lock.release()
                else:
                    logger.debug("Background sync: skipped, sync already in progress")
            except Exception:
                logger.exception("Background sync error")

            time.sleep(SYNC_INTERVAL)

    thread = threading.Thread(target=_sync_loop, daemon=True, name="smoobu-bg-sync")
    thread.start()
    logger.info("Background Smoobu sync thread scheduled (first run in %ds)", INITIAL_DELAY)
```

- [ ] **Step 3: Call `_start_background_sync(app)` in `create_app()`**

In `create_app()`, add the call just before the final log line and `return app`. After the blueprint registration and root redirect (after line 318), add:

```python
    # Start background Smoobu message sync (every 2 minutes)
    _start_background_sync(app)

    logger.info(f"ChatBotAI application created (debug={app.config.get('DEBUG')})")

    return app
```

Replace the existing `logger.info(...)` and `return app` lines — don't duplicate them.

- [ ] **Step 4: Verify the app starts cleanly**

Run the app and check the console output:

```bash
python -m ChatBotAI.run
```

Expected in logs:
```
Background Smoobu sync thread scheduled (first run in 30s)
```

Then after 30 seconds:
```
Background Smoobu sync started (every 120s)
Background sync: imported 0 new messages
```

Or if Smoobu isn't configured:
```
Background sync: Smoobu not configured, skipping
```

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add background Smoobu sync every 2 minutes"
```

---

### Task 2: Verify end-to-end with a real Smoobu message

- [ ] **Step 1: Start the app and wait for first background sync**

Start the app, wait ~30 seconds for the first sync cycle to run. Confirm the log shows the sync ran.

- [ ] **Step 2: Send a test message via Smoobu**

Send a message through Airbnb or Booking.com to one of the properties. Note the exact time.

- [ ] **Step 3: Wait for automatic pickup**

Without clicking any manual sync button, wait up to 2 minutes. The message should appear in the inbox automatically (the 3-second frontend poll will pick it up from the DB once the background sync imports it).

- [ ] **Step 4: Verify timing**

Check the logs for the `Background sync: imported 1 new messages` line. Confirm the delay from message send to app display is under 2.5 minutes (2 min sync interval + 30s worst-case offset + 3s frontend poll).
