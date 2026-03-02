import json
import os
import re
from . import config

SEEN_JOBS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seen_jobs.json")


def load_seen_jobs() -> set:
    """Load IDs of previously processed jobs."""
    if os.path.exists(SEEN_JOBS_PATH):
        with open(SEEN_JOBS_PATH, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen: set):
    """Persist seen job IDs."""
    with open(SEEN_JOBS_PATH, "w") as f:
        json.dump(list(seen), f)


def dedup(jobs: list[dict], seen: set) -> list[dict]:
    """Remove duplicates by ID and already-seen jobs."""
    unique = {}
    for job in jobs:
        job_id = job["id"] or job["job_url"]
        if job_id and job_id not in seen and job_id not in unique:
            unique[job_id] = job
    print(f"  Dedup: {len(jobs)} → {len(unique)}")
    return list(unique.values())


def hard_filter(job: dict) -> bool:
    """Return True if job passes hard filters."""
    title_lower = job["title"].lower()

    # Exclude by title keywords
    for kw in config.EXCLUDE_TITLE_KEYWORDS:
        if kw in title_lower:
            return False

    # Blacklist companies
    company_lower = job["company"].lower()
    for company in config.BLACKLIST_COMPANIES:
        if company.lower() in company_lower:
            return False

    # Salary filter (only if salary data exists)
    if job.get("salary_min") and job["salary_min"] > 0:
        if job["salary_min"] < config.MIN_SALARY_YEARLY:
            return False

    return True


def keyword_score(job: dict) -> int:
    """Score a job based on keyword matches in title + description."""
    text = (job["title"] + " " + job["description"]).lower()
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


def apply_filters(jobs: list[dict], seen: set) -> list[dict]:
    """Run full filter pipeline: dedup → hard filter → keyword score."""
    jobs = dedup(jobs, seen)

    filtered = [j for j in jobs if hard_filter(j)]
    print(f"  Hard filters: {len(jobs)} → {len(filtered)}")

    scored = []
    for job in filtered:
        job["keyword_score"] = keyword_score(job)
        if job["keyword_score"] >= config.MIN_KEYWORD_SCORE:
            scored.append(job)

    print(f"  Keyword scoring (>={config.MIN_KEYWORD_SCORE}): {len(filtered)} → {len(scored)}")
    return scored
