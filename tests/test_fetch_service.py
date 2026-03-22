"""Tests for FetchService: fetch → dedup → hard filter → save."""

from unittest.mock import patch

import pytest

from model import Job
from tests.test_job_repository_port import InMemoryJobRepository
from triage.service.fetch.service import FetchService
from triage.service.fetch.criteria import SearchCriteria, HardFilters


# --- Fixtures ---

@pytest.fixture
def filters():
    return HardFilters(
        exclude_title_keywords=["junior", "intern", "manager", "lead", "senior"],
        blacklist_companies=["SpamCorp"],
        min_salary_yearly=35000,
    )


@pytest.fixture
def criteria(filters):
    return SearchCriteria(
        queries=[
            {"site": "linkedin", "term": "python developer", "location": "Barcelona"},
        ],
        results_per_query=50,
        hours_old=72,
        hard_filters=filters,
    )


@pytest.fixture
def repo():
    return InMemoryJobRepository()


@pytest.fixture
def service(criteria, repo):
    return FetchService(criteria=criteria, job_repo=repo)


# --- Helpers ---

def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Backend Developer",
        company="GoodCo",
        location="Barcelona",
        description="Python, Django, REST APIs",
        job_url="https://example.com/job/1",
        site="linkedin",
        is_remote=False,
    )
    defaults.update(overrides)
    return Job(**defaults)


# =============================================================
# Deduplication (runs first, before hard filters)
# =============================================================

class TestDeduplication:

    def test_dedup_within_batch(self, service, repo):
        """Same URL appearing twice in one fetch → saved once."""
        jobs = [
            _make_job(title="Backend Dev", job_url="https://example.com/dup"),
            _make_job(title="Backend Dev Copy", job_url="https://example.com/dup"),
        ]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 1

    def test_dedup_against_repo(self, service, repo):
        """Job already in repo → not saved again."""
        existing = _make_job(job_url="https://example.com/old")
        repo.save(existing)
        assert len(repo._jobs) == 1

        jobs = [
            _make_job(job_url="https://example.com/old"),
            _make_job(job_url="https://example.com/new"),
        ]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 2  # old + new

    def test_dedup_empty_url_skipped(self, service, repo):
        """Jobs with empty URL should be skipped."""
        jobs = [_make_job(job_url="")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0


# =============================================================
# Hard filters (applied after dedup)
# =============================================================

class TestHardFilters:

    def test_rejects_excluded_keyword_in_title(self, service, repo):
        jobs = [_make_job(title="Junior Python Developer")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0

    def test_rejects_excluded_keyword_case_insensitive(self, service, repo):
        jobs = [_make_job(title="SENIOR Backend Engineer")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0

    def test_rejects_blacklisted_company(self, service, repo):
        jobs = [_make_job(company="SpamCorp International")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0

    def test_rejects_blacklisted_company_case_insensitive(self, service, repo):
        jobs = [_make_job(company="spamcorp")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0

    def test_rejects_salary_below_minimum(self, service, repo):
        jobs = [_make_job(title="Backend Dev", salary_min=20000, salary_max=30000)]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0

    def test_keeps_job_without_salary_info(self, service, repo):
        """Jobs without salary should pass — most offers don't include it."""
        jobs = [_make_job()]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 1

    def test_keeps_job_with_salary_above_minimum(self, service, repo):
        jobs = [_make_job(salary_min=40000, salary_max=55000)]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 1

    def test_keeps_job_passing_all_filters(self, service, repo):
        jobs = [_make_job(title="Backend Developer", company="GoodCo")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 1

    def test_mixed_batch_filters_correctly(self, service, repo):
        jobs = [
            _make_job(title="Backend Developer", job_url="https://example.com/1"),
            _make_job(title="Junior Dev", job_url="https://example.com/2"),
            _make_job(title="Python Engineer", company="SpamCorp", job_url="https://example.com/3"),
            _make_job(title="Senior Manager", job_url="https://example.com/4"),
            _make_job(title="Python Developer", job_url="https://example.com/5"),
        ]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 2
        saved_urls = {j.job_url for j in repo._jobs.values()}
        assert saved_urls == {"https://example.com/1", "https://example.com/5"}


# =============================================================
# Saved job status
# =============================================================

class TestSavedJobStatus:

    def test_saved_jobs_have_unscored_status(self, service, repo):
        jobs = [_make_job()]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        saved = list(repo._jobs.values())[0]
        assert saved.status == "unscored"

    def test_filtered_out_jobs_not_saved(self, service, repo):
        jobs = [_make_job(title="Junior Intern")]
        with patch.object(service, "_fetch", return_value=jobs):
            service.run()
        assert len(repo._jobs) == 0
