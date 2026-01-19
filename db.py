"""
Database utilities for Sherpa Check-In.

PostgreSQL database with tables for:
- checkin_events: client check-in records with Excel sync tracking
- professionals: staff members who handle clients
- mail_log: outbound mail/document tracking with Excel sync tracking
"""

import os
import uuid
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL', '')


@contextmanager
def get_db():
    """Get a database connection with dict cursor."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables if they don't exist."""
    with get_db() as conn:
        cur = conn.cursor()

        # Check-in events table (enhanced)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS checkin_events (
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
            )
        ''')

        # Professionals table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS professionals (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        # Mail log table (enhanced)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mail_log (
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
            )
        ''')

        conn.commit()


def seed_professionals():
    """Seed default professionals if the table is empty."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) as count FROM professionals')
        count = cur.fetchone()['count']
        if count == 0:
            defaults = [
                ('John Smith', 'john@example.com'),
                ('Jane Doe', 'jane@example.com'),
            ]
            for name, email in defaults:
                cur.execute(
                    'INSERT INTO professionals (name, email) VALUES (%s, %s)',
                    (name, email)
                )
            conn.commit()


# -----------------------------
# Check-in functions
# -----------------------------

def insert_checkin(
    client_name: str,
    professional: str,
    professional_id: int = None,
    client_email: str = None,
    client_phone: str = None,
    intake_type: str = 'Appointment',
    notes: str = None
) -> str:
    """Insert a check-in record and return the new UUID."""
    event_id = str(uuid.uuid4())
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO checkin_events
               (id, client_name, professional, professional_id, client_email,
                client_phone, intake_type, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (event_id, client_name, professional, professional_id, client_email,
             client_phone, intake_type, notes)
        )
        conn.commit()
    return event_id


def list_checkins(limit: int = 50):
    """List check-ins, most recent first."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM checkin_events ORDER BY created_at DESC LIMIT %s',
            (limit,)
        )
        return cur.fetchall()


def get_checkin(checkin_id: str):
    """Get a single check-in by UUID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM checkin_events WHERE id = %s', (checkin_id,))
        return cur.fetchone()


def mark_handled(checkin_id: str):
    """Mark a check-in as handled."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE checkin_events SET handled = TRUE WHERE id = %s',
            (checkin_id,)
        )
        conn.commit()


def update_checkin_email_status(checkin_id: str, success: bool, error: str = None):
    """Update the email status for a check-in."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE checkin_events SET email_sent = %s, email_error = %s WHERE id = %s',
            (success, error, checkin_id)
        )
        conn.commit()


def update_checkin_excel_status(checkin_id: str, status: str, error: str = None):
    """Update the Excel sync status for a check-in."""
    with get_db() as conn:
        cur = conn.cursor()
        if status == 'success':
            cur.execute(
                '''UPDATE checkin_events
                   SET excel_write_status = %s, excel_last_error = NULL, excel_written_at = NOW()
                   WHERE id = %s''',
                (status, checkin_id)
            )
        else:
            cur.execute(
                '''UPDATE checkin_events
                   SET excel_write_status = %s, excel_last_error = %s
                   WHERE id = %s''',
                (status, error, checkin_id)
            )
        conn.commit()


def get_pending_excel_checkins():
    """Get check-ins that need Excel sync (pending or failed)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            '''SELECT * FROM checkin_events
               WHERE excel_write_status IN ('pending', 'failed')
               ORDER BY created_at ASC
               LIMIT 100'''
        )
        return cur.fetchall()


# -----------------------------
# Professional functions
# -----------------------------

def list_professionals():
    """List all professionals."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM professionals ORDER BY name')
        return cur.fetchall()


def get_professional(prof_id: int):
    """Get a single professional by ID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM professionals WHERE id = %s', (prof_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_professional(name: str, email: str) -> int:
    """Add a new professional and return the ID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO professionals (name, email) VALUES (%s, %s) RETURNING id',
            (name, email)
        )
        prof_id = cur.fetchone()['id']
        conn.commit()
        return prof_id


def update_professional(prof_id: int, name: str, email: str):
    """Update a professional's name and email."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE professionals SET name = %s, email = %s WHERE id = %s',
            (name, email, prof_id)
        )
        conn.commit()


def delete_professional(prof_id: int):
    """Delete a professional by ID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM professionals WHERE id = %s', (prof_id,))
        conn.commit()


# -----------------------------
# Mail log functions
# -----------------------------

def insert_mail_record(
    client_name: str,
    professional_id: int,
    professional_name: str,
    item_type: str,
    method: str,
    tracking_number: str = None,
    sent_by: str = None,
    notes: str = None
) -> str:
    """Insert a mail_log row and return the new UUID."""
    mail_id = str(uuid.uuid4())
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO mail_log
               (id, client_name, professional_id, professional_name, item_type,
                method, tracking_number, sent_by, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (mail_id, client_name, professional_id, professional_name, item_type,
             method, tracking_number, sent_by, notes)
        )
        conn.commit()
    return mail_id


def list_mail_records(limit: int = 50):
    """List mail records, most recent first."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM mail_log ORDER BY created_at DESC LIMIT %s',
            (limit,)
        )
        return cur.fetchall()


def update_mail_excel_status(mail_id: str, status: str, error: str = None):
    """Update the Excel sync status for a mail record."""
    with get_db() as conn:
        cur = conn.cursor()
        if status == 'success':
            cur.execute(
                '''UPDATE mail_log
                   SET excel_write_status = %s, excel_last_error = NULL, excel_written_at = NOW()
                   WHERE id = %s''',
                (status, mail_id)
            )
        else:
            cur.execute(
                '''UPDATE mail_log
                   SET excel_write_status = %s, excel_last_error = %s
                   WHERE id = %s''',
                (status, error, mail_id)
            )
        conn.commit()


def get_pending_excel_mail():
    """Get mail records that need Excel sync (pending or failed)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            '''SELECT * FROM mail_log
               WHERE excel_write_status IN ('pending', 'failed')
               ORDER BY created_at ASC
               LIMIT 100'''
        )
        return cur.fetchall()
