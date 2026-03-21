import re
from model import Job
from store import JobRepository
from . import config


def dedup(jobs: list[Job], repo: JobRepository) -> list[Job]:
    """Remove duplicates by URL and already-seen jobs."""
    seen_urls = repo.get_seen_urls()
    unique: dict[str, Job] = {}
    for job in jobs:
        if job.job_url and job.job_url not in seen_urls and job.job_url not in unique:
            unique[job.job_url] = job
    print(f"  Dedup: {len(jobs)} → {len(unique)}")
    return list(unique.values())


def hard_filter(job: Job) -> bool:
    """Return True if job passes hard filters."""
    title_lower = job.title.lower()

    for kw in config.EXCLUDE_TITLE_KEYWORDS:
        if kw in title_lower:
            return False

    company_lower = job.company.lower()
    for company in config.BLACKLIST_COMPANIES:
        if company.lower() in company_lower:
            return False

    return True


def keyword_score(job: Job) -> int:
    """Score a job based on keyword matches in title + description."""
    text = (job.title + " " + job.description).lower()
    score = 0

    for kw in config.CORE_STACK:
        if kw.lower() in text:
            score += 3

    for kw in config.SECONDARY_STACK:
        if kw.lower() in text:
            score += 2

    for kw in config.BONUS_STACK:
        if kw.lower() in text:
            score += 1

    return score


def apply_filters(jobs: list[Job], repo: JobRepository) -> list[Job]:
    """Run full filter pipeline: dedup → hard filter → keyword score.

    Returns (filtered_jobs, keyword_scores) where keyword_scores maps job_url to score.
    The scores are kept separate because they belong to TriageResult, not Job.
    """
    jobs = dedup(jobs, repo)

    filtered = [j for j in jobs if hard_filter(j)]
    print(f"  Hard filters: {len(jobs)} → {len(filtered)}")

    scored = []
    keyword_scores: dict[str, int] = {}
    for job in filtered:
        ks = keyword_score(job)
        if ks >= config.MIN_KEYWORD_SCORE:
            keyword_scores[job.job_url] = ks
            scored.append(job)

    print(f"  Keyword scoring (>={config.MIN_KEYWORD_SCORE}): {len(filtered)} → {len(scored)}")
    return scored, keyword_scores
