"""
database.py - SQLite storage for application history and user settings.
Passwords are NEVER stored in the database.
"""
import sqlite3
import os
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartapply.db")

DEFAULT_TEMPLATE_SUBJECT = "Application for {job_title} — {your_name}"
DEFAULT_TEMPLATE_BODY = """Dear Hiring Team,

I hope you are doing well.

I am writing to express my interest in the {job_title} position at {company}. Please find my resume attached for your consideration.

I would welcome the opportunity to discuss how my skills and experience align with your requirements.

Thank you for your time and consideration.

Best regards,
{your_name}
{your_contact}"""


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize SQLite tables if they do not exist."""
    conn = get_db(db_path)
    cursor = conn.cursor()

    # Application history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            company_name TEXT,
            job_title TEXT,
            subject TEXT NOT NULL,
            body_snippet TEXT,
            resume_name TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index for fast search and ordering
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_history_created 
        ON application_history(created_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_history_status 
        ON application_history(status)
    """)

    # Non-sensitive SMTP settings table (Passwords are strictly stored in .env)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smtp_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
            port INTEGER NOT NULL DEFAULT 587,
            security TEXT NOT NULL DEFAULT 'STARTTLS',
            sender_email TEXT NOT NULL DEFAULT '',
            sender_name TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert default SMTP row if empty
    cursor.execute("""
        INSERT OR IGNORE INTO smtp_settings (id, host, port, security, sender_email, sender_name)
        VALUES (1, 'smtp.gmail.com', 587, 'STARTTLS', '', '')
    """)

    # Template and sender profile settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS template_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            candidate_name TEXT NOT NULL DEFAULT 'Job Applicant',
            candidate_contact TEXT NOT NULL DEFAULT '',
            delay_seconds REAL NOT NULL DEFAULT 2.0,
            batch_limit INTEGER NOT NULL DEFAULT 5,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert default template row if empty
    cursor.execute("""
        INSERT OR IGNORE INTO template_settings (id, subject, body, candidate_name, candidate_contact, delay_seconds, batch_limit)
        VALUES (1, ?, ?, 'Job Applicant', '', 2.0, 5)
    """, (DEFAULT_TEMPLATE_SUBJECT, DEFAULT_TEMPLATE_BODY))

    conn.commit()
    conn.close()


def add_history_record(
    recipient_email: str,
    company_name: Optional[str],
    job_title: Optional[str],
    subject: str,
    body_snippet: Optional[str],
    resume_name: Optional[str],
    status: str,
    error_message: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Record an email dispatch attempt to the SQLite history."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO application_history 
        (recipient_email, company_name, job_title, subject, body_snippet, resume_name, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        recipient_email,
        company_name or "",
        job_title or "",
        subject,
        body_snippet or "",
        resume_name or "",
        status,
        error_message or ""
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_history(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve application history records with filtering and pagination."""
    conn = get_db(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM application_history WHERE 1=1"
    params = []

    if status_filter and status_filter.strip() and status_filter.lower() != "all":
        query += " AND status = ?"
        params.append(status_filter.strip())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (recipient_email LIKE ? OR company_name LIKE ? OR job_title LIKE ? OR subject LIKE ?)"
        params.extend([term, term, term, term])

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    return result


def get_history_stats(db_path: Optional[str] = None) -> Dict[str, int]:
    """Get aggregated statistics of sent, failed, and skipped applications."""
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM application_history")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM application_history WHERE status = 'Sent to SMTP server'")
    sent = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM application_history WHERE status = 'Failed'")
    failed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM application_history WHERE status LIKE 'Skipped%'")
    skipped = cursor.fetchone()[0]

    conn.close()
    return {
        "total": total,
        "sent": sent,
        "failed": failed,
        "skipped": skipped
    }


def clear_history(db_path: Optional[str] = None) -> None:
    """Clear all application history records."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM application_history")
    conn.commit()
    conn.close()


def get_smtp_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve non-sensitive SMTP settings."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT host, port, security, sender_email, sender_name FROM smtp_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "host": "smtp.gmail.com",
        "port": 587,
        "security": "STARTTLS",
        "sender_email": "",
        "sender_name": ""
    }


def save_smtp_settings(
    host: str,
    port: int,
    security: str,
    sender_email: str,
    sender_name: str,
    db_path: Optional[str] = None
) -> None:
    """Save non-sensitive SMTP settings."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE smtp_settings 
        SET host = ?, port = ?, security = ?, sender_email = ?, sender_name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (host, int(port), security, sender_email.strip(), sender_name.strip()))
    conn.commit()
    conn.close()


def get_template_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve default template & campaign defaults."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT subject, body, candidate_name, candidate_contact, delay_seconds, batch_limit 
        FROM template_settings WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "subject": DEFAULT_TEMPLATE_SUBJECT,
        "body": DEFAULT_TEMPLATE_BODY,
        "candidate_name": "Job Applicant",
        "candidate_contact": "",
        "delay_seconds": 2.0,
        "batch_limit": 5
    }


def save_template_settings(
    subject: str,
    body: str,
    candidate_name: str,
    candidate_contact: str,
    delay_seconds: float = 2.0,
    batch_limit: int = 5,
    db_path: Optional[str] = None
) -> None:
    """Save email template and campaign defaults."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE template_settings 
        SET subject = ?, body = ?, candidate_name = ?, candidate_contact = ?, delay_seconds = ?, batch_limit = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (subject, body, candidate_name.strip(), candidate_contact.strip(), float(delay_seconds), int(batch_limit)))
    conn.commit()
    conn.close()

