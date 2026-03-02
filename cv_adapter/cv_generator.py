import base64
import json
import os
import requests
from jinja2 import Template
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

RESUME_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resume-data")
CV_BASE_PATH = os.path.join(RESUME_DATA_DIR, "cv-base.md")
PERSONAL_INFO_PATH = os.path.join(RESUME_DATA_DIR, "personal-info.json")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")

SYSTEM_PROMPT = """You are an expert CV writer that tailors CVs to specific job offers.
Given a job offer and a candidate's full CV data in markdown, generate a tailored CV as a JSON object.

Rules:
- Tailor the "about_me" section to highlight what's most relevant for this specific job. Keep it to 2 sentences maximum: the first covers the professional pitch (experience, stack, strengths), the second adds a personal touch — the candidate's way of thinking, curiosity, or what genuinely motivates them. Draw the personal angle from the "About me" and "Type of position" sections in the CV data, synthesising naturally without copying verbatim.
- Order experience entries and highlights by relevance to the job.
- Never copy "About me" or "Type of position" sections verbatim — synthesize from context.
- Reorder skills to put the most job-relevant ones first within each category.
- Keep descriptions concise and achievement-oriented.
- Write in the same language as the job offer (Spanish or English).
- Include only highlights that are relevant or transferable to the role.

Respond ONLY with a valid JSON object, no markdown, no backticks:
{
  "font_scale": <float between 0.82 and 1.0, see page-fit rules below>,
  "about_me": "<2 sentences maximum — one for the professional pitch, one for the personal touch>",
  "experience": [
    {
      "company": "<company name — industry/team if relevant, e.g. 'Company — Fintech · Data Team'>",
      "role": "<job title held>",
      "period": "<start - end>",
      "bullets": [
        "<achievement or responsibility, concise and outcome-oriented>",
        "<...>",
        "<...>"
      ],
      "tags": ["<tech or skill relevant to this specific offer>", "..."]
    }
  ],
  "education": [
    {
      "degree": "<degree name — institution, e.g. 'Computer Science — UPC'>",
      "school": "<relevant subjects or subtitle, e.g. 'Algorithms, OS, Networks, C/C++'>",
      "date": "<period, e.g. '2020 — 2022 · 4 semesters completed'>"
    }
  ]
}

Page-fit rules (the CV MUST fit in a single A4 page):
- Write exactly 3 bullets per experience entry — no more, no fewer.
- Each bullet must be a single concise sentence, maximum 20 words.
- After drafting all content, estimate if it fits on one A4 page.
- If still too long: set font_scale to 0.92. Only go lower (min 0.82) if content is significantly overflowing.
- Default font_scale is 1.0. Only reduce it when content cutting alone is not enough.

Section rules — strict boundaries:
- "experience": ONLY paid professional employment (companies where the candidate was hired). Never include personal projects, side projects, or open source work here.
- "education": ONLY formal academic degrees and university programs. Never include certifications, courses, bootcamps, or online training here.
- Certifications, courses, and personal projects are handled separately and must NOT appear in either section.

Rules for experience bullets:
- Exactly 3 bullets per experience entry — never more.
- Each bullet must be a single concise sentence, maximum 20 words, outcome-oriented.
- Pick the 3 most relevant achievements for the job offer.
- Tags must be a flat list of strings (tech names, tools, methodologies) relevant to this specific offer."""


def _load_cv_base() -> str:
    with open(CV_BASE_PATH, "r") as f:
        return f.read()


def _load_personal_info() -> dict:
    with open(PERSONAL_INFO_PATH, "r") as f:
        return json.load(f)


def _call_claude(job: dict, cv_base: str) -> dict:
    prompt = f"""Generate a tailored CV for the following job offer:

JOB OFFER:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Remote: {job.get('is_remote', False)}
Description:
{job.get('description', '')[:4000]}

CANDIDATE FULL CV DATA (markdown):
{cv_base}"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Claude API error {response.status_code}: {response.text[:300]}")

    text = response.json()["content"][0]["text"].strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def generate_cv(job: dict) -> bytes:
    """Generate a tailored PDF CV for the given job offer."""
    cv_base = _load_cv_base()
    cv_data = _call_claude(job, cv_base)
    cv_data["personal"] = _load_personal_info()

    with open(TEMPLATE_PATH, "r") as f:
        template_str = f.read()

    html_content = Template(template_str).render(**cv_data)
    return _html_to_pdf(html_content)


def _html_to_pdf(html_content: str) -> bytes:
    # Embed profile image as base64 data URL
    profile_path = os.path.join(RESUME_DATA_DIR, "profile.jpg")
    if os.path.exists(profile_path):
        with open(profile_path, "rb") as f:
            profile_b64 = base64.b64encode(f.read()).decode()
        html_content = html_content.replace('src="profile.jpg"', f'src="data:image/jpeg;base64,{profile_b64}"')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        pdf = page.pdf(format="A4", print_background=True)
        browser.close()
    return pdf
