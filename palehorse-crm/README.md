# PALE HORSE BARBELL — CRM (v0.2.0 development update)

Separate from BearStrong. Branded black, white and charcoal. Uses FastAPI, React + TypeScript, PostgreSQL and Docker Compose, the same broad technology choices as GymGenie. **This is an independently authored starter, not a clone or fork of GymGenie**: the build environment could inspect its public source via GitHub but could not clone it. No GymGenie source code is included.

## Working MVP features
- Owner login with cookie session + CSRF token
- Create prospect leads and update stages; scheduling workflow assigns leads to trainers
- Create trainer accounts for users of any email provider
- Trainer accounts see only their assigned leads; can update stage and add notes
- Prospect activity notes persist in PostgreSQL
- Pale Horse monochrome responsive dashboard, summary cards and lead table
- Gmail status card for `noah@palehorsebarbell.com`: **NOT CONNECTED**, no OAuth credentials or Gmail access

## Local startup (PowerShell)

1. Extract ZIP into a separate folder, e.g. `C:\Users\johna\source\palehorse-crm`. Do not mix with BearStrong.
2. Copy config: `Copy-Item .env.example .env`
3. Edit `.env`: choose a strong PostgreSQL password, random SESSION_SECRET of 32+ characters, and a unique owner password of 12+ characters. The example owner address is only a login identifier; no email is sent.
4. Run `docker compose up -d --build`
5. Browse to http://localhost:5173 and sign in with the owner email/password from `.env`.
6. `docker compose logs --tail=80 api` if needed.

**Important:** The initial owner is created only if the users table is empty. Changing `.env` after initialization does not reset an existing user's password. All operations are additive; do not delete the volume to troubleshoot if you need to retain data.

## Limitations / before production
This is a development MVP, **not a hardened production deployment**. Before exposing it publicly: add password reset/invitation, email verification, stronger auth/rate limiting, secure-cookie reverse proxy HTTPS settings, DB migrations/Alembic, audit logs for every state change, password rotation, secret manager, backups and restore testing, deployment security review and tests. The backend startup uses `create_all` for initial schema only.

## Gmail integration roadmap
1. Create Google Cloud project in the `palehorsebarbell.com` Workspace organization and enable Gmail API.
2. Configure Internal OAuth client and explicit permission from Noah for `noah@palehorsebarbell.com` (read-only first).
3. Implement authorization callback, encrypted token storage, renewal/revocation and mailbox sync checkpoint.
4. Import emails only into owner's private review queue; never grant trainers full mailbox access. Match approved messages to leads and expose only explicitly approved threads.
5. Only later request send scope and require approval for outbound email.

## Architecture
- `frontend/`: React + TypeScript + Vite
- `backend/`: FastAPI + SQLAlchemy
- `compose.yml`: local PostgreSQL 17 with persistent named volume

## Reference
GymGenie: https://github.com/yashpagade-yp/GymGenie. Its GitHub metadata displayed no license at inspection time; no source copied into this package.

## v0.2.0 — Trainer scheduling and assignment management (development update)

- Trainer/owner create recurring weekly availability in **America/New_York** (Monday=0) and date-specific time-off or additional-hours exceptions. Rules and exceptions are archived rather than deleted.
- Owner requests an assignment for a client and trainer and dates; trainer accepts, declines, or proposes a different time. Owner approves a proposal or cancels. Trainer can return a confirmed client to owner.
- Scheduling section in the React sidebar, in-app notifications, and event history for every assignment transition. A confirmed assignment updates the existing lead's `assigned_trainer_id`.
- PostgreSQL `btree_gist` exclusion constraints prevent concurrent overlapping confirmed bookings for trainers **and clients**. Starting the API requires PostgreSQL permission to create the extension (normally granted to the PostgreSQL database owner).
- Legacy direct PATCH of `assigned_trainer_id` is deliberately rejected so new assignments cannot evade the approval/audit workflow; lead stage editing continues to work.
- Owner/admin see all assignment requests, trainer users see only requests addressed to themselves.

### Apply without losing the existing database

1. **Back up** the existing PostgreSQL database before any update. For example, in PowerShell in the existing project directory: `docker compose exec -T db pg_dump -U palehorse -d palehorse_crm -Fc > palehorse-crm-before-v0.2.dump`. Keep that file outside the project tree.
2. Make a backup of your old source folder too. Extract this archive and copy its `backend/`, `frontend/`, and `README.md` over your existing corresponding paths. **Keep your existing `.env`**; do not overwrite it. Do not run `docker compose down -v`.
3. Run `docker compose up -d --build`, then `docker compose logs --tail=100 api`. Confirm API startup before signing in at `http://localhost:5173`.
4. Open Trainer scheduling, add recurring hours, create a lead and trainer (if necessary), request a slot, log in as that trainer to accept, then check the owner's pipeline and history/notifications.

**Validation status:** Python syntax compilation succeeded. React dependency installation and full container integration could not be run in the packaging environment; run Docker build and the listed scenarios locally. This is a development update, not a production-hardened deployment.

**Important caveats:** All time inputs in the UI use the browser's local timezone; scheduling rules use America/New_York. Run browser in Eastern time or add an explicit timezone-aware picker before use from other zones. In-app notifications are not yet Gmail messages. Recurring rule edits and exception archives are preserved by deactivation, but unlike assignment events their change operations do not yet have actor/timestamp event records. An existing v0.1.0 lead assigned directly to a trainer remains as-is and has no retroactive scheduling history. Add Alembic migrations, broader test coverage and production-grade hardening before deployment.


## v0.2.1 — Master and personal calendars (development)

New **Master calendar** (owner/admin) and **My calendar** (trainer) views support day/week/month navigation. Owner can filter by trainer. Availability is calculated from recurring rules plus additions minus unavailable exceptions and confirmed sessions. Confirmed, pending/proposed, free, and unavailable segments are color coded. Times display in America/New_York.

**Personal calendar exports:** trainers can download a rolling 61-day `.ics` snapshot or create a read-only private subscription feed. Only confirmed sessions are exported, with generic event summaries and **no client name**. The private link is shown only once after creation, can be revoked, and must be treated as a password. Google Calendar: Other calendars → From URL → paste the full subscription URL. Google Calendar polling is outside the app's control. The feed intentionally requires no login since subscription readers cannot supply CRM session cookies. **Do not issue subscription URLs over plain HTTP on a public host.** Configure HTTPS before production.

The owner-wide iCalendar export has intentionally not been enabled because it would share appointments from multiple trainers. In-app master calendar is owner/admin only; trainers' API access is restricted to their own events.

### Install update safely

Backup your PostgreSQL volume/database first. Copy this package's `backend/` and `frontend/` contents over the existing source directories without copying over secrets or deleting volumes; retain your existing compose.yml and .env. From your existing project root:

```powershell
docker compose up -d --build --force-recreate api frontend
docker compose logs --tail=80 api
docker compose logs --tail=80 frontend
```

Visit http://localhost:5173. Confirm that the sidebar contains Master calendar for Noah and My calendar for trainers. Test opening a confirmed session and changing calendar filters; in a trainer account, download an ICS file and generate/revoke a subscription URL.

**Status / limitations:** Python syntax compilation succeeded; the frontend dependency install/build was unable to finish in the packaging environment and full running-PostgreSQL integration has not been performed. This is a development update, not production validated. Only confirmed assignment records are represented as training sessions; recurring *client training appointments*, drag-and-drop rescheduling, automated trainer-change notifications and two-way Google API sync are not part of this release. Existing scheduling constraints remain as in v0.2.0. For production, add robust database migrations, deeper transaction/concurrency tests, deploy HTTPS, restrict cookie origins, and configure backups and monitoring.

## v0.2.2 — Existing clients, bookings and recurring series (development)

**New navigation:** Client sessions. A trainer can submit an existing client for owner review. The owner approves/rejects the onboarding request; only approved clients can be booked. A trainer cannot see or modify another trainer's client sessions. The owner can review all.

**Sessions:** trainers and owners can book for approved/assigned clients, reschedule a single occurrence, cancel it, record a no-show, and see a per-session audit trail. Sessions appear in the existing visual calendar and read-only iCalendar export. Backend checks trainer availability and conflicts against both the original assignment bookings and the new session bookings. On PostgreSQL, new exclusion constraints also prohibit two confirmed session rows overlapping for the same trainer or client, including concurrent submissions.

**Recurring bookings:** select weekly, every other week, or every four weeks; choose start weekday/time, duration, and an optional end date (up to 12 months from start). Preview reports *all* conflicting occurrences; creation is atomic and refuses any conflicting date. Recurrences are anchored to `America/New_York` wall time so weekly times survive DST changes. A single occurrence can be moved or cancelled without changing the remaining series. Stop Series cancels future confirmed occurrences, retaining historical rows. An indefinite rule creates 180 days of appointments at first; use **Extend 180 Days** periodically to roll the booking window forward. This is **not yet an automated forever booking**; automate extension and add owner alerts before live use.

**Known limitations:** Series-wide rescheduling (this-and-future), drag-and-drop, client email delivery, bulk CSV onboarding/import, automated indefinite extension, recurring no-show/cancellation policies, and Google two-way sync are **not implemented**. Trainers may add only clients pending owner review; owner can approve after checking duplicates (automatic duplicate detection is not yet implemented). There is no in-app view of session audit history yet; endpoint `GET /api/sessions/{id}/history` is available. Existing client sessions must be entered manually and owners must review onboarding. A session's notes are stored in the database; consider privacy and retention policy before production.

**Important:** The database still uses startup `create_all` plus SQL constraints, not versioned Alembic migrations. Test from a **backed-up copy** before migrating real data. Do not use `docker compose down -v`.

### Upgrade safely on your Windows installation

1. Back up the PostgreSQL database separately, plus your current source (`backend/` and `frontend/`).
2. Extract this ZIP **outside** the active CRM directory to prevent nested `palehorse-crm/palehorse-crm` mistakes. Copy the inner `backend/` and `frontend/` files to the active `C:\Users\johna\PycharmProjects\palehorse-crm` directories. Keep your existing `.env`, `compose.yml`, and database volume.
3. From project root, `docker compose up -d --build --force-recreate api frontend`.
4. Confirm `docker compose logs --tail=100 api` and `docker compose logs --tail=100 frontend`; open `http://localhost:5173` and hard refresh. You should see **Client sessions** in the sidebar.
5. With a trainer account, submit a test existing client; with Noah's account approve; with trainer create one session and one recurring series, preview conflicts, move and cancel one occurrence, and inspect owner calendar.

**Validation:** Python syntax compiled. Frontend TypeScript build and a live Docker/PostgreSQL integration test were not completed in this environment. This is a development package, not a production release.
