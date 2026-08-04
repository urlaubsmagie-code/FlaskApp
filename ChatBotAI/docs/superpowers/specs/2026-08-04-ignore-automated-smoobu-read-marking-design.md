# Ignore automated Smoobu messages when marking conversations read

**Date:** 2026-08-04
**Status:** Approved (design)

## Problem

Guests report messages "disappearing" from the unread list (the `missing_message`
Problem-Report category). Root cause: when the Smoobu sync imports an incoming
host message, it unconditionally marks the whole conversation read:

- `smoobu_service.py:820` (full daemon sync, `sync_messages`)
- `smoobu_service.py:1274` (per-conversation / webhook sync, `sync_conversation_messages`)

Both run, for every host (`type == 2`, outbox) message:

```python
conv.is_read = True                      # "someone already replied outside the app"
if not conv.last_read_message_id or owner_msg.id > conv.last_read_message_id:
    conv.last_read_message_id = owner_msg.id
```

That assumption is wrong for **automated templates** (Buchungsbestätigung,
Dein Check-in, WhatsApp Kanal, Checkout, Bewertung, …). An automated message is
not a reply to the guest, so an unanswered guest question gets falsely cleared
and the team never sees it.

Unread is computed only from `sender_type == 'guest'` messages
(`models.py:355`, `379`, `822`), so the *only* thing wrongly flipping these
conversations to read is the two lines above.

## Fix

Add one shared helper and guard both call sites with it. When the incoming host
message is an automated template, **skip the read-marking only** — the message is
still stored, and still bumps `last_message_at` / `updated_at` as today.

```python
# module-level in smoobu_service.py
AUTOMATED_SUBJECT_PREFIXES = [
    'buchungsbestätigung',   # all "Buchungsbestätigung …" variants
    'whatsapp kanal',        # WhatsApp Kanal (+ … Booking)
    'dein check-in',
    'guten morgen',
    'checkout',
    'bitte um bewertung',
    'bewertung booking',
    'verlängerung',          # Verlängerung - Aktion / Verlängerung Rechnung
    'rechnung ferienwohnung',
]

def _is_automated_smoobu_message(msg):
    """True if a Smoobu message is one of our configured automated templates,
    identified by its subject line. Manual chat replies have an empty subject."""
    subject = (msg.get('subject') or '').strip().casefold()
    return bool(subject) and any(
        subject.startswith(p) for p in AUTOMATED_SUBJECT_PREFIXES)
```

At both sites, wrap the read-marking:

```python
if not _is_automated_smoobu_message(msg):
    conv.is_read = True
    if not conv.last_read_message_id or owner_msg.id > conv.last_read_message_id:
        conv.last_read_message_id = owner_msg.id
```

Detection is normalized (`strip().casefold()`) + `startswith` because real
subjects carry trailing spaces (`"Buchungsbestätigung "`) and case varies. Prefix
matching covers all current variants and future `Buchungsbestätigung mit X`
without a list change. Templates whose recipient is our own email never appear in
guest threads; including their prefixes is harmless.

## Decisions

- **Detection:** known subject-prefix list (not "any subject", to avoid ever
  swallowing a manual reply that happened to carry a subject).
- **List location:** hardcoded constant in `smoobu_service.py`. These are stable
  core templates. If the list starts churning, move it to an editable
  `AISettings` value. (`ponytail:` mark the constant with this upgrade path.)

## Non-goals

- Not hiding automated messages from the chat view or from UMI's AI context
  (separate concern; not what causes the missing-message bug).
- Not changing inbox sort — an automated message may still surface the chat;
  combined with the fix that is correct (it stays unread and visible).

## Test

`tests/` (extend the Smoobu sync tests):

1. Conversation with an unread guest message → sync an automated host message
   (subject `"Buchungsbestätigung "`, type 2) → conversation stays `is_read == False`.
2. Same setup → sync a **manual** host reply (empty subject, type 2) →
   conversation becomes `is_read == True` (today's behavior preserved).
