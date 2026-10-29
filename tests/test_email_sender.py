"""
test_email_sender.py - Tests for email message creation, template interpolation,
SMTP connection error handling, and campaign batch execution with cancellation.
Mocks all network and SMTP calls so no real emails are ever sent.
"""
import os
import time
import tempfile
import smtplib
from unittest.mock import patch, MagicMock
from email_sender import (
    render_template, build_email_message,
    test_smtp_connection as check_smtp_connection,
    CampaignManager
)
from database import init_db, get_history, clear_history, DEFAULT_DB_PATH


def test_render_template_placeholders():
    template = "Hi, I am applying for {job_title} at {company}. Regards, {your_name}."
    context = {
        "job_title": "Python Architect",
        "company": "DeepMind",
        "your_name": "Senior Dev"
    }
    rendered = render_template(template, context)
    assert rendered == "Hi, I am applying for Python Architect at DeepMind. Regards, Senior Dev."


def test_render_template_fallback_defaults():
    template = "Position: {job_title} at {company} from {your_name}"
    rendered = render_template(template, {})
    assert "the open position" in rendered
    assert "the hiring team" in rendered
    assert "Applicant" in rendered


def test_build_email_message_without_attachment():
    msg = build_email_message(
        sender_email="sender@example.com",
        sender_name="Jane Doe",
        recipient_email="recruiter@target.com",
        subject="Application for Developer",
        body="Please see my application details.",
        resume_path=None
    )
    assert msg["From"] == "Jane Doe <sender@example.com>"
    assert msg["To"] == "recruiter@target.com"
    assert msg["Subject"] == "Application for Developer"
    assert msg.get_content().strip() == "Please see my application details."
    assert len(list(msg.iter_attachments())) == 0


def test_build_email_message_with_attachment():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 sample resume content")
        tmp_path = tmp.name

    try:
        msg = build_email_message(
            sender_email="sender@example.com",
            sender_name="Jane Doe",
            recipient_email="recruiter@target.com",
            subject="Application for Developer",
            body="Attached is my resume.",
            resume_path=tmp_path,
            resume_filename="Jane_Doe_Resume.pdf"
        )
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1
        att = attachments[0]
        assert att.get_filename() == "Jane_Doe_Resume.pdf"
        assert att.get_content_type() == "application/pdf"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_build_email_message_missing_resume_file():
    # If a resume path is given but does not exist on disk, handle gracefully without crashing
    non_existent_path = "/tmp/does_not_exist_resume_12345.pdf"
    msg = build_email_message(
        sender_email="sender@example.com",
        sender_name="Jane Doe",
        recipient_email="recruiter@target.com",
        subject="Application",
        body="Body text",
        resume_path=non_existent_path
    )
    # Should build cleanly with 0 attachments
    assert len(list(msg.iter_attachments())) == 0


@patch("smtplib.SMTP")
def test_smtp_connection_success(mock_smtp):
    instance = MagicMock()
    mock_smtp.return_value = instance

    ok, message = check_smtp_connection(
        host="smtp.gmail.com",
        port=587,
        security="STARTTLS",
        username="user@gmail.com",
        password="app_password_123"
    )
    assert ok is True
    assert "Successfully authenticated" in message
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("user@gmail.com", "app_password_123")


@patch("smtplib.SMTP")
def test_smtp_connection_auth_error(mock_smtp):
    instance = MagicMock()
    instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    mock_smtp.return_value = instance

    ok, message = check_smtp_connection(
        host="smtp.gmail.com",
        port=587,
        security="STARTTLS",
        username="user@gmail.com",
        password="bad_password"
    )
    assert ok is False
    assert "Authentication failed (code 535)" in message
    assert "App Password" in message


@patch("smtplib.SMTP")
def test_smtp_connection_timeout(mock_smtp):
    mock_smtp.side_effect = TimeoutError("Connection timed out")

    ok, message = check_smtp_connection(
        host="smtp.gmail.com",
        port=587,
        security="STARTTLS",
        username="user@gmail.com",
        password="app_password"
    )
    assert ok is False
    assert "timed out" in message.lower()


def test_campaign_manager_bulk_send_and_deduplication():
    # Use isolated test database
    test_db = os.path.join(tempfile.gettempdir(), f"test_smartapply_{time.time()}.db")
    init_db(test_db)

    with patch("database.DEFAULT_DB_PATH", test_db), \
         patch("email_sender.add_history_record") as mock_add_record:

        mgr = CampaignManager()
        # Mock single send to succeed
        mgr._send_single_email = MagicMock(return_value=(True, "Sent to SMTP server"))

        recipients = [
            {"email": "first@company.com", "company": "First Co", "job_title": "Dev", "selected": True},
            {"email": "first@company.com", "company": "First Co", "job_title": "Dev", "selected": True}, # duplicate
            {"email": "second@company.com", "company": "Second Co", "job_title": "Dev", "selected": True}
        ]

        smtp_config = {
            "host": "smtp.gmail.com",
            "port": 587,
            "security": "STARTTLS",
            "username": "me@gmail.com",
            "password": "secret_app_password"
        }

        ok, msg = mgr.start_campaign(
            recipients=recipients,
            template_subject="Applying for {job_title}",
            template_body="Hello {company}",
            smtp_config=smtp_config,
            delay_seconds=0.1,
            batch_limit=5
        )
        assert ok is True

        # Wait for background thread
        mgr._thread.join(timeout=5)

        state = mgr.get_state()
        assert state["status"] == "completed"
        assert state["total"] == 3
        assert state["processed"] == 3
        assert state["sent"] == 2
        assert state["skipped"] == 1  # The duplicate was skipped


def test_campaign_manager_cancellation():
    mgr = CampaignManager()
    mgr._send_single_email = MagicMock(return_value=(True, "Sent to SMTP server"))

    # 10 recipients with 0.5s delay
    recipients = [
        {"email": f"applicant_{i}@domain.com", "company": "Corp", "job_title": "Eng", "selected": True}
        for i in range(10)
    ]
    smtp_config = {
        "host": "smtp.gmail.com",
        "port": 587,
        "security": "STARTTLS",
        "username": "me@gmail.com",
        "password": "pass"
    }

    with patch("email_sender.add_history_record"):
        ok, msg = mgr.start_campaign(
            recipients=recipients,
            template_subject="Job",
            template_body="Body",
            smtp_config=smtp_config,
            delay_seconds=0.5,
            batch_limit=10
        )
        assert ok is True

        # Let the first recipient begin, then cancel immediately
        time.sleep(0.15)
        cancel_ok, cancel_msg = mgr.cancel_campaign()
        assert cancel_ok is True

        mgr._thread.join(timeout=3)
        state = mgr.get_state()
        assert state["status"] == "cancelled"
        assert state["processed"] < 10


def test_history_persistence_in_database():
    test_db = os.path.join(tempfile.gettempdir(), f"test_hist_{time.time()}.db")
    init_db(test_db)

    from database import add_history_record, get_history, get_history_stats

    # Add records
    add_history_record(
        recipient_email="recruiter1@firm.com",
        company_name="Firm One",
        job_title="Software Engineer",
        subject="Application for SWE",
        body_snippet="Hello team",
        resume_name="resume.pdf",
        status="Sent to SMTP server",
        db_path=test_db
    )
    add_history_record(
        recipient_email="recruiter2@firm.com",
        company_name="Firm Two",
        job_title="Backend Dev",
        subject="Application for Backend",
        body_snippet="Hello team",
        resume_name="resume.pdf",
        status="Failed",
        error_message="Authentication failed 535",
        db_path=test_db
    )

    records = get_history(db_path=test_db)
    assert len(records) == 2
    assert records[0]["recipient_email"] == "recruiter2@firm.com"
    assert records[0]["status"] == "Failed"
    assert records[0]["error_message"] == "Authentication failed 535"

    stats = get_history_stats(db_path=test_db)
    assert stats["total"] == 2
    assert stats["sent"] == 1
    assert stats["failed"] == 1

    if os.path.exists(test_db):
        os.remove(test_db)
