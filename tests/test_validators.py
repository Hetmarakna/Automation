"""
test_validators.py - Tests for input validation and sanitation.
"""
import io
from validators import (
    validate_email, clean_email, validate_pdf_file,
    validate_import_file, validate_smtp_config, sanitize_text
)


class DummyFileStorage:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._stream = io.BytesIO(content)

    def read(self, size=-1):
        return self._stream.read(size)

    def seek(self, offset, whence=0):
        return self._stream.seek(offset, whence)

    def tell(self):
        return self._stream.tell()


def test_valid_emails():
    valid_cases = [
        "recruiter@google.com",
        "john.doe@company.org",
        "careers+engineering@tech.co.uk",
        "hr_team123@sub.domain.io"
    ]
    for email in valid_cases:
        assert validate_email(email) is True


def test_invalid_emails():
    invalid_cases = [
        "",
        "notanemail",
        "missingatsign.com",
        "@nodomain.com",
        "spaces in@address.com",
        "image@domain.png",  # Reject image extensions
        "doc@domain.pdf",
        None,
        12345
    ]
    for email in invalid_cases:
        assert validate_email(email) is False


def test_clean_email():
    assert clean_email("  Recruiter@Example.COM.  ") == "recruiter@example.com"
    assert clean_email("<candidate@firm.org>") == "candidate@firm.org"
    assert clean_email("") == ""


def test_pdf_validation_success():
    valid_pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    file_obj = DummyFileStorage("my_resume.pdf", valid_pdf_content)
    is_valid, msg = validate_pdf_file(file_obj)
    assert is_valid is True
    assert "Valid PDF" in msg


def test_pdf_validation_wrong_extension():
    file_obj = DummyFileStorage("resume.docx", b"%PDF-dummy")
    is_valid, msg = validate_pdf_file(file_obj)
    assert is_valid is False
    assert "Only PDF files" in msg


def test_pdf_validation_invalid_header():
    file_obj = DummyFileStorage("document.pdf", b"NOT_A_REAL_PDF_HEADER")
    is_valid, msg = validate_pdf_file(file_obj)
    assert is_valid is False
    assert "missing %PDF header" in msg


def test_pdf_validation_empty_file():
    file_obj = DummyFileStorage("empty.pdf", b"")
    is_valid, msg = validate_pdf_file(file_obj)
    assert is_valid is False
    assert "empty" in msg.lower()


def test_pdf_validation_oversize():
    # 2 MB file with limit 1 MB
    big_content = b"%PDF-" + b"0" * (2 * 1024 * 1024)
    file_obj = DummyFileStorage("large.pdf", big_content)
    is_valid, msg = validate_pdf_file(file_obj, max_size_mb=1)
    assert is_valid is False
    assert "exceeds maximum allowed limit" in msg


def test_validate_smtp_config():
    # Valid
    ok, _ = validate_smtp_config("smtp.gmail.com", 587, "STARTTLS", "user@gmail.com")
    assert ok is True

    # Invalid port
    ok, err = validate_smtp_config("smtp.gmail.com", 99999, "STARTTLS", "user@gmail.com")
    assert ok is False
    assert "Port" in err

    # Invalid host
    ok, err = validate_smtp_config("", 587, "STARTTLS", "user@gmail.com")
    assert ok is False
    assert "Host" in err

    # Invalid security
    ok, err = validate_smtp_config("smtp.gmail.com", 587, "INVALID_SEC", "user@gmail.com")
    assert ok is False

    # Invalid sender email
    ok, err = validate_smtp_config("smtp.gmail.com", 587, "STARTTLS", "invalid_email")
    assert ok is False
    assert "Sender email" in err


def test_sanitize_text():
    assert sanitize_text("  Hello \x00 World  ") == "Hello  World"
    assert sanitize_text(None) == ""


def test_validate_import_file():
    # Valid CSV
    csv_file = DummyFileStorage("leads.csv", b"Email,Company\na@b.com,Co\n")
    ok, msg = validate_import_file(csv_file)
    assert ok is True
    assert "CSV" in msg

    # Valid Excel (.xlsx) with PK zip magic header
    xlsx_file = DummyFileStorage("data.xlsx", b"PK\x03\x04excelcontents")
    ok, msg = validate_import_file(xlsx_file)
    assert ok is True
    assert "XLSX" in msg

    # Invalid extension (.txt)
    txt_file = DummyFileStorage("readme.txt", b"some text")
    ok, msg = validate_import_file(txt_file)
    assert ok is False
    assert "Invalid format" in msg


