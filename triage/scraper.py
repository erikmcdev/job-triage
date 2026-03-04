import os
from dotenv import load_dotenv
from jobspy import scrape_jobs
from . import config

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
PROXY_URL = os.getenv("PROXY_URL")


def fetch_all_jobs() -> list[dict]:
    """Fetch jobs from all configured queries using JobSpy."""
    all_jobs = []

    for query in config.SEARCH_QUERIES:
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=query["term"],
                location=query.get("location", "Barcelona"),
                results_wanted=config.RESULTS_PER_QUERY,
                country_indeed="Spain",
                linkedin_fetch_description=True,
                proxies=[PROXY_URL] if PROXY_URL else None
            )

            for _, row in df.iterrows():
                job = {
                    "id": str(row.get("id", "")),
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "")),
                    "location": str(row.get("location", "")),
                    "job_url": str(row.get("job_url", "")),
                    "description": str(row.get("description", "")),
                    "salary_min": row.get("min_amount"),
                    "salary_max": row.get("max_amount"),
                    "date_posted": str(row.get("date_posted", "")),
                    "site": str(row.get("site", "")),
                    "is_remote": bool(row.get("is_remote", False)),
                }
                all_jobs.append(job)

            print(f"  [{query['term']}] → {len(df)} ofertas")

        except Exception as e:
            import traceback
            print(f"  [{query['term']}] Error: {e}")
            traceback.print_exc()

    print(f"Total bruto: {len(all_jobs)} ofertas")
    return all_jobs
