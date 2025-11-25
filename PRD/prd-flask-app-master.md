# Product Requirements Document (PRD) - FlaskApp Visualization

## 1. Introduction
This document defines the requirements and structure of the **Gästebewertungen Slideshow Application** (Flask App). It serves as the single source of truth for the current state of the project, ensuring that future modifications, bug fixes, and feature additions are implemented with minimal risk and maximum stability.

**Goal:** To provide a robust, maintainable, and visually appealing interface for displaying guest reviews from Airbnb and Booking.com on various devices (TVs, tablets, mobile).

## 2. Goals & Objectives
*   **Maintainability:** Ensure the codebase is easy to understand and modify for future developers.
*   **Stability:** Prevent regressions when editing CSS or HTML templates.
*   **Responsiveness:** Guarantee optimal display on all target devices (Raspberry Pi/TV, Desktop, Mobile).
*   **Data Integrity:** Correctly parse and display data from the JSON source without errors.

## 3. User Stories
*   **As a Host (Anna-Lena):** I want to display a slideshow of positive guest reviews on a TV in the apartment so that guests feel welcome and reassured.
*   **As a Host:** I want to be able to filter reviews by rating or date on my mobile device to show specific feedback to potential clients.
*   **As a Developer:** I want a clear separation of concerns (Backend vs. Frontend) so that I can change the color scheme without breaking the data loading logic.
*   **As a Developer:** I want to know exactly which files control which part of the UI to reduce debugging time.

## 4. Functional Requirements

### 4.1. Dashboard (Index Page)
*   **Statistics Display:**
    *   Must show total number of reviews.
    *   Must show average rating (calculated from available data).
    *   Must show distribution of star ratings (1-5 stars).
*   **Review List:**
    *   Must list reviews with: Reviewer Name, Avatar (or placeholder), Date, Rating, Text, and Source (Airbnb/Booking).
    *   Must support filtering by Star Rating (1-5).
    *   Must support sorting by: Newest, Oldest, Highest Rating, Lowest Rating.
    *   Must support text search within reviews.

### 4.2. Slideshow Mode
*   **Auto-Play:** Slides must advance automatically every 30 seconds.
*   **Visuals:**
    *   Must display Reviewer Name, Avatar, Rating, and Review Text.
    *   Must show a progress bar indicating time remaining for the current slide.
    *   Must be optimized for 1920x1080 resolution (TV).
*   **Apartment Info:** Must display the specific apartment code/name associated with the review.

### 4.3. Data Processing (Backend)
*   **Source:** Read data from `DatasetScr.json` (Airbnb) and `DatasetScrBooking.json` (Booking).
*   **Filtering:**
    *   Exclude reviews older than 30 days (configurable).
    *   Exclude specific Apartment IDs (configurable).
*   **Parsing:**
    *   Convert ISO dates to readable German format (e.g., "Vor 2 Wochen", "Oktober 2025").
    *   Handle missing data gracefully (default avatars, "Anonym" name).

## 5. Non-Goals (Out of Scope)
*   **Scraping Logic:** This project does **NOT** include the implementation or maintenance of the web scrapers. It assumes valid JSON data is provided.
*   **User Authentication:** The app is intended for local/internal use; no login system is required.
*   **Database:** No SQL database is used; data is read directly from JSON files.

## 6. Design & UI/UX Requirements
*   **Color Palette:**
    *   Primary: Wine/Merlot (`#722F37`)
    *   Gradient: `#904E55` to `#580f1b`
    *   Accent: Gold (`#ffc107`) for stars.
*   **Typography:** Use 'Inter' or system sans-serif fonts for readability.
*   **Responsive Breakpoints:**
    *   Mobile: < 768px (Stacked layout, larger touch targets).
    *   Tablet/Laptop: 769px - 1399px.
    *   TV: > 1400px (Large text, maximized use of screen real estate).

## 7. Technical Considerations
*   **Framework:** Flask (Python).
*   **Templating:** Jinja2.
*   **Styling:** Bootstrap 5 + Custom CSS (`static/css/slideshow.css`).
*   **File Structure:**
    *   `app.py`: Main application logic and routing.
    *   `templates/index.html`: Main dashboard template.
    *   `templates/slideshow.html` (or dynamic generation): Slideshow template.
    *   `static/css/`: Custom styles.

## 8. Success Metrics
*   **Zero UI Regressions:** Future color/style changes do not break layout on TV.
*   **Data Accuracy:** 100% of valid reviews in the JSON are displayed (unless filtered).
*   **Load Time:** Dashboard loads in < 2 seconds locally.

## 9. Open Questions / Future Work
*   *Potential:* Integration with VRBO data source (requires JSON schema definition).
*   *Potential:* Admin interface to manually hide specific reviews without editing code.
