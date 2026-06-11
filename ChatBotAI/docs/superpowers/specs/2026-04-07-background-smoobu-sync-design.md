# Background Smoobu Sync

## Problem

Guest messages arrive in Smoobu but only appear in the app when someone manually triggers a sync. Observed delays of 11+ minutes — unacceptable for guest communication.

## Solution

A daemon thread in the Flask process that automatically calls `sync_messages()` every 120 seconds.

## Design

### New function: `_start_background_sync(app)` in `app.py`

- Starts a `threading.Thread(daemon=True)` at the end of `create_app()`
- Thread loop: sleep 120s → acquire lock → call `sync_messages()` inside `app.app_context()` → release lock → repeat
- Initial delay of 30s before first sync (let app fully boot)
- Only starts if Smoobu is configured (has API key)
- All exceptions caught and logged — thread never crashes

### Safety

- **Cooldown**: Existing 30s cooldown in `sync_messages()` prevents overlap with manual syncs
- **Lock**: Simple `threading.Lock()` prevents concurrent sync if a cycle takes longer than 120s
- **Daemon**: Thread dies automatically when server process stops
- **No new dependencies**: Uses stdlib `threading` only

### What does NOT change

- Frontend polling intervals (3-10s against local DB)
- Manual sync buttons (still work, cooldown deduplicates)
- `sync_messages()` implementation (reused as-is)
- `sync_conversation_messages()` per-conversation sync (unaffected)

### API budget

- Smoobu limit: 1,000 requests/minute
- Background sync: ~2-3 requests per cycle (threads list + individual messages only when new)
- 1 cycle every 2 minutes = ~1.5 req/min average — negligible

### Result

Worst-case delay for new guest messages drops from "infinite (until manual sync)" to ~2 minutes.
