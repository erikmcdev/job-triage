"""Composition root: wire adapters and services."""

import os
from dotenv import load_dotenv

from store import SqliteJobRepository
from triage.service.fetch.service import FetchService
from triage.service.fetch.criteria import SearchCriteria, HardFilters
from triage.service.score.service import ScoreService
from triage.service.score.criteria import ScoreCriteria
from triage.service.triage.service import TriageService
from triage.service.notify.service import NotifyService
from . import config

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

CV_SUMMARY_PATH = os.getenv("CV_SUMMARY_PATH")


def _load_cv_summary() -> str:
    with open(CV_SUMMARY_PATH, "r") as f:
        return f.read()


repo = SqliteJobRepository()

fetch_service = FetchService(
    criteria=SearchCriteria(
        queries=config.SEARCH_QUERIES,
        results_per_query=config.RESULTS_PER_QUERY,
        hours_old=config.HOURS_OLD,
        hard_filters=HardFilters(
            exclude_title_keywords=config.EXCLUDE_TITLE_KEYWORDS,
            blacklist_companies=config.BLACKLIST_COMPANIES,
            min_salary_yearly=config.MIN_SALARY_YEARLY,
        ),
    ),
    job_repo=repo,
)

score_service = ScoreService(
    criteria=ScoreCriteria(
        core_stack=config.CORE_STACK,
        secondary_stack=config.SECONDARY_STACK,
        bonus_stack=config.BONUS_STACK,
        min_keyword_score=config.MIN_KEYWORD_SCORE,
    ),
    job_repo=repo,
)

triage_service = TriageService(
    job_repo=repo,
    score_threshold=config.CLAUDE_SCORE_THRESHOLD,
    cv_summary=_load_cv_summary(),
    model=config.CLAUDE_MODEL,
)

notify_service = NotifyService(job_repo=repo)
