## Relevant Files

- `c:\Users\admin\Server\FlaskApp\ProblemListingData\` - Source directory for JSON files.
- `c:\Users\admin\Server\FlaskApp\ProblemListingData\HistoryReviews.json` - Target output file.
- `c:\Users\admin\Server\FlaskApp\scripts\aggregate_reviews.py` - Script to be created.

### Notes

- **Input**: Individual JSON files in `ProblemListingData` (e.g., `ABF1.json`, `BKF1.json`).
- **Logic**:
    - `AB` prefix = Airbnb, `BK` prefix = Booking.
    - Code after prefix is the apartment ID (e.g., `F1` from `ABF1` and `BKF1`).
    - Data for the same apartment ID should be merged.
- **Output Structure**: Similar to `GeneralReviews.json` (nested under `wohnungen` array).

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

## Tasks

- [x] 0.0 Create feature branch
  - [x] 0.1 Create and checkout branch `feature/create-history-reviews`
- [x] 1.0 Analyze Data and Schema
  - [x] 1.1 Verify filename patterns (AB/BK prefixes)
  - [x] 1.2 Confirm target schema matches `GeneralReviews.json`
- [x] 2.0 Create Aggregation Script
  - [x] 2.1 Create `scripts/aggregate_reviews.py`
  - [x] 2.2 Implement logic to parse filenames and extract apartment codes (remove AB/BK)
  - [x] 2.3 Implement logic to read individual JSON files
  - [x] 2.4 Implement logic to merge issues for the same apartment code
  - [x] 2.5 Implement logic to generate `HistoryReviews.json` with correct structure
- [x] 3.0 Execute Aggregation
  - [x] 3.1 Run `python scripts/aggregate_reviews.py`
- [x] 4.0 Verify Output
  - [x] 4.1 Check `HistoryReviews.json` exists and is valid JSON
  - [x] 4.2 Verify specific apartments (e.g., F1) have merged data from AB/BK sources
