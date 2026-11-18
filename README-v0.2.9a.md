# Pale Horse CRM v0.2.9a — Full Class Calendar Export

Small update to v0.2.9. **No database changes or extra Python packages.**

## New feature
In **Classes & Blocks → Manage a Group Class**, click **ADD FULL CLASS TO CALENDAR (UP TO 1 YEAR)** to download one `palehorse-class-series.ics` file with each upcoming *confirmed* class date through the next 365 days. The existing single-date **ADD TO CALENDAR** buttons remain in place.

- Moved occurrences use their rescheduled times.
- Cancelled occurrences are excluded.
- Class roster, client contact information, and personal details are excluded.
- Multi-coach classes produce **one** calendar event per class date, not one per coach.
- The endpoint requires a logged-in owner/admin or a currently assigned coach.
- Classes extending beyond 365 days will require another export later; only materialized occurrences currently in CRM are included. If more dates are needed, use **EXTEND UPCOMING DATES** before downloading.
- `.ics` is a snapshot, not a live sync: future CRM schedule changes will not automatically update events previously imported to Google/Apple Calendar. Avoid reimporting the same file repeatedly, which may result in duplicates depending on the destination application.
- Download only works for **Group Class** events; private Block Time retains its separate existing calendar options.

## Install
1. Back up your source and PostgreSQL database.
2. Extract this archive to a temporary folder OUTSIDE your working project.
3. Copy contents of `backend/` and `frontend/` into matching folders of `C:\Users\johna\PycharmProjects\palehorse-crm`. Keep your existing `.env`, Compose setup, and database volume.
4. From the active project directory: `docker compose up -d --build --force-recreate api frontend`.
5. Log in, open **Classes & Blocks**, and expand an active group class with upcoming confirmed dates. Click **ADD FULL CLASS TO CALENDAR (UP TO 1 YEAR)**. Import the downloaded `.ics` in Google Calendar or open with Apple Calendar. Check that canceled occurrences are absent and moved dates use updated times.
6. Check authorization by signing in as a trainer who is not one of the class coaches: they must not be able to access the series export endpoint.

## Verification and limitations
- Python syntax compilation passed, all TSX parse checks passed, archive integrity checked.
- No live Docker/PostgreSQL integration test, full frontend build, or Google/Apple end-to-end import test was run here. Validate locally before making this a stable release.
