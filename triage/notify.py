import os
import requests
from dotenv import load_dotenv

from model import Job
from ports import JobRepository

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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


def notify_jobs(jobs: list[Job], repo: JobRepository):
    """Send a Telegram notification for each good job."""
    if not jobs:
        send_message("🔍 Hoy no hay ofertas nuevas que pasen el filtro.")
        return

    send_message(f"🎯 *{len(jobs)} ofertas nuevas encontradas:*")

    for job in jobs:
        triage = job.triage
        missing = ", ".join(triage.missing_skills) if triage else "?"
        dealbreakers = ", ".join(triage.dealbreaker_gaps) if triage else ""
        score = triage.score if triage else "?"
        reason = triage.reason if triage else ""
        salary_min = triage.salary_min if triage else 0
        salary_max = triage.salary_max if triage else 0
        currency = triage.salary_currency if triage else "EUR"
        industry = triage.company_industry if triage else "?"

        msg = (
            f"*{job.title}*\n"
            f"🏢 {job.company} ({industry})\n"
            f"💰 {salary_min} - {salary_max} {currency}\n"
            f"📍 {job.location}\n"
            f"⭐ Match: {score}/10\n"
            f"💬 {reason}\n"
            f"⚠️ Missing: {missing or 'ninguna'}\n"
            + (f"🚫 Dealbreakers: {dealbreakers}\n" if dealbreakers else "")
            + f"🔗 [Ver oferta]({job.job_url})"
        )
        reply_markup = {
            "inline_keyboard": [[
                {"text": "👍", "callback_data": f"up:{job.id}"},
                {"text": "👎", "callback_data": f"dn:{job.id}"},
                {"text": "📄 Generar CV", "callback_data": f"cv:{job.id}"},
            ]]
        }
        send_message(msg, reply_markup=reply_markup)

        repo.update_status(job.id, "notified")

    print(f"  {len(jobs)} notificaciones enviadas")
