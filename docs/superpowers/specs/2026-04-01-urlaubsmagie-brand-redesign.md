# Urlaubsmagie Brand Redesign — Design Spec

**Date:** 2026-04-01
**Approach:** Variable Swap + Targeted Polish (Approach B)

## Overview

Rebrand the ChatBotAI web app from its generic blue color scheme to the Urlaubsmagie brand identity. The brand color is a deep wine/burgundy derived from the Urlaubsmagie logo (~`#6B1C23`). The redesign covers both light and dark modes across all pages.

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
- Subtle shadow card
- Wine `#7B2332` login button
- Input field icons tinted wine

## Files to Modify

1. **`static/css/style.css`** — CSS variable swap (`:root` and `[data-theme="dark"]`), sidebar styles, button hover states, any hardcoded blue values
2. **`templates/chatbot/login.html`** — Add logo image, wine-tinted icons
3. **`templates/chatbot/base.html`** — Bump cache version
4. **`static/` folder** — Copy `UMProfile.png` into static assets

## Out of Scope
- No structural HTML changes (except login logo)
- No JavaScript changes
- No bot/page naming changes (idea only, deferred)
- Avatar colors unchanged
- Platform colors unchanged
