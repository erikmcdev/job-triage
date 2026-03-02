"""
Integration test for the cv_adapter webhook flow.

Mocks: Claude API + Telegram API + Playwright PDF rendering
Tests: webhook receives callback → looks up job → generates CV → sends PDF
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# --- Fixtures ---

MOCK_JOB = {
    "title": "Backend Engineer",
    "company": "Acme Corp",
    "location": "Barcelona, Spain",
    "is_remote": True,
    "job_url": "https://example.com/job/123",
    "company_industry": "SaaS",
    "min_salary": 45000,
    "max_salary": 60000,
    "salary_currency": "EUR",
    "ai_score": 8,
    "ai_reason": "Strong match",
    "ai_missing": [],
    "description": "We are looking for a backend engineer with Python and PostgreSQL experience.",
}

MOCK_CLAUDE_RESPONSE = {
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "font_scale": 1.0,
                    "about_me": "Experienced backend engineer. Passionate about clean architecture.",
                    "experience": [
                        {
                            "company": "Acme Corp — SaaS",
                            "role": "Backend Engineer",
                            "period": "2020 — 2024",
                            "bullets": [
                                "Designed REST APIs serving 10k RPM.",
                                "Migrated legacy monolith to microservices.",
                                "Implemented CI/CD pipeline with Docker.",
                            ],
                            "tags": ["Python", "PostgreSQL", "Docker"],
                        }
                    ],
                    "education": [
                        {
                            "degree": "Computer Science — UPC",
                            "school": "Algorithms, OS, Networks",
                            "date": "2016 — 2020",
                        }
                    ],
                }
            ),
        }
    ]
}

MOCK_PERSONAL_INFO = {
    "name": "Test User",
    "email": "test@example.com",
    "phone": "+34 600 000 000",
    "location": "Barcelona, Spain",
    "linkedin": "linkedin.com/in/testuser",
    "web": "testuser.dev",
    "github": "github.com/testuser",
}

JOB_KEY = "test_job_key_01"


@pytest.fixture()
def pending_jobs_file(tmp_path):
    """Create a temp pending_jobs.json with our mock job."""
    path = tmp_path / "pending_jobs.json"
    path.write_text(json.dumps({JOB_KEY: MOCK_JOB}))
    return str(path)


@pytest.fixture()
def personal_info_file(tmp_path):
    path = tmp_path / "personal-info.json"
    path.write_text(json.dumps(MOCK_PERSONAL_INFO))
    return str(path)


@pytest.fixture()
def cv_base_file(tmp_path):
    path = tmp_path / "cv-base.md"
    path.write_text("# Test CV\nBackend engineer with 4 years of experience.")
    return str(path)


@pytest.fixture()
def client(pending_jobs_file, personal_info_file, cv_base_file):
    """
    Create a FastAPI TestClient with all external deps patched.
    """
    fake_pdf = b"%PDF-1.4 fake pdf content for testing"

    mock_claude_resp = MagicMock()
    mock_claude_resp.status_code = 200
    mock_claude_resp.json.return_value = MOCK_CLAUDE_RESPONSE

    mock_telegram_resp = MagicMock()
    mock_telegram_resp.status_code = 200
    mock_telegram_resp.json.return_value = {"ok": True}

    def mock_post(url, **kwargs):
        if "api.anthropic.com" in url:
            return mock_claude_resp
        return mock_telegram_resp

    with (
        patch("cv_adapter.api.PENDING_JOBS_PATH", pending_jobs_file),
        patch("cv_adapter.api.TELEGRAM_BOT_TOKEN", "fake-token"),
        patch("cv_adapter.api.TELEGRAM_SECRET_TOKEN", "test-secret"),
        patch("cv_adapter.cv_generator.CV_BASE_PATH", cv_base_file),
        patch("cv_adapter.cv_generator.PERSONAL_INFO_PATH", personal_info_file),
        patch("cv_adapter.cv_generator.ANTHROPIC_API_KEY", "fake-key"),
        patch("cv_adapter.cv_generator._html_to_pdf", return_value=fake_pdf),
        patch("requests.post", side_effect=mock_post),
    ):
        from cv_adapter.api import app

        yield TestClient(app)


# --- Helpers ---

def _make_callback_payload(job_key: str, callback_id: str = "cb_123") -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": callback_id,
            "data": f"cv:{job_key}",
            "from": {"id": 12345, "first_name": "Test"},
            "message": {
                "message_id": 1,
                "chat": {"id": 67890, "type": "private"},
                "text": "test",
            },
        },
    }


# --- Tests ---

class TestWebhookFlow:
    def test_full_cv_generation_flow(self, client):
        """Happy path: callback → lookup → generate → send PDF."""
        payload = _make_callback_payload(JOB_KEY)
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # Verify Telegram API was called: answerCallback + sendMessage + sendDocument
        import requests
        calls = requests.post.call_args_list
        urls = [c.args[0] if c.args else c.kwargs.get("url", "") for c in calls]

        assert any("answerCallbackQuery" in u for u in urls)
        assert any("sendMessage" in u for u in urls)
        assert any("sendDocument" in u for u in urls)

        # Verify sendDocument was called with PDF
        doc_call = next(c for c in calls if "sendDocument" in str(c))
        files = doc_call.kwargs.get("files") or (doc_call[1].get("files") if len(doc_call) > 1 else None)
        assert files is not None
        filename = files["document"][0]
        assert filename.startswith("CV_")
        assert filename.endswith(".pdf")

    def test_missing_job_key(self, client):
        """Unknown job key returns error message to user."""
        payload = _make_callback_payload("nonexistent_key")
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200

        import requests
        calls = requests.post.call_args_list
        # Should send "no encontrada" error via sendMessage
        msg_calls = [c for c in calls if "sendMessage" in str(c)]
        assert any("no encontrada" in str(c) for c in msg_calls)

    def test_non_cv_callback_ignored(self, client):
        """Callback with non-cv: prefix is ignored."""
        payload = _make_callback_payload("something")
        payload["callback_query"]["data"] = "other:action"
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200
        import requests
        assert requests.post.call_count == 0

    def test_non_callback_update_ignored(self, client):
        """Regular message (not callback) is ignored."""
        payload = {"update_id": 1, "message": {"text": "hello"}}
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200

    def test_wrong_secret_rejected(self, client):
        """Wrong secret token returns 403."""
        payload = _make_callback_payload(JOB_KEY)
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )

        assert resp.status_code == 403
