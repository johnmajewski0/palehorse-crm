# Pale Horse CRM v0.2.8 development package

Builds directly on v0.2.7. Separate from BearStrong.

## What's new
- **Classes & Blocks** in navigation and both home pages. Two choices: Group Class or Block Time.
- Owner can put Noah and Andy on the same recurring Wednesday/Saturday Powerlifting Group. Trainer can manage classes where they are a coach; a trainer can create an event for themselves, but only owner/admin can assign multiple coaches.
- Create a one-off event or repeating weekly event with several days/times. Schedule occurrences for a finite period up to one year; press **Extend Upcoming Dates** to materialize another 6 months for ongoing events.
- Maintain current class member list using approved clients; add/remove without recreating a class. Roster changes are logged and past logs are retained. This is a **membership roster**, not attendance tracking per occurrence.
- Cancel/restore or move one occurrence without changing other dates; change group coaches through owner controls.
- Same class appears on every assigned coach's personal calendar, and the gym-wide master calendar collapses repeated coach entries into a single class event. Free time subtracts group classes and blocks.
- **Today's Briefing** preview in Owner Operations lists due/overdue tasks and pending approval counts.

## Installation
1. Back up the live PostgreSQL database and the existing local source. Never overwrite `.env` or existing Compose config.
2. Extract the ZIP **outside** `C:\Users\johna\PycharmProjects\palehorse-crm`. Its root contains `backend/` and `frontend/`, **not a nested palehorse-crm folder**.
3. Copy the **contents** of its `backend` and `frontend` directories into the active project folders. Keep current database volumes.
4. Run `docker compose up -d --build --force-recreate api frontend` in the active project directory.
5. Check `docker compose logs --tail=100 api frontend`. Open `http://localhost:5173`, hard refresh.
6. Owner: create Powerlifting Group, add two coaches and Wed/Sat times, run Check Times, Save Event, then add an approved client. Confirm all assigned coach calendars show the event. Test an overlapping personal training booking is rejected.

## Safety / not yet finished
- **Morning email is not active.** The briefing preview exists in Owner Operations, but scheduling an outbound 7 AM email requires a verified Gmail send authorization, resilient scheduler, deduplication and production host URL. The CRM will NOT send a message just by installing this update.
- **Google / Apple calendar account integration is next**, not included. Existing read-only `.ics` subscriptions remain available and now include group slots; full OAuth and two-way syncing are not enabled.
- Current group membership is **not** a per-date attendance or RSVP list. Removing a client changes current membership and logs the action, not their participation history. Attendance can be added separately when needed.
- New event times are validated against existing group and individual bookings at creation, rescheduling, coach addition and reactivation. The live DB has not been load-tested for **all concurrent cross-module booking races**; do not represent the update as production-safe until integration and concurrent booking tests pass.
- **Indefinite** means retain a pattern with no end date and extend future dates in finite batches; there is no autonomous extension job yet. Do not promise all future sessions are prebooked.
- Automatic email reminders, individual occurrence coach replacement, series-wide edits, attendee RSVP, and room capacity are not implemented.
- Source uses automatic additive `Base.metadata.create_all` at startup for new tables. For production, convert schema changes to reviewed migrations. Do not delete volumes.
- Python syntax checks, TSX parser checks, and a local SQLite integration smoke test passed. React dependencies could not be installed in this sandbox (npm registry DNS unavailable), so **no full TypeScript/Vite or PostgreSQL integration build has been verified**.

## Next milestones
1. v0.2.9: Apple `.ics` invitations, Google Calendar subscriptions, external calendar privacy defaults and an explicit sync model.
2. v0.3.0: Noah's Workspace Gmail OAuth sending permission, opt-in daily briefing, tested one-email-per-day delivery, business-task links.
