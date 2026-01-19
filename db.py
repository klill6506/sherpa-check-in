"""
Database utilities for Sherpa Check-In.

SQLite database with tables for:
- checkins: client check-in records
- professionals: staff members who handle clients
- mail_log: outbound mail/document tracking
"""

import sqlite3
import os

DB_PATH = os.environ.get('CHECKIN_DB_PATH', 'checkins.db')


def get_db():
    """Get a database connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()

    # Check-ins table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            professional TEXT NOT NULL,
            professional_id INTEGER,
            handled INTEGER DEFAULT 0,
            email_sent INTEGER DEFAULT 0,
            email_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Professionals table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS professionals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Mail log table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mail_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            professional_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            method TEXT NOT NULL,
            tracking_number TEXT,
            sent_by TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def seed_professionals():
    """Seed default professionals if the table is empty."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM professionals')
    count = cur.fetchone()[0]
    if count == 0:
        # Add some default professionals - customize as needed
        defaults = [
            ('John Smith', 'john@example.com'),
            ('Jane Doe', 'jane@example.com'),
        ]
        cur.executemany('INSERT INTO professionals (name, email) VALUES (?, ?)', defaults)
        conn.commit()
    conn.close()


# -----------------------------
# Check-in functions
# -----------------------------

def insert_checkin(client_name: str, professional: str, professional_id: int = None) -> int:
    """Insert a check-in record and return the new ID."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO checkins (client_name, professional, professional_id) VALUES (?, ?, ?)',
        (client_name, professional, professional_id)
    )
    conn.commit()
    checkin_id = cur.lastrowid
    conn.close()
    return checkin_id


def list_checkins():
    """List all check-ins, most recent first."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM checkins ORDER BY created_at DESC')
    rows = cur.fetchall()
    conn.close()
    return rows


def get_checkin(checkin_id: int):
    """Get a single check-in by ID."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM checkins WHERE id = ?', (checkin_id,))
    row = cur.fetchone()
    conn.close()
    return row


def mark_handled(checkin_id: int):
    """Mark a check-in as handled."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE checkins SET handled = 1 WHERE id = ?', (checkin_id,))
    conn.commit()
    conn.close()


def update_checkin_email_status(checkin_id: int, success: bool, error: str = None):
    """Update the email status for a check-in."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'UPDATE checkins SET email_sent = ?, email_error = ? WHERE id = ?',
        (1 if success else 0, error, checkin_id)
    )
    conn.commit()
    conn.close()


# -----------------------------
# Professional functions
# -----------------------------

def list_professionals():
    """List all professionals."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM professionals ORDER BY name')
    rows = cur.fetchall()
    conn.close()
    return rows


def get_professional(prof_id: int):
    """Get a single professional by ID."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM professionals WHERE id = ?', (prof_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def add_professional(name: str, email: str) -> int:
    """Add a new professional and return the ID."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO professionals (name, email) VALUES (?, ?)', (name, email))
    conn.commit()
    prof_id = cur.lastrowid
    conn.close()
    return prof_id


def update_professional(prof_id: int, name: str, email: str):
    """Update a professional's name and email."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE professionals SET name = ?, email = ? WHERE id = ?', (name, email, prof_id))
    conn.commit()
    conn.close()


def delete_professional(prof_id: int):
    """Delete a professional by ID."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM professionals WHERE id = ?', (prof_id,))
    conn.commit()
    conn.close()


# -----------------------------
# Mail log functions
# -----------------------------

def insert_mail_record(
    client_name: str,
    professional_id: int,
    item_type: str,
    method: str,
    tracking_number: str = None,
    sent_by: str = None,
    notes: str = None
) -> int:
    """
    Insert a mail_log row and return the new mail_id.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO mail_log
           (client_name, professional_id, item_type, method, tracking_number, sent_by, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (client_name, professional_id, item_type, method, tracking_number, sent_by, notes)
    )
    conn.commit()
    mail_id = cur.lastrowid
    conn.close()
    return mail_id


def list_mail_records():
    """List all mail records, most recent first."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM mail_log ORDER BY created_at DESC')
    rows = cur.fetchall()
    conn.close()
    return rows
