"""
test_pdf_extractor.py - Tests for PDF extraction, deduplication, and context detection.
"""
import fitz  # PyMuPDF
from pdf_extractor import extract_emails_from_pdf


def create_sample_pdf_bytes(text_content: str) -> bytes:
    """Helper to generate a valid in-memory PDF using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text_content)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


def test_extract_emails_success():
    sample_text = """
    Tech Openings 2026:
    Company: Acme Cloud Solutions
    Position: Senior Python Developer
    Please send resumes to: careers@acmecloud.com

    For questions, contact our recruiter at: recruiter@acmecloud.com
    """
    pdf_bytes = create_sample_pdf_bytes(sample_text)
    result = extract_emails_from_pdf(pdf_bytes, source_filename="jobs.pdf")

    assert result["success"] is True
    assert result["is_scanned"] is False
    assert len(result["recipients"]) == 2

    emails = [r["email"] for r in result["recipients"]]
    assert "careers@acmecloud.com" in emails
    assert "recruiter@acmecloud.com" in emails

    # Check context extraction
    first = result["recipients"][0]
    assert first["company"] == "Acme Cloud Solutions"
    assert first["job_title"] == "Senior Python Developer"


def test_extract_emails_deduplication():
    # PDF containing repeated emails
    repeated_text = """
    Open Role: Data Engineer
    Contact: jobs@company.org
    Repeat listing:
    Contact: jobs@company.org
    Also reach out to: jobs@company.org
    And secondary: info@company.org
    """
    pdf_bytes = create_sample_pdf_bytes(repeated_text)
    result = extract_emails_from_pdf(pdf_bytes)

    assert result["success"] is True
    assert len(result["recipients"]) == 2
    emails = [r["email"] for r in result["recipients"]]
    assert emails == ["jobs@company.org", "info@company.org"]


def test_scanned_pdf_detection():
    # PDF with virtually no text layer (e.g. image-only scan)
    scanned_text = "   \n "
    pdf_bytes = create_sample_pdf_bytes(scanned_text)
    result = extract_emails_from_pdf(pdf_bytes, source_filename="scanned_resume.pdf")

    assert result["success"] is True
    assert result["is_scanned"] is True
    assert "Scanned or image-based PDF" in result["notice"]
    assert "OCR" in result["notice"]
    assert len(result["recipients"]) == 0


def test_malformed_pdf_bytes():
    bad_bytes = b"This is not a real PDF document at all"
    result = extract_emails_from_pdf(bad_bytes, source_filename="corrupted.pdf")
    assert result["success"] is False
    assert "Failed to open PDF document" in result["error"]
