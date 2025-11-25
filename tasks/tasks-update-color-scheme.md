## Relevant Files

- `templates/analytics.html` - Contains charts and statistics, currently using purple/blue gradients.
- `templates/apartment_issues.html` - Contains issue tracking, currently using purple/blue gradients.
- `templates/rankings.html` - Contains apartment rankings, currently using purple/blue gradients.
- `static/css/slideshow.css` - Main CSS file (already updated, but good for reference).
- `templates/index.html` - Main dashboard (already updated, reference).

### Notes

- The target color scheme is "Wine":
    - Primary: `#722F37` (Merlot)
    - Gradient Start: `#904E55` (Old Rose)
    - Gradient End: `#580f1b` (Darker Wine)
    - Accent/Hover: `#5D1F25` (Darker Merlot) or `#722F37`
- Ensure all gradients and primary colors are replaced.
- Keep the structure and logic intact, only change styles.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

Example:
- `- [ ] 1.1 Read file` → `- [x] 1.1 Read file` (after completing)

Update the file after completing each sub-task, not just after completing an entire parent task.

## Tasks

- [x] 0.0 Create feature branch
  - [x] 0.1 Create and checkout a new branch for this feature (e.g., `git checkout -b feature/wine-color-scheme`)
- [x] 1.0 Update `analytics.html` to Wine Color Scheme
  - [x] 1.1 Update `body` background gradient to `linear-gradient(135deg, #904E55 0%, #580f1b 100%)`.
  - [x] 1.2 Update `.nav-btn` icon colors (font-awesome icons) to `#722F37`.
  - [x] 1.3 Update Chart.js `colors` array in the `<script>` section to use wine tones (e.g., `#722F37`, `#904E55`, `#580f1b`) instead of the current bright palette.
- [x] 2.0 Update `apartment_issues.html` to Wine Color Scheme
  - [x] 2.1 Update `body` background gradient to `linear-gradient(135deg, #904E55 0%, #580f1b 100%)`.
  - [x] 2.2 Update `.navbar-brand` color to `#722F37`.
  - [x] 2.3 Update `.header-section` text color to `#722F37`.
  - [x] 2.4 Update `.stat-number` color to `#722F37`.
  - [x] 2.5 Update `.filter-btn.active` background and border to `#722F37`.
  - [x] 2.6 Update `.filter-btn:hover` border color to `#722F37`.
  - [x] 2.7 Update `.apartment-section` border-left color to `#722F37`.
  - [x] 2.8 Update `.apartment-code` background color to `#722F37`.
  - [x] 2.9 Update `.problem-item:hover` border color to `#722F37`.
  - [x] 2.10 Update `.problem-checkbox` accent-color to `#722F37`.
  - [x] 2.11 Update `.mentions-badge` background color to `#722F37`.
  - [x] 2.12 Update `.spinner` border-top color to `#722F37` and `.loading` text color.
- [x] 3.0 Update `rankings.html` to Wine Color Scheme
  - [x] 3.1 Update `.header-section` background gradient to `linear-gradient(135deg, #904E55 0%, #580f1b 100%)`.
  - [x] 3.2 Update `.ranking-position` background gradient to `linear-gradient(135deg, #904E55 0%, #580f1b 100%)`.
  - [x] 3.3 Update `.avg-rating` color to `#722F37`.
  - [x] 3.4 Update `.apartment-url a` color to `#722F37`.
  - [x] 3.5 Update `.group-header` background gradient to `linear-gradient(135deg, #904E55 0%, #580f1b 100%)`.
  - [x] 3.6 Update `.group-header:hover` background gradient to a slightly darker/lighter wine gradient.
  - [x] 3.7 Update `.group-prefix` color to `#722F37`.
  - [x] 3.8 Update `.apt-rank` background color to `#722F37`.
  - [x] 3.9 Update `.apt-rating-value` color to `#722F37`.
  - [x] 3.10 Update `.nav-btn` icon colors to `#722F37`.
  - [x] 3.11 Update Global Statistics `.stat-number` colors to `#722F37` (except the gold one).
- [x] 4.0 Verify Visual Consistency across all pages
  - [x] 4.1 Manually verify `analytics.html` in browser.
  - [x] 4.2 Manually verify `apartment_issues.html` in browser.
  - [x] 4.3 Manually verify `rankings.html` in browser.
- [x] 5.0 Update Slideshow Templates to Wine Color Scheme
  - [x] 5.1 Update `slideshow.html` background gradients and colors.
  - [x] 5.2 Update `slideshow_OPTIMIZED.html` background gradients and colors.
  - [x] 5.3 Verify Slideshow templates.
