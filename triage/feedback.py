import json
import os
from datetime import datetime

FEEDBACK_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "triage_feedback.json")

REASON_CODES = {
    "sen": "Demasiado senior",
    "sec": "Sector equivocado",
    "stk": "Mal stack",
    "con": "Consultora",
    "oth": "Otro",
}


def load_feedback() -> list[dict]:
    if not os.path.exists(FEEDBACK_PATH):
        return []
    with open(FEEDBACK_PATH, "r") as f:
        return json.load(f)


def save_feedback(entry: dict):
    feedback_list = load_feedback()
    feedback_list.append(entry)
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(feedback_list, f, ensure_ascii=False, indent=2)


def build_feedback_entry(job: dict, feedback: str, feedback_reason: str | None = None) -> dict:
    return {
        "job_id": job.get("id", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "company_industry": job.get("company_industry", ""),
        "location": job.get("location", ""),
        "ai_score": job.get("ai_score"),
        "ai_reason": job.get("ai_reason", ""),
        "ai_missing": job.get("ai_missing", []),
        "keyword_score": job.get("keyword_score"),
        "feedback": feedback,
        "feedback_reason": feedback_reason,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "description_snippet": job.get("description", "")[:500],
    }
