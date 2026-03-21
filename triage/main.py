#!/usr/bin/env python3
"""Job search pipeline: scrape → filter → triage → notify."""

import json
import os

from .scraper import fetch_all_jobs
from .filters import apply_filters, load_seen_jobs, save_seen_jobs
from .triage import triage_jobs
from .notify import notify_jobs

PENDING_TRIAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pending_triage.json")


def _load_pending_triage() -> list[dict]:
    if os.path.exists(PENDING_TRIAGE_PATH):
        with open(PENDING_TRIAGE_PATH) as f:
            data = json.load(f)
            if data:
                print(f"  📋 {len(data)} jobs pendientes de triaje anterior")
            return data
    return []


def _save_pending_triage(jobs: list[dict]):
    with open(PENDING_TRIAGE_PATH, "w") as f:
        json.dump(jobs, f)


def _clear_pending_triage():
    _save_pending_triage([])


def _merge_jobs(filtered: list[dict], pending: list[dict]) -> list[dict]:
    """Merge filtered + pending retry jobs, dedup by id/url."""
    seen_keys = set()
    merged = []
    for job in filtered + pending:
        key = job["id"] or job["job_url"]
        if key not in seen_keys:
            seen_keys.add(key)
            merged.append(job)
    return merged


def main():
    print("=" * 50)
    print("🔍 Job Search Pipeline")
    print("=" * 50)

    to_triage = []

    try:
        # 1. Scrape
        print("\n📡 Fetching jobs...")
        jobs = fetch_all_jobs()

        # 2. Filter
        print("\n🔧 Applying filters...")
        seen = load_seen_jobs()
        filtered = apply_filters(jobs, seen) if jobs else []

        # 2.5 Merge pending triage from previous failed runs
        pending_retry = _load_pending_triage()
        to_triage = _merge_jobs(filtered, pending_retry)

        if not to_triage:
            print("No jobs to triage. Exiting.")
            return

        # 3. Triage with Claude
        print(f"\n🤖 Claude triage ({len(to_triage)} jobs)...")
        good_jobs = triage_jobs(to_triage)

        # 4. Notify
        print("\n📱 Sending notifications...")
        notify_jobs(good_jobs)

        # 5. Mark all triaged jobs as seen + clear pending
        for job in to_triage:
            seen.add(job["id"] or job["job_url"])
        save_seen_jobs(seen)
        _clear_pending_triage()

        print(f"\n✅ Done. {len(good_jobs)}/{len(to_triage)} jobs notified.")

    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        if to_triage:
            _save_pending_triage(to_triage)
            print(f"  💾 {len(to_triage)} jobs guardados en pending_triage.json para reintento")
        from .notify import send_message
        send_message(f"⚠️ Error en el pipeline, no se pudo completar el proceso:\n`{e}`")


if __name__ == "__main__":
    main()
