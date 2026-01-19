"""
Excel sync via Zapier webhooks.

Sends check-in and mail log data to Zapier webhooks which then
append rows to Excel tables in SharePoint.
"""

import os
import logging
from datetime import datetime

import requests
import pytz

logger = logging.getLogger('client_checkin')

# Zapier webhook URLs (set in environment)
ZAPIER_CHECKIN_WEBHOOK = os.environ.get('ZAPIER_CHECKIN_WEBHOOK_URL', '')
ZAPIER_MAIL_WEBHOOK = os.environ.get('ZAPIER_MAIL_WEBHOOK_URL', '')

# Timezone for Excel display (store UTC, display local)
TIMEZONE = os.environ.get('TIMEZONE', 'America/New_York')


def _get_local_timestamp(utc_dt=None):
    """Convert UTC datetime to local timezone string for Excel."""
    if utc_dt is None:
        utc_dt = datetime.utcnow()

    tz = pytz.timezone(TIMEZONE)
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


def _get_local_date(utc_dt=None):
    """Convert UTC datetime to local date string for Excel."""
    if utc_dt is None:
        utc_dt = datetime.utcnow()

    tz = pytz.timezone(TIMEZONE)
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime('%Y-%m-%d')


def sync_checkin_to_excel(checkin_data: dict) -> tuple[bool, str]:
    """
    Send check-in data to Zapier webhook for Excel sync.

    Args:
        checkin_data: Dict with check-in fields from database

    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if not ZAPIER_CHECKIN_WEBHOOK:
        logger.warning('ZAPIER_CHECKIN_WEBHOOK_URL not configured, skipping Excel sync')
        return False, 'Webhook URL not configured'

    try:
        # Format due date if present
        due_date = checkin_data.get('due_date')
        if due_date:
            if isinstance(due_date, datetime):
                due_date = due_date.strftime('%Y-%m-%d')
            elif hasattr(due_date, 'isoformat'):
                due_date = due_date.isoformat()

        # Build payload matching Excel table columns
        payload = {
            'EventID': str(checkin_data.get('id', '')),
            'TimestampLocal': _get_local_timestamp(checkin_data.get('created_at')),
            'ClientName': checkin_data.get('client_name', ''),
            'ClientEmail': checkin_data.get('client_email', '') or '',
            'ClientPhone': checkin_data.get('client_phone', '') or '',
            'Professional': checkin_data.get('professional', ''),
            'IntakeType': checkin_data.get('intake_type', 'Appointment'),
            'DueDate': due_date or '',
            'Status': 'Not started',
            'Notes': checkin_data.get('notes', '') or '',
        }

        logger.info(f'Sending check-in {payload["EventID"]} to Zapier webhook')

        response = requests.post(
            ZAPIER_CHECKIN_WEBHOOK,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f'Successfully synced check-in {payload["EventID"]} to Excel')
            return True, None
        else:
            error = f'Zapier returned status {response.status_code}: {response.text[:200]}'
            logger.error(f'Failed to sync check-in: {error}')
            return False, error

    except requests.exceptions.Timeout:
        error = 'Zapier webhook request timed out'
        logger.error(error)
        return False, error
    except requests.exceptions.RequestException as e:
        error = f'Request error: {str(e)}'
        logger.error(f'Failed to sync check-in: {error}')
        return False, error
    except Exception as e:
        error = f'Unexpected error: {str(e)}'
        logger.error(f'Failed to sync check-in: {error}')
        return False, error


def sync_mail_to_excel(mail_data: dict) -> tuple[bool, str]:
    """
    Send mail log data to Zapier webhook for Excel sync.

    Args:
        mail_data: Dict with mail log fields from database

    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    if not ZAPIER_MAIL_WEBHOOK:
        logger.warning('ZAPIER_MAIL_WEBHOOK_URL not configured, skipping Excel sync')
        return False, 'Webhook URL not configured'

    try:
        # Build payload matching Excel table columns
        payload = {
            'EventID': str(mail_data.get('id', '')),
            'DateSent': _get_local_date(mail_data.get('created_at')),
            'ClientName': mail_data.get('client_name', ''),
            'Professional': mail_data.get('professional_name', ''),
            'ItemType': mail_data.get('item_type', ''),
            'Method': mail_data.get('method', ''),
            'TrackingNumber': mail_data.get('tracking_number', '') or '',
            'SentBy': mail_data.get('sent_by', '') or '',
            'Notes': mail_data.get('notes', '') or '',
        }

        logger.info(f'Sending mail record {payload["EventID"]} to Zapier webhook')

        response = requests.post(
            ZAPIER_MAIL_WEBHOOK,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f'Successfully synced mail record {payload["EventID"]} to Excel')
            return True, None
        else:
            error = f'Zapier returned status {response.status_code}: {response.text[:200]}'
            logger.error(f'Failed to sync mail record: {error}')
            return False, error

    except requests.exceptions.Timeout:
        error = 'Zapier webhook request timed out'
        logger.error(error)
        return False, error
    except requests.exceptions.RequestException as e:
        error = f'Request error: {str(e)}'
        logger.error(f'Failed to sync mail record: {error}')
        return False, error
    except Exception as e:
        error = f'Unexpected error: {str(e)}'
        logger.error(f'Failed to sync mail record: {error}')
        return False, error
