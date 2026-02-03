## Relevant Files

- `c:\Users\admin\Server\FlaskApp\app.py` - Backend logic to serve data.
- `c:\Users\admin\Server\FlaskApp\templates\apartment_issues.html` - Frontend UI to be updated.
- `c:\Users\admin\Server\FlaskApp\ProblemListingData\HistoryReviews.json` - New data source.
- `c:\Users\admin\n8n-docker\files\GeneralReviews.json` - Existing data source.

### Notes

- **Backend**: Need new API endpoints or modify existing one to return both datasets.
    - `/api/apartment-issues` could return `{ "history": [...], "recents": [...] }`.
- **Frontend**:
    - Add tabs/sections for "History", "Recents", "General".
    - "General" view merges both datasets (summing mentions if same issue exists? Or just listing all?). *Assumption: Just listing all for now, or merging if identical description.*
    - "Recents" corresponds to `GeneralReviews.json`.
    - "History" corresponds to `HistoryReviews.json`.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

## Tasks

```
## Relevant Files

- `c:\Users\admin\Server\FlaskApp\app.py` - Backend logic to serve data.
- `c:\Users\admin\Server\FlaskApp\templates\apartment_issues.html` - Frontend UI to be updated.
- `c:\Users\admin\Server\FlaskApp\ProblemListingData\HistoryReviews.json` - New data source.
- `c:\Users\admin\n8n-docker\files\GeneralReviews.json` - Existing data source.

### Notes

- **Backend**: Need new API endpoints or modify existing one to return both datasets.
    - `/api/apartment-issues` could return `{ "history": [...], "recents": [...] }`.
- **Frontend**:
    - Add tabs/sections for "History", "Recents", "General".
    - "General" view merges both datasets (summing mentions if same issue exists? Or just listing all?). *Assumption: Just listing all for now, or merging if identical description.*
    - "Recents" corresponds to `GeneralReviews.json`.
    - "History" corresponds to `HistoryReviews.json`.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

## Tasks

- [ ] 0.0 Create feature branch
  - [ ] 0.1 Create and checkout branch `feature/update-apartment-issues-ui`
- [ ] 1.0 Update Backend (app.py)
  - [ ] 1.1 Modify `api_apartment_issues` to read `HistoryReviews.json`
  - [ ] 1.2 Modify `api_apartment_issues` to read `GeneralReviews.json` (existing)
  - [ ] 1.3 Return combined structure: `{ "history": [...], "recents": [...] }`
- [x] 2.0 Update `apartment_issues.html`
    - [x] Add tab navigation for "General", "Recents", "History"
    - [x] Update JavaScript to fetch and handle the new API response structure
    - [x] Implement logic to switch views and filter data based on the selected tab
    - [x] Ensure "General" view merges history and recents correctly (avoiding duplicates)
- [x] Verify functionality
    - [x] Test switching between tabs
    - [x] Verify data display for each source
    - [x] Check persistence of "completed" status across views (polling or refresh button?) *User said "detect any new data", implying auto-refresh or just correct loading on refresh.*
- [ ] 3.0 Verify Implementation
  - [ ] 3.1 Verify "History" tab shows data from `HistoryReviews.json`
  - [ ] 3.2 Verify "Recents" tab shows data from `GeneralReviews.json`
  - [ ] 3.3 Verify "General" tab shows merged data
  - [ ] 3.4 Verify persistence works correctly across tabs
```
