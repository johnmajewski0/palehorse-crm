# Pale Horse CRM v0.2.7 — Owner tasks, archive and Gmail task import

## What changed
- Owner Operations now has **Active Tasks** and **Archive** tabs.
- Completed tasks remain in Active Tasks for 7 full days after completion, then appear in Archive automatically when the page reloads. **No background scheduler is needed; no tasks are deleted.**
- Archived tasks can be **Reopened**, restoring them to To Do while retaining all previous events and notes.
- Existing completed tasks receive their previous `updated_at` timestamp as an approximate completion date in an additive database migration.
- **From Gmail** connects the account owner through Google OAuth and lets Noah select a message from his latest 15 inbox emails, select the business, set an optional due date, and click Create Task.
- Imported tasks use the email subject and sender name/email only. They do **not** copy message bodies or attachments. Duplicate imports are blocked by Google message ID. Gmail is accessed only when the owner explicitly requests it.

## Install
1. Back up the existing PostgreSQL volume/database and project files.
2. Extract this ZIP into a **temporary folder outside** the project directory.
3. Copy `backend/` and `frontend/` contents into the active project at `C:\Users\johna\PycharmProjects\palehorse-crm`, preserving `.env` and `docker-compose.yml`.
4. From the project directory: `docker compose up -d --build --force-recreate api frontend`.
5. Inspect `docker compose logs --tail=80 api frontend`; sign in and open **Owner Operations**.

## Gmail OAuth configuration (only when you choose to connect Noah)
Gmail is **not connected just by installing this ZIP**.

- Create a Google Cloud project owned/controlled by Pale Horse, enable the Gmail API, and configure an OAuth consent screen. Prefer an **Internal** app if the Google Workspace configuration and policies permit.
- Create an OAuth **Web application** client and authorize redirect URI `http://localhost:5173/api/owner/gmail/callback` for local testing. Configure a separate HTTPS redirect URI for production later.
- Add the following to the **root** project `.env` (do **not** commit):
  - `GOOGLE_OAUTH_CLIENT_ID=...`
  - `GOOGLE_OAUTH_CLIENT_SECRET=...`
  - `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5173/api/owner/gmail/callback`
  - `GOOGLE_TOKEN_ENCRYPTION_KEY=...` (generate using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
  - `GOOGLE_ALLOWED_EMAIL=noah@palehorsebarbell.com`
- Ensure the **api** service receives these variables via `environment:` or `env_file:` in Docker Compose. An ordinary Compose `.env` file does not automatically inject its variables into a container.
- **Never commit** secrets, refresh tokens, or credentials. Keep the Fernet key secure and backed up; changing it will require reconnection.
- In CRM, sign in as `noah@palehorsebarbell.com`, open **Owner Operations → From Gmail → Connect Gmail**, approve Google's consent prompt, and load emails.
- The `gmail.readonly` permission is a **restricted scope** and Google may require OAuth app verification or Workspace admin approval. Don't enable this for general public use until the applicable requirements have been handled.

## Safeguards and limits
- `Owner Operations` is still restricted to owners/admins. Gmail connection and Gmail import are restricted further to the designated Gmail account owner.
- Gmail does not automatically ingest all email or message bodies. Owner explicitly selects messages to turn into tasks.
- Importing an email does **not** change the email itself (no Gmail deletion, labels, or mark-as-read changes).
- Archived tasks remain in the DB with notes and audit events; task status changes are logged.
- Use this only for ordinary business admin correspondence. Do not import protected medical details or sensitive treatment information into the gym CRM.
- The feature is locally **code-ready**, but requires real Google OAuth credentials and local Docker/PostgreSQL testing; it is not a verified production integration.
