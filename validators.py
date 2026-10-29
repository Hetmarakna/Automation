"""
validators.py - Input validation and sanitation routines for SmartApply.
"""
import re
import os
from typing import Tuple

# RFC 5322 compliant simplified email regex
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Common non-email or static asset extensions to reject if regex falsely matches
INVALID_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf",
    ".doc", ".docx", ".zip", ".tar", ".gz", ".mp4", ".mp3",
    ".css", ".js", ".json", ".xml", ".html"
)


def validate_email(email: str) -> bool:
    """
    Validate that an email string is formatted properly.
    """
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) > 254:
        return False
    if not EMAIL_REGEX.match(email):
        return False
    # Check domain does not end in an image/asset extension
    lower = email.lower()
    for ext in INVALID_EXTENSIONS:
        if lower.endswith(ext):
            return False
    return True


def clean_email(email: str) -> str:
    """
    Trim whitespace, strip unwanted trailing punctuation, and normalize to lowercase.
    """
    if not email:
        return ""
    email = email.strip().strip(".,;:<>\"'()[]{}")
    return email.lower()


def validate_pdf_file(file_storage, max_size_mb: int = 15) -> Tuple[bool, str]:
    """
    Validate that an uploaded file is a valid PDF and does not exceed max size.
    file_storage: Werkzeug FileStorage object or a file-like object with .filename and .read/.seek
    """
    if not file_storage or not file_storage.filename:
        return False, "No file was selected for upload."

    filename = file_storage.filename.strip()
    base, ext = os.path.splitext(filename)
    if ext.lower() != ".pdf":
        return False, f"Invalid file format '{ext}'. Only PDF files (.pdf) are supported."

    # Check file size by seeking
    try:
        file_storage.seek(0, os.SEEK_END)
        size_bytes = file_storage.tell()
        file_storage.seek(0)
    except Exception as e:
        return False, f"Could not determine file size: {e}"

    if size_bytes == 0:
        return False, "The uploaded file is empty (0 bytes)."

    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        size_mb = size_bytes / (1024 * 1024)
        return False, f"File size ({size_mb:.1f} MB) exceeds maximum allowed limit of {max_size_mb} MB."

    # Validate PDF signature / magic bytes: %PDF-
    header = file_storage.read(5)
    file_storage.seek(0)
    if not header.startswith(b"%PDF"):
        return False, "The file does not appear to be a valid PDF document (missing %PDF header)."

    return True, "Valid PDF file."


def validate_smtp_config(host: str, port: any, security: str, sender_email: str) -> Tuple[bool, str]:
    """
    Validate basic SMTP parameters.
    """
    if not host or not str(host).strip():
        return False, "SMTP Host is required."
    
    try:
        port_num = int(port)
        if not (1 <= port_num <= 65535):
            return False, "SMTP Port must be between 1 and 65535."
    except (ValueError, TypeError):
        return False, "SMTP Port must be a valid integer."

    valid_security = ["STARTTLS", "SSL/TLS", "None"]
    if security not in valid_security:
        return False, f"Security option must be one of: {', '.join(valid_security)}."

    if not validate_email(sender_email):
        return False, "Sender email is invalid."

    return True, "Valid SMTP configuration."


def sanitize_text(text: str) -> str:
    """
    Basic text cleanup: strip null bytes and excessive whitespace.
    """
    if not text:
        return ""
    # Strip null characters to avoid issues in SQLite or email headers
    return text.replace("\x00", "").strip()
