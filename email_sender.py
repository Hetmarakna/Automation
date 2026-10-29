"""
email_sender.py - SMTP email composition, validation, connection testing,
and controlled batch execution with pause, cancel, and delay controls.
"""
import smtplib
import ssl
import os
import time
import threading
from email.message import EmailMessage
from email.utils import formataddr
from typing import Dict, List, Any, Optional, Tuple
from database import add_history_record
from validators import validate_email, clean_email


def render_template(template_str: str, context: Dict[str, str]) -> str:
    """
    Safely substitute placeholders like {company}, {job_title}, {your_name}, etc.
    If a variable is missing, fallback gracefully to a clean placeholder.
    """
    if not template_str:
        return ""
    
    # Safe fallback replacements
    rendered = template_str
    replacements = {
        "{company}": context.get("company") or "the hiring team",
        "{job_title}": context.get("job_title") or "the open position",
        "{your_name}": context.get("your_name") or "Applicant",
        "{your_contact}": context.get("your_contact") or "",
        "{recipient_email}": context.get("recipient_email") or "",
    }
    for placeholder, val in replacements.items():
        rendered = rendered.replace(placeholder, val)

    return rendered


def build_email_message(
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    body: str,
    resume_path: Optional[str] = None,
    resume_filename: Optional[str] = None
) -> EmailMessage:
    """
    Construct a MIME EmailMessage with proper headers, body, and resume attachment.
    """
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name or "", sender_email))
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.set_content(body)

    # Attach resume if provided and file exists
    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            pdf_bytes = f.read()
        attachment_name = resume_filename or os.path.basename(resume_path)
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=attachment_name
        )

    return msg


def test_smtp_connection(
    host: str,
    port: int,
    security: str,
    username: str,
    password: str,
    timeout: int = 12
) -> Tuple[bool, str]:
    """
    Test connectivity and credentials against the specified SMTP server.
    Returns (success: bool, detailed_message: str).
    Never exposes passwords in output.
    """
    if not host or not username or not password:
        return False, "Host, sender email, and password / App Password are required."

    try:
        port = int(port)
    except (ValueError, TypeError):
        return False, "Port must be an integer."

    server = None
    try:
        if security == "SSL/TLS":
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            if security == "STARTTLS":
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()

        # Attempt authentication
        server.login(username, password)
        return True, f"Successfully authenticated with {host}:{port} via {security}!"

    except smtplib.SMTPAuthenticationError as auth_err:
        msg = (
            f"Authentication failed (code {auth_err.smtp_code}). "
            "If you are using Gmail, make sure 2-Step Verification is active on your Google account "
            "and use a 16-character Google App Password (not your normal account password). "
            "Visit myaccount.google.com/apppasswords to generate one."
        )
        return False, msg

    except smtplib.SMTPConnectError:
        return False, f"Could not connect to SMTP server at {host}:{port}. Please check the server address and port."

    except (TimeoutError, smtplib.SMTPException) as e:
        err_str = str(e)
        if "timed out" in err_str.lower():
            return False, f"Connection to {host}:{port} timed out after {timeout} seconds. Check your internet connection or firewall."
        return False, f"SMTP Error: {err_str}"

    except Exception as ex:
        return False, f"Connection failed: {str(ex)}"

    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


class CampaignManager:
    """
    Coordinates safe, paused, cancelled, and rate-limited batch email sending in a background thread.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # set = running, clear = paused
        self._cancel_event = threading.Event()

        # Campaign state
        self.status = "idle"  # idle, running, paused, cancelled, completed
        self.total = 0
        self.processed = 0
        self.sent = 0
        self.failed = 0
        self.skipped = 0
        self.current_recipient = ""
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.logs: List[Dict[str, Any]] = []

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = 0.0
            if self.start_time:
                end = self.end_time or time.time()
                elapsed = round(end - self.start_time, 1)

            percent = 0
            if self.total > 0:
                percent = int((self.processed / self.total) * 100)

            return {
                "status": self.status,
                "total": self.total,
                "processed": self.processed,
                "sent": self.sent,
                "failed": self.failed,
                "skipped": self.skipped,
                "percent": percent,
                "current_recipient": self.current_recipient,
                "elapsed_seconds": elapsed,
                "logs": self.logs[-50:]  # Return latest 50 logs
            }

    def _add_log(self, log_type: str, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append({
            "timestamp": timestamp,
            "type": log_type,  # 'info', 'success', 'warning', 'error'
            "message": message
        })

    def start_campaign(
        self,
        recipients: List[Dict[str, Any]],
        template_subject: str,
        template_body: str,
        smtp_config: Dict[str, Any],
        resume_path: Optional[str] = None,
        resume_filename: Optional[str] = None,
        delay_seconds: float = 2.0,
        batch_limit: int = 5,
        candidate_name: str = "Job Applicant",
        candidate_contact: str = ""
    ) -> Tuple[bool, str]:
        with self._lock:
            if self.status in ["running", "paused"]:
                return False, "A campaign is already actively running or paused."

            # Filter only selected recipients
            active_recipients = [r for r in recipients if r.get("selected", True)]
            if not active_recipients:
                return False, "No recipients are selected to receive emails."

            self.status = "running"
            self.total = min(len(active_recipients), batch_limit)
            self.processed = 0
            self.sent = 0
            self.failed = 0
            self.skipped = 0
            self.current_recipient = ""
            self.start_time = time.time()
            self.end_time = None
            self.logs = []
            self._pause_event.set()
            self._cancel_event.clear()

            self._add_log("info", f"Starting campaign for {self.total} recipients (Batch Limit: {batch_limit}, Delay: {delay_seconds}s).")

            # Launch runner thread
            self._thread = threading.Thread(
                target=self._run_campaign,
                args=(
                    active_recipients,
                    template_subject,
                    template_body,
                    smtp_config,
                    resume_path,
                    resume_filename,
                    delay_seconds,
                    batch_limit,
                    candidate_name,
                    candidate_contact
                ),
                daemon=True
            )
            self._thread.start()
            return True, "Campaign started successfully."

    def pause_campaign(self) -> Tuple[bool, str]:
        with self._lock:
            if self.status != "running":
                return False, f"Cannot pause: campaign is currently {self.status}."
            self._pause_event.clear()
            self.status = "paused"
            self._add_log("warning", "Campaign paused by user.")
            return True, "Campaign paused."

    def resume_campaign(self) -> Tuple[bool, str]:
        with self._lock:
            if self.status != "paused":
                return False, f"Cannot resume: campaign is currently {self.status}."
            self.status = "running"
            self._pause_event.set()
            self._add_log("info", "Campaign resumed.")
            return True, "Campaign resumed."

    def cancel_campaign(self) -> Tuple[bool, str]:
        with self._lock:
            if self.status not in ["running", "paused"]:
                return False, f"Cannot cancel: campaign is currently {self.status}."
            self._cancel_event.set()
            self._pause_event.set()  # Unblock if waiting in pause
            self.status = "cancelled"
            self._add_log("warning", "Campaign cancellation requested.")
            return True, "Cancellation in progress."

    def _sleep_interruptible(self, duration: float) -> bool:
        """Sleep for duration seconds while checking for cancellation and pauses. Returns False if cancelled."""
        steps = max(1, int(duration / 0.2))
        for _ in range(steps):
            if self._cancel_event.is_set():
                return False
            self._pause_event.wait()
            time.sleep(0.2)
        return not self._cancel_event.is_set()

    def _send_single_email(
        self,
        smtp_config: Dict[str, Any],
        msg: EmailMessage
    ) -> Tuple[bool, str]:
        """Establish connection and dispatch one message."""
        host = smtp_config["host"]
        port = int(smtp_config["port"])
        security = smtp_config.get("security", "STARTTLS")
        username = smtp_config["username"]
        password = smtp_config["password"]

        server = None
        try:
            if security == "SSL/TLS":
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
                server.ehlo()
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.ehlo()
                if security == "STARTTLS":
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()

            server.login(username, password)
            server.send_message(msg)
            server.quit()
            return True, "Sent to SMTP server"
        except Exception as e:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
            return False, str(e)

    def _run_campaign(
        self,
        recipients: List[Dict[str, Any]],
        template_subject: str,
        template_body: str,
        smtp_config: Dict[str, Any],
        resume_path: Optional[str],
        resume_filename: Optional[str],
        delay_seconds: float,
        batch_limit: int,
        candidate_name: str,
        candidate_contact: str
    ):
        seen_emails_in_batch = set()

        for idx, rec in enumerate(recipients):
            # Check for cancellation
            if self._cancel_event.is_set():
                break

            # Handle pause
            self._pause_event.wait()
            if self._cancel_event.is_set():
                break

            # Check batch limit
            if self.processed >= batch_limit:
                self._add_log("info", f"Reached session batch limit of {batch_limit}. Finishing batch.")
                break

            email = clean_email(rec.get("email", ""))
            company = rec.get("company", "").strip()
            job_title = rec.get("job_title", "").strip()

            self.current_recipient = email

            # Deduplication check within batch
            if email in seen_emails_in_batch:
                self.processed += 1
                self.skipped += 1
                msg = f"Skipping {email}: duplicate recipient in current batch."
                self._add_log("warning", msg)
                add_history_record(
                    recipient_email=email,
                    company_name=company,
                    job_title=job_title,
                    subject=template_subject,
                    body_snippet="Skipped duplicate",
                    resume_name=resume_filename,
                    status="Skipped: Duplicate in batch",
                    error_message="Recipient already appeared earlier in this batch."
                )
                continue

            seen_emails_in_batch.add(email)

            if not validate_email(email):
                self.processed += 1
                self.failed += 1
                err_msg = f"Invalid email format: '{email}'"
                self._add_log("error", err_msg)
                add_history_record(
                    recipient_email=email,
                    company_name=company,
                    job_title=job_title,
                    subject=template_subject,
                    body_snippet="",
                    resume_name=resume_filename,
                    status="Failed",
                    error_message=err_msg
                )
                continue

            # Render personalized subject and body
            context = {
                "company": company,
                "job_title": job_title,
                "your_name": candidate_name,
                "your_contact": candidate_contact,
                "recipient_email": email
            }
            personalized_subject = render_template(template_subject, context)
            personalized_body = render_template(template_body, context)

            self._add_log("info", f"Sending [{self.processed + 1}/{self.total}] to {email}...")

            # Build message
            msg = build_email_message(
                sender_email=smtp_config["username"],
                sender_name=smtp_config.get("sender_name", ""),
                recipient_email=email,
                subject=personalized_subject,
                body=personalized_body,
                resume_path=resume_path,
                resume_filename=resume_filename
            )

            # Send via SMTP
            success, message = self._send_single_email(smtp_config, msg)

            self.processed += 1
            if success:
                self.sent += 1
                self._add_log("success", f"✓ Sent to SMTP server: {email}")
                add_history_record(
                    recipient_email=email,
                    company_name=company,
                    job_title=job_title,
                    subject=personalized_subject,
                    body_snippet=personalized_body[:150],
                    resume_name=resume_filename,
                    status="Sent to SMTP server",
                    error_message=None
                )
            else:
                self.failed += 1
                self._add_log("error", f"✗ Failed for {email}: {message}")
                add_history_record(
                    recipient_email=email,
                    company_name=company,
                    job_title=job_title,
                    subject=personalized_subject,
                    body_snippet=personalized_body[:150],
                    resume_name=resume_filename,
                    status="Failed",
                    error_message=message
                )

            # Delay between messages if more to process and not cancelled
            if idx < len(recipients) - 1 and self.processed < batch_limit:
                if not self._sleep_interruptible(delay_seconds):
                    break

        with self._lock:
            self.end_time = time.time()
            if self._cancel_event.is_set():
                self.status = "cancelled"
                self._add_log("warning", f"Campaign cancelled. Processed: {self.processed}, Sent: {self.sent}, Failed: {self.failed}.")
            else:
                self.status = "completed"
                self._add_log("success", f"Campaign completed. Processed: {self.processed}, Sent: {self.sent}, Failed: {self.failed}, Skipped: {self.skipped}.")
            self.current_recipient = ""


# Global singleton instance of CampaignManager
campaign_manager = CampaignManager()
