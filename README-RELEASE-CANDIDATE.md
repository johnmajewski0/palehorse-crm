# Pale Horse CRM — v0.3.0 UX Release Candidate

This package is a **development/release candidate**, NOT certified production-ready.

## What changed
- Desktop left sidebar grouped into collapsible Schedule, Clients, and (owner-only) Owner sections.
- Corrected the owner "Client approvals" dashboard quick action to open Clients & Imports.
- Added a three-step getting-started shortcut panel to trainer desktop Home: set availability, import appointments, review calendar.
- Replaced outdated Gmail setup copy in the prospect pipeline.
- Clarified that current create-trainer temporary-password form is development-only, not a production invitation flow.
- Preserved existing trainer-only mobile mode and owner-specific restrictions.

No database schema or migration changes were made for this UX update. This update DOES NOT deliver secure email invitations, Gmail sending or the daily briefing scheduler, and makes no changes to existing booking algorithms. Do not advertise these as finished.

## Installation
1. Back up database (and test restoring it) and copy your current source to a safe location.
2. Extract package OUTSIDE your active project directory. Copy frontend/src contents into C:\\Users\\johna\\PycharmProjects\\palehorse-crm\\frontend\\src and keep existing .env and compose files intact.
3. In project root: `docker compose up -d --build --force-recreate frontend`
4. Verify owner desktop navigation, trainer desktop Home, and trainer mobile layout. Ensure that the owner-only section is absent for trainer roles.
5. Compile frontend in your actual runtime: `docker compose exec frontend sh -lc 'npm run build'` (if your container has dependencies and npm scripts). Run API integration tests separately.

## Production go/no-go gate (must pass before real client data)
- Secure trainer email invitation + one-time activation; retire owner-entered shared/temporary passwords.
- Gmail sending permissions, token handling, outbound email send tests, daily briefing scheduling and deduplication.
- Correct backend access checks for owner operations, prospects, clients, calendars, exports, group classes, and import paths.
- Fresh PostgreSQL schema migration and upgrade-with-data tests; no table resets.
- Booking race/conflict tests: individual + classes + imports; rescheduling, holidays, DST, recurring series.
- Secure OAuth callback, secret isolation (git history checked), production secure cookies/CSRF, rate limits, no development debug surfaces.
- Full TypeScript production build; end-to-end owner/trainer tests on phone + desktop.
- HTTPS domain, external Google OAuth redirect, least-privilege hosting, backups, restore drill, monitoring and rollback plan.
- Controlled pilot with Noah and Andy before broad rollout.

## Verification performed here
- Python `py_compile` passed for two backend Python modules.
- All nine TSX files passed TypeScript transpilation syntax diagnostics.
- Frontend dependency install and full TypeScript/Vite production build NOT completed (package registry install stalled in environment).
- No live Docker / PostgreSQL / Google OAuth tests performed here.
