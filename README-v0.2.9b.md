# Pale Horse CRM v0.2.9b — Session navigation (development)

This is an incremental update based on v0.2.9a. Existing calendar exports, sessions, groups, permissions, and schemas are retained.

## New
- Client selector and Today / This Week / This Month / Last 30–Next 31 days filters
- Upcoming / Completed / All status selector
- Compact session actions: Reschedule, Add to Calendar, More (complete, cancel, no show)
- Server-scoped pagination (30 per page), respecting trainer permissions

## Install
Back up your database and source. Extract into a temporary directory and copy `backend/` and `frontend/` contents into your existing project. Keep your local `.env` and Compose configuration. Run `docker compose up -d --build --force-recreate api frontend`.

## Test
Sign in as a trainer and open Client Sessions. Check This Week + Upcoming, select one client, switch to This Month, click Show 30 More if present, and check More actions. Confirm a trainer cannot query another trainer's sessions.

## Next milestone: trainer invitations
Owner-only Trainer onboarding screen: name, email, optional phone; Send Invite using Noah's Google Workspace Gmail after OAuth setup. Single-use expiring invitation, role selected by server, password set by trainer, resend/revoke, audit events. Never send passwords over email. This design is not implemented in v0.2.9b.

## Verification
Python syntax compilation and TSX parsing as available; live Docker/PostgreSQL and full TypeScript build still need local verification.
