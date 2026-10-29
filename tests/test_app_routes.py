"""
test_app_routes.py - End-to-end route tests for the Flask web endpoints.
"""
import io
import json
import fitz
from unittest.mock import patch, MagicMock
from app import app


def test_index_page():
    with app.test_client() as client:
        response = client.get("/")
        assert response.status_code == 200
        assert b"Your Job Applications, Simplified" in response.data


def test_pages_render_successfully():
    with app.test_client() as client:
        for path in ["/import", "/composer", "/smtp", "/history", "/help"]:
            res = client.get(path)
            assert res.status_code == 200


def test_api_upload_pdf():
    # Build in-memory PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Company: Google\nJob Title: SWE\nContact: hiring@google.com\n")
    pdf_bytes = doc.write()
    doc.close()

    with app.test_client() as client:
        data = {
            "file": (io.BytesIO(pdf_bytes), "sample_jobs.pdf")
        }
        res = client.post("/api/upload-pdf", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        json_data = res.get_json()
        assert json_data["success"] is True
        assert len(json_data["recipients"]) == 1
        assert json_data["recipients"][0]["email"] == "hiring@google.com"


def test_api_upload_resume_and_remove():
    # Valid resume PDF
    resume_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

    with app.test_client() as client:
        data = {
            "resume": (io.BytesIO(resume_bytes), "my_resume.pdf")
        }
        res = client.post("/api/upload-resume", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        json_data = res.get_json()
        assert json_data["success"] is True
        assert json_data["filename"] == "my_resume.pdf"

        # Check resume info endpoint
        info_res = client.get("/api/resume-info")
        assert info_res.status_code == 200
        assert info_res.get_json()["has_resume"] is True

        # Remove resume
        del_res = client.post("/api/remove-resume")
        assert del_res.status_code == 200
        assert del_res.get_json()["removed"] is True

        # Check info again
        info_res2 = client.get("/api/resume-info")
        assert info_res2.get_json()["has_resume"] is False


def test_api_template_get_and_post():
    with app.test_client() as client:
        res = client.get("/api/template")
        assert res.status_code == 200
        current_tmpl = res.get_json()
        assert "subject" in current_tmpl

        # Update template
        update_data = {
            "subject": "New Subject {job_title}",
            "body": "New Body {company}",
            "candidate_name": "Test Candidate",
            "candidate_contact": "test@test.com",
            "delay_seconds": 3.0,
            "batch_limit": 8
        }
        post_res = client.post("/api/template", json=update_data)
        assert post_res.status_code == 200
        assert post_res.get_json()["success"] is True


def test_api_history_export():
    with app.test_client() as client:
        res = client.get("/api/history/export")
        assert res.status_code == 200
        assert res.mimetype == "text/csv"
        assert b"Recipient Email" in res.data
