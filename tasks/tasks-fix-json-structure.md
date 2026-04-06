## Relevant Files

- `c:\Users\admin\Server\FlaskApp\ProblemListingData\` - Directory containing JSON files to be corrected.
- `c:\Users\admin\Server\FlaskApp\scripts\fix_json_structure.py` - Script to be created for batch processing.

### Notes

- The target structure is based on `GeneralReviews.json` as described in `APARTMENT_ISSUES_DOCS.md` and `app.py`.
- Each file's content should be wrapped in a `wohnungen` array, with the apartment code derived from the filename.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

## Tasks

- [x] 0.0 Create feature branch
  - [x] 0.1 Create and checkout branch `feature/fix-json-structure`
- [x] 1.0 Analyze and Backup Data
  - [x] 1.1 List all JSON files in `ProblemListingData` to understand current state
  - [x] 1.2 Create a backup directory `ProblemListingData_Backup`
  - [x] 1.3 Copy all files from `ProblemListingData` to `ProblemListingData_Backup`
- [x] 2.0 Create Correction Script
  - [x] 2.1 Create `scripts/fix_json_structure.py`
  - [x] 2.2 Implement logic to read JSON files
  - [x] 2.3 Implement logic to extract `probleme` list
  - [x] 2.4 Implement logic to wrap data in `wohnungen` structure using filename as apartment code
  - [x] 2.5 Implement logic to save corrected JSON back to file
- [x] 3.0 Execute Correction Script
  - [x] 3.1 Run `python scripts/fix_json_structure.py`
- [x] 4.0 Verify Data Integrity
  - [x] 4.1 Randomly check 3-5 files to verify structure matches `GeneralReviews.json` schema
  - [x] 4.2 Verify no data was lost during transformation
