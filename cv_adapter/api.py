import asyncio
import json
import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException

from .cv_generator import generate_cv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "")

PENDING_JOBS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pending_jobs.json")

app = FastAPI()


def _load_pending() -> dict:
    if os.path.exists(PENDING_JOBS_PATH):
        with open(PENDING_JOBS_PATH) as f:
            return json.load(f)
    return {}


def _answer_callback(callback_id: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(
            url,
            json={"callback_query_id": callback_id, "text": "⏳ Generando CV..."},
            timeout=10,
        )
    except requests.RequestException:
        pass


def _send_message(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except requests.RequestException:
        pass


def _send_document(chat_id: str, pdf_bytes: bytes, filename: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        requests.post(
            url,
            data={"chat_id": chat_id},
            files={"document": (filename, pdf_bytes, "application/pdf")},
            timeout=60,
        )
    except requests.RequestException as e:
        print(f"  Error sending PDF: {e}")


@app.post("/webhook")
async def webhook(request: Request):
    if TELEGRAM_SECRET_TOKEN:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != TELEGRAM_SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    if "callback_query" not in data:
        return {"ok": True}

    callback = data["callback_query"]
    callback_id = callback["id"]
    callback_data = callback.get("data", "")
    chat_id = str(callback["message"]["chat"]["id"])

    if not callback_data.startswith("cv:"):
        return {"ok": True}

    job_key = callback_data[3:]
    await asyncio.to_thread(_answer_callback, callback_id)

    pending = await asyncio.to_thread(_load_pending)
    job = pending.get(job_key)
    if not job:
        await asyncio.to_thread(_send_message, chat_id, "❌ Oferta no encontrada (puede haber expirado).")
        return {"ok": True}

    await asyncio.to_thread(
        _send_message, chat_id, f"⏳ Generando CV para *{job['title']}* en *{job['company']}*..."
    )

    try:
        pdf_bytes = await asyncio.to_thread(generate_cv, job)
        company_slug = job["company"].replace(" ", "_")[:30]
        title_slug = job["title"].replace(" ", "_")[:30]
        filename = f"CV_{company_slug}_{title_slug}.pdf"
        await asyncio.to_thread(_send_document, chat_id, pdf_bytes, filename)
    except Exception as e:
        print(f"  CV generation error: {e}")
        await asyncio.to_thread(_send_message, chat_id, f"❌ Error generando CV: {e}")

    return {"ok": True}
