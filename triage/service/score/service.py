from model import Job
from ports import JobRepository
from .criteria import ScoreCriteria


class ScoreService:

    def __init__(self, criteria: ScoreCriteria, job_repo: JobRepository):
        self._criteria = criteria
        self._job_repo = job_repo

    def run(self) -> None:
        jobs = self._job_repo.get_by_status("unscored")
        for job in jobs:
            score = self._keyword_score(job)
            if score >= self._criteria.min_keyword_score:
                self._job_repo.update_status(job.id, "pending_triage")
            else:
                self._job_repo.update_status(job.id, "below_threshold")

    def _keyword_score(self, job: Job) -> int:
        text = (job.title + " " + job.description).lower()
        score = 0
        for kw in self._criteria.core_stack:
            if kw.lower() in text:
                score += 3
        for kw in self._criteria.secondary_stack:
            if kw.lower() in text:
                score += 2
        for kw in self._criteria.bonus_stack:
            if kw.lower() in text:
                score += 1
        return score
