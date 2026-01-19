"""
Background worker for retrying failed Excel syncs.

Run this as a separate process to periodically retry failed
Excel writes via Zapier webhooks.

Usage:
    python worker.py
"""

import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

from db import (
    get_pending_excel_checkins,
    get_pending_excel_mail,
    update_checkin_excel_status,
    update_mail_excel_status,
)
from excel_sync import sync_checkin_to_excel, sync_mail_to_excel

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger('excel_worker')

# Retry interval in seconds (default: 5 minutes)
RETRY_INTERVAL = int(os.environ.get('EXCEL_RETRY_INTERVAL', '300'))


def retry_failed_checkins():
    """Retry Excel sync for failed check-ins."""
    pending = get_pending_excel_checkins()
    if not pending:
        return 0

    logger.info(f'Found {len(pending)} check-ins to retry')
    success_count = 0

    for checkin in pending:
        checkin_id = str(checkin['id'])
        try:
            success, error = sync_checkin_to_excel(dict(checkin))
            if success:
                update_checkin_excel_status(checkin_id, 'success')
                logger.info(f'Successfully synced check-in {checkin_id}')
                success_count += 1
            else:
                update_checkin_excel_status(checkin_id, 'failed', error)
                logger.warning(f'Failed to sync check-in {checkin_id}: {error}')
        except Exception as e:
            update_checkin_excel_status(checkin_id, 'failed', str(e))
            logger.error(f'Error syncing check-in {checkin_id}: {e}')

        # Small delay between retries to avoid rate limiting
        time.sleep(1)

    return success_count


def retry_failed_mail():
    """Retry Excel sync for failed mail records."""
    pending = get_pending_excel_mail()
    if not pending:
        return 0

    logger.info(f'Found {len(pending)} mail records to retry')
    success_count = 0

    for mail in pending:
        mail_id = str(mail['id'])
        try:
            success, error = sync_mail_to_excel(dict(mail))
            if success:
                update_mail_excel_status(mail_id, 'success')
                logger.info(f'Successfully synced mail record {mail_id}')
                success_count += 1
            else:
                update_mail_excel_status(mail_id, 'failed', error)
                logger.warning(f'Failed to sync mail record {mail_id}: {error}')
        except Exception as e:
            update_mail_excel_status(mail_id, 'failed', str(e))
            logger.error(f'Error syncing mail record {mail_id}: {e}')

        # Small delay between retries
        time.sleep(1)

    return success_count


def run_worker():
    """Main worker loop."""
    logger.info(f'Starting Excel sync worker (retry interval: {RETRY_INTERVAL}s)')

    while True:
        try:
            checkin_success = retry_failed_checkins()
            mail_success = retry_failed_mail()

            if checkin_success or mail_success:
                logger.info(f'Retry cycle complete: {checkin_success} check-ins, {mail_success} mail records synced')

        except Exception as e:
            logger.error(f'Worker cycle error: {e}')

        # Wait before next retry cycle
        time.sleep(RETRY_INTERVAL)


if __name__ == '__main__':
    run_worker()
