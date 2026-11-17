# Pale Horse CRM v0.2.3 (development build)

Based on v0.2.2. Brand refresh uses the supplied official Pale Horse logo. Multi-day schedules allow 1–14 weekly slots in one creation request, different local times and lengths, weekly/biweekly/four-week intervals, finite or rolling 180-day sessions. Creation is atomic, preflights availability and existing bookings, rejects internal overlaps, and keeps existing per-session audit/history. Each weekday is maintained as an individual recurrence series after booking.

## Install
Back up PostgreSQL and your existing application first. Extract archive OUTSIDE the running project; copy only `frontend` and `backend` contents to their corresponding active directories, retaining `.env`, `compose.yml`, and DB volumes. Run `docker compose up -d --build --force-recreate api frontend`, inspect logs, and hard-refresh.

## Test
1. Verify login and existing prospects work. 2. In Client sessions choose approved client, tick Repeat, set Monday and Wednesday slots and future start date, preview. 3. Confirm the count, create booking, verify both calendars. 4. Move one occurrence. 5. Test overlapping slots and existing booked slot (must fail). 6. Test owner/trainer access separation.

## Limits
Open-ended schedules currently materialize 180 days at a time and must be extended manually. Series-wide rescheduling, holiday pause, CSV imports, and notifications remain future work. Backend/front-end require local Docker integration checks before production use. The original v0.2.2 client workflow remains intact.
