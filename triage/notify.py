import hashlib
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PENDING_JOBS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pending_jobs.json")


def _job_key(job: dict) -> str:
    return hashlib.md5(job["job_url"].encode()).hexdigest()[:16]


def _load_pending() -> dict:
    if os.path.exists(PENDING_JOBS_PATH):
        with open(PENDING_JOBS_PATH) as f:
            return json.load(f)
    return {}


def _save_pending(data: dict):
    with open(PENDING_JOBS_PATH, "w") as f:
        json.dump(data, f)


def send_message(text: str, reply_markup=None):
    """Send a message via Telegram bot."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException as e:
        print(f"  Telegram error: {e}")


def notify_jobs(jobs: list[dict]):
    """Send a Telegram notification for each good job, with a 'Generar CV' button."""
    if not jobs:
        send_message("🔍 Hoy no hay ofertas nuevas que pasen el filtro.")
        return

    send_message(f"🎯 *{len(jobs)} ofertas nuevas encontradas:*")

    pending = _load_pending()

    for job in jobs:
        key = _job_key(job)
        pending[key] = job

        missing = ", ".join(job.get("ai_missing", [])) or "ninguna"
        msg = (
            f"*{job['title']}*\n"
            f"🏢 {job['company']} ({job['company_industry']})\n"
            f"💰 {job['min_salary']} - {job['max_salary']} {job['salary_currency']}\n"
            f"📍 {job['location']}\n"
            f"⭐ Match: {job['ai_score']}/10\n"
            f"💬 {job['ai_reason']}\n"
            f"⚠️ Missing: {missing}\n"
            f"🔗 [Ver oferta]({job['job_url']})"
        )
        reply_markup = {
            "inline_keyboard": [[
                {"text": "📄 Generar CV", "callback_data": f"cv:{key}"}
            ]]
        }
        send_message(msg, reply_markup=reply_markup)

    _save_pending(pending)
    print(f"  {len(jobs)} notificaciones enviadas")
