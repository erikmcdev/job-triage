"""Tests for TriageService: load pending_triage → Claude evaluate → triaged_approved / triaged_rejected."""

from unittest.mock import patch, MagicMock

import pytest

from model import Job
from tests.test_job_repository_port import InMemoryJobRepository
from triage.service.triage.service import TriageService


# --- Fixtures ---

@pytest.fixture
def repo():
    return InMemoryJobRepository()


@pytest.fixture
def service(repo):
    return TriageService(
        job_repo=repo,
        score_threshold=7,
        cv_summary="Backend dev, 4 years Python/Django experience.",
    )


# --- Helpers ---

def _save_pending(repo, **overrides) -> Job:
    defaults = dict(
        title="Backend Developer",
        company="Acme",
        location="Barcelona",
        description="Python, Django, REST APIs",
        job_url="https://example.com/job/1",
        site="linkedin",
        is_remote=False,
        status="pending_triage",
    )
    defaults.update(overrides)
    job = repo.save(Job(**defaults))
    repo.update_status(job.id, "pending_triage")
    return job


GOOD_EVALUATION = {
    "score": 8,
    "reason": "Strong Python/Django match",
    "missing_skills": ["Kafka"],
    "dealbreaker_gaps": [],
    "company_industry": "fintech",
    "expected_salary": {"min": 45000, "max": 60000, "currency": "EUR"},
}

BAD_EVALUATION = {
    "score": 4,
    "reason": "Role requires Go, candidate has no Go experience",
    "missing_skills": ["Go", "gRPC"],
    "dealbreaker_gaps": ["Go"],
    "company_industry": "logistics",
    "expected_salary": {"min": 40000, "max": 55000, "currency": "EUR"},
}

BORDERLINE_EVALUATION = {
    "score": 7,
    "reason": "Meets threshold exactly",
    "missing_skills": [],
    "dealbreaker_gaps": [],
    "company_industry": "saas",
    "expected_salary": {"min": 40000, "max": 50000, "currency": "EUR"},
}


# =============================================================
# Status transitions
# =============================================================

class TestStatusTransitions:

    def test_approved_when_score_above_threshold(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=GOOD_EVALUATION):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "triaged_approved"

    def test_rejected_when_score_below_threshold(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=BAD_EVALUATION):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "triaged_rejected"

    def test_approved_when_score_exactly_at_threshold(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=BORDERLINE_EVALUATION):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "triaged_approved"


# =============================================================
# Triage result persistence
# =============================================================

class TestTriageResultPersistence:

    def test_triage_result_saved_to_repo(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=GOOD_EVALUATION):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.triage is not None
        assert job.triage.score == 8
        assert job.triage.reason == "Strong Python/Django match"
        assert job.triage.missing_skills == ["Kafka"]
        assert job.triage.dealbreaker_gaps == []
        assert job.triage.company_industry == "fintech"
        assert job.triage.salary_min == 45000
        assert job.triage.salary_max == 60000
        assert job.triage.salary_currency == "EUR"

    def test_triage_result_saved_for_rejected_too(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=BAD_EVALUATION):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.triage is not None
        assert job.triage.score == 4
        assert job.triage.dealbreaker_gaps == ["Go"]


# =============================================================
# Only processes pending_triage jobs
# =============================================================

class TestStatusFiltering:

    def test_only_processes_pending_triage_jobs(self, service, repo):
        _save_pending(repo, job_url="https://example.com/pending")
        unscored = repo.save(Job(
            title="Other", company="X", location="Y",
            description="Z", job_url="https://example.com/unscored",
            site="linkedin", is_remote=False, status="unscored",
        ))
        with patch.object(service, "_evaluate_job", return_value=GOOD_EVALUATION) as mock_eval:
            service.run()
        assert mock_eval.call_count == 1
        unscored_job = repo.get_by_id(unscored.id)
        assert unscored_job.status == "unscored"

    def test_no_pending_jobs_is_noop(self, service, repo):
        with patch.object(service, "_evaluate_job") as mock_eval:
            service.run()
        mock_eval.assert_not_called()


# =============================================================
# Failed evaluation handling
# =============================================================

class TestFailedEvaluation:

    def test_skips_job_when_evaluation_returns_none(self, service, repo):
        _save_pending(repo)
        with patch.object(service, "_evaluate_job", return_value=None):
            service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"
        assert job.triage is None

    def test_continues_batch_after_failed_evaluation(self, service, repo):
        _save_pending(repo, job_url="https://example.com/fail")
        _save_pending(repo, job_url="https://example.com/ok")
        returns = [None, GOOD_EVALUATION]
        with patch.object(service, "_evaluate_job", side_effect=returns):
            service.run()
        statuses = {j.job_url: j.status for j in repo._jobs.values()}
        assert statuses["https://example.com/fail"] == "pending_triage"
        assert statuses["https://example.com/ok"] == "triaged_approved"


# =============================================================
# Batch processing
# =============================================================

class TestBatch:

    def test_mixed_batch(self, service, repo):
        _save_pending(repo, job_url="https://example.com/good")
        _save_pending(repo, job_url="https://example.com/bad")
        returns = [GOOD_EVALUATION, BAD_EVALUATION]
        with patch.object(service, "_evaluate_job", side_effect=returns):
            service.run()
        statuses = {j.job_url: j.status for j in repo._jobs.values()}
        assert statuses["https://example.com/good"] == "triaged_approved"
        assert statuses["https://example.com/bad"] == "triaged_rejected"

    def test_run_returns_approved_jobs(self, service, repo):
        _save_pending(repo, job_url="https://example.com/good")
        _save_pending(repo, job_url="https://example.com/bad")
        returns = [GOOD_EVALUATION, BAD_EVALUATION]
        with patch.object(service, "_evaluate_job", side_effect=returns):
            approved = service.run()
        assert len(approved) == 1
        assert approved[0].job_url == "https://example.com/good"
