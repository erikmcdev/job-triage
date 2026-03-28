from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class TriageResult:
    score: int
    reason: str
    missing_skills: list[str]
    dealbreaker_gaps: list[str]
    company_industry: str
    keyword_score: int
    salary_min: int
    salary_max: int
    salary_currency: str


@dataclass(frozen=True)
class Feedback:
    verdict: str  # positive, negative, cv_generated
    reason: str | None
    timestamp: datetime


@dataclass
class Job:
    title: str
    company: str
    location: str
    description: str
    job_url: str
    site: str
    is_remote: bool
    date_posted: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    site_id: str | None = None
    id: int | None = None
    status: Literal["unscored", "pending_triage", "below_threshold", "triaged_approved", "triaged_rejected", "notified", "applied"] = "unscored"
    triage: TriageResult | None = None
    feedback: Feedback | None = None
    created_at: datetime = field(default_factory=datetime.now)
