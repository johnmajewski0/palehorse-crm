# Pale Horse CRM v0.2.4 — Usability Pass (development)

This is an incremental frontend update based on the v0.2.3 hotfix source. It does **not** modify the FastAPI backend or PostgreSQL schema.

## Included
- Role-specific owner/trainer home screen shown after login.
- Clear quick-action navigation to calendar, client sessions, trainer availability/assignments and prospects.
- Upcoming confirmed session preview covering the next seven days, with one-click calendar access.
- At-a-glance lead, request and trainer counts with context-appropriate visibility.
- Accessible, keyboard-focusable navigation buttons; mobile navigation no longer disappears on narrow screens.
- Existing Pale Horse logo and login design retained.
- Source-only update, delivered without nested project folder to avoid previous extract mistakes.

## Install
1. Back up the working source and PostgreSQL database. Keep your existing `.env` and Compose files.
2. Extract this archive **outside** your project. The zip has `frontend/`, `backend/` and this README at its root.
3. Copy **only `frontend/src/` and `frontend/package.json`** to `C:\Users\johna\PycharmProjects\palehorse-crm\frontend\` (existing backend is unchanged).
4. In the project directory: `docker compose up -d --build --force-recreate frontend`
5. Review `docker compose logs --tail=50 frontend` and hard-refresh Firefox.

## Validate
- Owner logs in to Owner home; trainer logs in to Trainer home.
- Quick actions open the existing working sections.
- Upcoming sessions show only permitted calendar data (server enforces trainer restrictions).
- On phone-size screens navigation remains usable.
- Scheduling, session editing, and existing prospect pipeline still work.

## Limitations
- TSX syntax transpilation was verified for all frontend components. Full TypeScript typecheck / Vite build and Docker runtime test were **not** completed because installing dependencies in this environment timed out.
- This package uses the last v0.2.3 development hotfix supplied in the conversation, not a fresh GitHub checkout. If you changed files locally after that, inspect the diff before overwriting.
- This release improves navigation and daily workflows but does not include new backend booking behavior, automated notifications, or series-wide rescheduling.
