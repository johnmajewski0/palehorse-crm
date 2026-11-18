# Pale Horse CRM v0.2.9 — Calendar handoff (development)

Built from the v0.2.8 Classes & Daily Operations project. Separate from BearStrong.

## What changed (simple first step)
- In **Client sessions**, a confirmed appointment has **ADD TO CALENDAR**, which downloads a privacy-minimized `.ics` event that can be opened in Apple Calendar, Google Calendar (via Import), Outlook or similar software.
- In **Classes & blocks**, each confirmed class occurrence has **ADD TO CALENDAR**. No group membership/contact data is embedded in the file.
- **My Calendar / Master Calendar** now enables the owner's own calendar export and private subscription alongside trainers'. The owner gets **their own appointments**, never a gym-wide personal-feed export.
- Updated in-app instructions for Google Calendar and Apple Calendar subscription setup.
- Single-event exports are authenticated and restricted to the assigned coach or owner/admin. Unconfirmed/cancelled events do not export. No new tables or additional third-party packages.
- Event files contain title, UTC start/end, stable ID, and generic description. No client email, phone, medical details or member roster.

## Install
1. Back up PostgreSQL and current application code.
2. Extract the ZIP to a folder **outside** `C:\Users\johna\PycharmProjects\palehorse-crm`.
3. Copy the ZIP's `backend/` and `frontend/` **contents** into those folders in the active project. Preserve `.env`, Compose config and database volume.
4. Run `docker compose up -d --build --force-recreate api frontend`.
5. Check `docker compose logs --tail=80 api frontend` and reload `http://localhost:5173`.
6. Create a test confirmed client session and download its calendar invitation. Open the file with Apple Calendar; or in Google Calendar on a computer go to Settings → Import & export → Import. Check time and duration in Eastern Time.
7. On the Classes & Blocks screen, select a class, download one occurrence, and check its time. Test that a trainer who is **not** a coach cannot export another trainer's class.

## Important limitations
- **No Google or Apple account OAuth in this update.** The `.ics` downloads are single-event snapshots, not automatic live updates to an imported event.
- **No client self-service portal or automated email delivery yet.** Coaches can download/share invitations manually, only through an appropriate secure channel.
- Existing personal private calendar subscription links are read-only, created/revoked from the calendar screen. They must be served from a publicly reachable HTTPS domain for Google/Apple to fetch them; localhost cannot be subscribed to from Google's servers. They may refresh with provider-controlled delays and may remain cached after revocation. Treat links like passwords.
- To add a Google subscription: on Google Calendar desktop → Other calendars → + → From URL. Apple Calendar on Mac: File → New Calendar Subscription. iPhone: Calendars → Add Calendar → Add Subscription Calendar.
- Owner Gmail send authorization, automated booking invitations, client RSVP, and two-way provider sync remain **future milestones**.
- Development environment is not production-hardened. Existing automatic database table creation still needs reviewed migrations prior to deployment.

## Verification
- Python syntax compilation passed.
- All TSX files parsed via the global TypeScript transpiler with zero syntax diagnostics.
- Single event ICS UTC start/end, escaping, structure and CRLF verified by a targeted smoke test.
- No full npm dependency build, live Docker/PostgreSQL integration, or provider end-to-end verification in this environment.
