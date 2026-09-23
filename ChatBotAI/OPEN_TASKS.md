# Open Tasks — opened 2026-09-09

Raised after a day of real use (sending replies, Vorlagen Generieren, WhatsApp
mirror running). Nothing here is started. Investigation notes are included so
the next session does not have to re-derive them.

---

## 0. WhatsApp: old account closed and its data deleted (2026-09-15) — WAHA test with another account next

Linked device removed 14.09 23:25 (`RESTRICT_ALL_COMPANIONS`); after re-pairing, WhatsApp
cut three connections in a row after 1–3 min. Full timeline, evidence, code state and
options: `WHATSAPP_INCIDENT_2026-09-15.md`.

## 1. Production logging is broken — do this first

**Why first:** it is the prerequisite for task 2. Right now a failure leaves no
trace, so the send problem cannot be diagnosed at all.

Evidence gathered 2026-09-09:
- `instance/chatbot.log` — 4,838 lines since 2026-06-20, **all INFO, all from
  `ChatBotAI.services.email_reconcile`**. Not one line from `smoobu_service`
  (40 logger calls), `routes.py` (66), or `ai_service.py` (39).
- The Smoobu sync provably runs anyway — 58 owner messages synced back from
  Smoobu on 2026-09-09 — so this is lost logging, not an idle daemon.
- `../server.log` (root logger, written by `FlaskApp/app.py.__main__`) has not
  been touched since **2026-03-11**.
- `init_debug_service()` is called only from `ChatBotAI/app.py:create_app()`
  (dev). **`init_chatbot()` in `__init__.py` never calls it**, and production
  goes through `init_chatbot`. So `_api_tracker is None`, `_track_api_call()`
  is a silent no-op, and the Debug dashboard's API stats are empty in prod by
  construction.

Not yet established: *why* only `email_reconcile` reaches the file when every
module uses the same `logging.getLogger(__name__)`. Both modules were compared
and their setup is identical — the cause is elsewhere (handler/propagation
state in the live process). Reproduce in a fresh process before changing code.

Do:
- [ ] Call `init_debug_service()` from the production path
- [ ] Find the real reason non-daemon modules never reach `chatbot.log`
- [ ] Log the Smoobu send failure path explicitly (status code + body) — today
      `send_message()` returns `None` and the caller reports a generic error
- [ ] Confirm with a deliberate failure that it now lands on disk

## 2. ~10% of sends fail, succeed on retry

Reported from real use on 2026-09-09: roughly 1 in 10 replies did not send;
resending the same text worked. 67 owner messages that day.

Why there is no evidence: `api_retry_message` **rewrites
`platform_message_id` on a successful retry**, which erases the `failed:`
prefix — so a failed-then-retried message is indistinguishable from a clean
one afterwards. Zero rows were marked failed at day's end.

Suspect (unproven): `send_message()` calls `_request(..., allow_retry=False)`,
so a transient Smoobu 429/5xx fails immediately with no retry and no log.
`allow_retry=False` is deliberate — retrying a POST that may already have
delivered is the double-send risk. Do not "fix" it by turning retry on.

Do:
- [ ] Task 1 first, then read a real failure
- [ ] Consider keeping a failure record even after a successful retry, so the
      rate is measurable

## 3. Duplicate delivery: the guard only catches exact text

Conversation 4049 received the Gästekarte message twice on 2026-09-09
(08:00:39 and 08:02:17), **both delivered**. The resend had been lightly
edited (`". "` → newline, trailing period dropped), and
`_recent_duplicate_owner_reply` matches normalized text **exactly**, so the
edit walked straight past it.

This is the realistic human pattern: a send looks like it failed, the person
rewords slightly and sends again. Worth a similarity threshold rather than
equality — but be careful, a genuinely different reply must never be blocked.

## 4. WhatsApp: our own messages are invisible

`whatsapp_bridge/index.js` skips every `msg.key.fromMe` message. That was to
avoid re-ingesting UMI's own sends, but it also drops replies the girls type
**on the phone** — so UMI shows the guest's half of the conversation only.

Do:
- [x] Ingest `fromMe` messages as `sender_type='owner'`, deduped on the
      WhatsApp message id (`whatsapp-<id>`), which UMI's own sends already store
      — done 2026-09-10, phone replies also mark the chat read
- [x] Check it does not double-render replies sent from UMI itself — Baileys
      echoes our own sends as `append` (skipped); msg-id dedup covers the rest
- [x] WhatsApp chats now live in "Alle" and the unread badge (quarantine lifted
      2026-09-10)
- [x] WhatsApp timestamps were stored in server-local time (+2h) — fixed for new
      messages; 25 old guest messages in 11 chats still carry the offset

Related, deliberately deferred:
- [x] Media and voice notes shown in the chat (2026-09-14): bridge downloads
      them (≤200 MB), UMI stores `instance/whatsapp_media/<msg id>.<ext>`, text is
      `[Bild]`/`[Sprachnachricht]`/... or the caption. AI history, pending question
      and memory extraction skip placeholders. Needs bridge + Flask restart.
- [ ] Hide the AI buttons in WhatsApp chats — user said "leave those there for
      the moment" on 2026-09-09. UMI already cannot auto-answer WhatsApp
      (`auto_respond=False` hardcoded in the webhook); this is only about a
      human being able to click Generieren.

## 5. Mine the Notion page for more knowledge

User found substantially more useful material in Notion than what is synced.
See `NOTION_HANDBOOK_CLASSIFICATION.md` and the existing Notion sync.

Do:
- [ ] Survey what is in Notion vs what is in the Wissensdatenbank
- [ ] Import the useful parts, flagging internal-only entries (there is still
      no guest-facing/internal flag — internal notes currently reach the
      guest-reply prompt)

## 6. Improve UMI's reply quality

User is running Vorlagen Generieren on nearly every reply and wants better
output. Worked example from 2026-09-08 (Kurtaxe + dog question): everything
UMI said was backed by the KB, but it **omitted the amounts it had** —
`Kurtaxe Sebnitz` rates and the "ab der 8. Nacht nur 8 €" pet rule — leaving
the guest unable to pay in advance, which is exactly what she asked to do. The
team's own saved corrections show the right move: ask how many people and what
ages first.

Do:
- [ ] Measure before changing (see `feedback_llm_change_sample_size.md`: n>=20
      per arm, with controls)
- [ ] KB hygiene: entry #24 "Kurtaxe Kosten" holds no costs and contradicts
      #35/#89; `trigger_words` empty on #15, #25, #89
