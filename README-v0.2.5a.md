# Pale Horse CRM — v0.2.5a frequency expansion (development)

Extends the existing v0.2.5 client import feature. All other CRM modules are retained.

## Trainer workflow

Open **Clients & imports** → **Download Excel Template** → fill in the schedule → upload → preview → confirm.

The Frequency dropdown (H2:H250) now includes:
- **One-time** — exactly one appointment on `start_date`.
- **Weekly** — every week on the selected day.
- **Biweekly** — every two weeks.
- **Every 3 Weeks** — every three weeks.
- **Every 4 Weeks** — every four weeks (not the same as Monthly).
- **Monthly** — on the same calendar day of the month as `start_date`. If the month has fewer days, use its last day (e.g. Jan 31 → Feb 28 → Mar 31).

For **One-time** and **Monthly**, `day` must match the weekday of `start_date`. For weekly frequencies, the first occurrence is the first selected weekday on or after `start_date`.

A blank end date generates appointments through the first 180 days (or exactly one for One-time). Monthly appointments are saved as separately auditable individual sessions, rather than as a continuously expanding series; extending the schedule beyond the first horizon will need a subsequent booking. Weekly/biweekly/3-week/4-week entries retain the existing weekly series logic.

## Install

1. Back up your working project and PostgreSQL database. Do not run `docker compose down -v`.
2. Extract this ZIP into a **temporary folder outside** the active project.
3. Copy the included `backend` and `frontend` contents into `C:\Users\johna\PycharmProjects\palehorse-crm`, preserving your `.env` and local Compose configuration.
4. From PowerShell in that directory:

```powershell
docker compose up -d --build --force-recreate api frontend
docker compose logs --tail=60 api
docker compose logs --tail=60 frontend
```

The existing download button serves `/palehorse-schedule-template.xlsx`, now bundled with the updated validation dropdowns.

## Smoke tests

- Download a **fresh** template from Clients & imports after redeploying.
- Fill a fictional client with a One-time slot, review that exactly one session is proposed.
- Try Every 3 Weeks, and confirm the 21-day cadence.
- Try Monthly with an end date, and confirm matching calendar-month dates (not a 28-day cadence).
- Use preview and verify duplicate/conflict checks still apply.
- For a new client, confirm Noah's approval remains required.

## Verification and limitations

Python syntax compilation, Excel dropdown XML verification, and targeted one-time / 3-week / calendar-month calculation checks passed. Full PostgreSQL + Docker + React integration testing **has not** been completed here. Excel dropdowns do not substitute for backend validation. This is a development update, not a production release.
