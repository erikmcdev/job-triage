"""
Integration test for the cv_adapter webhook flow.

Mocks: Claude API + Telegram API + Playwright PDF rendering
Tests: webhook receives callback → looks up job in DB → generates CV → sends PDF
"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from model import Job, TriageResult, Feedback
from store import JobRepository


# --- Fixtures ---

MOCK_JOB = Job(
    title="Backend Engineer",
    company="Acme Corp",
    location="Barcelona, Spain",
    is_remote=True,
    job_url="https://example.com/job/123",
    description="We are looking for a backend engineer with Python and PostgreSQL experience.",
    site="linkedin",
    status="notified",
    triage=TriageResult(
        score=8,
        reason="Strong match",
        missing_skills=[],
        dealbreaker_gaps=[],
        company_industry="SaaS",
        keyword_score=12,
        salary_min=45000,
        salary_max=60000,
        salary_currency="EUR",
    ),
)

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


@pytest.fixture()
def db_with_job(tmp_path):
    """Create a temp DB with our mock job."""
    db_path = str(tmp_path / "test_jobs.db")
    repo = JobRepository(db_path)
    repo.save(MOCK_JOB)
    if MOCK_JOB.triage:
        repo.update_triage(MOCK_JOB.id, MOCK_JOB.triage)
    repo.update_status(MOCK_JOB.id, "notified")
    repo.close()
    return db_path, MOCK_JOB.id


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
def client(db_with_job, personal_info_file, cv_base_file):
    """
    Create a FastAPI TestClient with all external deps patched.
    """
    db_path, job_id = db_with_job
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
        patch("cv_adapter.api._get_repo", lambda: JobRepository(db_path)),
        patch("cv_adapter.api.TELEGRAM_BOT_TOKEN", "fake-token"),
        patch("cv_adapter.api.TELEGRAM_SECRET_TOKEN", "test-secret"),
        patch("cv_adapter.cv_generator.CV_BASE_PATH", cv_base_file),
        patch("cv_adapter.cv_generator.PERSONAL_INFO_PATH", personal_info_file),
        patch("cv_adapter.cv_generator.ANTHROPIC_API_KEY", "fake-key"),
        patch("cv_adapter.cv_generator._html_to_pdf", return_value=fake_pdf),
        patch("requests.post", side_effect=mock_post),
    ):
        from cv_adapter.api import app

        yield TestClient(app), job_id


# --- Helpers ---

def _make_callback_payload(job_id: int, callback_id: str = "cb_123") -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": callback_id,
            "data": f"cv:{job_id}",
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
        test_client, job_id = client
        payload = _make_callback_payload(job_id)
        resp = test_client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        import requests
        calls = requests.post.call_args_list
        urls = [c.args[0] if c.args else c.kwargs.get("url", "") for c in calls]

        assert any("answerCallbackQuery" in u for u in urls)
        assert any("sendMessage" in u for u in urls)
        assert any("sendDocument" in u for u in urls)

        doc_call = next(c for c in calls if "sendDocument" in str(c))
        files = doc_call.kwargs.get("files") or (doc_call[1].get("files") if len(doc_call) > 1 else None)
        assert files is not None
        filename = files["document"][0]
        assert filename.startswith("CV_")
        assert filename.endswith(".pdf")

    def test_missing_job_key(self, client):
        """Unknown job id returns error message to user."""
        test_client, _ = client
        payload = _make_callback_payload(99999)
        resp = test_client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200

        import requests
        calls = requests.post.call_args_list
        msg_calls = [c for c in calls if "sendMessage" in str(c)]
        assert any("no encontrada" in str(c) for c in msg_calls)

    def test_non_cv_callback_ignored(self, client):
        """Callback with unknown prefix is ignored."""
        test_client, _ = client
        payload = _make_callback_payload(1)
        payload["callback_query"]["data"] = "other:action"
        resp = test_client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200
        import requests
        assert requests.post.call_count == 0

    def test_non_callback_update_ignored(self, client):
        """Regular message (not callback) is ignored."""
        test_client, _ = client
        payload = {"update_id": 1, "message": {"text": "hello"}}
        resp = test_client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

        assert resp.status_code == 200

    def test_wrong_secret_rejected(self, client):
        """Wrong secret token returns 403."""
        test_client, job_id = client
        payload = _make_callback_payload(job_id)
        resp = test_client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )

        assert resp.status_code == 403


# --- Feedback tests ---

def _make_callback(data: str, callback_id: str = "cb_123") -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": callback_id,
            "data": data,
            "from": {"id": 12345, "first_name": "Test"},
            "message": {
                "message_id": 100,
                "chat": {"id": 67890, "type": "private"},
                "text": "test job message",
            },
        },
    }


def _make_text_reply(user_text: str, reply_to_text: str) -> dict:
    return {
        "update_id": 2,
        "message": {
            "message_id": 102,
            "from": {"id": 12345, "first_name": "Test"},
            "chat": {"id": 67890, "type": "private"},
            "date": 1234567890,
            "text": user_text,
            "reply_to_message": {
                "message_id": 101,
                "from": {"id": 99999, "is_bot": True, "first_name": "bot"},
                "chat": {"id": 67890, "type": "private"},
                "text": reply_to_text,
            },
        },
    }


@pytest.fixture()
def feedback_client(db_with_job):
    """TestClient with DB patched for feedback tests."""
    db_path, job_id = db_with_job

    mock_telegram_resp = MagicMock()
    mock_telegram_resp.status_code = 200
    mock_telegram_resp.json.return_value = {"ok": True}

    with (
        patch("cv_adapter.api._get_repo", lambda: JobRepository(db_path)),
        patch("cv_adapter.api.TELEGRAM_BOT_TOKEN", "fake-token"),
        patch("cv_adapter.api.TELEGRAM_SECRET_TOKEN", ""),
        patch("requests.post", return_value=mock_telegram_resp),
    ):
        from cv_adapter.api import app
        yield TestClient(app), db_path, job_id


class TestFeedbackFlow:
    def test_thumbs_up_saves_positive(self, feedback_client):
        """👍 saves positive feedback."""
        client, db_path, job_id = feedback_client
        resp = client.post("/webhook", json=_make_callback(f"up:{job_id}"))
        assert resp.status_code == 200

        repo = JobRepository(db_path)
        job = repo.get_by_id(job_id)
        repo.close()
        assert job.feedback is not None
        assert job.feedback.verdict == "positive"

    def test_thumbs_down_preset_reason(self, feedback_client):
        """👎 → preset reason saves negative feedback."""
        client, db_path, job_id = feedback_client

        # Step 1: click 👎 — shows reason keyboard (no feedback saved yet)
        resp = client.post("/webhook", json=_make_callback(f"dn:{job_id}"))
        assert resp.status_code == 200
        repo = JobRepository(db_path)
        job = repo.get_by_id(job_id)
        repo.close()
        assert job.feedback is None

        # Step 2: pick "Demasiado senior"
        resp = client.post("/webhook", json=_make_callback(f"dr:{job_id}:sen"))
        assert resp.status_code == 200
        repo = JobRepository(db_path)
        job = repo.get_by_id(job_id)
        repo.close()
        assert job.feedback is not None
        assert job.feedback.verdict == "negative"
        assert job.feedback.reason == "Demasiado senior"

    def test_thumbs_down_otro_freetext(self, feedback_client):
        """👎 → Otro → free text reply saves negative feedback."""
        client, db_path, job_id = feedback_client

        # Step 1: click 👎
        client.post("/webhook", json=_make_callback(f"dn:{job_id}"))
        # Step 2: pick "Otro" — sends force_reply, no feedback yet
        client.post("/webhook", json=_make_callback(f"dr:{job_id}:oth"))
        repo = JobRepository(db_path)
        job = repo.get_by_id(job_id)
        repo.close()
        assert job.feedback is None

        # Step 3: user replies with free text
        reply_payload = _make_text_reply(
            "No me interesa el sector",
            f"✍️ Escribe la razón (ref:{job_id}):",
        )
        resp = client.post("/webhook", json=reply_payload)
        assert resp.status_code == 200
        repo = JobRepository(db_path)
        job = repo.get_by_id(job_id)
        repo.close()
        assert job.feedback is not None
        assert job.feedback.verdict == "negative"
        assert job.feedback.reason == "No me interesa el sector"

    def test_thumbs_up_missing_job(self, feedback_client):
        """👍 on unknown id shows error, saves nothing."""
        client, db_path, _ = feedback_client
        resp = client.post("/webhook", json=_make_callback("up:99999"))
        assert resp.status_code == 200

        import requests
        calls = requests.post.call_args_list
        assert any("no encontrada" in str(c) for c in calls)
