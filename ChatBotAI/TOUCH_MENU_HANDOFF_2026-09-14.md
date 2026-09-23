# Resume here: UMI message touch/context menu

## Next task

Implement a message action menu in ChatBotAI (UMI). The feature was discussed and planned, but no long-press/context-menu implementation has been made in this conversation. This file was requested as a handoff before clearing chat context. Confirm the next user's instruction to begin implementation; saving this file does not itself request implementation now.

Workspace: `C:\Users\admin\Documents\FlaskApp\ChatBotAI`

The team uses the installed phone WebApp through the public HTTPS address `https://umteamsbz.com`, as well as desktop browsers. The user values simple, compact, direct interactions for staff.

## Agreed design direction

- Phone: hold a message for roughly 500 ms to highlight it and open an action panel from the bottom.
- Desktop: right-click a message to open a small action menu near the pointer.
- Provide a small visible `⋯` button to open the same menu without knowing the gesture, and support keyboard access.
- Only show actions applicable to the selected message, reusing the current implementations and permission/availability rules.
- Opening a menu must not generate, send, approve, or otherwise modify anything.
- Initially retain existing message action icons while testing. Replace them with the `⋯` entry point only after the user has checked the interaction.

### Proposed actions

| Message | Actions |
| --- | --- |
| Guest | Copy text; Translate when available; UMI-Vorschlag for that message |
| Team/AI reply | Copy text; Save as knowledge; Save as reply example, where supported |
| Pending AI approval | Copy text; Approve; Edit; Reject |
| Confirmed failed delivery | Copy text; Retry using existing confirmation |

An uncertain send is not a confirmed failure. Preserve delivery safeguards and do not add automatic retransmission.

## Interaction requirements

- Cancel long press when the finger moves to scroll, a pointer is cancelled, or multiple touches begin. Preserve normal scrolling and zooming.
- Tap outside or press Escape to dismiss; also close when an action is chosen.
- Keep the selected bubble visibly highlighted while its menu is open.
- Clamp desktop menus to the visible content/viewport; do not let them disappear under the sidebar or beyond the screen.
- Scope browser-context-menu suppression to the message interaction only. Keep normal text selection, copy, and paste in the composer, and preserve appropriate link/input behavior.
- Provide Copy text because replacing the browser menu removes that route to copying.
- Phone native callouts/selection vary across browsers; test installed iPhone and Android WebApps rather than assuming desktop simulation proves behavior.
- Include German and English labels, readable focus states, accessible names, and focus restoration on dismissal.
- Handle initial messages, polled messages, and older messages loaded through pagination without duplicate event handlers.

## Existing code to inspect

- `templates/chatbot/conversation.html`: message markup, action buttons, pending/failed states, composer, script versions.
- `static/js/conversation.js`: rendering, pagination/polling, translation, `suggestForMessage`, knowledge/example saving, approval/edit/reject, retry.
- `static/css/style.css`: original side-positioned message icons, mobile layout, menus, theme variables.
- `static/js/i18n.js`: German/English translations.
- `tests/`: current regression tests; inspect existing conventions before adding relevant coverage.
- `IMPROVEMENTS_2026-09-11.md`: previous changes and follow-up decisions. Some early descriptions are superseded by later notes.

Review current code and repository instructions first. There are many pre-existing changes and untracked files; do not reset or overwrite unrelated work. Do not restart the running app or send test messages to real guests as part of UI verification. The user has been doing restarts and sharing screenshots.

## UI preferences established through screenshots

- The user rejected large message action buttons below bubbles. They were restored to their original small positions beside messages. Keep that until the touch menu has been validated.
- The user rejected the inbox `Aktionen` dropdown. Inbox actions are directly visible again.
- The user rejected a composer `Mehr` dropdown and explanatory automation text. Keep the three composer buttons compact and directly visible.
- The user rejected a separate AI draft preview dialog and the Previous draft button. Suggestions/templates go directly into the text field.
- Do not reintroduce these rejected UI choices while implementing the touch menu.

## Current composer behavior to preserve

The main suggestion button adapts to the text field:

- Empty: `UMI-Vorschlag`.
- Unchanged AI output: `Neue Variante` / `New variant`.
- Staff-written, pasted, template, or edited text: `Mit UMI verbessern` / `Improve with UMI`.

Enhancement uses the staff's intended message, not the earlier guest question as a new task. It has a dedicated prompt in `services/ai_service.py` that encourages fresh, warm rephrasing while preserving meaning, language, certainty, and commitments. Relevant property knowledge/history serve as factual reference. Example: `Alles gut! Bis bald` should become a rephrased reassurance/farewell, not a fresh answer about parking/payment. Actual model behavior needs live review; automated tests used mocks.

Enhancement variants reuse the original staff draft. A response must not overwrite text changed while generation was running. Errors preserve the draft. Restored drafts after reload are treated as text to enhance.

The other AI button is named `UMI-Antwort erstellen`. Its current frontend request still uses `draft_only: true` and requires approval. Restoring the old name did not restore automatic sending for that manual action. Do not change this incidentally.

Manual sending preserves the draft until acknowledgement, labels uncertain delivery, and avoids automatic retry/local fallback after a lost response. Preserve these protections.

## Validation and environment notes

- No browser connection was available during earlier work, so do not claim earlier mobile layout changes were visually verified. User screenshots revealed issues that were then corrected.
- Prefer meaningful tests for menu action dispatch, conditional availability, long-press cancellation, dismissal, and viewport positioning. Do not send live messages to test actions.
- Existing Python tests use isolated runtime settings and block live network access.
- The default pytest temporary/cache directories previously had permission errors. Use a fresh workspace path, for example `--basetemp=tmp/pytest-touch-<unique-suffix> -o cache_dir=tmp/pytest-ui-cache`.
- Relevant existing Node tests include `tests/test_composer_safety.mjs`, `tests/test_connection_feedback.mjs`, `tests/test_inbox_date_grouping.mjs`, and `tests/test_translate_language_markers.mjs`.
- Bump relevant static asset query versions when changing frontend files. Template/backend changes may require a Flask/Waitress restart; the user handles this.

## Existing restore point

The earlier backup was verified at creation:

`C:\Users\admin\Documents\FlaskApp_Backups\before-improvements_2026-09-11_12-51-28`

It contains the full project archive, SQLite snapshots, verification/restoration instructions, and a supplemental archive for a Windows-special filename. Do not restore it merely to implement the touch feature. Do not expose credentials contained in backups or `.env`.

## Suggested next-chat prompt

Read `TOUCH_MENU_HANDOFF_2026-09-14.md` and the current repository instructions. Inspect the current message actions, then implement the planned message context menu: phone long press, desktop right-click, and a visible `⋯` fallback. Preserve the documented UI preferences and delivery safeguards. Keep existing icons until tested, and do not restart or send real guest messages.
