# Guest Dedup — Run Log

Spec: docs/superpowers/specs/2026-06-08-guest-dedup-design.md
Plan: docs/superpowers/plans/2026-06-08-guest-dedup.md

## Procedure
1. Prevention shipped first (`smoobu_service` uses `find_existing_guest`, no longer stores `reservation_id` as `smoobu_guest_id`). Verified via test suite (42 passing).
2. Dry-run (from `C:\Users\admin\Documents\FlaskApp`):
   `python -m ChatBotAI.scripts.dedup_guests`
   Review: merge-group count, rows-to-delete, largest groups, and SKIPPED conflict groups (manual review).
3. Apply:
   `python -m ChatBotAI.scripts.dedup_guests --apply`
   Auto-backup written to `instance/chatbot.db.bak-pre-dedup-<ts>` before any change.
4. Re-run the dry-run to confirm 0 groups remain (idempotent).

## Rollback
Stop the server, then restore the backup (delete the `-wal`/`-shm` sidecars first):
```
del instance\chatbot.db-wal instance\chatbot.db-shm
copy instance\chatbot.db.bak-pre-dedup-<ts> instance\chatbot.db
```

## Step table
| Date | Action | Groups | Rows deleted | Backup file | Notes |
|------|--------|--------|--------------|-------------|-------|
| 2026-06-08 | dry-run | 476 | 2719 | — | read-only; 8 conflict groups flagged |
| 2026-06-08 | apply   | 477 | 2723 | `instance/chatbot.db.bak-pre-dedup-20260608-100529` | 4506→1872 guests; re-run = 0 (idempotent); 5 conflict groups remain |
