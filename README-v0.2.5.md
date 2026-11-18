# Pale Horse CRM v0.2.5 — Clients & Schedule Import (development)

**KISS workflow:** Download template → fill client contact + weekly slots → upload and preview → confirm.

## Included

- Excel `.xlsx` template (`frontend/public/palehorse-schedule-template.xlsx`), also CSV imports with identical headers.
- Trainer-facing **Clients & imports** screen, with owner trainer selector.
- Client name, email, phone and per-weekday recurring slots. One client can appear on multiple rows.
- Preview detects duplicate rows, existing import keys, contact conflicts, and overlaps with confirmed sessions.
- Existing **approved** clients schedule immediately. Unassigned/new clients generate a **pending approval** request for Noah. Once approved under **Client sessions**, their schedule rows are applied. Conflicting rows remain `needs_attention`, without deleting history.
- Client directory allows searching and editing contact fields (restricted by trainer ownership).
- Immutable appointment audit entries and durable import-row records; reupload cannot duplicate imported rows.

## Install without nesting the project

1. **Back up PostgreSQL and the current code** before replacing files. Do not use `docker compose down -v`.
2. Extract this ZIP to a temporary folder (not inside the active project).
3. Copy its `backend` and `frontend` **contents** into the existing project at `C:\Users\johna\PycharmProjects\palehorse-crm`. Preserve `.env`, Compose setup and database volume.
4. In PowerShell, from the active project root:

```powershell
docker compose up -d --build --force-recreate api frontend
docker compose logs --tail=100 api
docker compose logs --tail=100 frontend
```

5. Open http://localhost:5173, sign in, and choose **Clients & imports**.

## Template columns (exact order)

`first_name, last_name, email, phone, day, start_time, duration_minutes, frequency, start_date, end_date, session_type`

- Use **one row per weekly slot**, repeat client name/email/phone for each day.
- Email and phone are required in this importer. Phone should be **text**, e.g. `+1 802 555 0123`.
- Day: Monday through Sunday. Time: `17:00` or `5:00 PM`. Duration: 15–240 minutes.
- Frequency: `Weekly`, `Biweekly`, `Every 4 Weeks`.
- Dates: `YYYY-MM-DD`. Blank end date starts a rolling 180-day plan (extend periodically). Explicit end date must be within a year of start.
- Up to 250 rows / 900 KB per upload. Import accepts `.xlsx` and UTF-8 `.csv`.

## Important operating notes

- The **Example (do not upload)** sheet is illustrative; the importer reads **Schedule Import** only.
- Preview does not save anything. Confirmation re-validates; any invalid rows cause the whole import to be rejected.
- Existing bookings can be imported even if recurring trainer availability hasn't been entered yet. Import still checks for actual **booking conflicts**, not schedule availability. The owner should review availability separately.
- Contact matches are conservative: email must match exactly, and inconsistent name/phone is flagged for manual review. The importer does not automatically merge uncertain records.
- When approved-client bookings overlap, the importer rejects the commit; when newly approved bookings overlap later, the affected import row is retained for manual resolution.
- Imported pending requests show up in existing **Client sessions → Existing client onboarding**.
- This is a local development build; don't import real client personal information until authorization, backup, and privacy requirements have been reviewed for deployment.

## Local testing checklist

- [ ] Owner and trainer can log in; existing pages still work
- [ ] Download template; fill two rows for the same sample client
- [ ] Preview shows 2 approval-required rows; confirm
- [ ] Owner approves once; 2 weekly series appear in calendar
- [ ] Reimport same rows; preview flags duplicates
- [ ] Import a slot that overlaps confirmed appointment; conflict blocks it
- [ ] Trainer sees only assigned clients in directory; cannot alter another trainer's contact data
- [ ] Change client email/phone; audit entry appears in client activity

**Validation performed:** Python compilation and TSX parse checks passed. A simulated SQLite backend flow passed for preview → commit → owner approval → 52 appointments, and reupload was rejected. Full frontend build and PostgreSQL/Docker integration are still required locally.
