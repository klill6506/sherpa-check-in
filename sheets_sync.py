"""
Google Sheets sync module.

Sends check-in and mail log data directly to Google Sheets
using a service account. Replaces the old Zapier webhook approach.
"""

import os
import json
import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
import pytz

logger = logging.getLogger('client_checkin')

# Google Sheets config (set in environment)
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
GOOGLE_SHEETS_CREDENTIALS = os.environ.get('GOOGLE_SHEETS_CREDENTIALS', '')

# Timezone for display (store UTC, display local)
TIMEZONE = os.environ.get('TIMEZONE', 'America/New_York')

# Worksheet tab names
CHECKIN_TAB = 'Check-Ins'
MAIL_TAB = 'Mail Log'

# Google API scopes
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Module-level client (lazy-initialized)
_gspread_client = None


def _get_client():
    """Get or create the gspread client (lazy singleton)."""
    global _gspread_client
    if _gspread_client is not None:
        return _gspread_client

    if not GOOGLE_SHEETS_CREDENTIALS:
        raise ValueError('GOOGLE_SHEETS_CREDENTIALS not configured')

    creds_data = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    credentials = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    _gspread_client = gspread.authorize(credentials)
    return _gspread_client


def _get_worksheet(tab_name: str):
    """Open the configured spreadsheet and return the named worksheet."""
    if not GOOGLE_SHEET_ID:
        raise ValueError('GOOGLE_SHEET_ID not configured')

    client = _get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    return spreadsheet.worksheet(tab_name)


def _get_local_timestamp(utc_dt=None):
    """Convert UTC datetime to local timezone string."""
    if utc_dt is None:
        utc_dt = datetime.utcnow()

    tz = pytz.timezone(TIMEZONE)
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


def _get_local_date(utc_dt=None):
    """Convert UTC datetime to local date string."""
    if utc_dt is None:
        utc_dt = datetime.utcnow()

    tz = pytz.timezone(TIMEZONE)
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime('%Y-%m-%d')


def sync_checkin_to_sheets(checkin_data: dict) -> tuple[bool, str]:
    """
    Append a check-in row to the Google Sheet 'Check-Ins' tab.

    Args:
        checkin_data: Dict with check-in fields from database

    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if not GOOGLE_SHEET_ID or not GOOGLE_SHEETS_CREDENTIALS:
        logger.warning('Google Sheets not configured, skipping sync')
        return False, 'Google Sheets not configured'

    try:
        # Format due date if present
        due_date = checkin_data.get('due_date')
        if due_date:
            if isinstance(due_date, datetime):
                due_date = due_date.strftime('%Y-%m-%d')
            elif hasattr(due_date, 'isoformat'):
                due_date = due_date.isoformat()

        # Build row matching header columns:
        # EventID | TimestampLocal | ClientName | ClientEmail | ClientPhone |
        # Professional | IntakeType | DueDate | Status | Notes
        row = [
            str(checkin_data.get('id', '')),
            _get_local_timestamp(checkin_data.get('created_at')),
            checkin_data.get('client_name', ''),
            checkin_data.get('client_email', '') or '',
            checkin_data.get('client_phone', '') or '',
            checkin_data.get('professional', ''),
            checkin_data.get('intake_type', 'Appointment'),
            due_date or '',
            'Not started',
            checkin_data.get('notes', '') or '',
        ]

        event_id = row[0]
        logger.info(f'Syncing check-in {event_id} to Google Sheets')

        ws = _get_worksheet(CHECKIN_TAB)
        ws.append_row(row, value_input_option='USER_ENTERED')

        logger.info(f'Successfully synced check-in {event_id} to Google Sheets')
        return True, None

    except gspread.exceptions.APIError as e:
        error = f'Google Sheets API error: {str(e)}'
        logger.error(f'Failed to sync check-in: {error}')
        return False, error
    except Exception as e:
        error = f'Unexpected error: {str(e)}'
        logger.error(f'Failed to sync check-in: {error}')
        return False, error


def sync_mail_to_sheets(mail_data: dict) -> tuple[bool, str]:
    """
    Append a mail log row to the Google Sheet 'Mail Log' tab.

    Args:
        mail_data: Dict with mail log fields from database

    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if not GOOGLE_SHEET_ID or not GOOGLE_SHEETS_CREDENTIALS:
        logger.warning('Google Sheets not configured, skipping sync')
        return False, 'Google Sheets not configured'

    try:
        # Build row matching header columns:
        # EventID | DateSent | ClientName | Professional | ItemType |
        # Method | TrackingNumber | SentBy | Notes
        row = [
            str(mail_data.get('id', '')),
            _get_local_date(mail_data.get('created_at')),
            mail_data.get('client_name', ''),
            mail_data.get('professional_name', ''),
            mail_data.get('item_type', ''),
            mail_data.get('method', ''),
            mail_data.get('tracking_number', '') or '',
            mail_data.get('sent_by', '') or '',
            mail_data.get('notes', '') or '',
        ]

        event_id = row[0]
        logger.info(f'Syncing mail record {event_id} to Google Sheets')

        ws = _get_worksheet(MAIL_TAB)
        ws.append_row(row, value_input_option='USER_ENTERED')

        logger.info(f'Successfully synced mail record {event_id} to Google Sheets')
        return True, None

    except gspread.exceptions.APIError as e:
        error = f'Google Sheets API error: {str(e)}'
        logger.error(f'Failed to sync mail record: {error}')
        return False, error
    except Exception as e:
        error = f'Unexpected error: {str(e)}'
        logger.error(f'Failed to sync mail record: {error}')
        return False, error
