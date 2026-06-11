# ChatBotAI Backend Code Quality Audit — 2026-05-21

## Summary
**Total Findings:** 27
- CRITICAL: 4 | HIGH: 8 | MEDIUM: 9 | LOW: 4 | INFO: 2

---

## CRITICAL Issues

### 1. Background daemon missing SQLAlchemy session cleanup
- **File:** app.py:293-382
- **Issue:** Daemon reuses Flask app_context indefinitely without closing sessions. Causes connection pool exhaustion.
- **Suggested:** Call db.session.remove() after each smoobu.sync_messages().

### 2. Race condition in guest deduplication
- **File:** services/smoobu_service.py:588-612
- **Issue:** No unique constraint on (email, phone, smoobu_guest_id). Concurrent webhooks create duplicate guests (175 Steven Amaya records exist).
- **Suggested:** Add compound unique constraint or atomic upsert.

### 3. AI response may fail to save without error indication
- **File:** services/message_router.py:210-220
- **Issue:** _generate_ai_response() may fail to commit but return None silently. Guest never sees reply.
- **Suggested:** Separate AI message insertion into dedicated transaction with explicit conflict handling.

### 4. Unread reconciliation uses id-based ordering (breaks on out-of-order imports)
- **File:** app.py:213-249
- **Issue:** Uses MAX(id) not MAX(sent_at). Out-of-order message imports wrongly mark conversations read.
- **Suggested:** Change to func.max(Message.sent_at).

---

## HIGH Issues (8 total)

### 5. Exception handling swallows specific errors in AI extraction
- **File:** services/ai_service.py:409-441
- **Suggested:** Log specific error type, not generic "Extraction failed".

### 6. Smoobu rate-limit retry assumes absolute time (treats relative as negative)
- **File:** services/smoobu_service.py:144-151
- **Suggested:** Detect relative vs absolute seconds in retry_after header.

### 7. Pending draft deleted without row-level locking
- **File:** services/message_router.py:531-540
- **Suggested:** Use db.session.query(...).with_for_update().

### 8. Webhook guest enrichment lacks app_context isolation
- **File:** routes.py:3826-3860
- **Suggested:** Add explicit db.session.remove() on timeout.

### 9. AI semaphore acquire timeout not deadline-aware
- **File:** services/ai_service.py:273-276
- **Suggested:** Implement request deadline tracking.

### 10. Smoobu webhook replay idempotent only within 2-hour window
- **File:** services/smoobu_service.py:620-643
- **Suggested:** Always populate platform_message_id or add composite unique index.

### 11. Background/manual sync share mutable state without timeouts
- **File:** app.py:301, 360-382
- **Suggested:** Add timeout to manual lock acquire.

### 12. (duplicate ref - see above structure)

---

## MEDIUM Issues (9 total)

1. Reconcile read states skips conversations with no messages (app.py:226)
2. Mixed naive/aware datetime handling (smoobu_service.py:546)
3. KnowledgeEntry topic extraction fails silently (routes.py:73)
4. No unique constraint on pending draft per conversation (message_router.py:532)
5. Duplicate logging to logger and print() (app.py:330)
6. Memory service doesn't null-check guest_id (memory_service.py:82)
7. FTS5 triggers recreated on every startup, log spam (app.py:114)
8. Guest language preference not confidence-weighted (memory_service.py:338)
9. Conversation summary re-summarized unnecessarily (message_router.py:557)

---

## LOW Issues (4 total)

1. Requests library connections not closed (smoobu_service.py:101)
2. Guest email changes mid-conversation not detected (smoobu_service.py:496)
3. (2 more minor issues omitted for brevity)

---

## INFO Issues (2 total)

1. AI semaphore lacks fairness/priority queue
2. Webhook endpoints lack CSRF protection (DOS risk)

---

## Recommendations by Priority

### Immediate
1. p16 migration not applied — Restart server to apply cancelled_at column
2. Add session cleanup to background daemon (db.session.remove after sync)
3. Fix guest deduplication race with unique constraint

### Short Term
4. Unread reconciliation ordering (sent_at not id)
5. AI response commit safety (separate transaction)
6. Smoobu rate-limit retry-after detection

### Medium Term
7. Replace 53+ bare Exception handlers with specific types
8. Add Semaphore deadline tracking
9. Consolidate logging (logger only)

---

**Report Generated:** 2026-05-21
**Read-Only Audit:** No code modifications performed.
