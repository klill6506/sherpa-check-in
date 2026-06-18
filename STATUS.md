---
type: project-status
project: sherpa-check-in
last_updated: 2026-06-18
---

# STATUS — sherpa-check-in

*The freshest file. Answers "where am I on this project?" Updated at the end of every substantive session.*

---

## Current state

Live in production on Render.com (web service + background worker + a **dedicated Render Postgres `sherpa-db`** — NOT the shared tax-suite database). All core flows work: kiosk check-in, staff desk intake (5 intake types + ICS due dates), outbound mail log, Office 365 email notifications, Slack ping for Ken's check-ins, and direct **Google Sheets** sync (two tabs: `Check-Ins`, `Mail Log`). As of 2026-02-28 the old Zapier→SharePoint sync was fully replaced by gspread/service-account Google Sheets sync.

We are currently **brainstorming** (not yet executing) a migration of this app's database from the standalone Render Postgres to the **shared Supabase tax-suite DB**, plus wiring client name lookups against the central `clients_client` table. No migration code written yet.

## In progress

- [ ] Migration design **approved** (see `docs/superpowers/specs/2026-06-18-checkin-supabase-migration-design.md`). Ready to execute Phase 1.

## Next up

1. **Phase 1 — DB migration** (a CC kickoff prompt has been prepared): create `checkin` schema in Supabase, copy all rows from Render, repoint `DATABASE_URL`, keep Google Sheets sync intact, keep old Render DB as rollback. Behavior unchanged.
2. **Phase 2** — receptionist client lookup (`/api/clients`), create-new-client into `clients_client`/`clients_entity`, link `client_id` on check-in/mail, retire the kiosk. (Backup gate before first write to shared tables.)
3. (Deferred) Portal-side event log — extend existing `audit_auditentry` / `portal_accesslog`.
4. (Separate future project) Split the 1099 SaaS out of the suite into its own Supabase project — decoupled from check-in.

## Blocked / waiting on

- For Phase 1 execution, Ken provides: the Supabase session-pooler connection string for this app (ideally a dedicated `checkin_app` role) and the old Render external `DATABASE_URL`.

## Known issues

- Uses Flask + raw psycopg2 (predates the Sherpa FastAPI/Django standard).
- `/desk/*` staff routes have **no authentication** (only `/admin` is password-gated).
- Hand-written CSS; red (#BB0000) primary color conflicts with the suite's blue UI standard.
- **Stale/dead code:** `excel_sync.py` (old Zapier module) is unused — nothing imports it. `render.yaml` still declares `ZAPIER_*` env vars and a `sherpa-db` Render database; it has not been updated for the Google Sheets switch.
- `db.py` still names the sync-tracking columns `excel_write_status` / `excel_last_error` / `excel_written_at` even though the target is now Google Sheets (naming is misleading, not broken).
- `init_db()` and `seed_professionals()` run on **every** app boot — fine against a dedicated DB, but a hazard if pointed at the shared schema (see DECISIONS).
- No README.md.

## Recent wins

- 2026-02-28: Replaced Zapier/SharePoint webhook sync with direct Google Sheets sync via gspread service account.
- 2026-02-18: Added Slack notification (Ken's check-ins) and included client email in admin resend.
- 2026-01-19: Migrated from SQLite to Postgres; seeded the 8 real Tax Shelter staff.

## Last session recap

*2026-06-18* — Audited the actual codebase and the shared Supabase DB to prep for the migration brainstorm. Confirmed the app runs on its own Render Postgres, not the shared DB. Discovered the shared tax-suite database is the Supabase project misleadingly named **`sherpa-1099-ats`** (id `tmqypsbmswishqkngbrl`): it holds `clients_client` (723 clients), `firms_firm`, `returns_*` (tts-tax-app), and `portal_*` (sherpa-portal), all Django-managed with RLS on. The Tax Shelter firm_id is `dfe4540f-5ead-4030-9a3f-e5994837ae67`. Contact info (email/phone) lives on `clients_entity`, not `clients_client`. Filled in the four memory files; migration design still pending Ken's decisions.
