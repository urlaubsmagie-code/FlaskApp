# Implementation Plan - Update Apartment Issues UI

## Goal
Update the `/apartment-issues` page to display data from two sources: `HistoryReviews.json` (static history) and `GeneralReviews.json` (recent updates). The UI will provide three views: History, Recents, and General (merged).

## Proposed Changes

### Backend
#### [MODIFY] [app.py](file:///c:/Users/admin/Server/FlaskApp/app.py)
- **Function**: `api_apartment_issues`
- **Change**:
    - Read `ProblemListingData/HistoryReviews.json`.
    - Read `n8n-docker/files/GeneralReviews.json`.
    - Return a JSON object with both datasets:
      ```json
      {
        "history": [...],
        "recents": [...]
      }
      ```

### Frontend
#### [MODIFY] [apartment_issues.html](file:///c:/Users/admin/Server/FlaskApp/templates/apartment_issues.html)
- **UI Structure**:
    - Add a new tab bar (or segmented control) for "General", "Recents", "History".
- **Logic**:
    - `loadData()`: Fetch the new API structure.
    - `mergeData()`: Helper function to combine `history` and `recents` for the "General" view.
        - Strategy: Combine lists. If an apartment exists in both, merge their `probleme` lists.
    - `renderContent()`: Update to render based on the active tab (General/Recents/History) AND the existing status filter (All/Pending/Completed).

## Verification Plan

### Automated Verification
- None (UI changes are best verified manually).

### Manual Verification
1.  **History Tab**: Verify it displays data from `HistoryReviews.json`.
2.  **Recents Tab**: Verify it displays data from `GeneralReviews.json`.
3.  **General Tab**: Verify it displays a merged list.
4.  **Data Updates**: Modify `GeneralReviews.json` manually and refresh the page to confirm "Recents" and "General" update.
