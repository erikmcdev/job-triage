import os
from dotenv import load_dotenv
from jobspy import scrape_jobs

from model import Job
from ports import JobRepository
from .criteria import SearchCriteria

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"))
PROXY_URL = os.getenv("PROXY_URL")


class FetchService:

    def __init__(self, criteria: SearchCriteria, job_repo: JobRepository):
        self._criteria = criteria
        self._job_repo = job_repo

    def run(self) -> list[Job]:
        raw = self._fetch()
        deduped = self._dedup(raw)
        passed = [j for j in deduped if self._criteria.hard_filters.passes(
            j.title, j.company, j.salary_min, j.salary_max
        )]
        for job in passed:
            job.status = "unscored"
            self._job_repo.save(job)
        return passed

    def _fetch(self) -> list[Job]:
        all_jobs = []
        for query in self._criteria.queries:
            try:
                df = scrape_jobs(
                    site_name=[query["site"]],
                    search_term=query["term"],
                    location=query.get("location", "Barcelona"),
                    results_wanted=self._criteria.results_per_query,
                    hours_old=self._criteria.hours_old,
                    country_indeed="Spain",
                    linkedin_fetch_description=True,
                    proxies=[PROXY_URL] if PROXY_URL else None,
                )
                for _, row in df.iterrows():
                    all_jobs.append(Job(
                        site_id=str(row.get("id", "")) or None,
                        title=str(row.get("title", "")),
                        company=str(row.get("company", "")),
                        location=str(row.get("location", "")),
                        job_url=str(row.get("job_url", "")),
                        description=str(row.get("description", "")),
                        date_posted=str(row.get("date_posted", "")) or None,
                        site=str(row.get("site", "")),
                        is_remote=bool(row.get("is_remote", False)),
                    ))
            except Exception as e:
                import traceback
                print(f"  [{query['term']}] Error: {e}")
                traceback.print_exc()
        return all_jobs

    def _dedup(self, jobs: list[Job]) -> list[Job]:
        seen_urls = self._job_repo.get_seen_urls()
        unique: dict[str, Job] = {}
        for job in jobs:
            if job.job_url and job.job_url not in seen_urls and job.job_url not in unique:
                unique[job.job_url] = job
        return list(unique.values())
