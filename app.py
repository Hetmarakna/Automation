"""
app.py - SmartApply: Job Application Email Automation Web Application
Runs 100% locally on localhost without third-party email APIs or AI APIs.
"""
import os
import io
import csv
import secrets
from typing import Dict, Any, Optional
from flask import (
    Flask, render_template, request, jsonify,
    send_file, session, redirect, url_for
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

from database import (
    init_db, get_history, get_history_stats, clear_history,
    get_smtp_settings, save_smtp_settings,
    get_template_settings, save_template_settings,
    add_history_record
)
from validators import (
    validate_email, clean_email, validate_pdf_file,
    validate_smtp_config, sanitize_text
)
from pdf_extractor import extract_emails_from_pdf
from email_sender import (
    test_smtp_connection, build_email_message,
    render_template as interpolate_template,
    campaign_manager
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
RESUME_DIR = os.path.join(UPLOAD_DIR, "resumes")
TEMP_DIR = os.path.join(UPLOAD_DIR, "temp")
ENV_PATH = os.path.join(BASE_DIR, ".env")

os.makedirs(RESUME_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", secrets.token_hex(24))
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

# Initialize database
init_db()


def get_current_resume_path() -> Optional[str]:
    """Find the path of the currently uploaded resume, if any."""
    files = [f for f in os.listdir(RESUME_DIR) if f.lower().endswith(".pdf")]
    if files:
        # Return the newest file
        files.sort(key=lambda x: os.path.getmtime(os.path.join(RESUME_DIR, x)), reverse=True)
        return os.path.join(RESUME_DIR, files[0])
    return None


def update_env_variable(key: str, value: str) -> None:
    """Safely write or update a key=value pair in the local .env file."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value


def get_effective_smtp_config() -> Dict[str, Any]:
    """Retrieve combined SMTP configuration from SQLite settings and .env password."""
    db_config = get_smtp_settings()
    # Check environment variable first for host/port/sender if not in DB
    host = db_config.get("host") or os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = db_config.get("port") or int(os.getenv("SMTP_PORT", 587))
    security = db_config.get("security") or os.getenv("SMTP_SECURITY", "STARTTLS")
    sender_email = db_config.get("sender_email") or os.getenv("SMTP_SENDER_EMAIL", "")
    sender_name = db_config.get("sender_name") or os.getenv("SMTP_SENDER_NAME", "")
    password = os.getenv("SMTP_PASSWORD", "")

    return {
        "host": host,
        "port": port,
        "security": security,
        "username": sender_email,
        "sender_name": sender_name,
        "password": password,
        "has_password": bool(password and len(password.strip()) > 0)
    }


# ==========================================
# PAGE ROUTES
# ==========================================

@app.route("/")
def dashboard_page():
    stats = get_history_stats()
    smtp_cfg = get_effective_smtp_config()
    resume_path = get_current_resume_path()
    resume_name = os.path.basename(resume_path) if resume_path else None
    recent_history = get_history(limit=5)
    return render_template(
        "dashboard.html",
        stats=stats,
        smtp_cfg=smtp_cfg,
        resume_name=resume_name,
        recent_history=recent_history,
        active_page="dashboard"
    )


@app.route("/import")
def import_page():
    return render_template("import_pdf.html", active_page="import")


@app.route("/composer")
def composer_page():
    smtp_cfg = get_effective_smtp_config()
    template_cfg = get_template_settings()
    resume_path = get_current_resume_path()
    resume_info = None
    if resume_path:
        size_kb = round(os.path.getsize(resume_path) / 1024, 1)
        resume_info = {
            "filename": os.path.basename(resume_path),
            "size_kb": size_kb
        }
    return render_template(
        "composer.html",
        smtp_cfg=smtp_cfg,
        template_cfg=template_cfg,
        resume_info=resume_info,
        active_page="composer"
    )


@app.route("/smtp")
def smtp_page():
    smtp_cfg = get_effective_smtp_config()
    return render_template("smtp_settings.html", smtp_cfg=smtp_cfg, active_page="smtp")


@app.route("/history")
def history_page():
    stats = get_history_stats()
    history_records = get_history(limit=200)
    return render_template(
        "history.html",
        stats=stats,
        history_records=history_records,
        active_page="history"
    )


@app.route("/help")
def help_page():
    return render_template("help.html", active_page="help")


# ==========================================
# API ENDPOINTS
# ==========================================

@app.route("/api/upload-pdf", methods=["POST"])
def api_upload_pdf():
    """Upload job details PDF and extract email recipients."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    file = request.files["file"]
    is_valid, err_msg = validate_pdf_file(file, max_size_mb=15)
    if not is_valid:
        return jsonify({"success": False, "error": err_msg}), 400

    original_name = secure_filename(file.filename) or "document.pdf"
    file_bytes = file.read()

    result = extract_emails_from_pdf(file_bytes, source_filename=original_name)
    return jsonify(result)


@app.route("/api/upload-resume", methods=["POST"])
def api_upload_resume():
    """Upload and validate candidate PDF resume."""
    if "resume" not in request.files:
        return jsonify({"success": False, "error": "No resume file provided."}), 400

    file = request.files["resume"]
    is_valid, err_msg = validate_pdf_file(file, max_size_mb=10)
    if not is_valid:
        return jsonify({"success": False, "error": err_msg}), 400

    # Clear old resumes
    for old_file in os.listdir(RESUME_DIR):
        try:
            os.remove(os.path.join(RESUME_DIR, old_file))
        except Exception:
            pass

    safe_name = secure_filename(file.filename) or "resume.pdf"
    save_path = os.path.join(RESUME_DIR, safe_name)
    file.save(save_path)

    size_kb = round(os.path.getsize(save_path) / 1024, 1)
    return jsonify({
        "success": True,
        "filename": safe_name,
        "size_kb": size_kb,
        "message": f"Resume '{safe_name}' ({size_kb} KB) uploaded successfully."
    })


@app.route("/api/remove-resume", methods=["POST"])
def api_remove_resume():
    """Remove existing uploaded resume."""
    removed_any = False
    for old_file in os.listdir(RESUME_DIR):
        try:
            os.remove(os.path.join(RESUME_DIR, old_file))
            removed_any = True
        except Exception:
            pass
    return jsonify({"success": True, "removed": removed_any})


@app.route("/api/resume-info", methods=["GET"])
def api_resume_info():
    """Get current resume status."""
    resume_path = get_current_resume_path()
    if resume_path and os.path.exists(resume_path):
        return jsonify({
            "has_resume": True,
            "filename": os.path.basename(resume_path),
            "size_kb": round(os.path.getsize(resume_path) / 1024, 1)
        })
    return jsonify({"has_resume": False})


@app.route("/api/test-smtp", methods=["POST"])
def api_test_smtp():
    """Test SMTP connection and credentials."""
    data = request.get_json(silent=True) or {}
    host = data.get("host", "").strip()
    port = data.get("port")
    security = data.get("security", "STARTTLS")
    sender_email = data.get("sender_email", "").strip()
    password = data.get("password", "").strip()

    # If password is empty in request, fallback to saved .env password
    if not password:
        password = os.getenv("SMTP_PASSWORD", "")

    # Validate inputs
    is_valid, val_err = validate_smtp_config(host, port, security, sender_email)
    if not is_valid:
        return jsonify({"success": False, "message": val_err}), 400

    if not password:
        return jsonify({
            "success": False,
            "message": "Password is required for SMTP connection test. Please provide your Gmail App Password."
        }), 400

    success, message = test_smtp_connection(
        host=host,
        port=int(port),
        security=security,
        username=sender_email,
        password=password
    )
    return jsonify({"success": success, "message": message})


@app.route("/api/save-smtp", methods=["POST"])
def api_save_smtp():
    """Save SMTP configuration and securely store App Password in .env."""
    data = request.get_json(silent=True) or {}
    host = data.get("host", "smtp.gmail.com").strip()
    port = data.get("port", 587)
    security = data.get("security", "STARTTLS")
    sender_email = data.get("sender_email", "").strip()
    sender_name = data.get("sender_name", "").strip()
    password = data.get("password", "").strip()

    is_valid, err_msg = validate_smtp_config(host, port, security, sender_email)
    if not is_valid:
        return jsonify({"success": False, "message": err_msg}), 400

    # Save non-sensitive settings to SQLite
    save_smtp_settings(host, int(port), security, sender_email, sender_name)

    # If a new password was submitted, save to .env
    if password:
        update_env_variable("SMTP_PASSWORD", password)

    return jsonify({
        "success": True,
        "message": "SMTP configuration saved securely.",
        "has_password": bool(os.getenv("SMTP_PASSWORD"))
    })


@app.route("/api/template", methods=["GET", "POST"])
def api_template():
    """Retrieve or save template and campaign defaults."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        subject = sanitize_text(data.get("subject", ""))
        body = data.get("body", "").strip()
        candidate_name = sanitize_text(data.get("candidate_name", "Job Applicant"))
        candidate_contact = sanitize_text(data.get("candidate_contact", ""))
        delay_seconds = float(data.get("delay_seconds", 2.0))
        batch_limit = int(data.get("batch_limit", 5))

        if not subject:
            return jsonify({"success": False, "message": "Email subject cannot be empty."}), 400
        if not body:
            return jsonify({"success": False, "message": "Email body cannot be empty."}), 400

        save_template_settings(
            subject=subject,
            body=body,
            candidate_name=candidate_name,
            candidate_contact=candidate_contact,
            delay_seconds=delay_seconds,
            batch_limit=batch_limit
        )
        return jsonify({"success": True, "message": "Template saved successfully."})

    template_cfg = get_template_settings()
    return jsonify(template_cfg)


@app.route("/api/send/test", methods=["POST"])
def api_send_test():
    """Send a single test email to the user's test address."""
    data = request.get_json(silent=True) or {}
    test_recipient = clean_email(data.get("test_recipient", ""))
    subject_tmpl = data.get("subject", "")
    body_tmpl = data.get("body", "")
    candidate_name = data.get("candidate_name", "Job Applicant")
    candidate_contact = data.get("candidate_contact", "")

    if not validate_email(test_recipient):
        return jsonify({"success": False, "message": "Please provide a valid test recipient email address."}), 400

    smtp_cfg = get_effective_smtp_config()
    if not smtp_cfg.get("has_password") or not smtp_cfg.get("username"):
        return jsonify({"success": False, "message": "SMTP settings are incomplete. Please configure your sender email and App Password in SMTP Settings."}), 400

    # Interpolate template with sample context
    context = {
        "company": "Acme Innovations (Sample)",
        "job_title": "Software Engineer (Sample)",
        "your_name": candidate_name,
        "your_contact": candidate_contact,
        "recipient_email": test_recipient
    }
    rendered_subject = f"[TEST EMAIL] {interpolate_template(subject_tmpl, context)}"
    rendered_body = interpolate_template(body_tmpl, context)

    resume_path = get_current_resume_path()
    resume_name = os.path.basename(resume_path) if resume_path else None

    try:
        msg = build_email_message(
            sender_email=smtp_cfg["username"],
            sender_name=smtp_cfg.get("sender_name", ""),
            recipient_email=test_recipient,
            subject=rendered_subject,
            body=rendered_body,
            resume_path=resume_path,
            resume_filename=resume_name
        )

        success, err = campaign_manager._send_single_email(smtp_cfg, msg)
        if success:
            add_history_record(
                recipient_email=test_recipient,
                company_name="Sample Test Company",
                job_title="Sample Test Position",
                subject=rendered_subject,
                body_snippet=rendered_body[:150],
                resume_name=resume_name,
                status="Sent to SMTP server",
                error_message=None
            )
            return jsonify({
                "success": True,
                "message": f"Test email successfully sent to SMTP server for {test_recipient}!"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Failed to send test email: {err}"
            }), 400

    except Exception as e:
        return jsonify({"success": False, "message": f"Exception occurred: {str(e)}"}), 500


@app.route("/api/send/start", methods=["POST"])
def api_send_start():
    """Start controlled bulk sending campaign."""
    data = request.get_json(silent=True) or {}
    recipients = data.get("recipients", [])
    subject = data.get("subject", "")
    body = data.get("body", "")
    candidate_name = data.get("candidate_name", "Job Applicant")
    candidate_contact = data.get("candidate_contact", "")
    delay_seconds = float(data.get("delay_seconds", 2.0))
    batch_limit = int(data.get("batch_limit", 5))

    if not recipients:
        return jsonify({"success": False, "message": "No recipients provided for campaign."}), 400

    if not subject.strip() or not body.strip():
        return jsonify({"success": False, "message": "Subject and body cannot be empty."}), 400

    smtp_cfg = get_effective_smtp_config()
    if not smtp_cfg.get("has_password") or not smtp_cfg.get("username"):
        return jsonify({
            "success": False,
            "message": "SMTP credentials are missing. Please configure your sender email and App Password in SMTP Settings."
        }), 400

    resume_path = get_current_resume_path()
    resume_name = os.path.basename(resume_path) if resume_path else None

    success, msg = campaign_manager.start_campaign(
        recipients=recipients,
        template_subject=subject,
        template_body=body,
        smtp_config=smtp_cfg,
        resume_path=resume_path,
        resume_filename=resume_name,
        delay_seconds=delay_seconds,
        batch_limit=batch_limit,
        candidate_name=candidate_name,
        candidate_contact=candidate_contact
    )

    if not success:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({"success": True, "message": msg})


@app.route("/api/send/pause", methods=["POST"])
def api_send_pause():
    success, msg = campaign_manager.pause_campaign()
    return jsonify({"success": success, "message": msg})


@app.route("/api/send/resume", methods=["POST"])
def api_send_resume():
    success, msg = campaign_manager.resume_campaign()
    return jsonify({"success": success, "message": msg})


@app.route("/api/send/cancel", methods=["POST"])
def api_send_cancel():
    success, msg = campaign_manager.cancel_campaign()
    return jsonify({"success": success, "message": msg})


@app.route("/api/send/status", methods=["GET"])
def api_send_status():
    return jsonify(campaign_manager.get_state())


@app.route("/api/history", methods=["GET"])
def api_get_history():
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    records = get_history(limit=limit, offset=offset, search=search, status_filter=status_filter)
    stats = get_history_stats()
    return jsonify({"records": records, "stats": stats})


@app.route("/api/history/clear", methods=["POST"])
def api_clear_history():
    clear_history()
    return jsonify({"success": True, "message": "History cleared successfully."})


@app.route("/api/history/export", methods=["GET"])
def api_export_history():
    """Export application history to CSV."""
    records = get_history(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Recipient Email", "Company Name", "Job Title",
        "Subject", "Status", "Resume Name", "Date & Time", "Error Message"
    ])
    for r in records:
        writer.writerow([
            r["id"],
            r["recipient_email"],
            r["company_name"],
            r["job_title"],
            r["subject"],
            r["status"],
            r["resume_name"],
            r["created_at"],
            r["error_message"]
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="smartapply_application_history.csv"
    )


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(get_history_stats())


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "error": "File size exceeds the 16 MB maximum upload limit."}), 413


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "API route not found"}), 404
    return render_template("dashboard.html", active_page="dashboard"), 404


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Internal server error"}), 500
    return "Internal server error occurred.", 500


if __name__ == "__main__":
    # Restrict to localhost development server by default
    print("\n" + "=" * 60)
    print("🚀 SmartApply is starting locally on http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
