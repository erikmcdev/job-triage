"""End-to-end pipeline test: fetch → score → triage → notify.

All external services (JobSpy, Claude API, Telegram) are mocked.
Uses SqliteJobRepository with tmp_path — no prod impact.
"""

from unittest.mock import patch

import pytest

from model import Job
from store import SqliteJobRepository
from triage.service.fetch.service import FetchService
from triage.service.fetch.criteria import SearchCriteria, HardFilters
from triage.service.score.service import ScoreService
from triage.service.score.criteria import ScoreCriteria
from triage.service.notify.service import NotifyService
from triage.service.triage.service import TriageService


# --- Wiring ---

@pytest.fixture
def repo(tmp_path):
    r = SqliteJobRepository(str(tmp_path / "test.db"))
    yield r
    r.close()


@pytest.fixture
def fetch_service(repo):
    return FetchService(
        criteria=SearchCriteria(
            queries=[{"site": "linkedin", "term": "python developer", "location": "Barcelona"}],
            results_per_query=50,
            hours_old=72,
            hard_filters=HardFilters(
                exclude_title_keywords=["junior", "intern", "senior", "manager"],
                blacklist_companies=["SpamCorp"],
                min_salary_yearly=35000,
            ),
        ),
        job_repo=repo,
    )


@pytest.fixture
def score_service(repo):
    return ScoreService(
        criteria=ScoreCriteria(
            core_stack=["python", "django", "rest api"],
            secondary_stack=["docker", "postgresql"],
            bonus_stack=["agile"],
            min_keyword_score=4,
        ),
        job_repo=repo,
    )


@pytest.fixture
def triage_service(repo):
    return TriageService(
        job_repo=repo,
        score_threshold=7,
        cv_summary="Backend dev, 4 years Python/Django experience.",
    )


@pytest.fixture
def notify_service(repo):
    return NotifyService(job_repo=repo)


# --- Fake data ---

FETCHED_JOBS = [
    Job(
        title="Backend Developer",
        company="GoodCo",
        location="Barcelona",
        description="We need a Python Django developer with REST API experience. Docker and PostgreSQL knowledge is a plus. Agile team.",
        job_url="https://example.com/job/good",
        site="linkedin",
        is_remote=False,
    ),
    Job(
        title="Go Developer",
        company="GoCorp",
        location="Barcelona",
        description="Go microservices, Kubernetes, gRPC. No Python needed.",
        job_url="https://example.com/job/bad-score",
        site="linkedin",
        is_remote=False,
    ),
    Job(
        title="Junior Python Developer",
        company="JuniorCo",
        location="Barcelona",
        description="Entry level Python role with Django.",
        job_url="https://example.com/job/filtered-title",
        site="linkedin",
        is_remote=False,
    ),
    Job(
        title="Python Developer",
        company="SpamCorp",
        location="Barcelona",
        description="Python Django developer needed.",
        job_url="https://example.com/job/filtered-company",
        site="linkedin",
        is_remote=False,
    ),
    Job(
        title="PHP Developer",
        company="OkCo",
        location="Barcelona",
        description="PHP Symfony developer. Knowledge of Python, Django and REST API is valued. Docker environment.",
        job_url="https://example.com/job/rejected-triage",
        site="linkedin",
        is_remote=False,
    ),
]

GOOD_EVALUATION = {
    "score": 8,
    "reason": "Strong Python/Django match",
    "missing_skills": ["Kafka"],
    "dealbreaker_gaps": [],
    "company_industry": "fintech",
    "expected_salary": {"min": 45000, "max": 60000, "currency": "EUR"},
}

REJECTED_EVALUATION = {
    "score": 5,
    "reason": "PHP is the primary stack, Python is secondary",
    "missing_skills": ["Symfony"],
    "dealbreaker_gaps": ["PHP"],
    "company_industry": "saas",
    "expected_salary": {"min": 35000, "max": 50000, "currency": "EUR"},
}


# =============================================================
# Full pipeline
# =============================================================

class TestPipelineE2E:

    def test_full_flow_fetch_to_notify(
        self, repo, fetch_service, score_service, triage_service, notify_service,
    ):
        """Jobs flow through all 4 stages with correct status transitions."""
        # 1. Fetch — 5 jobs in, 2 filtered out (junior title + blacklisted company)
        with patch.object(fetch_service, "_fetch", return_value=FETCHED_JOBS):
            fetched = fetch_service.run()

        assert len(fetched) == 3
        assert len(repo.get_by_status("unscored")) == 3

        # 2. Score — "good" and "rejected-triage" have Python/Django keywords → pending_triage
        #            "bad-score" has no matching keywords → below_threshold
        score_service.run()

        pending = repo.get_by_status("pending_triage")
        below = repo.get_by_status("below_threshold")
        assert len(pending) == 2
        assert len(below) == 1
        assert below[0].job_url == "https://example.com/job/bad-score"

        # 3. Triage — "good" approved (score 8), "rejected-triage" rejected (score 5)
        evaluations = [GOOD_EVALUATION, REJECTED_EVALUATION]
        with patch.object(triage_service, "_evaluate_job", side_effect=evaluations):
            approved = triage_service.run()

        assert len(approved) == 1
        assert approved[0].job_url == "https://example.com/job/good"
        assert repo.get_by_url("https://example.com/job/good").status == "triaged_approved"
        assert repo.get_by_url("https://example.com/job/rejected-triage").status == "triaged_rejected"

        # 4. Notify — approved job gets notified
        with patch.object(notify_service, "send_message"):
            notify_service.run()

        assert repo.get_by_url("https://example.com/job/good").status == "notified"

    def test_full_flow_no_jobs_pass_scoring(
        self, repo, fetch_service, score_service, triage_service, notify_service,
    ):
        """When no jobs pass keyword scoring, triage and notify still run gracefully."""
        low_score_jobs = [
            Job(
                title="Data Analyst",
                company="DataCo",
                location="Barcelona",
                description="Excel, Tableau, SQL dashboards.",
                job_url="https://example.com/job/analyst",
                site="linkedin",
                is_remote=False,
            ),
        ]
        with patch.object(fetch_service, "_fetch", return_value=low_score_jobs):
            fetch_service.run()

        score_service.run()
        assert len(repo.get_by_status("pending_triage")) == 0
        assert len(repo.get_by_status("below_threshold")) == 1

        with patch.object(triage_service, "_evaluate_job") as mock_eval:
            triage_service.run()
        mock_eval.assert_not_called()

        with patch.object(notify_service, "send_message") as mock_send:
            notify_service.run()
        mock_send.assert_called_once()
        assert "no hay ofertas" in mock_send.call_args[0][0].lower()

    def test_triage_result_persisted_through_sqlite(
        self, repo, fetch_service, score_service, triage_service,
    ):
        """Triage result fields survive SQLite serialization/deserialization."""
        jobs = [FETCHED_JOBS[0]]  # "good" job
        with patch.object(fetch_service, "_fetch", return_value=jobs):
            fetch_service.run()

        score_service.run()

        with patch.object(triage_service, "_evaluate_job", return_value=GOOD_EVALUATION):
            triage_service.run()

        job = repo.get_by_url("https://example.com/job/good")
        assert job.triage is not None
        assert job.triage.score == 8
        assert job.triage.reason == "Strong Python/Django match"
        assert job.triage.missing_skills == ["Kafka"]
        assert job.triage.dealbreaker_gaps == []
        assert job.triage.company_industry == "fintech"
        assert job.triage.salary_min == 45000
        assert job.triage.salary_max == 60000
        assert job.triage.salary_currency == "EUR"

    def test_notify_failure_preserves_status_for_retry(
        self, repo, fetch_service, score_service, triage_service, notify_service,
    ):
        """If Telegram fails, job stays triaged_approved for retry."""
        jobs = [FETCHED_JOBS[0]]
        with patch.object(fetch_service, "_fetch", return_value=jobs):
            fetch_service.run()

        score_service.run()

        with patch.object(triage_service, "_evaluate_job", return_value=GOOD_EVALUATION):
            triage_service.run()

        # First call is the header message (succeeds), second is the job message (fails)
        with patch.object(notify_service, "send_message", side_effect=[None, Exception("Telegram down")]):
            notify_service.run()

        job = repo.get_by_url("https://example.com/job/good")
        assert job.status == "triaged_approved"
