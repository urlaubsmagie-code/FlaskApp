# Urlaubsmagie Brand Redesign — Design Spec

**Date:** 2026-04-01
**Approach:** Variable Swap + Targeted Polish (Approach B)

## Overview

Rebrand the ChatBotAI web app from its generic blue color scheme to the Urlaubsmagie brand identity. The brand color is a deep wine/burgundy derived from the Urlaubsmagie logo (~`#6B1C23`). The redesign covers both light and dark modes across all pages.

Additionally, the AI assistant is branded as **UMI-Bot** (UrlaubsMagie Intelligent Bot). All "KI" / "AI" references in the UI become "UMI", and the AI system prompt gets UMI's personality.

## Color Palette

### Brand Core
| Token | Value | Usage |
|-------|-------|-------|
| `--primary-color` | `#7B2332` | Buttons, links, active states |
| `--primary-hover` | `#5E1A27` | Button hover/pressed states |
| `--primary-light` | `#F9E8EB` | Subtle highlights, selected rows (light mode) |

### Sidebar
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-sidebar` | `#4A1520` | Dark wine sidebar background (both modes) |
| Sidebar hover | `#5E1A27` | Nav item hover |
| Sidebar active | `#7B2332` | Active page background + white left border |

### Light Mode
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#FDF6F7` | Page background (faint warm tint) |
| `--bg-secondary` | `#FFFFFF` | Cards, panels |
| `--card-bg` | `#FFFFFF` | Card backgrounds |
| `--border-color` | `#e2e8f0` | Keep neutral (unchanged) |

### Dark Mode
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#1A0F12` | Page background (wine-tinted black) |
| `--bg-secondary` | `#2A1519` | Cards, panels |
| `--card-bg` | `#2A1519` | Card backgrounds |
| `--border-color` | `#3D2025` | Warm-tinted borders |
| Primary button | `#8B2D3C` | Slightly lighter for visibility on dark bg |

### Unchanged
- **Text colors**: `--text-primary`, `--text-secondary`, `--text-light` stay as-is
- **Status colors**: success (`#22c55e`), warning (`#f59e0b`), danger (`#ef4444`) unchanged
- **Platform colors**: Airbnb (`#ff5a5f`), Booking (`#003580`), etc. unchanged
- **Avatar palette**: Stays diverse/multi-color for distinguishability

## Component Adjustments

### Buttons
- **Primary**: `#7B2332` bg, white text, hover `#5E1A27`
- **Primary (dark mode)**: `#8B2D3C` bg for better contrast, hover `#7B2332`
- **Secondary**: Existing style, but border/text get slight warm tint
- **Send button**: Wine-colored (was blue)

### Sidebar
- Background: `#4A1520` (same in light and dark mode)
- Nav text: `rgba(255,255,255,0.7)`, hover brightens to `#FFFFFF`
- Active nav item: `#7B2332` bg, white text, left accent border
- App title area: white text on dark wine

### Dark Mode
- Sidebar stays `#4A1520`
- Input fields: `#2A1519` background, `#3D2025` borders
- Shadows adjusted with warm-tinted rgba values

### Login Page
- White background (`#FFFFFF`)
- `UMProfile.png` logo (no text variant) centered above form
- Subtitle: "Powered by UMI"
- Subtle shadow card
- Wine `#7B2332` login button
- Input field icons tinted wine

## UMI-Bot Branding

### Name & Identity
- **Full name**: UMI-Bot (UrlaubsMagie Intelligent Bot)
- **Short name**: UMI
- **Personality**: Warm, friendly, casual (du/tú form). Always happy, helpful, and respectful toward guests. Professional when needed but never stiff.

### AI System Prompt Personality (2-3 lines)
Add to the system prompt role definition in `ai_service.py`:
> "You are UMI, the friendly AI assistant for Urlaubsmagie vacation rentals. You are warm, helpful, and casual — always treating guests like welcome visitors."

This replaces the generic "You are a vacation rental host" opener in the three prompt-building locations:
1. `_build_compact_prompt()` — line 660
2. Closing message shortcut — line 753
3. `_build_chat_messages()` full prompt — line 824

### UI Label Changes: "KI" → "UMI"
Replace all user-facing "KI" references with "UMI" in:

1. **`static/js/i18n.js`** — German strings (~45 occurrences) and English strings (~30 occurrences)
   - "KI-Vorschlag" → "UMI-Vorschlag"
   - "KI-Antwort" → "UMI-Antwort"
   - "KI-Freigabe" → "UMI-Freigabe"
   - "KI aktiv" → "UMI aktiv"
   - "KI-Assistent" → "UMI-Assistent"
   - "KI-Konfiguration" → "UMI-Konfiguration"
   - etc.
   - English: "AI" → "UMI" in matching strings

2. **`templates/chatbot/conversation.html`** — Hardcoded German fallback labels (~7 occurrences)

3. **`templates/chatbot/settings.html`** — Hardcoded German fallback labels (~15 occurrences)

4. **`templates/chatbot/inbox.html`** — Server-rendered "KI:" sender prefix (line 114)

5. **`templates/chatbot/help.html`** — Full German help text with ~50 "KI" references

6. **`templates/chatbot/guest_profile.html`** — "KI-extrahiert" label

7. **`static/js/inbox.js`** — JS fallback strings "KI aktiv", "KI pausiert", "KI-Freigabe" (~5 occurrences)

8. **`static/js/knowledge.js`** — JS fallback strings "KI sagte", "KI-Entwürfe" (~4 occurrences)

### What NOT to rename
- Internal code identifiers (variable names, CSS classes like `.ai-badge`, database fields like `ai_enabled`, Python function names) — these stay as-is
- The `sender_type='ai'` database value
- API route paths containing "ai"

## Files to Modify

1. **`static/css/style.css`** — CSS variable swap (`:root` and `[data-theme="dark"]`), sidebar styles, button hover states, any hardcoded blue values
2. **`templates/chatbot/login.html`** — Add logo image, "Powered by UMI" subtitle, wine-tinted icons
3. **`templates/chatbot/base.html`** — Bump cache version
4. **`static/` folder** — Copy `UMProfile.png` into static assets
5. **`services/ai_service.py`** — UMI personality in system prompt (3 locations)
6. **`static/js/i18n.js`** — Rename all "KI"→"UMI" and "AI"→"UMI" in user-facing strings
7. **`templates/chatbot/conversation.html`** — Rename hardcoded "KI" fallback labels
8. **`templates/chatbot/settings.html`** — Rename hardcoded "KI" fallback labels
9. **`templates/chatbot/inbox.html`** — Rename "KI:" sender prefix
10. **`templates/chatbot/help.html`** — Rename all "KI" references in help text
11. **`templates/chatbot/guest_profile.html`** — Rename "KI-extrahiert"
12. **`static/js/inbox.js`** — Rename JS fallback strings
13. **`static/js/knowledge.js`** — Rename JS fallback strings

## Out of Scope
- No structural HTML changes (except login logo + subtitle)
- No database changes
- No internal code identifier renames (Python vars, CSS classes, API routes)
- Avatar colors unchanged
- Platform colors unchanged
