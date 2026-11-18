# v0.2.10 — Trainer-only mobile experience (development)

## Behavior
- Trainer role and screen <=700px: streamlined Today, Calendar, Clients, More interface.
- Trainer on desktop (>700px): existing full trainer CRM, unchanged.
- Owner/admin on any screen: existing full CRM, unchanged.
- On a phone, More > Open full CRM provides an optional manual override until the next login.
- Same authenticated backend and trainer-scope checks. No separate accounts or app.
- No offline booking or automatic push notifications; mobile view requires connectivity.

## Install
Backup current source and database. Copy `frontend/src` from this package into your active `frontend/src`. No database or backend changes required. Rebuild: `docker compose up -d --build --force-recreate frontend`.

## Test
1. Sign in as a trainer on desktop: verify full sidebar and all screens.
2. Use browser device emulation at iPhone/Android widths <=700px: verify four-tab layout.
3. Sign in as Noah at phone width: verify full owner CRM remains.
4. Confirm mobile events list and assigned client data are trainer scoped.
5. Test logout and that protected endpoints reject cross-trainer access.

This update is a development build pending local React/TypeScript and Docker integration testing.
