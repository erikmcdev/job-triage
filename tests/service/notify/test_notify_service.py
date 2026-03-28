"""Tests for NotifyService: load triaged_approved → send Telegram → mark notified."""

from unittest.mock import patch, call

import pytest

from model import Job, TriageResult
from tests.test_job_repository_port import InMemoryJobRepository
from triage.service.notify.service import NotifyService


# --- Fixtures ---

TRIAGE = TriageResult(
    score=8,
    reason="Strong Python match",
    missing_skills=["Kafka"],
    dealbreaker_gaps=[],
    company_industry="fintech",
    keyword_score=5,
    salary_min=45000,
    salary_max=60000,
    salary_currency="EUR",
)


@pytest.fixture
def repo():
    return InMemoryJobRepository()


@pytest.fixture
def service(repo):
    return NotifyService(job_repo=repo)


# --- Helpers ---

def _save_approved(repo, **overrides) -> Job:
    defaults = dict(
        title="Backend Developer",
        company="Acme",
        location="Barcelona",
        description="Python, Django",
        job_url="https://example.com/job/1",
        site="linkedin",
        is_remote=False,
        status="triaged_approved",
    )
    defaults.update(overrides)
    job = repo.save(Job(**defaults))
    repo.update_triage(job.id, TRIAGE)
    repo.update_status(job.id, "triaged_approved")
    return job


# =============================================================
# Status transitions
# =============================================================

class TestStatusTransitions:

    def test_marks_notified_on_success(self, service, repo):
        _save_approved(repo)
        with patch.object(service, "_send_message"):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "notified"

    def test_keeps_status_on_send_failure(self, service, repo):
        _save_approved(repo)
        # Header succeeds, job notification fails
        with patch.object(service, "_send_message", side_effect=[None, Exception("Telegram down")]):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "triaged_approved"


# =============================================================
# Only processes triaged_approved jobs
# =============================================================

class TestStatusFiltering:

    def test_only_processes_triaged_approved(self, service, repo):
        _save_approved(repo, job_url="https://example.com/approved")
        rejected = repo.save(Job(
            title="Other", company="X", location="Y",
            description="Z", job_url="https://example.com/rejected",
            site="linkedin", is_remote=False, status="triaged_approved",
        ))
        repo.update_status(rejected.id, "triaged_rejected")

        with patch.object(service, "_send_message") as mock_send:
            service.run()
        # header + 1 job notification = 2 calls (not 3)
        assert mock_send.call_count == 2

    def test_no_approved_jobs_sends_no_results_message(self, service, repo):
        with patch.object(service, "_send_message") as mock_send:
            service.run()
        mock_send.assert_called_once()
        assert "no hay ofertas" in mock_send.call_args[0][0].lower()


# =============================================================
# Telegram message content
# =============================================================

class TestMessageContent:

    def test_job_message_contains_key_fields(self, service, repo):
        _save_approved(repo, title="Python Engineer", company="FinCo",
                       job_url="https://example.com/job/42")
        with patch.object(service, "_send_message") as mock_send:
            service.run()
        # Second call is the job notification (first is header)
        job_msg = mock_send.call_args_list[1][0][0]
        assert "Python Engineer" in job_msg
        assert "FinCo" in job_msg
        assert "8/10" in job_msg
        assert "https://example.com/job/42" in job_msg

    def test_job_message_includes_inline_keyboard(self, service, repo):
        job = _save_approved(repo)
        with patch.object(service, "_send_message") as mock_send:
            service.run()
        reply_markup = mock_send.call_args_list[1][1].get("reply_markup")
        assert reply_markup is not None
        buttons = reply_markup["inline_keyboard"][0]
        callback_datas = [b["callback_data"] for b in buttons]
        assert any(f"up:{job.id}" in cd for cd in callback_datas)
        assert any(f"dn:{job.id}" in cd for cd in callback_datas)
        assert any(f"cv:{job.id}" in cd for cd in callback_datas)

    def test_header_message_shows_count(self, service, repo):
        _save_approved(repo, job_url="https://example.com/1")
        _save_approved(repo, job_url="https://example.com/2")
        with patch.object(service, "_send_message") as mock_send:
            service.run()
        header = mock_send.call_args_list[0][0][0]
        assert "2" in header


# =============================================================
# Batch processing
# =============================================================

class TestBatch:

    def test_mixed_batch_only_successful_marked_notified(self, service, repo):
        _save_approved(repo, job_url="https://example.com/ok")
        _save_approved(repo, job_url="https://example.com/fail")

        call_count = 0

        def selective_fail(text, **kwargs):
            nonlocal call_count
            call_count += 1
            # Header succeeds (call 1), first job succeeds (call 2), second job fails (call 3)
            if call_count == 3:
                raise Exception("Telegram down")

        with patch.object(service, "_send_message", side_effect=selective_fail):
            service.run()

        statuses = {j.job_url: j.status for j in repo._jobs.values()}
        assert statuses["https://example.com/ok"] == "notified"
        assert statuses["https://example.com/fail"] == "triaged_approved"

    def test_all_successful_marks_all_notified(self, service, repo):
        _save_approved(repo, job_url="https://example.com/1")
        _save_approved(repo, job_url="https://example.com/2")
        with patch.object(service, "_send_message"):
            service.run()
        statuses = {j.status for j in repo._jobs.values()}
        assert statuses == {"notified"}
