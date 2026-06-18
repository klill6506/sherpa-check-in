# Sherpa Check-In → Shared Supabase Migration — Design Spec

**Date:** 2026-06-18
**Status:** Approved (direction). Phase 1 ready to execute; Phase 2 sketched.
**Author:** Ken Lill + Claude (brainstorm session)

---

## Goal

Move the Sherpa Check-In app off its standalone Render Postgres (`sherpa-db`) and onto the **shared tax-suite Supabase database**, so that the front desk can look up clients from the central client list (`clients_client`) instead of re-typing names — without losing any existing data and without disrupting the Google Sheets sync.

## Verified context (2026-06-18)

- **Shared DB** = Supabase project `sherpa-1099-ats`, ref `tmqypsbmswishqkngbrl`, region `us-east-1`, Postgres 17. Django-managed, RLS on. Connect via the **session-mode pooler** (port 5432, host `aws-0-us-east-1.pooler.supabase.com`, user `postgres.tmqypsbmswishqkngbrl`) — NOT transaction mode (6543), and the direct host is IPv6-only.
- **Firm:** The Tax Shelter `firm_id = dfe4540f-5ead-4030-9a3f-e5994837ae67` (723 active clients).
- `clients_client` = `id uuid, name, status, firm_id, created_at, updated_at` (no contact info). Email/phone live on `clients_entity` (FK `client_id`, not 1:1).
- This app today runs on Render `sherpa-db`, with 3 tables: `checkin_events` (uuid), `professionals` (serial, 8 staff), `mail_log` (uuid). No `firm_id`; client name is free text.
- The Supabase project actually contains **two products** that are cleanly separable (verified: **zero foreign keys cross** between the `tenants`-rooted 1099 SaaS cluster and the `firms_firm`-rooted suite cluster; they share only the Django framework layer). A future product split is a **separate, deliberately-decoupled project** (sherpa-1099 will be sold standalone). Check-in is firm-scoped and belongs to the **suite** side; isolating it in its own schema keeps it split-friendly.

## Decisions

1. This app's tables go in a dedicated **`checkin`** Postgres schema, never `public`. (Avoids collision with Django tables — e.g. portal staff naming — and keeps the app trivially separable.)
2. The app reads `public.clients_client` **cross-schema, read-only** (Phase 2).
3. **Copy all** existing rows from Render → Supabase, preserving UUIDs and the `professionals` id sequence.
4. **Phase the work.** Phase 1 = pure infra move, behavior unchanged, reversible. Phase 2 = receptionist lookup + create-client + retire kiosk.
5. **Decoupled** from the 1099/suite product split (a real future project, tracked separately).
6. Take a verified, encrypted, gitignored **backup before any write** to the shared production DB.

---

## Phase 1 — Database migration (infrastructure only, behavior unchanged)

**Prerequisites (Ken provides at execution):**
- `NEW_DATABASE_URL` — Supabase session-pooler connection string for this app. **Recommended:** a dedicated least-privilege role `checkin_app` that owns the `checkin` schema and has only `SELECT` on `public.clients_client` / `public.clients_entity`. **Fallback:** reuse the suite's existing `postgres.<ref>` pooler string.
- `OLD_DATABASE_URL` — the Render external connection string for `sherpa-db` (for the one-time copy).
- Confirmation that the Google Sheets (`GOOGLE_SHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS`), SMTP, and `SLACK_WEBHOOK_URL` env vars carry over to the same web/worker services.

**Steps:**

0. **Backup first.** `pg_dump -Fc` (client v17+) of the Supabase DB to a timestamped file in a gitignored, encrypted location outside the repo. Confirm size is non-trivial. (Phase 1 only adds an isolated schema, but back up before any production DDL as a matter of discipline.)

1. **Provision schema + tables** via a committed `migrations/001_checkin_schema.sql`:
   - `CREATE SCHEMA IF NOT EXISTS checkin;`
   - Recreate `checkin.checkin_events`, `checkin.professionals`, `checkin.mail_log` with the **exact** columns/types/defaults from `db.py` (keep `gen_random_uuid()`, the `professionals` SERIAL, and the existing `excel_*` sync-status column names — renaming is a separate cleanup, out of scope).
   - If using the dedicated role: `ALTER SCHEMA checkin OWNER TO checkin_app;` + appropriate grants.
   - Apply once via psql/Supabase. Idempotent. **Do not run any DDL against `public`.**

2. **`db.py` changes:**
   - Add connection option so unqualified table names resolve to the new schema and `public` stays reachable:
     `psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, options='-c search_path=checkin,public')`
   - **Stop boot-time DDL/seed.** Guard the module-load calls to `init_db()` and `seed_professionals()` behind `if os.environ.get('RUN_DB_INIT') == '1':` (default off in production). Schema/seed are handled by the migration + data copy; this prevents accidental DDL/seeding against the shared DB while keeping the functions usable for local dev.

3. **Data copy** — committed one-shot `migrate_data.py`:
   - Reads from `OLD_DATABASE_URL`, writes to `NEW_DATABASE_URL` (search_path=checkin).
   - Order: `professionals` (preserve `id`) → `checkin_events` → `mail_log` (preserve UUIDs + all columns incl. `excel_*` and timestamps).
   - Idempotent inserts: `INSERT ... ON CONFLICT (id) DO NOTHING`.
   - After professionals: reset the sequence — `SELECT setval(pg_get_serial_sequence('checkin.professionals','id'), (SELECT COALESCE(MAX(id),1) FROM checkin.professionals));`
   - Print before/after row counts per table; assert new ≥ old.

4. **Repoint + clean up:**
   - Point Render's `DATABASE_URL` at `NEW_DATABASE_URL`.
   - Update `render.yaml`: remove the `databases:` (`sherpa-db`) block and its `fromDatabase` wiring; set `DATABASE_URL` as a `sync: false` secret; remove the stale `ZAPIER_*` vars; add `GOOGLE_SHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS`, `SLACK_WEBHOOK_URL`, `SHEETS_RETRY_INTERVAL`, `DEFAULT_INTAKE_DAYS`. Keep the `web` and `worker` services.
   - **Keep the old Render `sherpa-db` alive** as the rollback path until verification passes. Delete nothing.

5. **Verify:**
   - Per-table row counts match old vs new.
   - Run the app locally against Supabase; perform a test check-in and a test mail entry; confirm rows land in `checkin.*` **and** the Google Sheets sync fires.
   - Confirm the worker connects and drains pending syncs.
   - After production cutover: live smoke test (one kiosk check-in, one desk intake, one mail entry).

6. **Rollback:** flip `DATABASE_URL` back to the Render string. The old DB is untouched.

**Security note:** the `checkin` schema is not exposed through Supabase's API (only `public` is exposed by default), so these tables are unreachable via the anon key — cleaner than the standalone DB.

**Out of scope for Phase 1 (no behavior change):** the `/client` kiosk stays as-is; no `firm_id` added yet; no client linkage yet; dead `excel_sync.py` left in place (optional later cleanup, requires Ken's OK to delete).

---

## Phase 2 — Receptionist check-in: client lookup + create (next session)

- Add read-only `GET /api/clients?q=` → `SELECT id, name FROM public.clients_client WHERE firm_id = <TTS> AND name ILIKE '%'||:q||'%' ORDER BY name LIMIT 20`.
- Add nullable `client_id uuid` to `checkin.checkin_events` and `checkin.mail_log`; store it when a match is chosen.
- Receptionist intake UI: typeahead against the endpoint; **"Create new client"** captures name + basic contact, writing `public.clients_client` (id, name, status='active', firm_id, timestamps) and a `public.clients_entity` row for email/phone. **Must match Django model NOT-NULL/defaults — verify the model constraints before inserting.** This is the first *write* to shared suite tables → requires the backup gate (step 0) first.
- Retire the self-service `/client` kiosk route in favor of receptionist-driven intake.
- Add `firm_id` (default The Tax Shelter) to the check-in/mail tables for multi-tenant alignment.

## Deferred — portal-side event log

The shared DB already has `audit_auditentry` (firm-scoped, actor → auth_user) and `portal_accesslog`. (`activity_log` is 1099-side, not the suite log.) When this conversation happens, extend existing infra rather than invent a new log.
