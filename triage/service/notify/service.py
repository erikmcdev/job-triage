import os
import requests
from dotenv import load_dotenv

from model import Job
from ports import JobRepository

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


class NotifyService:

    def __init__(self, job_repo: JobRepository):
        self._job_repo = job_repo

    def run(self) -> None:
        jobs = self._job_repo.get_by_status("triaged_approved")

        if not jobs:
            self._send_message("🔍 Hoy no hay ofertas nuevas que pasen el filtro.")
            return

        self._send_message(f"🎯 *{len(jobs)} ofertas nuevas encontradas:*")

        for job in jobs:
            try:
                self._notify_job(job)
                self._job_repo.update_status(job.id, "notified")
            except Exception as e:
                print(f"  Error notifying {job.title}: {e}")

    def _notify_job(self, job: Job) -> None:
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
        self._send_message(msg, reply_markup=reply_markup)

    def _send_message(self, text: str, **kwargs) -> None:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        if "reply_markup" in kwargs:
            payload["reply_markup"] = kwargs["reply_markup"]
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
