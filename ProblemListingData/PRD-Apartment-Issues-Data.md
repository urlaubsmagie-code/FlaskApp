# PRD: Apartment Issues Data Structure

## 1. Introduction/Overview
The `ProblemListingData` folder contains JSON files that store summarized data about issues (problems) reported for each apartment. These files serve as the data source for the `/apartment-issues` section of the project, allowing property managers to track and resolve maintenance issues and guest complaints.

## 2. Goals
*   **Standardization**: Define a consistent JSON schema for storing apartment issues.
*   **Accessibility**: Ensure the data is structured in a way that can be easily parsed and displayed by the `/apartment-issues` frontend.
*   **Granularity**: Maintain separate data files (or entries) for different apartments/reviews to allow for granular updates.

## 3. User Stories
*   **Property Manager**: "As a property manager, I want to view a consolidated list of issues for each apartment (e.g., 'Cleanliness', 'Broken items') so that I can prioritize maintenance tasks."
*   **Developer**: "As a developer, I want a clear data contract for apartment issues so that I can reliably render the issues list in the UI."

## 4. Functional Requirements
1.  **Data Storage**: The system shall store apartment issue summaries in JSON format within the `ProblemListingData` directory.
2.  **Data Structure**: Each JSON file must follow a specific schema containing the apartment identifier and a list of issues.
3.  **Integration**: The `/apartment-issues` page (via `/api/apartment-issues`) must be able to consume this data (either directly or via an aggregation process like `GeneralReviews.json`).
4.  **Issue Attributes**: Each issue must contain:
    *   `beschreibung` (Description): A text description of the issue.
    *   `erwähnungen` (Mentions): The number of times this issue has been reported.

## 5. Data Schema
The data files in `ProblemListingData` (e.g., `ABB1.json`) follow this structure:

```json
[
  {
    "index": 0,
    "message": {
      "role": "assistant",
      "content": {
        "probleme": [
          {
            "beschreibung": "Description of the issue",
            "erwähnungen": 1
          }
        ],
        "wohnungen": [
            {
                "wohnung": "Apartment Code",
                "probleme": [...]
            }
        ]
      }
    }
  }
]
```
*Note: Some files contain a `probleme` list directly under `content`, while others (like the one expected by `app.py`) might nest them under `wohnungen`. The PRD recommends standardizing on the `wohnungen` structure for multi-apartment support.*

## 6. Non-Goals (Out of Scope)
*   **Real-time Sync**: This PRD does not cover real-time synchronization with external booking platforms (Airbnb/Booking.com). It assumes the data is generated/placed in the folder by an external process (e.g., n8n or LLM analysis).
*   **Issue Resolution Workflow**: The logic for marking issues as "done" is handled by the frontend/local storage, not by this data structure.

## 7. Technical Considerations
*   **File Naming**: Files are named with a prefix (e.g., `ABB`, `ABF`) followed by a number/ID.
*   **Parsing Logic**: The `app.py` currently reads `GeneralReviews.json`. A future task may be to aggregate the individual files from `ProblemListingData` into `GeneralReviews.json` or modify `app.py` to read `ProblemListingData` directly.

## 8. Success Metrics
*   **Data Integrity**: All files in `ProblemListingData` parse validly against the schema.
*   **UI Representation**: The `/apartment-issues` page accurately reflects the issues listed in these files.
