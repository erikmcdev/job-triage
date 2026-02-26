import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_message(text: str):
    """Send a message via Telegram bot."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"  Telegram error: {e}")


def notify_jobs(jobs: list[dict]):
    """Send a Telegram notification for each good job."""
    if not jobs:
        send_message("🔍 Hoy no hay ofertas nuevas que pasen el filtro.")
        return

    send_message(f"🎯 *{len(jobs)} ofertas nuevas encontradas:*")

    for job in jobs:
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
        send_message(msg)

    print(f"  {len(jobs)} notificaciones enviadas")