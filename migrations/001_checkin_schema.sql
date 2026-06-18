-- migrations/001_checkin_schema.sql
-- Phase 1: Sherpa Check-In tables, isolated in the `checkin` schema of the shared
-- Supabase DB (project sherpa-1099-ats / tmqypsbmswishqkngbrl).
--
-- Mirrors the original db.py schema EXACTLY, including the legacy excel_* column
-- names (which now track Google Sheets sync status — renaming is a separate cleanup).
-- Tables are owned by `postgres`; the least-privilege `checkin_app` role (the app's
-- DB user) gets DML access via grants + an RLS policy. RLS is enabled for consistency
-- with the rest of the database; the `checkin` schema is NOT exposed via the Data API.
--
-- Idempotent. Already applied to production on 2026-06-18 via the Supabase MCP.

CREATE SCHEMA IF NOT EXISTS checkin;

CREATE TABLE IF NOT EXISTS checkin.checkin_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name TEXT NOT NULL,
    professional TEXT NOT NULL,
    professional_id INTEGER,
    client_email TEXT,
    client_phone TEXT,
    intake_type TEXT DEFAULT 'Appointment',
    notes TEXT,
    handled BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    email_error TEXT,
    excel_write_status TEXT DEFAULT 'pending',
    excel_last_error TEXT,
    excel_written_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS checkin.professionals (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS checkin.mail_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name TEXT NOT NULL,
    professional_id INTEGER NOT NULL,
    professional_name TEXT,
    item_type TEXT NOT NULL,
    method TEXT NOT NULL,
    tracking_number TEXT,
    sent_by TEXT,
    notes TEXT,
    excel_write_status TEXT DEFAULT 'pending',
    excel_last_error TEXT,
    excel_written_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE checkin.checkin_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkin.professionals  ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkin.mail_log       ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS checkin_app_all ON checkin.checkin_events;
DROP POLICY IF EXISTS checkin_app_all ON checkin.professionals;
DROP POLICY IF EXISTS checkin_app_all ON checkin.mail_log;
CREATE POLICY checkin_app_all ON checkin.checkin_events FOR ALL TO checkin_app USING (true) WITH CHECK (true);
CREATE POLICY checkin_app_all ON checkin.professionals  FOR ALL TO checkin_app USING (true) WITH CHECK (true);
CREATE POLICY checkin_app_all ON checkin.mail_log       FOR ALL TO checkin_app USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA checkin TO checkin_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA checkin TO checkin_app;
