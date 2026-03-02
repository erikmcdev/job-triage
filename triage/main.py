#!/usr/bin/env python3
"""Job search pipeline: scrape → filter → triage → notify."""

from .scraper import fetch_all_jobs
from .filters import apply_filters, load_seen_jobs, save_seen_jobs
from .triage import triage_jobs
from .notify import notify_jobs


def main():
    print("=" * 50)
    print("🔍 Job Search Pipeline")
    print("=" * 50)

    # 1. Scrape
    print("\n📡 Fetching jobs...")
    jobs = fetch_all_jobs()
    if not jobs:
        print("No jobs found. Exiting.")
        return

    # 2. Filter
    print("\n🔧 Applying filters...")
    seen = load_seen_jobs()
    filtered = apply_filters(jobs, seen)
    if not filtered:
        print("No jobs passed filters. Exiting.")
        return

    # 3. Triage with Claude
    print("\n🤖 Claude triage...")
    good_jobs = triage_jobs(filtered)

    # 4. Notify
    print("\n📱 Sending notifications...")
    notify_jobs(good_jobs)

    # 5. Mark all filtered jobs as seen (not just good ones)
    for job in filtered:
        seen.add(job["id"] or job["job_url"])
    save_seen_jobs(seen)

    print(f"\n✅ Done. {len(good_jobs)}/{len(jobs)} jobs notified.")


if __name__ == "__main__":
    main()
