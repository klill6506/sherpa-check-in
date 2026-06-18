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

- [x] **Phase 1 — DB migration: COMPLETE (2026-06-18).** App is live on the shared Supabase DB. Data migrated (8 professionals, 2554 checkin_events, 303 mail_log; IDs/sequence preserved). Cutover done: Render web service `DATABASE_URL` → checkin_app Supabase pooler string (`aws-1-us-east-1.pooler.supabase.com`; there is **no** worker service despite render.yaml's old block). Smoke-tested end-to-end: a live check-in and a live mail entry both wrote to Supabase AND synced to Google Sheets (`excel_write_status=success`) with email firing. `render.yaml` updated so `DATABASE_URL` is `sync:false` (a blueprint sync can't revert the cutover). Local venv rebuilt on Python 3.12.

## Done-but-pending-confidence

- Old Render `sherpa-db` still running as **rollback** (instant revert = point `DATABASE_URL` back). Retire it (and the exposed old password) after a few days of confidence — `render.yaml` keeps the block until then.
- Test rows deleted from Supabase 2026-06-18 (counts back to 2554 check-ins / 303 mail). They remain in the Google Sheet (sync is append-only) — delete manually there if desired.

## Next up

1. **Finish Phase 1:** Ken runs `migrate_data.py` (needs `OLD_DATABASE_URL` = Render external + `NEW_DATABASE_URL` = checkin_app pooler string) → verify row counts → set Render `DATABASE_URL` to the Supabase string → smoke-test (check-in + mail + Sheets sync). Keep old Render `sherpa-db` as rollback. Then clean `render.yaml`.
2. **Phase 2** — receptionist client lookup (`/api/clients`), create-new-client into `clients_client`/`clients_entity`, link `client_id` on check-in/mail, retire the kiosk. (Backup gate before first write to shared tables.) Client reads via a `postgres`-owned, firm-scoped, SSN-excluding view (no BYPASSRLS).
3. (Deferred) Portal-side event log — extend existing `audit_auditentry` / `portal_accesslog`.
4. (Separate future project) Split the 1099 SaaS out of the suite into its own Supabase project — decoupled from check-in.

## Blocked / waiting on

- To finish Phase 1, Ken provides (kept out of chat): the old Render external `DATABASE_URL` and the `checkin_app` Supabase pooler string — both set as env vars to run `migrate_data.py`. `render.yaml` intentionally NOT yet changed (avoids a push triggering Render to repoint/drop the old DB before the copy is verified).

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
