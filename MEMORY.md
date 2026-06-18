---
type: project-memory
project: sherpa-check-in
last_updated: 2026-06-18
---

# MEMORY — sherpa-check-in

*Standing facts, preferences, and accumulated context. Long-lived — not "what I did yesterday" (that's STATUS.md). Update when you learn something worth keeping.*

---

## Purpose and scope

A lightweight client check-in, intake-tracking, and outbound-mail logging app for **The Tax Shelter**. Three audiences: walk-in clients (self-service iPad kiosk), office staff (desk intake + mail logging), and admins (dashboard). Its job is to notify the assigned tax professional when a client arrives or drops something off, and to keep a record of what was mailed out.

## Domain knowledge

- **Intake types** (desk): Walk-in, Drop-off, Email, Portal Upload, Mail-in. Kiosk check-ins are always type `Appointment`.
- **Due date** for desk intakes = today + `DEFAULT_INTAKE_DAYS` (default 7). An all-day ICS event is attached to the notification email.
- **Mail item types:** Original Return, Amended Return, E-file Authorization, Notice Response, Other. **Methods:** USPS, USPS Certified, FedEx, UPS, Hand-delivered, Portal Upload.
- **Slack** notification fires **only** for check-ins assigned to `Ken Lill` (`SLACK_NOTIFY_PROFESSIONAL`).
- 8 seeded professionals = real Tax Shelter staff (see `db.py seed_professionals`).

## User preferences discovered

- Ken wants to consolidate onto the **shared Supabase tax-suite database** rather than keep standalone per-app databases, and to reuse the central client list instead of re-typing client names.
- Data preservation is a hard requirement for the migration — the two Google Sheets (check-ins, mail) must keep working and no existing rows may be lost.
- Wants an eventual **portal-side event log** of check-ins/mailed items (explicitly deferred for a later conversation).

## Integrations and external systems

- **Office 365 SMTP** (`smtp.office365.com:587`, STARTTLS) for preparer notifications, with exponential-backoff retry (3 attempts).
- **Google Sheets** via `gspread` + a Google service account (`GOOGLE_SHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS` JSON). Appends rows to tabs `Check-Ins` and `Mail Log`. Best-effort on write; a background `worker.py` retries failures. **Replaced** the old Zapier→SharePoint webhooks (Feb 2026).
- **Slack** incoming webhook (`SLACK_WEBHOOK_URL`).
- Times are stored UTC, displayed in `TIMEZONE` (America/New_York).

## Gotchas and lessons learned

- The app currently runs on its **own Render Postgres (`sherpa-db`)**, *not* the shared tax-suite DB. Don't assume "Supabase" — verify the live `DATABASE_URL`.
- `init_db()` (CREATE TABLE IF NOT EXISTS ×3) and `seed_professionals()` run on **every boot**. Safe against a private DB; **dangerous** if naively pointed at the shared Django schema — must be neutered/guarded before any migration.
- Sync-status columns are named `excel_*` for historical reasons but now track **Google Sheets** state. `excel_sync.py` is dead Zapier code (unused). `render.yaml` is stale (still Zapier env vars).
- `client_name` is **free text** today — there is no link to the central client record.

## Data model highlights

This app's own tables (3): `checkin_events` (UUID PK), `professionals` (SERIAL PK, 8 staff), `mail_log` (UUID PK). None have `firm_id`; client identity is a typed string. Full schema lives in `db.py` — don't duplicate it here.

### Shared tax-suite DB (migration target) — verified 2026-06-18
- **Project:** Supabase `sherpa-1099-ats`, id `tmqypsbmswishqkngbrl` (the name is misleading — this is THE shared suite DB, Django-managed, RLS enabled, Postgres 17). Also serves tts-tax-app (`returns_*`), sherpa-portal (`portal_*`), sherpa-1099 (`forms_1099`/`recipients`/`filers`).
- **Firm:** The Tax Shelter `firm_id = dfe4540f-5ead-4030-9a3f-e5994837ae67` (723 clients, all active). A second firm "Dev Tax Firm" has 0 clients.
- **`clients_client`** (the backbone): `id uuid`, `name varchar`, `status varchar`, `firm_id uuid`, `created_at`, `updated_at`. **No email/phone here.**
- **`clients_entity`** (1026 rows): per-client entities (`client_id` FK) carrying `email`, `phone`, `legal_name`, `ein`, address, spouse fields, `entity_type`. Contact info lives here, and it's **not 1:1** with client.
- Existing logging infra worth knowing for the deferred portal log: `audit_auditentry` (firm-scoped, actor→auth_user) and `portal_accesslog`. NOTE: `activity_log` is **1099-side** (FK to filers/tenants), not the suite log.

### Two products share this project (verified 2026-06-18)
The `sherpa-1099-ats` project actually holds **two cleanly separable products**:
- **1099 SaaS**, multi-tenant, rooted at `tenants`/`tenant_id` (tables: tenants, tenant_members, operating_years, filers, recipients, forms_1099, submissions, filer_filing_status, tin_match_log, import_*, activity_log, user_profiles, column_aliases, ats_submissions).
- **Per-firm tax suite**, rooted at `firms_firm`/`firm_id` (clients_*, returns_*, portal_*, depreciation_*, diagnostics_*, documents_*, mappings_*, imports_trialbalance*, audit_auditentry, ai_help_helpquery).
- Verified there are **ZERO foreign keys crossing** between the two clusters; they share only the Django framework layer (auth_user, django_*). So a future split into separate Supabase projects is technically feasible.
- Ken's intent: **sherpa-1099 will be sold as a standalone SaaS** (to other firms as tenants) **as well as** used inside the suite. So a split is a real *future* project — but it is **decoupled** from the check-in work. Check-in is firm-scoped → belongs to the **suite** side; isolating it in a `checkin` schema keeps it split-friendly.
- A separate AI (chat app) proposed splitting the products first (backup + separation manifest, read-only). Sound as a Step 1 *for the split project*, but it is not a prerequisite for check-in and reverses Ken's documented shared-DB architecture — so we decoupled it.
