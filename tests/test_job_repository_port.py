"""Contract tests for the JobRepository port.

Any adapter implementing JobRepository must pass these tests.
"""

import copy

import pytest
from datetime import datetime

from model import Job, TriageResult, Feedback
from ports.job_repository import JobRepository


class InMemoryJobRepository(JobRepository):
    """Minimal in-memory adapter to validate the contract tests themselves."""

    def __init__(self):
        self._jobs: dict[int, Job] = {}
        self._next_id = 1
        self._closed = False

    def save(self, job: Job) -> Job:
        if any(j.job_url == job.job_url for j in self._jobs.values()):
            raise ValueError(f"Duplicate job_url: {job.job_url}")
        job = copy.deepcopy(job)
        job.id = self._next_id
        self._next_id += 1
        self._jobs[job.id] = job
        return job

    def save_batch(self, jobs: list[Job]) -> list[Job]:
        saved = []
        for job in jobs:
            if self.exists(job.job_url):
                continue
            saved.append(self.save(job))
        return saved

    def get_by_id(self, job_id: int) -> Job | None:
        job = self._jobs.get(job_id)
        return copy.deepcopy(job) if job else None

    def get_by_url(self, job_url: str) -> Job | None:
        for job in self._jobs.values():
            if job.job_url == job_url:
                return copy.deepcopy(job)
        return None

    def exists(self, job_url: str) -> bool:
        return any(j.job_url == job_url for j in self._jobs.values())

    def get_by_status(self, status: str) -> list[Job]:
        return [copy.deepcopy(j) for j in self._jobs.values() if j.status == status]

    def update_triage(self, job_id: int, triage: TriageResult) -> None:
        self._jobs[job_id].triage = triage
        self._jobs[job_id].status = "triaged"

    def update_feedback(self, job_id: int, feedback: Feedback) -> None:
        self._jobs[job_id].feedback = feedback

    def update_status(self, job_id: int, status: str) -> None:
        self._jobs[job_id].status = status

    def get_seen_urls(self) -> set[str]:
        return {j.job_url for j in self._jobs.values()}

    def close(self) -> None:
        self._closed = True


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        location="Remote",
        description="Build APIs",
        job_url="https://example.com/job/1",
        site="linkedin",
        is_remote=True,
        date_posted="2026-03-20",
    )
    defaults.update(overrides)
    return Job(**defaults)


TRIAGE = TriageResult(
    score=82,
    reason="Strong backend fit",
    missing_skills=["Kafka"],
    dealbreaker_gaps=[],
    company_industry="fintech",
    salary_min=50000,
    salary_max=70000,
    salary_currency="EUR",
)

FEEDBACK = Feedback(
    verdict="positive",
    reason=None,
    timestamp=datetime(2026, 3, 22, 10, 0, 0),
)


class TestJobRepositoryContract:
    """Contract tests that any JobRepository adapter must satisfy."""

    @pytest.fixture
    def repo(self) -> JobRepository:
        """Default: in-memory mock. Override in adapter-specific test modules."""
        return InMemoryJobRepository()

    # --- save & get_by_id ---

    def test_save_assigns_id(self, repo):
        job = _make_job()
        assert job.id is None
        saved = repo.save(job)
        assert saved.id is not None

    def test_get_by_id_returns_saved_job(self, repo):
        job = repo.save(_make_job())
        found = repo.get_by_id(job.id)
        assert found is not None
        assert found.title == "Backend Engineer"
        assert found.company == "Acme Corp"
        assert found.job_url == "https://example.com/job/1"
        assert found.is_remote is True
        assert found.status == "unscored"

    def test_get_by_id_returns_none_for_missing(self, repo):
        assert repo.get_by_id(99999) is None

    # --- save duplicate url ---

    def test_save_duplicate_url_raises(self, repo):
        repo.save(_make_job())
        with pytest.raises(Exception):
            repo.save(_make_job(title="Different Title"))

    # --- get_by_url ---

    def test_get_by_url(self, repo):
        repo.save(_make_job())
        found = repo.get_by_url("https://example.com/job/1")
        assert found is not None
        assert found.title == "Backend Engineer"

    def test_get_by_url_returns_none_for_missing(self, repo):
        assert repo.get_by_url("https://nonexistent.com") is None

    # --- exists ---

    def test_exists_true(self, repo):
        repo.save(_make_job())
        assert repo.exists("https://example.com/job/1") is True

    def test_exists_false(self, repo):
        assert repo.exists("https://example.com/nope") is False

    # --- get_by_status ---

    def test_get_by_status(self, repo):
        repo.save(_make_job(job_url="https://example.com/1"))
        repo.save(_make_job(job_url="https://example.com/2"))
        unscored = repo.get_by_status("unscored")
        assert len(unscored) == 2

    def test_get_by_status_empty(self, repo):
        assert repo.get_by_status("triaged") == []

    # --- update_triage ---

    def test_update_triage(self, repo):
        job = repo.save(_make_job())
        repo.update_triage(job.id, TRIAGE)
        updated = repo.get_by_id(job.id)
        assert updated.status == "triaged"
        assert updated.triage is not None
        assert updated.triage.score == 82
        assert updated.triage.reason == "Strong backend fit"
        assert updated.triage.missing_skills == ["Kafka"]
        assert updated.triage.dealbreaker_gaps == []
        assert updated.triage.company_industry == "fintech"
        assert updated.triage.salary_min == 50000
        assert updated.triage.salary_max == 70000
        assert updated.triage.salary_currency == "EUR"

    # --- update_feedback ---

    def test_update_feedback(self, repo):
        job = repo.save(_make_job())
        repo.update_feedback(job.id, FEEDBACK)
        updated = repo.get_by_id(job.id)
        assert updated.feedback is not None
        assert updated.feedback.verdict == "positive"
        assert updated.feedback.reason is None
        assert updated.feedback.timestamp == FEEDBACK.timestamp

    # --- update_status ---

    def test_update_status(self, repo):
        job = repo.save(_make_job())
        repo.update_status(job.id, "notified")
        updated = repo.get_by_id(job.id)
        assert updated.status == "notified"

    # --- get_seen_urls ---

    def test_get_seen_urls(self, repo):
        repo.save(_make_job(job_url="https://example.com/a"))
        repo.save(_make_job(job_url="https://example.com/b"))
        urls = repo.get_seen_urls()
        assert urls == {"https://example.com/a", "https://example.com/b"}

    def test_get_seen_urls_empty(self, repo):
        assert repo.get_seen_urls() == set()

    # --- save_batch ---

    def test_save_batch(self, repo):
        jobs = [
            _make_job(job_url="https://example.com/1"),
            _make_job(job_url="https://example.com/2"),
            _make_job(job_url="https://example.com/3"),
        ]
        saved = repo.save_batch(jobs)
        assert len(saved) == 3
        assert all(j.id is not None for j in saved)

    def test_save_batch_skips_duplicates(self, repo):
        repo.save(_make_job(job_url="https://example.com/existing"))
        jobs = [
            _make_job(job_url="https://example.com/existing"),
            _make_job(job_url="https://example.com/new"),
        ]
        saved = repo.save_batch(jobs)
        assert len(saved) == 1
        assert saved[0].job_url == "https://example.com/new"

    # --- close ---

    def test_close_is_idempotent(self, repo):
        repo.close()
        repo.close()  # should not raise
