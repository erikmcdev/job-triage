#!/usr/bin/env python3
"""Job search pipeline: fetch → score → triage → notify."""

from triage.dependencies import (
    fetch_service,
    score_service,
    triage_service,
    notify_service,
    repo,
)
def main():
    print("=" * 50)
    print("🔍 Job Search Pipeline")
    print("=" * 50)

    try:
        # 1. Fetch → dedup → hard filter → save as unscored
        print("\n📡 Fetching jobs...")
        fetched = fetch_service.run()
        print(f"  {len(fetched)} jobs tras dedup + filtros")

        if not fetched:
            print("No new jobs fetched.")

        # 2. Score unscored → pending_triage / below_threshold
        print("\n📊 Keyword scoring...")
        score_service.run()
        pending = repo.get_by_status("pending_triage")
        below = repo.get_by_status("below_threshold")
        print(f"  {len(pending)} pending triage, {len(below)} below threshold")

        if not pending:
            print("No jobs to triage.")

        # 3. Triage pending → triaged_approved / triaged_rejected
        print(f"\n🤖 Claude triage ({len(pending)} jobs)...")
        approved = triage_service.run()
        print(f"  {len(approved)} approved")

        # 4. Notify triaged_approved → notified
        print("\n📱 Sending notifications...")
        notify_service.run()

        print(f"\n✅ Done. {len(approved)} jobs notified.")

    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        try:
            notify_service.send_message(
                f"⚠️ Error en el pipeline, no se pudo completar el proceso:\n`{e}`"
            )
        except Exception as notify_error:
            print(f"  Failed to send error notification to Telegram: {notify_error}")

    finally:
        repo.close()


if __name__ == "__main__":
    main()
