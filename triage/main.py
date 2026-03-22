#!/usr/bin/env python3
"""Job search pipeline: scrape → filter → triage → notify."""

from store import JobRepository
from .scraper import fetch_all_jobs
from .filters import apply_filters
from .triage import triage_jobs
from .notify import notify_jobs, send_message


def main():
    print("=" * 50)
    print("🔍 Job Search Pipeline")
    print("=" * 50)

    repo = None
    to_triage = []

    try:
        repo = JobRepository()
        # 1. Scrape
        print("\n📡 Fetching jobs...")
        jobs = fetch_all_jobs()

        # 2. Filter (dedup uses DB instead of seen_jobs.json)
        print("\n🔧 Applying filters...")
        filtered, keyword_scores = apply_filters(jobs, repo) if jobs else ([], {})

        # 2.5 Recover jobs from previous failed triage
        pending_retry = repo.get_by_status("scraped")
        if pending_retry:
            print(f"  📋 {len(pending_retry)} jobs pendientes de triaje anterior")
            # Merge: filtered first, then pending (dedup by url)
            seen_urls = {j.job_url for j in filtered}
            for job in pending_retry:
                if job.job_url not in seen_urls:
                    filtered.append(job)
                    seen_urls.add(job.job_url)

        to_triage = filtered
        if not to_triage:
            print("No jobs to triage. Exiting.")
            return

        # 3. Save new jobs to DB (pending_retry already have ids)
        print(f"\n💾 Saving {sum(1 for j in to_triage if j.id is None)} new jobs to DB...")
        for job in to_triage:
            if job.id is None:
                repo.save(job)

        # 4. Triage with Claude
        print(f"\n🤖 Claude triage ({len(to_triage)} jobs)...")
        good_jobs = triage_jobs(to_triage, keyword_scores, repo)

        # 5. Notify
        print("\n📱 Sending notifications...")
        notify_jobs(good_jobs, repo)

        print(f"\n✅ Done. {len(good_jobs)}/{len(to_triage)} jobs notified.")

    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        send_message(f"⚠️ Error en el pipeline, no se pudo completar el proceso:\n`{e}`")

    finally:
        if repo:
            repo.close()


if __name__ == "__main__":
    main()
