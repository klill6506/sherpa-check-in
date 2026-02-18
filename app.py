import os
import time
import logging
from datetime import date, datetime, timedelta
from uuid import uuid4
from flask import Flask, render_template, request, redirect, url_for, session
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

from db import (
    init_db, insert_checkin, list_checkins, mark_handled,
    seed_professionals, list_professionals, get_professional,
    add_professional, update_professional, delete_professional,
    update_checkin_email_status, get_checkin,
    update_checkin_excel_status, get_pending_excel_checkins,
    insert_mail_record, update_mail_excel_status, get_pending_excel_mail
)

from excel_sync import sync_checkin_to_excel, sync_mail_to_excel
import requests as http_requests

# --------------- Slack integration ---------------
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
SLACK_NOTIFY_PROFESSIONAL = 'Ken Lill'


def send_slack_notification(client_name: str, intake_type: str = 'Appointment',
                            client_email: str = None, client_phone: str = None,
                            notes: str = None) -> None:
    """Send a Slack message when a client checks in for Ken Lill."""
    if not SLACK_WEBHOOK_URL:
        return
    lines = [f":wave: *{client_name}* just checked in ({intake_type})"]
    if client_email:
        lines.append(f"Email: {client_email}")
    if client_phone:
        lines.append(f"Phone: {client_phone}")
    if notes:
        lines.append(f"Notes: {notes}")
    try:
        http_requests.post(SLACK_WEBHOOK_URL, json={'text': '\n'.join(lines)}, timeout=5)
    except Exception as e:
        logger.warning('Slack notification failed: %s', e)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

# configure logging
logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger('client_checkin')

# File logging (rotating)
LOG_DIR = os.environ.get('LOG_DIR', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, 'client_checkin.log')
try:
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
except Exception:
    logger.warning('Could not set up file logging to %s', log_file)

# Admin password (simple). For production use a user system.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

# Default intake days for desk intakes
DEFAULT_INTAKE_DAYS = int(os.environ.get('DEFAULT_INTAKE_DAYS', '7'))

# Init DB
init_db()
seed_professionals()


def build_due_date_ics(client_name: str, intake_type: str, due_date) -> str:
    """
    Build a simple all-day ICS event for the given due_date.
    """
    if hasattr(due_date, "date"):
        due_date = due_date.date()

    uid = f"{uuid4()}@thetaxshelter.com"
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = due_date.strftime("%Y%m%d")
    dtend = (due_date + timedelta(days=1)).strftime("%Y%m%d")

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//The Tax Shelter//Sherpa Check-In//EN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART;VALUE=DATE:{dtstart}
DTEND;VALUE=DATE:{dtend}
SUMMARY:Return due for {client_name}
DESCRIPTION:{intake_type} intake for {client_name} is due.
END:VEVENT
END:VCALENDAR
"""
    return ics


def send_email(to_email: str, subject: str, body: str, ics_content: str = None) -> None:
    smtp_server = os.environ.get("SMTP_SERVER", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL", username or "no-reply@example.com")
    use_tls = os.environ.get("USE_TLS", "0").lower() in ("1", "true", "yes")
    use_ssl = os.environ.get("USE_SSL", "0").lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if ics_content:
        msg.add_attachment(
            ics_content.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename="return_due.ics"
        )

    context = ssl.create_default_context()
    max_retries = int(os.environ.get('SMTP_MAX_RETRIES', '3'))
    base_backoff = float(os.environ.get('SMTP_BACKOFF_SECS', '1.0'))

    attempt = 0
    last_exc = None
    while attempt <= max_retries:
        try:
            if use_ssl:
                logger.debug('Attempt %d: connecting via SMTP_SSL to %s:%s', attempt + 1, smtp_server, smtp_port)
                with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10, context=context) as smtp:
                    if username and password:
                        smtp.login(username, password)
                    smtp.send_message(msg)
            else:
                logger.debug('Attempt %d: connecting via SMTP to %s:%s (STARTTLS=%s)', attempt + 1, smtp_server, smtp_port, use_tls)
                with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as smtp:
                    try:
                        smtp.ehlo()
                    except Exception:
                        pass
                    if use_tls:
                        smtp.starttls(context=context)
                        try:
                            smtp.ehlo()
                        except Exception:
                            pass
                    if username and password:
                        smtp.login(username, password)
                    smtp.send_message(msg)

            logger.info('Email sent to %s (subject=%s) on attempt %d', to_email, subject, attempt + 1)
            return
        except smtplib.SMTPRecipientsRefused as e:
            logger.error('Recipient refused: %s', e)
            raise
        except Exception as e:
            last_exc = e
            logger.warning('Email send attempt %d failed: %s', attempt + 1, e)
            attempt += 1
            if attempt > max_retries:
                logger.error('All %d attempts failed for %s: %s', max_retries, to_email, last_exc)
                raise
            backoff = base_backoff * (2 ** (attempt - 1))
            logger.info('Retrying in %.1f seconds...', backoff)
            time.sleep(backoff)


def sync_checkin_async(checkin_id: str, checkin_data: dict, due_date=None):
    """Sync check-in to Excel via Zapier (best-effort)."""
    try:
        data = dict(checkin_data)
        if due_date:
            data['due_date'] = due_date
        success, error = sync_checkin_to_excel(data)
        if success:
            update_checkin_excel_status(checkin_id, 'success')
        else:
            update_checkin_excel_status(checkin_id, 'failed', error)
    except Exception as e:
        logger.warning('Failed to sync check-in %s to Excel: %s', checkin_id, e)
        update_checkin_excel_status(checkin_id, 'failed', str(e))


def sync_mail_async(mail_id: str, mail_data: dict):
    """Sync mail record to Excel via Zapier (best-effort)."""
    try:
        success, error = sync_mail_to_excel(mail_data)
        if success:
            update_mail_excel_status(mail_id, 'success')
        else:
            update_mail_excel_status(mail_id, 'failed', error)
    except Exception as e:
        logger.warning('Failed to sync mail %s to Excel: %s', mail_id, e)
        update_mail_excel_status(mail_id, 'failed', str(e))


@app.route('/')
def home():
    """Landing page with Client vs Employee choice."""
    return render_template('home.html')


@app.route('/client', methods=['GET', 'POST'])
def client_checkin():
    """Client-facing kiosk check-in screen."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        prof_id = request.form.get('professional')
        client_email = request.form.get('email', '').strip()
        client_phone = request.form.get('phone', '').strip()

        if not name or not prof_id:
            proflist = list_professionals()
            proflist = [dict(id=r['id'], name=r['name'], email=r['email']) for r in proflist]
            return render_template('index.html', professionals=proflist, error='Please enter your name and pick a professional.')

        prof = get_professional(int(prof_id))
        if not prof:
            proflist = list_professionals()
            proflist = [dict(id=r['id'], name=r['name'], email=r['email']) for r in proflist]
            return render_template('index.html', professionals=proflist, error='Selected professional not found.')

        # Insert check-in with all fields
        checkin_id = insert_checkin(
            client_name=name,
            professional=prof['name'],
            professional_id=prof['id'],
            client_email=client_email or None,
            client_phone=client_phone or None,
            intake_type='Appointment',
            notes='Kiosk check-in'
        )

        # Sync to Excel via Zapier (best-effort)
        checkin_data = {
            'id': checkin_id,
            'client_name': name,
            'professional': prof['name'],
            'client_email': client_email,
            'client_phone': client_phone,
            'intake_type': 'Appointment',
            'notes': 'Kiosk check-in',
            'created_at': datetime.utcnow(),
        }
        sync_checkin_async(checkin_id, checkin_data)

        # Send email (best-effort)
        subject = f'Client check-in: {name} has arrived'
        body = f"Client name: {name}\nProfessional: {prof['name']}\nCheck-in ID: {checkin_id}"
        if client_email:
            body += f"\nClient email: {client_email}"
        if client_phone:
            body += f"\nClient phone: {client_phone}"
        try:
            send_email(prof['email'], subject, body)
            update_checkin_email_status(checkin_id, True)
        except Exception as e:
            update_checkin_email_status(checkin_id, False, str(e))

        # Slack notification (Ken Lill only)
        if prof['name'] == SLACK_NOTIFY_PROFESSIONAL:
            send_slack_notification(name, 'Appointment', client_email, client_phone)

        return render_template('checked_in.html', name=name, professional=prof['name'])

    proflist = list_professionals()
    proflist = [dict(id=r['id'], name=r['name'], email=r['email']) for r in proflist]
    return render_template('index.html', professionals=proflist)


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('admin_login.html', error='Invalid password')

    if not session.get('admin'):
        return render_template('admin_login.html')

    checkins = list_checkins()
    return render_template('admin_list.html', checkins=checkins)


@app.route('/admin/resend/<checkin_id>', methods=['POST'])
def admin_resend(checkin_id):
    if not session.get('admin'):
        return ('', 403)
    ci = get_checkin(checkin_id)
    if not ci:
        return redirect(url_for('admin'))

    prof = None
    if ci['professional_id']:
        prof = get_professional(ci['professional_id'])
    else:
        proflist = list_professionals()
        for p in proflist:
            if p['name'] == ci['professional']:
                prof = dict(p)
                break
    if not prof:
        update_checkin_email_status(checkin_id, False, 'Professional not found')
        return redirect(url_for('admin'))

    subject = f"Client check-in: {ci['client_name']} has arrived"
    body = f"Client name: {ci['client_name']}\nProfessional: {prof['name']}\nCheck-in ID: {checkin_id}"
    if ci.get('client_email'):
        body += f"\nClient email: {ci['client_email']}"
    if ci.get('client_phone'):
        body += f"\nClient phone: {ci['client_phone']}"
    try:
        send_email(prof['email'], subject, body)
        update_checkin_email_status(checkin_id, True)
    except Exception as e:
        update_checkin_email_status(checkin_id, False, str(e))
    return redirect(url_for('admin'))


@app.route('/admin/retry-excel/<checkin_id>', methods=['POST'])
def admin_retry_excel(checkin_id):
    """Retry Excel sync for a failed check-in."""
    if not session.get('admin'):
        return ('', 403)
    ci = get_checkin(checkin_id)
    if not ci:
        return redirect(url_for('admin'))

    sync_checkin_async(checkin_id, dict(ci))
    return redirect(url_for('admin'))


@app.route('/admin/professionals')
def admin_professionals():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    proflist = list_professionals()
    return render_template('admin_professionals.html', professionals=proflist)


@app.route('/admin/logo', methods=['GET', 'POST'])
def admin_logo():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    if request.method == 'POST':
        f = request.files.get('logo')
        if not f:
            return render_template('admin_logo.html', error='No file uploaded')
        if not f.filename.lower().endswith('.png'):
            return render_template('admin_logo.html', error='Only PNG files are accepted')
        static_dir = app.static_folder or 'static'
        os.makedirs(static_dir, exist_ok=True)
        save_path = os.path.join(static_dir, 'logo.png')
        f.save(save_path)
        return render_template('admin_logo.html', success='Logo uploaded')
    return render_template('admin_logo.html')


@app.route('/admin/professionals/add', methods=['GET', 'POST'])
def admin_add_professional():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        if name and email:
            add_professional(name, email)
            return redirect(url_for('admin_professionals'))
        return render_template('admin_professional_form.html', error='Name and email required')
    return render_template('admin_professional_form.html')


@app.route('/admin/professionals/edit/<int:prof_id>', methods=['GET', 'POST'])
def admin_edit_professional(prof_id):
    if not session.get('admin'):
        return redirect(url_for('admin'))
    prof = get_professional(prof_id)
    if not prof:
        return redirect(url_for('admin_professionals'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        if name and email:
            update_professional(prof_id, name, email)
            return redirect(url_for('admin_professionals'))
        return render_template('admin_professional_form.html', professional=prof, error='Name and email required')
    return render_template('admin_professional_form.html', professional=prof)


@app.route('/admin/professionals/delete/<int:prof_id>', methods=['POST'])
def admin_delete_professional(prof_id):
    if not session.get('admin'):
        return redirect(url_for('admin'))
    delete_professional(prof_id)
    return redirect(url_for('admin_professionals'))


@app.route('/admin/handle/<checkin_id>', methods=['POST'])
def admin_handle(checkin_id):
    if not session.get('admin'):
        return ('', 403)
    mark_handled(checkin_id)
    return redirect(url_for('admin'))


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin'))


# -----------------------------
# Desk Portal Routes
# -----------------------------

@app.route('/desk')
def desk_home():
    """Desk home page with links to intake and mail log."""
    return render_template('desk_home.html')


@app.route('/desk/intake', methods=['GET', 'POST'])
def desk_intake():
    """Desk intake screen for non-appointment intakes."""
    proflist = list_professionals()
    proflist = [dict(id=r['id'], name=r['name'], email=r['email']) for r in proflist]

    intake_types = ['Walk-in', 'Drop-off', 'Email', 'Portal Upload', 'Mail-in']

    if request.method == 'POST':
        client_name = request.form.get('client_name', '').strip()
        client_email = request.form.get('client_email', '').strip()
        client_phone = request.form.get('client_phone', '').strip()
        prof_id = request.form.get('professional')
        intake_type = request.form.get('intake_type', '').strip()
        notes = request.form.get('notes', '').strip()

        if not client_name or not prof_id:
            return render_template(
                'desk_intake.html',
                professionals=proflist,
                intake_types=intake_types,
                error='Client name and professional are required.'
            )

        prof = get_professional(int(prof_id))
        if not prof:
            return render_template(
                'desk_intake.html',
                professionals=proflist,
                intake_types=intake_types,
                error='Selected professional not found.'
            )

        # Compute due date
        due_date = date.today() + timedelta(days=DEFAULT_INTAKE_DAYS)

        # Insert check-in with all fields
        checkin_id = insert_checkin(
            client_name=client_name,
            professional=prof['name'],
            professional_id=prof['id'],
            client_email=client_email or None,
            client_phone=client_phone or None,
            intake_type=intake_type or 'Drop-off',
            notes=notes or None
        )

        # Sync to Excel via Zapier (best-effort)
        checkin_data = {
            'id': checkin_id,
            'client_name': client_name,
            'professional': prof['name'],
            'client_email': client_email,
            'client_phone': client_phone,
            'intake_type': intake_type or 'Drop-off',
            'notes': notes,
            'created_at': datetime.utcnow(),
        }
        sync_checkin_async(checkin_id, checkin_data, due_date=due_date)

        # Send email notification
        subject = f"New {intake_type or 'Drop-off'} for {client_name}"
        body_lines = [
            "New intake received:",
            "",
            f"Client Name: {client_name}",
            f"Intake Type: {intake_type or 'Drop-off'}",
            f"Due Date for Return: {due_date.strftime('%B %d, %Y')}",
        ]
        if client_email:
            body_lines.append(f"Client Email: {client_email}")
        if client_phone:
            body_lines.append(f"Client Phone: {client_phone}")
        if notes:
            body_lines.append("")
            body_lines.append(f"Notes: {notes}")

        body = "\n".join(body_lines)
        ics_content = build_due_date_ics(client_name, intake_type or 'Drop-off', due_date)

        try:
            send_email(prof['email'], subject, body, ics_content=ics_content)
            update_checkin_email_status(checkin_id, True)
        except Exception as e:
            logger.warning('Failed to send desk intake email: %s', e)
            update_checkin_email_status(checkin_id, False, str(e))

        # Slack notification (Ken Lill only)
        if prof['name'] == SLACK_NOTIFY_PROFESSIONAL:
            send_slack_notification(client_name, intake_type or 'Drop-off',
                                    client_email, client_phone, notes)

        return render_template(
            'desk_intake.html',
            professionals=proflist,
            intake_types=intake_types,
            success=f'Intake created for {client_name} (ID: {checkin_id[:8]}...). Due: {due_date.strftime("%Y-%m-%d")}'
        )

    return render_template(
        'desk_intake.html',
        professionals=proflist,
        intake_types=intake_types,
    )


@app.route('/desk/mail', methods=['GET', 'POST'])
def desk_mail():
    """Mail log screen for tracking outbound mail/documents."""
    proflist = list_professionals()
    proflist = [dict(id=r['id'], name=r['name'], email=r['email']) for r in proflist]

    item_types = ['Original Return', 'Amended Return', 'E-file Authorization', 'Notice Response', 'Other']
    methods = ['USPS', 'USPS Certified', 'FedEx', 'UPS', 'Hand-delivered', 'Portal Upload']

    if request.method == 'POST':
        client_name = request.form.get('client_name', '').strip()
        prof_id = request.form.get('professional')
        item_type = request.form.get('item_type', '').strip()
        method = request.form.get('method', '').strip()
        tracking_number = request.form.get('tracking_number', '').strip()
        sent_by = request.form.get('sent_by', '').strip()
        notes = request.form.get('notes', '').strip()

        if not client_name or not prof_id:
            return render_template(
                'desk_mail.html',
                professionals=proflist,
                item_types=item_types,
                methods=methods,
                error='Client name and professional are required.'
            )

        prof = get_professional(int(prof_id))
        if not prof:
            return render_template(
                'desk_mail.html',
                professionals=proflist,
                item_types=item_types,
                methods=methods,
                error='Selected professional not found.'
            )

        # Create mail record in DB
        mail_id = insert_mail_record(
            client_name=client_name,
            professional_id=prof['id'],
            professional_name=prof['name'],
            item_type=item_type or 'Other',
            method=method or 'USPS',
            tracking_number=tracking_number or None,
            sent_by=sent_by or None,
            notes=notes or None,
        )

        # Sync to Excel via Zapier (best-effort)
        mail_data = {
            'id': mail_id,
            'client_name': client_name,
            'professional_name': prof['name'],
            'item_type': item_type or 'Other',
            'method': method or 'USPS',
            'tracking_number': tracking_number,
            'sent_by': sent_by,
            'notes': notes,
            'created_at': datetime.utcnow(),
        }
        sync_mail_async(mail_id, mail_data)

        return render_template(
            'desk_mail.html',
            professionals=proflist,
            item_types=item_types,
            methods=methods,
            success=f'Mail record created for {client_name} (ID: {mail_id[:8]}...)'
        )

    return render_template(
        'desk_mail.html',
        professionals=proflist,
        item_types=item_types,
        methods=methods,
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8001)), debug=True)
