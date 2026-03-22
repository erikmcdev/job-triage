import json
import os
import time
import requests
from dotenv import load_dotenv

from model import Job, TriageResult
from ports import JobRepository

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """You are a strict assistant that evaluates how well a job offer matches a candidate's profile.
You give a score from 1 to 10 and explain the reason.
You also list any important skills mentioned in the job offer that are missing from the candidate profile.
Include the matching skills in the reason, so the candidate knows what to highlight in their application.

STEP 1 — SKILL CRITICALITY ANALYSIS (do this first, before scoring):
For each technology/skill mentioned in the offer, classify its criticality:
    - DEALBREAKER: The offer explicitly says "mandatory", "required", "must-have", "solid/advanced experience needed",
      demands X+ years of professional experience in it, or it's clearly the PRIMARY daily-use technology
      (e.g. the role title says "Node.js Developer", or the description centers around it).
    - IMPORTANT: Listed as required but without strong language about depth or years. The role uses it regularly.
    - NICE-TO-HAVE: Explicitly marked as "valorable", "bonus", "plus", or secondary in the role's day-to-day.

STEP 2 — HONEST EXPERIENCE MATCHING:
    - For each skill, check the candidate's ACTUAL professional experience. Do not inflate.
    - Self-taught, personal projects, or "learning" does NOT count as professional experience.
    - Basic/intermediate knowledge is NOT "solid experience" — be honest about proficiency levels.
    - If the candidate has 2 years with a technology, do not describe it as 4+ years.

STEP 3 — SCORING:
    - Evaluate dealbreaker gaps in CONTEXT: consider how many dealbreaker skills the offer lists, and what
      proportion the candidate is missing. Missing 1 dealbreaker out of 5 required skills where the candidate
      matches the other 4 strongly is very different from missing the single core technology the role revolves around.
    - If the candidate lacks THE primary technology the entire role is built around (e.g. the role title is
      "Go Developer" and the candidate has zero Go experience), the score should be low (3-5).
    - If the candidate lacks 1-2 dealbreaker skills out of many but matches the majority of the role well,
      the score can still be 6-7 depending on how central those missing skills are.
    - Missing IMPORTANT skills lowers the score proportionally but is less severe than dealbreakers.
    - Missing NICE-TO-HAVE skills only causes minor deductions.

    SCORE RANGE GUIDE:
    - 9-10: Excellent match. Candidate meets ALL dealbreaker skills, most important skills, seniority aligns, salary fits. Only minor nice-to-have gaps.
    - 7-8: Good match. Candidate meets most dealbreaker skills with at most 1-2 minor gaps in important skills. Viable application.
    - 5-6: Partial match. Candidate has partial experience in some dealbreaker skills or notable gaps in seniority/important skills. Stretch application.
    - 3-4: Weak match. Candidate lacks the primary technology the role revolves around, or has multiple dealbreaker gaps.
    - 1-2: No match. Completely outside the candidate's profile, or freelance/contract position.

    Additional criteria:
    - Seniority: Compare the required seniority/years with the candidate's actual experience (~4 years backend total).
      If the gap is >2 years for the overall role, lower the score. But evaluate seniority per-skill when the offer
      specifies it that way (e.g. "senior Python but mid-level in other areas is ok").
    - Role type: If the role REQUIRES professional experience in a discipline the candidate has never worked in
      professionally (e.g. "must have professional full-stack experience", "requires DevOps/SRE background"),
      treat that as a dealbreaker skill gap.
    - Employment type: Freelance/contractor positions when the offer is NOT permanent employment — score ≤ 3.
    - Salary: If the offer states a salary below the candidate's minimum, deduct heavily.
      If the salary is not stated, infer a range from company, role, and location.
    - Company/industry: Respect any preferences the candidate states in their summary.

Respond ONLY with a JSON object, no markdown, no backticks:
{
"company_industry": str,  // e.g. fintech, consultancy, e-commerce, ...
"score": <1-10 integer>,
"reason": "<1-3 sentences: which skills match, which dealbreaker/important skills are missing, and why the score is what it is>",
"missing_skills": ["<skill1>", "<skill2>"],
"dealbreaker_gaps": ["<skill the candidate lacks that the offer treats as mandatory>"],
"expected_salary": {"min": int, "max": int, "currency": str}
}
"""


class TriageService:

    def __init__(self, job_repo: JobRepository, score_threshold: int,
                 cv_summary: str, model: str = "claude-haiku-4-5-20251001"):
        self._job_repo = job_repo
        self._score_threshold = score_threshold
        self._cv_summary = cv_summary
        self._model = model

    def run(self) -> list[Job]:
        jobs = self._job_repo.get_by_status("pending_triage")
        approved = []

        for job in jobs:
            evaluation = self._evaluate_job(job)
            if evaluation is None:
                continue

            triage = TriageResult(
                score=evaluation.get("score", 0),
                reason=evaluation.get("reason", ""),
                missing_skills=evaluation.get("missing_skills", []),
                dealbreaker_gaps=evaluation.get("dealbreaker_gaps", []),
                company_industry=evaluation.get("company_industry", "Unknown"),
                keyword_score=0,
                salary_min=evaluation.get("expected_salary", {}).get("min", 0),
                salary_max=evaluation.get("expected_salary", {}).get("max", 0),
                salary_currency=evaluation.get("expected_salary", {}).get("currency", "EUR"),
            )

            self._job_repo.update_triage(job.id, triage)

            if triage.score >= self._score_threshold:
                self._job_repo.update_status(job.id, "triaged_approved")
                job.triage = triage
                job.status = "triaged_approved"
                approved.append(job)
            else:
                self._job_repo.update_status(job.id, "triaged_rejected")

        return approved

    def _evaluate_job(self, job: Job) -> dict | None:
        prompt = f"""Evaluate the match between this job offer and the candidate profile.

JOB OFFER:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Remote: {job.is_remote}
Description:
{job.description[:3000]}

CANDIDATE PROFILE in markdown:
{self._cv_summary}
CANDIDATE PROFILE END
"""
        try:
            time.sleep(0.8)
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self._model,
                    "max_tokens": 800,
                    "system": [
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Claude API error {response.status_code}: {response.text[:200]}"
                )

            text = response.json()["content"][0]["text"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"  Error parsing Claude response: {e}")
            return None
        except requests.RequestException as e:
            raise RuntimeError(f"Claude request error: {e}")
