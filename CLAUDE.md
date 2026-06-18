# Sherpa Check-In - CLAUDE.md

## Project Overview
**Name:** Sherpa Check-In (Client Kiosk & Intake Tracker)
**Port:** 8001
**Stack:** Python, Flask, PostgreSQL, Jinja2, Gunicorn
**GitHub:** https://github.com/klill6506/sherpa-check-in
**Production URL:** Deployed on Render.com
**Status:** LIVE

## What This App Does
A client check-in, intake tracking, and outbound mail logging system for The Tax Shelter. Serves three audiences: walk-in clients (self-service kiosk), office staff (intake & mail logging), and admins (dashboard & management).

- **Client Kiosk** -- Self-service tablet check-in for walk-in clients; notifies the assigned tax professional via email
- **Staff Intake Portal** -- Log non-appointment intakes (Walk-in, Drop-off, Email, Portal Upload, Mail-in) with auto-calculated due dates and ICS calendar attachments
- **Outbound Mail Log** -- Track documents sent to clients with item type, shipping method, and tracking numbers
- **Admin Dashboard** -- View all check-ins, manage professionals, resend failed emails, retry failed Google Sheets syncs
- **Google Sheets Sync** -- All check-ins and mail entries sync directly to Google Sheets (tabs `Check-Ins` and `Mail Log`) via a gspread service account. Replaced the old Zapier→SharePoint webhooks on 2026-02-28.
- **Email Notifications** -- SMTP via Office 365 with exponential backoff retry (up to 3 attempts)
- **Slack** -- Posts a message when a client checks in for Ken Lill

## Current State / What I Was Working On
> For the live state, see **STATUS.md** (updated every session). This section is a stable high-level summary only.

### What's Working:
- Client kiosk check-in with auto-refresh confirmation page
- Staff intake form with 5 intake types and due date calculation
- Outbound mail logging with tracking numbers
- Email notifications to professionals (SMTP via Office 365)
- ICS calendar attachments for intake due dates
- Direct Google Sheets sync (check-ins + mail), best-effort with a retry worker
- Slack notification for Ken Lill check-ins
- Admin dashboard with resend/retry actions
- Professional management (CRUD) with 8 seeded Tax Shelter staff
- Custom logo upload
- Deployed on Render.com (web service + background worker + dedicated Render Postgres `sherpa-db`)

### What's Not Working / TODO:
- [ ] Uses Flask instead of FastAPI (deviation from Sherpa standards)
- [ ] Hand-written CSS instead of Tailwind CDN
- [ ] Red (#BB0000) used as primary color -- conflicts with Sherpa UI standard (should be blue)
- [ ] Staff portal (/desk routes) has no authentication
- [ ] No README.md in the repo
- [ ] Dead code: `excel_sync.py` (old Zapier module, unused); `render.yaml` still references Zapier env vars
- [ ] DB runs on a standalone Render Postgres, not the shared Supabase suite DB (migration under discussion — see DECISIONS.md)

## Key Files
| File | Purpose |
|------|---------|
| `app.py` | Main Flask application (585 lines) -- all routes and business logic |
| `db.py` | PostgreSQL database layer -- schema init, CRUD operations (sync-status columns named `excel_*` for historical reasons) |
| `sheets_sync.py` | **Active** Google Sheets sync module (gspread + service account) |
| `excel_sync.py` | **Dead code** -- old Zapier webhook module, no longer imported |
| `worker.py` | Background worker for retrying failed Google Sheets syncs |
| `requirements.txt` | Dependencies: flask, python-dotenv, gunicorn, psycopg2-binary, requests, pytz, gspread |
| `render.yaml` | Render.com deployment blueprint (web + worker + database) |
| `run.bat` | Windows launch script (creates venv, installs deps, starts app) |
| `templates/` | Jinja2 HTML templates (12 files) |

## Database
- **Engine:** PostgreSQL (migrated from SQLite)
- **Connection:** `DATABASE_URL` environment variable
- **Key tables:** `checkin_events` (client check-ins & intakes), `professionals` (tax staff), `mail_log` (outbound mail tracking)
- **Render database:** `sherpa-db` (free plan)

## Running the App
```powershell
cd "T:\sherpa-check-in"

# Option 1: Use the batch file
.\run.bat

# Option 2: Manual
pip install -r requirements.txt
python app.py
# Opens at http://localhost:8001
```

## Environment Variables
Required in `.env` (see `.env.example`):
- `DATABASE_URL` -- PostgreSQL connection string
- `SECRET_KEY` -- Flask session secret
- `ADMIN_PASSWORD` -- Admin panel password
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`, `USE_TLS` -- Email config
- `GOOGLE_SHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS` (service-account JSON) -- Google Sheets sync
- `SLACK_WEBHOOK_URL` -- Slack check-in notifications
- `TIMEZONE` -- Default timezone (e.g., America/New_York)
- `DEFAULT_INTAKE_DAYS`, `SHEETS_RETRY_INTERVAL` -- intake/worker tuning

## Notes
- This app uses **Flask** (not FastAPI) -- predates the Sherpa standard stack
- Uses **PostgreSQL** instead of SQLite (justified by Render.com deployment)
- The client kiosk is designed for iPad use with Apple mobile web app meta tags
- Background worker runs as a separate Render.com service
- Companion docs: **MEMORY.md** (standing facts incl. the shared-DB schema), **STATUS.md** (live state), **DECISIONS.md** (architectural choices)
