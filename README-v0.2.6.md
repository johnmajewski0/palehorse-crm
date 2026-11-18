# Pale Horse CRM v0.2.6 — Owner Operations (development)

Built on the **corrected v0.2.5b** package. This is a standalone update; earlier v0.2.5b package does not need to be installed separately.

## What's new
- **Owner Operations** appears only for `owner`/`admin` users, both in the sidebar and Owner Home quick actions.
- Two clearly separated businesses: **Pale Horse Barbell** and **Crucible Wellness**. Crucible Wellness tasks are *business administration only*; they do not create gym prospects, clients, appointments, or healthcare records.
- Create callbacks, follow-ups, supplier/order tasks, admin tasks, and other tasks, optionally with contact name, phone, email, due date and business notes.
- Filter by business; mark complete or reopen; retain event history and append follow-up notes.
- All `/api/owner/tasks` endpoints enforce owner/admin access on the server. Trainers cannot access these records. CSRF protection remains in place.
- No destructive task deletion workflow. Existing data and prior CRM functions are preserved.

## Installation
1. Back up your project and PostgreSQL database **before deploying**.
2. Extract this ZIP **outside** your working project. The ZIP contains top-level `backend` and `frontend` folders (not another nested `palehorse-crm`).
3. Copy the *contents* of these folders into `C:\Users\johna\PycharmProjects\palehorse-crm\backend` and `...\frontend`. Keep existing `.env`, Compose files, and database volume.
4. In PowerShell:

```powershell
cd C:\Users\johna\PycharmProjects\palehorse-crm
docker compose up -d --build --force-recreate api frontend
docker compose logs --tail=70 api
docker compose logs --tail=70 frontend
```

5. Sign in as an owner: verify **Owner Operations**, add a **Crucible Wellness** callback with phone and date, mark it complete, then reopen and add a note. Sign in as a trainer: verify the sidebar entry is absent and `/api/owner/tasks` responds **403**.

## Limitations and next steps
- This module manages **non-clinical business follow-ups only**. Do not enter protected health information, peptide regimens, prescriptions or treatment notes.
- No SMS/email notifications, integrations, recurring owner tasks, or access control beyond the current owner/admin roles yet.
- Python syntax and TSX parsing verified. Full React build and live Docker/PostgreSQL test are pending local validation. The backend presently uses `Base.metadata.create_all` rather than a versioned Alembic migration; **back up the database** first.
