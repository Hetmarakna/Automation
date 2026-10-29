"""
pdf_extractor.py - Extract readable text and email recipients from PDF, CSV, and Excel documents.
Supports .pdf (PyMuPDF), .csv (standard library csv), and .xlsx / .xls (openpyxl).
"""
import re
import os
import io
import csv
import fitz  # PyMuPDF
from typing import Dict, List, Any, Union, Optional
from validators import clean_email, validate_email

# Email extraction regex for finding emails embedded in general text
PDF_EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Column aliases for CSV / Excel spreadsheets
EMAIL_HEADER_ALIASES = {
    "email", "e-mail", "mail", "email address", "recruiter email",
    "contact email", "hr email", "to email", "recipient email",
    "email_address", "recruiter_email", "contact_email", "recipients"
}

COMPANY_HEADER_ALIASES = {
    "company", "company name", "organization", "firm", "employer",
    "client", "org", "companyname", "company_name", "business", "workplace"
}

JOB_HEADER_ALIASES = {
    "job title", "role", "position", "job", "title", "designation",
    "job role", "opening", "jobtitle", "job_title", "vacancy", "profile"
}

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


def _parse_tabular_rows(raw_rows: List[List[Any]], source_filename: str) -> Dict[str, Any]:
    """
    Parse generic grid / tabular rows (from CSV or Excel) into structured recipients.
    Automatically detects headers for Email, Company, Job Title, or falls back to cell regex.
    """
    if not raw_rows:
        return {
            "success": True,
            "filename": source_filename,
            "page_count": 1,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "The uploaded spreadsheet contains no data rows.",
            "recipients": [],
            "raw_text_preview": ""
        }

    # Normalize rows to string lists
    str_rows = []
    for r in raw_rows:
        row_vals = [str(cell).strip() if cell is not None else "" for cell in r]
        if any(row_vals):  # skip completely empty lines
            str_rows.append(row_vals)

    if not str_rows:
        return {
            "success": True,
            "filename": source_filename,
            "page_count": 1,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "No data found in spreadsheet.",
            "recipients": [],
            "raw_text_preview": ""
        }

    # Detect header row
    header_idx = -1
    email_col = -1
    company_col = -1
    job_col = -1

    for row_idx, row in enumerate(str_rows[:5]):
        for col_idx, cell in enumerate(row):
            norm = cell.lower().replace("_", " ").strip()
            if norm in EMAIL_HEADER_ALIASES and email_col == -1:
                email_col = col_idx
                header_idx = row_idx
            elif norm in COMPANY_HEADER_ALIASES and company_col == -1:
                company_col = col_idx
            elif norm in JOB_HEADER_ALIASES and job_col == -1:
                job_col = col_idx

        if email_col != -1:
            break

    seen_emails = set()
    recipients = []
    data_rows = str_rows[header_idx + 1:] if header_idx != -1 else str_rows

    for row_idx, row in enumerate(data_rows):
        email_val = ""
        comp_val = ""
        job_val = ""

        if email_col != -1 and email_col < len(row):
            # Header column found
            raw_cell = row[email_col]
            match = PDF_EMAIL_REGEX.search(raw_cell)
            if match:
                email_val = match.group(0)
            elif validate_email(clean_email(raw_cell)):
                email_val = clean_email(raw_cell)

            if company_col != -1 and company_col < len(row):
                comp_val = row[company_col]
            if job_col != -1 and job_col < len(row):
                job_val = row[job_col]
        else:
            # Fallback: scan all cells in the row for an email
            found_col = -1
            for c_idx, cell in enumerate(row):
                match = PDF_EMAIL_REGEX.search(cell)
                if match:
                    email_val = match.group(0)
                    found_col = c_idx
                    break

            if email_val:
                # Use other non-empty cells in the same row as company and title hints
                other_cells = [cell for c_idx, cell in enumerate(row) if c_idx != found_col and cell.strip()]
                if len(other_cells) >= 1:
                    comp_val = other_cells[0]
                if len(other_cells) >= 2:
                    job_val = other_cells[1]

        if email_val:
            cleaned = clean_email(email_val)
            if validate_email(cleaned) and cleaned not in seen_emails:
                seen_emails.add(cleaned)
                if not comp_val:
                    comp_val = _infer_company_from_email(cleaned)

                recipients.append({
                    "id": len(recipients) + 1,
                    "email": cleaned,
                    "company": comp_val.strip(),
                    "job_title": job_val.strip(),
                    "source_page": f"Row {row_idx + (2 if header_idx != -1 else 1)}",
                    "selected": True
                })

    notice = f"Successfully extracted {len(recipients)} unique recipient{'s' if len(recipients) != 1 else ''} from {source_filename}."
    if not recipients:
        notice = f"No valid email addresses were found in {source_filename}. Check that the spreadsheet contains an Email column."

    preview_lines = ["\t".join(r[:4]) for r in str_rows[:10]]
    preview = "\n".join(preview_lines)

    return {
        "success": True,
        "filename": source_filename,
        "page_count": 1,
        "total_characters": sum(len(" ".join(r)) for r in str_rows),
        "is_scanned": False,
        "notice": notice,
        "recipients": recipients,
        "raw_text_preview": preview
    }


def extract_emails_from_csv(csv_source: Union[str, bytes], source_filename: str = "recipients.csv") -> Dict[str, Any]:
    """
    Extract recipients from CSV file bytes or path.
    Handles various encodings (UTF-8, UTF-8-BOM, Latin-1) and delimiters (comma, semicolon, tab).
    """
    try:
        if isinstance(csv_source, bytes):
            raw_bytes = csv_source
        else:
            with open(csv_source, "rb") as f:
                raw_bytes = f.read()

        # Graceful decoding
        text = None
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            text = raw_bytes.decode("utf-8", errors="replace")

        # Sniff delimiter
        sample = text[:2048]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except Exception:
            # Fallback check
            if "\t" in sample and sample.count("\t") > sample.count(","):
                delimiter = "\t"
            elif ";" in sample and sample.count(";") > sample.count(","):
                delimiter = ";"

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [list(r) for r in reader]
        return _parse_tabular_rows(rows, source_filename)

    except Exception as e:
        return {
            "success": False,
            "filename": source_filename,
            "error": f"Failed to parse CSV file: {str(e)}",
            "page_count": 0,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "Error parsing CSV.",
            "recipients": [],
            "raw_text_preview": ""
        }


def extract_emails_from_excel(excel_source: Union[str, bytes], source_filename: str = "recipients.xlsx") -> Dict[str, Any]:
    """
    Extract recipients from Excel (.xlsx or .xls) file using openpyxl.
    """
    try:
        import openpyxl

        if isinstance(excel_source, bytes):
            stream = io.BytesIO(excel_source)
        else:
            stream = excel_source

        wb = openpyxl.load_workbook(stream, read_only=True, data_only=True)
        # Read from active sheet or first sheet
        ws = wb.active or wb.worksheets[0]

        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))

        wb.close()
        return _parse_tabular_rows(rows, source_filename)

    except Exception as e:
        return {
            "success": False,
            "filename": source_filename,
            "error": f"Failed to parse Excel workbook: {str(e)}",
            "page_count": 0,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "Error parsing Excel workbook.",
            "recipients": [],
            "raw_text_preview": ""
        }


def extract_recipients_from_file(file_source: Union[str, bytes], filename: str) -> Dict[str, Any]:
    """
    Unified dispatcher to extract recipients from PDF, CSV, or Excel files based on filename extension.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return extract_emails_from_csv(file_source, source_filename=filename)
    elif ext in [".xlsx", ".xls"]:
        return extract_emails_from_excel(file_source, source_filename=filename)
    elif ext == ".pdf":
        return extract_emails_from_pdf(file_source, source_filename=filename)
    else:
        return {
            "success": False,
            "filename": filename,
            "error": f"Unsupported file type '{ext}'. Please upload a PDF, CSV, or Excel file.",
            "page_count": 0,
            "total_characters": 0,
            "is_scanned": False,
            "notice": "Unsupported format.",
            "recipients": [],
            "raw_text_preview": ""
        }


