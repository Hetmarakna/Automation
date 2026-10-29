"""
pdf_extractor.py - Extract readable text and email recipients from PDF documents using PyMuPDF.
"""
import re
import fitz  # PyMuPDF
from typing import Dict, List, Any, Union
from validators import clean_email, validate_email

# Email extraction regex for finding emails embedded in general text
PDF_EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Common free webmail domains that should not be used as company name fallbacks
GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "protonmail.com", "mail.com", "aol.com", "zoho.com", "gmx.com", "yandex.com"
}


def _infer_company_from_email(email: str) -> str:
    """Infer a human-readable company name from an email domain if not generic."""
    try:
        domain = email.split("@")[1].lower()
        if domain in GENERIC_DOMAINS:
            return ""
        # e.g., acme-corp.co.uk -> acme-corp -> Acme Corp
        parts = domain.split(".")
        name_part = parts[0]
        # Clean hyphens and underscores
        cleaned = re.sub(r"[-_]+", " ", name_part).strip().title()
        return cleaned if len(cleaned) > 1 else ""
    except Exception:
        return ""


def _extract_context_fields(lines: List[str], email_line_idx: int, email: str) -> Dict[str, str]:
    """
    Look around the email in neighboring lines to detect company or job title cues.
    """
    company = ""
    job_title = ""

    # Check a window of 3 lines before and 3 lines after
    start_idx = max(0, email_line_idx - 3)
    end_idx = min(len(lines), email_line_idx + 4)
    window = lines[start_idx:end_idx]

    for line in window:
        line_clean = line.strip()
        if not line_clean or line_clean == email:
            continue

        # Look for explicit company patterns
        comp_match = re.search(r"(?:company|organization|at|client)\s*[:\-]\s*([A-Za-z0-9 &.,'-]{2,50})", line_clean, re.IGNORECASE)
        if comp_match and not company:
            company = comp_match.group(1).strip()

        # Look for explicit job/role patterns
        job_match = re.search(r"(?:position|role|job\s*title|opening|looking\s*for)\s*[:\-]\s*([A-Za-z0-9 /&.,'-]{2,60})", line_clean, re.IGNORECASE)
        if job_match and not job_title:
            job_title = job_match.group(1).strip()

    # Fallback to domain for company if still empty
    if not company:
        company = _infer_company_from_email(email)

    return {"company": company, "job_title": job_title}


def extract_emails_from_pdf(pdf_source: Union[str, bytes], source_filename: str = "document.pdf") -> Dict[str, Any]:
    """
    Extract readable text and all unique email addresses from a PDF document.
    pdf_source: file path (str) or raw bytes of the PDF.
    
    Returns a dict with:
      - success (bool)
      - filename (str)
      - page_count (int)
      - total_characters (int)
      - is_scanned (bool)
      - notice (str)
      - recipients (list of dicts: email, company, job_title, source_page, selected)
      - raw_text_preview (str)
    """
    try:
        if isinstance(pdf_source, bytes):
            doc = fitz.open(stream=pdf_source, filetype="pdf")
        else:
            doc = fitz.open(pdf_source)
    except Exception as e:
        return {
            "success": False,
            "filename": source_filename,
            "error": f"Failed to open PDF document: {str(e)}",
            "page_count": 0,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "Error opening document.",
            "recipients": [],
            "raw_text_preview": ""
        }

    total_pages = doc.page_count
    total_text = ""
    page_texts = []

    for page_idx in range(total_pages):
        page = doc[page_idx]
        text = page.get_text("text") or ""
        total_text += text + "\n"
        page_texts.append(text)

    doc.close()

    total_chars = len(total_text.strip())
    is_scanned = (total_pages > 0 and total_chars < 30)

    notice = ""
    if is_scanned:
        notice = (
            "Scanned or image-based PDF detected with minimal selectable text. "
            "SmartApply extracts readable text directly from PDFs; an OCR (Optical Character Recognition) "
            "tool would be required to extract text from pure images. No emails were found in the digital text layer."
        )

    # Extract all emails preserving order and deduplicating
    seen_emails = set()
    recipients = []

    for page_idx, page_text in enumerate(page_texts):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for line_idx, line in enumerate(lines):
            matches = PDF_EMAIL_REGEX.findall(line)
            for raw_match in matches:
                clean = clean_email(raw_match)
                if validate_email(clean) and clean not in seen_emails:
                    seen_emails.add(clean)
                    context = _extract_context_fields(lines, line_idx, clean)
                    recipients.append({
                        "id": len(recipients) + 1,
                        "email": clean,
                        "company": context["company"],
                        "job_title": context["job_title"],
                        "source_page": page_idx + 1,
                        "selected": True
                    })

    if not is_scanned and not recipients:
        notice = "No email addresses were found in this document. You can add recipients manually below."
    elif recipients:
        notice = f"Successfully extracted {len(recipients)} unique recipient email{'s' if len(recipients) != 1 else ''} from {total_pages} page{'s' if total_pages != 1 else ''}."

    # Preview of extracted text (truncated safely for UI review)
    preview = total_text[:1200] + ("..." if len(total_text) > 1200 else "")

    return {
        "success": True,
        "filename": source_filename,
        "page_count": total_pages,
        "total_characters": total_chars,
        "is_scanned": is_scanned,
        "notice": notice,
        "recipients": recipients,
        "raw_text_preview": preview
    }
