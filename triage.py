import json
import os
import time
import requests
from time import sleep
from dotenv import load_dotenv
import config

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CV_SUMMARY_PATH = os.getenv("CV_SUMMARY_PATH")


def load_cv_summary() -> str:
    with open(CV_SUMMARY_PATH, "r") as f:
        return f.read()


def evaluate_job(job: dict, cv_summary: str) -> dict | None:
    """Ask Claude to evaluate job-CV match. Returns parsed evaluation or None."""
    prompt = f"""Evaluate the match between this job offer and the candidate profile.

        JOB OFFER:
        Title: {job['title']}
        Company: {job['company']}
        Location: {job['location']}
        Remote: {job['is_remote']}
        Description:
        {job['description'][:3000]}

        CANDIDATE PROFILE:
        {cv_summary}
        CANDIDATE PROFILE END

        Respond ONLY with a JSON object, no markdown, no backticks:
        {{
        "score": <1-10 integer>,
        "reason": "<1-2 sentences explaining the score>",
        "missing_skills": ["<skill1>", "<skill2>"]
        }}"""

    try:
        sleep(0.8)
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": config.CLAUDE_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"  Claude API error {response.status_code}: {response.text[:200]}")
            return None
        print(response.status_code)
        print(response.text)
        text = response.json()["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  Error parsing Claude response: {e}")
        return None
    except requests.RequestException as e:
        print(f"  Claude request error: {e}")
        return None


def triage_jobs(jobs: list[dict]) -> list[dict]:
    """Evaluate all jobs with Claude and return those above threshold."""
    cv_summary = load_cv_summary()
    good_jobs = []

    for i, job in enumerate(jobs):
        print(f"  Triaging [{i+1}/{len(jobs)}]: {job['title']} @ {job['company']}")

        evaluation = evaluate_job(job, cv_summary)
        if not evaluation:
            continue

        job["ai_score"] = evaluation.get("score", 0)
        job["ai_reason"] = evaluation.get("reason", "")
        job["ai_missing"] = evaluation.get("missing_skills", [])

        if job["ai_score"] >= config.CLAUDE_SCORE_THRESHOLD:
            good_jobs.append(job)
            print(f"    ✅ Score: {job['ai_score']}/10")
        else:
            print(f"    ❌ Score: {job['ai_score']}/10")

        # Rate limit: ~3 requests per second
        time.sleep(0.4)

    print(f"  Triaje: {len(jobs)} → {len(good_jobs)} (>={config.CLAUDE_SCORE_THRESHOLD}/10)")
    return good_jobs