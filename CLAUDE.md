# Job Triage

Daily job scraping pipeline + Telegram bot with CV generation webhook.

## Project structure

```
├── main.py                  # Pipeline entry: scrape → filter → triage → notify
├── triage/                  # Pipeline package
│   ├── config.py            # Search queries, filters, Claude model config
│   ├── scraper.py           # JobSpy → list[dict]
│   ├── filters.py           # Dedup, hard filter, keyword score
│   ├── triage.py            # Claude Haiku evaluation
│   ├── notify.py            # Telegram send + inline 👍/👎/CV buttons
│   └── feedback.py          # Feedback persistence (triage_feedback.json)
├── cv_adapter/              # CV generation + feedback webhook (FastAPI)
│   ├── api.py               # POST /webhook — handles all Telegram callbacks
│   └── cv_generator.py      # Claude Sonnet + Jinja2 → WeasyPrint → PDF
├── resume-data/
│   ├── cv-base.md           # Full CV data (used by cv_generator)
│   └── cv-summary           # Short summary (used by triage)
├── tests/
│   ├── test_cv_adapter_flow.py  # Webhook + feedback integration tests
│   └── test_cv_generation.py
├── docker-compose.yml       # cv-adapter, nginx, certbot
└── Dockerfile
```

## Runtime data files

These files are read/written at runtime and must be volume-mounted in Docker:
- `seen_jobs.json` — tracks processed job IDs (dedup)
- `pending_jobs.json` — full job dicts keyed by MD5(job_url)[:16], written by notify.py, read by api.py
- `triage_feedback.json` — user feedback from Telegram buttons

## Key design decisions

- Telegram callback_data prefixes: `up:`, `dn:`, `dr:`, `cv:` + 16-char hex key
- Feedback flow: 👍 saves directly; 👎 shows reason keyboard → preset saves directly, "Otro" uses ForceReply for free text
- triage uses `claude-haiku-4-5-20251001`; cv_generator uses `claude-sonnet-4-6`
- CV gen system prompt: omit gap Jan 2022–Feb 2024; write in job offer's language
- All file paths resolved via `os.path.dirname(os.path.dirname(__file__))` relative to package

## Development

```bash
# Activate venv
source .venv/bin/activate

# Run tests
python -m pytest tests/ -v

# Run pipeline locally
python main.py

# Run webhook locally
uvicorn cv_adapter.api:app --host 0.0.0.0 --port 8000
```

## Docker / VPS deployment

```bash
# On VPS — ensure runtime data files exist before first deploy
touch seen_jobs.json pending_jobs.json triage_feedback.json
echo '{}' > seen_jobs.json
echo '{}' > pending_jobs.json
echo '[]' > triage_feedback.json

# Deploy
docker compose up -d
```

Container filesystem is ephemeral — any runtime data file NOT volume-mounted in docker-compose.yml will be lost on container recreation.

## .env variables

- ANTHROPIC_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- CV_SUMMARY_PATH (path to resume-data/cv-summary)
- TELEGRAM_SECRET_TOKEN (optional, webhook security)
- DOMAIN (used by nginx)
