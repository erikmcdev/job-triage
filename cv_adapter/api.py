import asyncio
import json
import logging
import os
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException

from model import Job, Feedback
from store import SqliteJobRepository
from .cv_generator import generate_cv

logger = logging.getLogger("cv_adapter")
logging.basicConfig(level=logging.INFO)

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "")

REASON_CODES = {
    "sen": "Demasiado senior",
    "sec": "Sector equivocado",
    "stk": "Mal stack",
    "con": "Consultora",
    "oth": "Otro",
}

app = FastAPI()


def _get_repo() -> SqliteJobRepository:
    return SqliteJobRepository()


def _answer_callback(callback_id: str, text: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException:
        pass


def _send_message(chat_id: str, text: str, reply_markup=None, force_reply: bool = False):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    elif force_reply:
        payload["reply_markup"] = {"force_reply": True, "selective": True}
    try:
        requests.post(url, json=payload, timeout=10)
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


def _edit_reply_markup(chat_id: str, message_id: int, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"
    payload = {"chat_id": chat_id, "message_id": message_id}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    else:
        payload["reply_markup"] = {"inline_keyboard": []}
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException:
        pass


def _get_job(job_id: int) -> Job | None:
    repo = _get_repo()
    try:
        return repo.get_by_id(job_id)
    finally:
        repo.close()


def _save_job_feedback(job_id: int, verdict: str, reason: str | None = None):
    feedback = Feedback(
        verdict=verdict,
        reason=reason,
        timestamp=datetime.now(),
    )
    repo = _get_repo()
    try:
        repo.update_feedback(job_id, feedback)
    finally:
        repo.close()


def _original_buttons(job_id: int) -> dict:
    """Return the original inline keyboard for a job notification."""
    return {
        "inline_keyboard": [[
            {"text": "👍", "callback_data": f"up:{job_id}"},
            {"text": "👎", "callback_data": f"dn:{job_id}"},
            {"text": "📄 Generar CV", "callback_data": f"cv:{job_id}"},
        ]]
    }


# --- Callback handlers ---

async def _handle_thumbs_up(callback_id: str, chat_id: str, message_id: int, job_id: int):
    logger.info("👍 handler: job_id=%s", job_id)
    job = await asyncio.to_thread(_get_job, job_id)
    if not job:
        logger.warning("👍 job not found: job_id=%s", job_id)
        await asyncio.to_thread(_answer_callback, callback_id, "❌ Oferta no encontrada")
        return

    try:
        await asyncio.to_thread(_save_job_feedback, job_id, "positive")
        logger.info("👍 feedback saved: job_id=%s title=%s", job_id, job.title)
    except Exception as e:
        logger.exception("👍 failed to save feedback: job_id=%s", job_id)
        await asyncio.to_thread(_answer_callback, callback_id, f"❌ Error guardando: {e}")
        return

    await asyncio.to_thread(_answer_callback, callback_id, "👍 Guardado")

    new_markup = {
        "inline_keyboard": [[
            {"text": "✅ 👍", "callback_data": "noop"},
            {"text": "📄 Generar CV", "callback_data": f"cv:{job_id}"},
        ]]
    }
    await asyncio.to_thread(_edit_reply_markup, chat_id, message_id, new_markup)


async def _handle_thumbs_down(callback_id: str, chat_id: str, message_id: int, job_id: int):
    logger.info("👎 handler: job_id=%s", job_id)
    await asyncio.to_thread(_answer_callback, callback_id, "Selecciona la razón:")

    reason_keyboard = {
        "inline_keyboard": [
            [
                {"text": "Demasiado senior", "callback_data": f"dr:{job_id}:sen"},
                {"text": "Sector equivocado", "callback_data": f"dr:{job_id}:sec"},
            ],
            [
                {"text": "Mal stack", "callback_data": f"dr:{job_id}:stk"},
                {"text": "Consultora", "callback_data": f"dr:{job_id}:con"},
            ],
            [
                {"text": "Otro", "callback_data": f"dr:{job_id}:oth"},
            ],
        ]
    }
    await asyncio.to_thread(_edit_reply_markup, chat_id, message_id, reason_keyboard)


async def _handle_down_reason(callback_id: str, chat_id: str, message_id: int, job_id: int, code: str):
    logger.info("👎 reason handler: job_id=%s code=%s", job_id, code)
    job = await asyncio.to_thread(_get_job, job_id)
    if not job:
        logger.warning("👎 reason: job not found job_id=%s", job_id)
        await asyncio.to_thread(_answer_callback, callback_id, "❌ Oferta no encontrada")
        return

    if code == "oth":
        await asyncio.to_thread(_answer_callback, callback_id)
        await asyncio.to_thread(
            _send_message, chat_id,
            f"✍️ Escribe la razón (ref:{job_id}):",
            force_reply=True,
        )
        await asyncio.to_thread(_edit_reply_markup, chat_id, message_id)
        return

    reason_text = REASON_CODES.get(code, code)
    try:
        await asyncio.to_thread(_save_job_feedback, job_id, "negative", reason_text)
        logger.info("👎 feedback saved: job_id=%s reason=%s", job_id, reason_text)
    except Exception as e:
        logger.exception("👎 failed to save feedback: job_id=%s", job_id)
        await asyncio.to_thread(_answer_callback, callback_id, f"❌ Error guardando: {e}")
        await asyncio.to_thread(_edit_reply_markup, chat_id, message_id, _original_buttons(job_id))
        return

    await asyncio.to_thread(_answer_callback, callback_id, f"👎 Guardado: {reason_text}")
    await asyncio.to_thread(_edit_reply_markup, chat_id, message_id)


async def _handle_cv_generation(callback_id: str, chat_id: str, message_id: int, job_id: int):
    await asyncio.to_thread(_answer_callback, callback_id, "⏳ Generando CV...")

    job = await asyncio.to_thread(_get_job, job_id)
    if not job:
        await asyncio.to_thread(_send_message, chat_id, "❌ Oferta no encontrada (puede haber expirado).")
        return

    await asyncio.to_thread(_save_job_feedback, job_id, "cv_generated")

    await asyncio.to_thread(
        _send_message, chat_id, f"⏳ Generando CV para *{job.title}* en *{job.company}*..."
    )

    try:
        pdf_bytes = await asyncio.to_thread(generate_cv, job)
        company_slug = job.company.replace(" ", "_")[:30]
        title_slug = job.title.replace(" ", "_")[:30]
        filename = f"CV_{company_slug}_{title_slug}.pdf"
        await asyncio.to_thread(_send_document, chat_id, pdf_bytes, filename)
    except Exception as e:
        print(f"  CV generation error: {e}")
        await asyncio.to_thread(_send_message, chat_id, f"❌ Error generando CV: {e}")


async def _handle_force_reply(chat_id: str, text: str, reply_text: str):
    """Handle text reply to ForceReply (free-text reason for negative feedback)."""
    logger.info("Force reply handler: user_text=%s reply_text=%s", text[:100], reply_text[:100])
    match = re.search(r"ref:(\d+)", reply_text)
    if not match:
        logger.warning("Force reply: no ref: pattern found in reply_text")
        return

    job_id = int(match.group(1))
    logger.info("Force reply: job_id=%s", job_id)
    job = await asyncio.to_thread(_get_job, job_id)
    if not job:
        logger.warning("Force reply: job not found job_id=%s", job_id)
        await asyncio.to_thread(_send_message, chat_id, "❌ Oferta no encontrada.")
        return

    try:
        await asyncio.to_thread(_save_job_feedback, job_id, "negative", text)
        logger.info("Force reply: feedback saved job_id=%s reason=%s", job_id, text)
    except Exception as e:
        logger.exception("Force reply: failed to save feedback job_id=%s", job_id)
        await asyncio.to_thread(_send_message, chat_id, f"❌ Error guardando feedback: {e}")
        return

    await asyncio.to_thread(_send_message, chat_id, f"👎 Guardado: {text}")


def _parse_job_id(data: str) -> int | None:
    """Parse job ID from callback data like 'up:123'."""
    try:
        return int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


# --- Main webhook ---

@app.post("/webhook")
async def webhook(request: Request):
    if TELEGRAM_SECRET_TOKEN:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != TELEGRAM_SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()
    logger.info("Webhook received: %s", json.dumps(data, ensure_ascii=False)[:500])

    # Handle callback queries (button presses)
    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        callback_data = callback.get("data", "")
        chat_id = str(callback["message"]["chat"]["id"])
        message_id = callback["message"]["message_id"]
        logger.info("Callback: data=%s chat=%s msg=%s", callback_data, chat_id, message_id)

        try:
            if callback_data.startswith("cv:"):
                job_id = _parse_job_id(callback_data)
                if job_id is not None:
                    await _handle_cv_generation(callback_id, chat_id, message_id, job_id)
            elif callback_data.startswith("up:"):
                job_id = _parse_job_id(callback_data)
                if job_id is not None:
                    await _handle_thumbs_up(callback_id, chat_id, message_id, job_id)
            elif callback_data.startswith("dn:"):
                job_id = _parse_job_id(callback_data)
                if job_id is not None:
                    await _handle_thumbs_down(callback_id, chat_id, message_id, job_id)
            elif callback_data.startswith("dr:"):
                parts = callback_data.split(":")
                if len(parts) == 3:
                    job_id = int(parts[1])
                    await _handle_down_reason(callback_id, chat_id, message_id, job_id, parts[2])
                else:
                    logger.warning("Unexpected dr: parts count: %d -> %s", len(parts), parts)
            else:
                logger.warning("Unknown callback_data: %s", callback_data)
        except Exception:
            logger.exception("Error handling callback %s", callback_data)
            raise

        return {"ok": True}

    # Handle text messages (ForceReply responses for "Otro")
    message = data.get("message", {})
    if message.get("reply_to_message") and message.get("text"):
        reply_text = message["reply_to_message"].get("text", "")
        logger.info("Reply message detected. reply_text=%s user_text=%s", reply_text[:100], message["text"][:100])
        if "ref:" in reply_text:
            chat_id = str(message["chat"]["id"])
            await _handle_force_reply(chat_id, message["text"], reply_text)
        else:
            logger.warning("Reply message did not contain 'ref:' — ignoring")
    elif "message" in data:
        logger.info("Non-reply message received — ignoring")

    return {"ok": True}
