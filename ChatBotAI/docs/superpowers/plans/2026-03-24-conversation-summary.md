# Conversation Summary Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cached AI-generated conversation summaries so the AI has context about older messages that fall outside the recent message window.

**Architecture:** When a conversation exceeds `max_conversation_history` messages, a summary of older messages is generated via Ollama, cached on the Conversation model, and injected into the system prompt. Incremental updates keep the summary current without re-processing the entire history.

**Tech Stack:** Flask, SQLAlchemy, Alembic (batch mode for SQLite), Ollama chat API

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `migrations/versions/p9_summary_add_conversation_summary.py` | Create | Alembic migration adding `ai_summary` and `ai_summary_through_id` to conversation |
| `models.py` | Modify | Add two columns to Conversation model |
| `services/ai_service.py` | Modify | Add `generate_conversation_summary()` method, add `conversation_summary` param to `_build_chat_messages()` |
| `services/message_router.py` | Modify | Add summary lifecycle logic to `_generate_ai_response()` |

---

### Task 1: Database Migration

**Files:**
- Create: `migrations/versions/p9_summary_add_conversation_summary.py`
- Modify: `models.py:187-236` (Conversation class)

- [ ] **Step 1: Add columns to Conversation model**

In `models.py`, add these two columns to the `Conversation` class, after the `escalated_at` column (line ~222):

```python
# Conversation summary for AI context (cached)
ai_summary = db.Column(db.Text, nullable=True)
ai_summary_through_id = db.Column(db.Integer, nullable=True)
```

- [ ] **Step 2: Create migration file**

Create `migrations/versions/p9_summary_add_conversation_summary.py`:

```python
"""Add AI summary columns to conversation

Revision ID: p9_summary
Revises: p8_escalation
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p9_summary'
down_revision = 'p8_escalation'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ai_summary_through_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('ai_summary_through_id')
        batch_op.drop_column('ai_summary')
```

- [ ] **Step 3: Run migration**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run`
Verify: App starts without errors. Check logs for successful DB initialization.

- [ ] **Step 4: Commit**

```bash
git add models.py migrations/versions/p9_summary_add_conversation_summary.py
git commit -m "feat(summary): add ai_summary columns to conversation model"
```

---

### Task 2: AI Service — Summary Generation Method

**Files:**
- Modify: `services/ai_service.py` (add `generate_conversation_summary()` after `generate_guest_response()`, around line ~494)

- [ ] **Step 1: Add `generate_conversation_summary()` method**

Add this method to `AIService` class, after `generate_guest_response()`:

```python
def generate_conversation_summary(
        self,
        messages: List[Dict[str, str]],
        existing_summary: Optional[str] = None
) -> Optional[str]:
    """Generate or update a conversation summary for AI context.

    Args:
        messages: Message dicts to summarize (each has 'sender_type', 'content', 'sent_at')
        existing_summary: If provided, update this summary with the new messages

    Returns:
        Summary text (bullet points) or None on failure
    """
    if not messages:
        return existing_summary

    # Format messages for the prompt
    sender_labels = {'guest': 'Guest', 'owner': 'Host', 'ai': 'Host'}
    formatted = []
    for msg in messages:
        label = sender_labels.get(msg.get('sender_type', 'guest'), 'Guest')
        content = self._strip_html(msg.get('content', ''))
        content = self._strip_email_quotes(content)
        if content.strip():
            formatted.append(f"{label}: {content.strip()}")

    if not formatted:
        return existing_summary

    formatted_messages = "\n".join(formatted)

    system = "You are a summarization assistant. Be concise and factual."

    if existing_summary:
        prompt = (
            "Here is an existing summary of an ongoing conversation "
            "between a vacation rental host and a guest:\n\n"
            f"{existing_summary}\n\n"
            "New messages since the last summary:\n"
            f"{formatted_messages}\n\n"
            "Update the summary to include the new information.\n"
            "Keep the same bullet-point format. Keep it under 300 words.\n"
            "Write in the same language as the conversation.\n"
            "Remove items that are no longer pending. "
            "Add new decisions, promises, or open items."
        )
    else:
        prompt = (
            "Summarize this conversation between a vacation rental host and a guest.\n"
            "Write concise bullet points covering:\n"
            "- Key decisions made\n"
            "- Promises or commitments by either party\n"
            "- Questions that were answered (and the answers)\n"
            "- Pending or open items\n\n"
            "Keep it under 300 words. Write in the same language as the conversation.\n"
            "Do NOT include greetings, pleasantries, or filler.\n\n"
            f"Conversation:\n{formatted_messages}"
        )

    try:
        response = self.generate_response(prompt, system=system)
        if response:
            response = self._strip_think_tags(response).strip()
            if len(response) < 10:
                logger.warning(f"[SUMMARY] Generated summary too short ({len(response)} chars), discarding")
                return existing_summary
            logger.info(f"[SUMMARY] Generated summary: {len(response)} chars")
            return response
        logger.warning("[SUMMARY] No response from Ollama for summary generation")
        return existing_summary
    except Exception as e:
        logger.warning(f"[SUMMARY] Summary generation failed: {e}")
        return existing_summary
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('services/ai_service.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(summary): add generate_conversation_summary() to AIService"
```

---

### Task 3: AI Service — Inject Summary into System Prompt

**Files:**
- Modify: `services/ai_service.py` — `_build_chat_messages()` method (line ~504)

- [ ] **Step 1: Add `conversation_summary` parameter to `_build_chat_messages()`**

Add `conversation_summary: Optional[str] = None` to the method signature, after `knowledge_entries`.

- [ ] **Step 2: Inject summary into system prompt**

In `_build_chat_messages()`, after the `host_instructions` block (after line ~618 `messages.append({'role': 'system', ...})`), but BEFORE that `messages.append` call — add the summary injection into `system_parts`:

```python
if conversation_summary:
    system_parts.append(
        f"\n=== CONVERSATION SUMMARY (older messages not shown below) ===\n"
        f"{conversation_summary}\n"
        f"=== The recent messages below continue from this summary. ==="
    )
```

This goes right after the `host_instructions` block and before the final `messages.append({'role': 'system', ...})` call.

- [ ] **Step 3: Add parameter passthrough in `generate_guest_response()`**

Add `conversation_summary: Optional[str] = None` parameter to `generate_guest_response()` signature (after `knowledge_entries`).

Pass it through to `_build_chat_messages()`:

```python
messages = self._build_chat_messages(
    ...
    knowledge_entries=knowledge_entries,
    conversation_summary=conversation_summary
)
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "import ast; ast.parse(open('services/ai_service.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(summary): inject conversation summary into AI system prompt"
```

---

### Task 4: Message Router — Summary Lifecycle

**Files:**
- Modify: `services/message_router.py` — `_generate_ai_response()` method (line ~423)

- [ ] **Step 1: Add summary generation logic to `_generate_ai_response()`**

In `_generate_ai_response()`, after the line that reads `max_history` from AISettings (line ~443) and before the line that queries conversation messages (line ~446), add the summary lifecycle:

```python
# --- Conversation summary for long conversations ---
conversation_summary = conversation.ai_summary  # Use cached by default
total_msg_count = Message.query.filter_by(conversation_id=conversation.id).count()

if total_msg_count > max_history:
    # Find the cutoff message (the oldest message that WON'T be in recent history)
    cutoff_msg = Message.query.filter_by(
        conversation_id=conversation.id
    ).order_by(Message.sent_at.desc()).offset(max_history).first()

    if cutoff_msg:
        summary_is_stale = (
            conversation.ai_summary_through_id is None
            or cutoff_msg.id > conversation.ai_summary_through_id
        )

        if summary_is_stale and self.ai_service:
            try:
                # Fetch messages to summarize (between last summary and cutoff)
                summary_query = Message.query.filter_by(
                    conversation_id=conversation.id
                ).filter(
                    Message.id <= cutoff_msg.id
                )
                if conversation.ai_summary_through_id:
                    summary_query = summary_query.filter(
                        Message.id > conversation.ai_summary_through_id
                    )
                msgs_to_summarize = summary_query.order_by(
                    Message.sent_at.asc()
                ).limit(50).all()

                if msgs_to_summarize:
                    summary_result = self.ai_service.generate_conversation_summary(
                        [m.to_dict() for m in msgs_to_summarize],
                        existing_summary=conversation.ai_summary
                    )
                    if summary_result:
                        conversation.ai_summary = summary_result
                        # Track through the last message actually summarized
                        # (not cutoff_msg.id — the .limit(50) may not reach it)
                        conversation.ai_summary_through_id = msgs_to_summarize[-1].id
                        conversation_summary = summary_result
                        db.session.commit()
                        logger.info(f"[SUMMARY] Updated summary for conversation {conversation.id} "
                                    f"(through msg {msgs_to_summarize[-1].id})")
            except Exception as e:
                logger.warning(f"[SUMMARY] Failed to update summary for conversation {conversation.id}: {e}")
                # Proceed with existing cached summary (or None)
```

- [ ] **Step 2: Pass summary to AI response generation**

In the same method, update the `self.ai_service.generate_guest_response()` call to include `conversation_summary`:

```python
response_text = self.ai_service.generate_guest_response(
    ...
    knowledge_entries=knowledge_entries,
    conversation_summary=conversation_summary
)
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('services/message_router.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Manual test**

1. Start the app: `python -m ChatBotAI.run`
2. Open a conversation with >10 messages (or create a test conversation and add messages)
3. Click "KI-Vorschlag" (AI Suggest) to trigger AI response generation
4. Check the terminal logs for `[SUMMARY]` entries confirming summary was generated
5. Trigger another AI response — logs should show the cached summary being reused (no new `[SUMMARY] Generated` log)

- [ ] **Step 5: Commit**

```bash
git add services/message_router.py
git commit -m "feat(summary): add summary lifecycle to message router"
```

---

### Task 5: Cache Version Bump

**Files:**
- No cache bumps needed — this feature is purely backend with no JS/CSS changes.
- Just verify the app runs cleanly.

- [ ] **Step 1: Full smoke test**

1. Start the app
2. Open inbox — verify conversations load normally
3. Open a short conversation (<10 messages) — verify AI suggest works without summary
4. Open a long conversation (>10 messages) — verify AI suggest generates a summary (check logs)
5. Trigger AI suggest again on the same long conversation — verify summary is cached (no regeneration)

- [ ] **Step 2: Final commit if any cleanup needed**

Only if issues were found and fixed during testing.
