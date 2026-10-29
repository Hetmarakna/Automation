# SmartApply — Job Application Email Automation

A complete, functional desktop-friendly web application that automates sending personalized job application emails using Python, **without paid APIs, AI APIs, browser automation, or third-party email sending services**.

---

## 🌟 Key Features

- **Multi-Format Contact Import (PDF, CSV, Excel)**:
  - Drag-and-drop interface supporting **PDF (.pdf)**, **CSV (.csv)**, and **Excel (.xlsx, .xls)**.
  - Extracts text layers from PDFs via **PyMuPDF (`fitz`)**, and spreadsheet grids via **openpyxl** and the standard `csv` library.
  - Auto-maps standard spreadsheet column headers (`Email`, `Company`, `Job Title` / `Role`) or regex scans cell values.
  - Automatic email deduplication and company domain inference.
  - Transparent scanned document detection: clearly informs when a PDF is a scanned image with no selectable text layer.
  - **Zero auto-sending**: Extracted emails are never dispatched automatically.

- **PDF Resume Management**:
  - Upload, replace, or remove your PDF resume.
  - Validates file extensions, headers (`%PDF`), and safe size limits.
  - Automatically attaches the resume to outgoing emails without altering the original file.

- **Professional Email Composer**:
  - Pre-loaded with customizable job application templates.
  - Real-time dynamic placeholders: `{company}`, `{job_title}`, `{your_name}`, `{your_contact}`, and `{recipient_email}`.
  - Live preview frame with recipient switcher to inspect rendered emails.
  - Send Test Email functionality to verify presentation in your own inbox.

- **Standard Library SMTP Engine**:
  - Uses Python's built-in `smtplib` and `email.message`.
  - Native presets for Gmail (`smtp.gmail.com:587`, STARTTLS), Outlook / Microsoft 365, and custom servers.
  - Secure credential storage: Passwords are saved in a local `.env` file (excluded from Git) and are **never stored in the SQLite database**.
  - Interactive **Test Connection** tool with diagnostic feedback for code 535 authentication errors and network timeouts.

- **Controlled Safe Sending Workflow**:
  - Strict explicit confirmation required before sending.
  - Individual messaging (recipients are never grouped in shared CC or BCC fields).
  - Configurable rate-delay intervals (e.g. 2–5 seconds) to avoid spam filters.
  - Per-session batch limit (default 5) to prevent accidental bulk dispatches.
  - Real-time **Pause**, **Resume**, and **Cancel** controls during sending.
  - Intra-batch deduplication: skips duplicate email addresses automatically.

- **Local Application History**:
  - SQLite audit trail storing recipient, company, job title, subject, timestamp, and status.
  - Transparent SMTP status labeling: successfully queued emails are labeled **"Sent to SMTP server"** (acknowledging outgoing handoff without falsely guaranteeing inbox delivery).
  - Filter by status, search by keywords, and export to CSV.

- **Premium SaaS UI/UX**:
  - Charcoal navy sidebar, indigo accents, rounded cards, elevation shadows, and inline SVG Lucide icons.
  - 100% offline-ready: bundled CSS and JavaScript without external CDN dependencies.

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| **Backend** | Python 3.9+ with Flask |
| **Frontend** | HTML5, CSS3, JavaScript (Vanilla ES6), Bootstrap 5.3 |
| **PDF Extraction** | PyMuPDF (`fitz`) |
| **Email Protocol** | Python Standard Library (`smtplib`, `email.message`) |
| **Database** | SQLite3 (`sqlite3`) |
| **Configuration** | `python-dotenv` & `.env` |
| **Test Suite** | `pytest` with mocked SMTP connections |

---

## 📁 Project Structure

```
Automation/
├── app.py                      # Flask web application & API routing
├── job_application.py          # Application entrypoint alias
├── email_sender.py             # SMTP connection, message builder & CampaignManager
├── pdf_extractor.py            # PyMuPDF text & email extraction logic
├── validators.py               # File validation, email RFC check, sanitization
├── database.py                 # SQLite schema, history persistence, templates
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── .env.example                # Example configuration template
├── .gitignore                  # Git exclusions for secrets, uploads, and db
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               # Shared SaaS layout, sidebar, modals
│   ├── dashboard.html          # Overview, KPIs, quick-start, recent activity
│   ├── import_pdf.html         # Drag & drop upload, extraction table, add recipient
│   ├── composer.html           # Resume upload, template editor, live preview
│   ├── smtp_settings.html      # SMTP config, Gmail guide, test connection
│   ├── history.html            # Application audit log, details modal, CSV export
│   └── help.html               # Step-by-step Gmail App Password setup guide
├── static/
│   ├── css/
│   │   ├── bootstrap.min.css   # Offline Bootstrap 5.3 styling
│   │   └── style.css           # Custom SaaS dashboard stylesheet
│   └── js/
│       ├── bootstrap.bundle.min.js # Offline Bootstrap JS
│       └── app.js              # Reactive UI controller & sending engine
├── uploads/                    # Local storage for resumes & documents
│   └── resumes/
└── tests/                      # Automated test suite
    ├── test_app_routes.py      # Flask route & API tests
    ├── test_email_sender.py    # SMTP, email creation, and batch engine tests
    ├── test_pdf_extractor.py   # PDF text & deduplication tests
    └── test_validators.py      # Input validation & security tests
```

---

## 🚀 Installation & Execution

### Windows (PowerShell)

```powershell
# 1. Create a virtual environment
py -m venv .venv

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1

# 3. Install dependencies
python -m pip install -r requirements.txt

# 4. Run the web application
python app.py
```

### macOS / Linux

```bash
# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Install dependencies
python3 -m pip install -r requirements.txt

# 4. Run the web application
python3 app.py
```

Once running, navigate your web browser to:
**`http://127.0.0.1:5000`**

---

## 🔒 Gmail App Password Setup Guide

Google accounts with 2-Step Verification do not permit logging in with standard account passwords on SMTP clients. Follow these steps to generate a safe 16-character App Password:

1. Go to your **[Google Account Security Settings](https://myaccount.google.com/security)**.
2. Confirm that **2-Step Verification** is enabled under the *"How you sign in to Google"* section.
3. Open **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)** in your browser.
4. Enter `SmartApply` in the **App name** field and click **Create**.
5. Google will display a 16-character code (e.g. `abcd efgh ijkl mnop`).
6. In SmartApply, go to **SMTP Settings**, paste the 16 characters into the **App Password** field, and click **Test Connection**.

> **Security Note:** SmartApply saves this password exclusively in your local `.env` file on your hard drive. It is never transmitted to any third party and is never written into the SQLite database.

---

## 📖 How to Send Your First Job Application

1. **Configure SMTP**: Go to **SMTP Settings** (`/smtp`), enter your sender email and Gmail App Password, then click **Test Connection** to confirm connectivity. Click **Save Configuration**.
2. **Import Job Openings**: Go to **Import Job Details** (`/import`), drag and drop a PDF listing openings or recruiter contacts. Review the extracted table, adjust company names or roles if needed, and click **Continue to Composer**.
3. **Upload Resume**: In the **Email Composer** (`/composer`), upload your PDF resume.
4. **Customize Message**: Review the email subject and body. Insert dynamic placeholders like `{company}` or `{job_title}`. Use the live preview on the right to verify how the email looks for each recipient.
5. **Send a Test Email**: Click **Send Test Email**, input your own personal address, and verify receipt in your inbox.
6. **Launch Campaign**: Click **Review & Send**. Inspect the safety checklist (total recipients, rate delay, batch session limit), check the confirmation box, and click **Confirm & Start Sending**.
7. **Monitor & Track**: Observe real-time progress in the dispatch modal (with Pause and Cancel controls). After completion, check **Application History** (`/history`) for an audit trail or export records to CSV.

---

## 🧪 Running the Test Suite

SmartApply includes an automated `pytest` test suite that verifies PDF extraction, deduplication, input validation, template interpolation, mocked SMTP connectivity, and bulk send cancellation without sending real emails:

```bash
# Activate your virtual environment and run:
pytest -v
```

All tests run locally in sandbox mode using mocked SMTP connections.

