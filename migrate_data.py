"""
One-shot data migration: copy Sherpa Check-In data from the old Render Postgres
into the `checkin` schema of the shared Supabase DB. Idempotent and non-destructive.

Usage (PowerShell):
    $env:OLD_DATABASE_URL = "postgresql://...render external connection string..."
    $env:NEW_DATABASE_URL = "postgresql://checkin_app.tmqypsbmswishqkngbrl:<pw>@<pooler-host>:5432/postgres"
    python migrate_data.py

Reads from OLD (tables in public), writes to NEW (checkin schema). Preserves
ids/UUIDs, resets the professionals sequence, and prints before/after row counts.
Safe to re-run: INSERT ... ON CONFLICT (id) DO NOTHING.
"""

import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

OLD_URL = os.environ.get("OLD_DATABASE_URL")
NEW_URL = os.environ.get("NEW_DATABASE_URL")

# table -> ordered column list (must match db.py / migrations/001_checkin_schema.sql)
TABLES = {
    "professionals": ["id", "name", "email", "created_at"],
    "checkin_events": [
        "id", "client_name", "professional", "professional_id", "client_email",
        "client_phone", "intake_type", "notes", "handled", "email_sent",
        "email_error", "excel_write_status", "excel_last_error", "excel_written_at",
        "created_at",
    ],
    "mail_log": [
        "id", "client_name", "professional_id", "professional_name", "item_type",
        "method", "tracking_number", "sent_by", "notes", "excel_write_status",
        "excel_last_error", "excel_written_at", "created_at",
    ],
}
# copy order respects the professional_id references
ORDER = ["professionals", "checkin_events", "mail_log"]


def _count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def main():
    if not OLD_URL or not NEW_URL:
        sys.exit("Set OLD_DATABASE_URL and NEW_DATABASE_URL environment variables.")

    old = psycopg2.connect(OLD_URL)
    new = psycopg2.connect(NEW_URL, options="-c search_path=checkin,public")
    old.autocommit = False
    new.autocommit = False

    try:
        with old.cursor(cursor_factory=RealDictCursor) as ocur, new.cursor() as ncur:
            for table in ORDER:
                cols = TABLES[table]
                ocur.execute(f"SELECT {', '.join(cols)} FROM public.{table}")
                rows = ocur.fetchall()

                before = _count(ncur, f"checkin.{table}")
                if rows:
                    values = [[r[c] for c in cols] for r in rows]
                    collist = ", ".join(cols)
                    execute_values(
                        ncur,
                        f"INSERT INTO checkin.{table} ({collist}) VALUES %s "
                        f"ON CONFLICT (id) DO NOTHING",
                        values,
                    )
                after = _count(ncur, f"checkin.{table}")
                print(f"{table:15s} source={len(rows):4d}  dest_before={before:4d}  dest_after={after:4d}")

            # reset the professionals serial so future inserts don't collide
            ncur.execute(
                "SELECT setval(pg_get_serial_sequence('checkin.professionals','id'), "
                "COALESCE((SELECT MAX(id) FROM checkin.professionals), 1), true)"
            )

        new.commit()
        print("\nData copy committed successfully.")
    except Exception:
        new.rollback()
        print("\nERROR — rolled back, no changes committed.", file=sys.stderr)
        raise
    finally:
        old.close()
        new.close()


if __name__ == "__main__":
    main()
