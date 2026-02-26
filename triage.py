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
    system_prompt = """You are a helpful assistant that evaluates how well a job offer matches a candidate's profile.
        You give a score from 1 to 10 and explain the reason.
        You also list any important skills mentioned in the job offer that are missing from the candidate profile, this justifies why the score is not a 10.
        Also include the matching skills in the reason, so the candidate knows what to highlight in their application.
        
        Criteria for scoring:
            - Seniority of the role:
                - Find the seniority level stated in the offer could be a role title (e.g. senior, lead, mid, junior) or in years of experience (e.g. 3+ years).
                - Compare it with the candidate's experience level. If the offer is for a senior role but the candidate is mid-level, that would lower the score.
                - If its years, and the candidate has an experience gap of more than 2 years from the offer, that would also lower the score.
                - Sometimes seniority is not at offer level but skill-level, e.g. "looking for senior python developer but mid-level in other skills is ok".
                    - In that case, evaluate the seniority for each skill and average it for the final score.
            - Skills:
                - Check the required skills in the offer and see if they are mentioned in the candidate profile.
                - If they're not mentioned but you can find transferable skills or similar experience, that can mitigate the missing skill and make it a partial match in this aspect.
                - Required skills vs nice-to-have: if the offer distinguishes between must-have and nice-to-have skills, weigh them accordingly. Missing a must-have skill is more detrimental than missing a nice-to-have.
            - Type of company:
                - If the candidate states a preference for a certain company type, or sector in they summary, take that into account.
            - Expected salary:
                - If the offer doesnt state a salary, try to infer it from the company, role, and location. And define a range of expected salary fot the offer.

        Respond ONLY with a JSON object, no markdown, no backticks:
        {
        "company_industry": str,  # e.g. fintech, consultancy, e-commerce, ... 
        "score": <1-10 integer>,
        "reason": "<1-3 sentences explaining the score>",
        "missing_skills": ["<skill1>", "<skill2>"],
        "expected_salary": {"min": int, "max": int, "currency": str}  # inferred if not stated in the offer
        }
    """
    prompt = f"""Evaluate the match between this job offer and the candidate profile.

        JOB OFFER:
        Title: {job['title']}
        Company: {job['company']}
        Location: {job['location']}
        Remote: {job['is_remote']}
        Description:
        {job['description'][:3000]}

        CANDIDATE PROFILE in markdown:
        {cv_summary}
        CANDIDATE PROFILE END

        """

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
                "max_tokens": 800,
                "system": [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
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
        job["company_industry"] = evaluation.get("company_industry", "Unknown")
        job["min_salary"] = evaluation.get("expected_salary", {}).get("min", 0)
        job["max_salary"] = evaluation.get("expected_salary", {}).get("max", 0)
        job["salary_currency"] = evaluation.get("expected_salary", {}).get("currency", "EUR")

        if job["ai_score"] >= config.CLAUDE_SCORE_THRESHOLD:
            good_jobs.append(job)
            print(f"    ✅ Score: {job['ai_score']}/10")
        else:
            print(f"    ❌ Score: {job['ai_score']}/10")

        # Rate limit: ~3 requests per second
        time.sleep(0.4)

    print(f"  Triaje: {len(jobs)} → {len(good_jobs)} (>={config.CLAUDE_SCORE_THRESHOLD}/10)")
    return good_jobs