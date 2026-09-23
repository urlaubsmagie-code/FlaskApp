# Mobile chat keyboard gap report - 2026-09-14

Status: deferred at the user's request. Cause unknown; no application code changed for this report.

## Reported behavior

- Boss uses the installed, app-like web app (PWA), on a Google Pixel believed to be a 9 or 10; exact model, OS, browser engine version, and keyboard settings are unknown.
- While typing a reply, the space between the composer/status row and the keyboard grows. When typing stops it returns to normal; resuming typing makes it grow again, according to the user's review of the video.
- Two video screenshots show different blank-gap heights beneath the draft-saved row and different vertical positions of the conversation messages. The keyboard top stays at approximately the same height.
- User's Nothing Phone 2 does not reproduce it, including testing a very long draft: the text field grows upward normally with no jumping.
- No similar reports heard from the Digital Team; this does not establish that every other device is unaffected.
- Swipe typing was suggested based on a visible keyboard trail. The user rejected that as unrelated. Do not treat swipe typing as an established cause.
- Only screenshots were inspected; the source video was not provided. Timing comes from the user's description.

## Evidence

- [Screenshot 1](docs/bug-reports/mobile-keyboard-2026-09-14/frame-1.png)
- [Screenshot 2](docs/bug-reports/mobile-keyboard-2026-09-14/frame-2.png)

## Code observations, not a diagnosis

- `static/js/conversation.js`, `autoResizeTextarea`: resets height to `auto` on input, then measures scrollHeight and caps mobile height at 40% of window.innerHeight.
- `static/css/style.css`: mobile chat container and conversation body use 100svh; surrounding layout also contains vh/dvh sizing and scroll containers.
- VisualViewport handling found in `static/js/app.js` repositions notifications, not the chat layout.
- Some conversation flows call scrollIntoView; this alone does not explain movement during typing.
- `templates/chatbot/conversation.html` has an optional `?diag=1` overlay, but it measures innerHeight rather than the keyboard-reduced visual viewport.
- A resizing/cursor-visibility interaction was proposed, then explicitly qualified: not reproduced or confirmed. Long text alone is insufficient to trigger the issue on the user's phone.

## When resumed

Reproduce before selecting a fix. Establish exact affected device/runtime and record visual viewport height/offset, composer bounds, textarea height/scroll position, and page/message-list scroll positions during typing and pauses in installed mode. Compare against the unaffected device. No workaround or device-specific change has been approved or implemented by this report.
