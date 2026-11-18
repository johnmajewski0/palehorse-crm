# Pale Horse CRM — v0.2.5b corrected (Prospect Interests)

This ZIP **replaces** the earlier v0.2.5b UX/reasons package. It includes the owner dashboard and permanent Clients & Imports navigation from that version, together with the corrected **New Prospect → Interested in** control.

## What changed

- **Interested in** on the New Prospect form is a validated shared dropdown.
- **Other — add new interest…** allows an owner/admin to create an offering. A duplicate name (ignoring case and extra spaces) reuses the existing entry.
- New types live in `crm_interest_types`, shared by the New Prospect form, owner prospect editing, and the prospect pipeline interest filter. The pipeline also displays the canonical label.
- The backend checks the selected interest against active catalog entries; it does not trust arbitrary submitted text.
- Existing prospect interest values are preserved and automatically added to the list on startup (up to 80 characters). Existing lead rows are not rewritten.
- The **availability exception reason** field has been restored to its original free-text behavior; this was mistakenly changed in the first v0.2.5b. If an earlier release created `crm_availability_reasons`, that unused table is deliberately left alone to avoid data destruction.
- All prior scheduling, client import, owner dashboard, and frequency changes remain in the project source.

Initial interest options: Personal training, Powerlifting coaching, Strength & conditioning, General fitness, Assessment / consultation, Nutrition coaching, Group training, Online coaching. These are editable through the **Other** workflow; no manual database editing is required to add an option.

## Install (Windows PowerShell)

1. **Back up PostgreSQL and the project**. Stop if your backup fails.
2. Extract this ZIP to a temporary folder **outside** `C:\Users\johna\PycharmProjects\palehorse-crm`.
3. Copy the **contents** of `backend` and `frontend` from the ZIP into the matching folders in the active project. Do not replace your existing `.env`, Compose file, PostgreSQL volume, or secrets.
4. From the active project root, run:

```powershell
cd C:\Users\johna\PycharmProjects\palehorse-crm
docker compose up -d --build --force-recreate api frontend
docker compose logs --tail=50 api
docker compose logs --tail=50 frontend
```

5. Sign in as Noah/owner, go to **Prospect pipeline → New Prospect**. The **Interested in** field should be a dropdown. Choose **Other**, enter a new offering, save the prospect, then create another prospect and verify that the new offering appears. Open an existing prospect and verify that Noah can update its interest. Check the **All interests** pipeline filter.

## Validation / limitations

- Backend passed Python `py_compile` syntax checks.
- All six TSX source files passed TypeScript transpiler parse diagnostics.
- Full React type-check and a running PostgreSQL/Docker integration test are **not** verified in this environment.
- Do not treat this development snapshot as a production release until the local end-to-end test passes.
