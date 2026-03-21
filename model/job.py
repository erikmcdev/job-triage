from dataclasses import dataclass, field
from datetime import datetime


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
    site_id: str | None = None
    id: int | None = None
    status: str = "scraped"
    triage: TriageResult | None = None
    feedback: Feedback | None = None
    created_at: datetime = field(default_factory=datetime.now)
