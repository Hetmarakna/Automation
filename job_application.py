"""
job_application.py - Entry point for SmartApply job application automation app.
"""
from app import app

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 SmartApply is starting locally on http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
