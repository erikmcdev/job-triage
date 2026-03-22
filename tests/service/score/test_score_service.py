"""Tests for ScoreService: load unscored jobs → keyword score → update status."""

import pytest

from model import Job
from tests.test_job_repository_port import InMemoryJobRepository
from triage.service.score.service import ScoreService
from triage.service.score.criteria import ScoreCriteria


# --- Fixtures ---

@pytest.fixture
def criteria():
    return ScoreCriteria(
        core_stack=["python", "django"],           # +3 each
        secondary_stack=["docker", "redis"],        # +2 each
        bonus_stack=["agile"],                      # +1 each
        min_keyword_score=4,
    )


@pytest.fixture
def repo():
    return InMemoryJobRepository()


@pytest.fixture
def service(criteria, repo):
    return ScoreService(criteria=criteria, job_repo=repo)


# --- Helpers ---

def _save_unscored(repo, **overrides) -> Job:
    defaults = dict(
        title="Backend Developer",
        company="Acme",
        location="Barcelona",
        description="We use python and django",
        job_url="https://example.com/job/1",
        site="linkedin",
        is_remote=False,
        status="unscored",
    )
    defaults.update(overrides)
    return repo.save(Job(**defaults))


# =============================================================
# Keyword scoring logic
# =============================================================

class TestKeywordScoring:

    def test_core_stack_adds_3_per_keyword(self, service, repo):
        """python(3) + django(3) = 6 → passes threshold of 4."""
        _save_unscored(repo, description="We use python and django")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_secondary_stack_adds_2_per_keyword(self, service, repo):
        """docker(2) + redis(2) = 4 → passes threshold of 4."""
        _save_unscored(repo, description="Running on docker with redis cache")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_bonus_stack_adds_1_per_keyword(self, service, repo):
        """agile(1) alone = 1 → below threshold of 4."""
        _save_unscored(repo, description="Agile team looking for someone")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "below_threshold"

    def test_mixed_stacks_accumulate(self, service, repo):
        """python(3) + docker(2) = 5 → passes threshold of 4."""
        _save_unscored(repo, description="python service in docker")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_keywords_matched_in_title_too(self, service, repo):
        """python in title(3) + django in desc(3) = 6."""
        _save_unscored(repo, title="Python Developer", description="Working with django")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_keyword_matching_is_case_insensitive(self, service, repo):
        _save_unscored(repo, description="PYTHON and DJANGO required")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_no_keywords_scores_zero(self, service, repo):
        _save_unscored(repo, title="Office Admin", description="Filing paperwork")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "below_threshold"


# =============================================================
# Threshold behavior
# =============================================================

class TestThreshold:

    def test_score_exactly_at_threshold_passes(self, service, repo):
        """docker(2) + redis(2) = 4, threshold = 4 → passes."""
        _save_unscored(repo, description="docker and redis stack")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "pending_triage"

    def test_score_below_threshold_rejected(self, service, repo):
        """python(3) = 3, threshold = 4 → below."""
        _save_unscored(repo, description="python scripting only")
        service.run()
        job = list(repo._jobs.values())[0]
        assert job.status == "below_threshold"


# =============================================================
# Only processes unscored jobs
# =============================================================

class TestStatusFiltering:

    def test_only_processes_unscored_jobs(self, service, repo):
        _save_unscored(repo, job_url="https://example.com/1")
        job2 = _save_unscored(repo, job_url="https://example.com/2")
        repo.update_status(job2.id, "pending_triage")

        service.run()
        statuses = {j.job_url: j.status for j in repo._jobs.values()}
        assert statuses["https://example.com/1"] in ("pending_triage", "below_threshold")
        assert statuses["https://example.com/2"] == "pending_triage"  # untouched

    def test_no_unscored_jobs_is_noop(self, service, repo):
        """No unscored jobs → nothing happens, no errors."""
        service.run()
        assert len(repo._jobs) == 0


# =============================================================
# Batch processing
# =============================================================

class TestBatch:

    def test_mixed_batch_scored_correctly(self, service, repo):
        _save_unscored(repo, job_url="https://example.com/good",
                       description="python django docker")
        _save_unscored(repo, job_url="https://example.com/bad",
                       description="marketing analytics")
        service.run()
        jobs = {j.job_url: j.status for j in repo._jobs.values()}
        assert jobs["https://example.com/good"] == "pending_triage"
        assert jobs["https://example.com/bad"] == "below_threshold"
