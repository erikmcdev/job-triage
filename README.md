# Job Triage

Automated job search pipeline that scrapes offers from multiple sources, filters and triages them with AI, generates tailored CVs, and delivers everything via Telegram.

Built to replace the manual cycle of searching offers, evaluating fit, and adapting CVs for each application.

## How it works

```
Scrape (LinkedIn, Indeed)  →  Filter (dedup, keywords, hard rules)  →  AI Triage (Claude Haiku)  →  Telegram notification
                                                                                                          ↓
                                                                                              👍 / 👎 feedback buttons
                                                                                              🎯 Generate tailored CV (PDF)
```

### 1. Multi-source scraping
- Scrapes LinkedIn and Indeed concurrently using [JobSpy](https://github.com/Bunsly/JobSpy).
- Rotating residential proxies to bypass bot detection from VPS.
- Deduplication between sources and across daily runs via `seen_jobs.json`.

### 2. Filtering and keyword scoring
Two-layer filtering before AI triage to save API costs:
- **Hard filters**: exclude by title keywords (junior, intern, frontend, consultant...), blacklisted companies, minimum salary.
- **Keyword scoring**: weighted system (core stack +3, secondary +2, bonus +1) with configurable threshold.

### 3. AI-powered triage
- Claude Haiku evaluates each offer against a CV summary.
- Returns structured JSON: score, reasoning, missing skills, expected salary, company industry.
- Prompt caching on system prompt to reduce costs on batch evaluations.

### 4. Tailored CV generation
- Claude Sonnet generates CV content (summary, experience bullets, skill selection, projects) adapted to the specific offer.
- Fills an HTML/CSS template and converts to PDF via Chromium.
- Anti-AI-writing guidelines: no generic phrases, no invented metrics, vary bullet structure.

### 5. Telegram bot
- Inline keyboard buttons on each notification: 👍 good match, 👎 bad match, 🎯 generate CV.
- Webhook (FastAPI) receives callbacks, triggers CV generation, returns PDF to chat.
- Feedback stored for periodic prompt refinement.

## Project structure

```
├── triage/                  # Pipeline package
│   ├── main.py              # Entry: scrape → filter → triage → notify
│   ├── config.py            # Search queries, filters, scoring weights, model config
│   ├── scraper.py           # JobSpy → list[dict]
│   ├── filters.py           # Dedup, hard filter, keyword score
│   ├── triage.py            # Claude Haiku evaluation
│   ├── notify.py            # Telegram notifications + inline buttons
│   └── feedback.py          # Feedback persistence
├── cv_adapter/              # CV generation + webhook (FastAPI)
│   ├── api.py               # POST /webhook — handles Telegram callbacks
│   ├── cv_generator.py      # Claude Sonnet + Jinja2 → Chromium → PDF
│   ├── template.html        # CV HTML/CSS template (bars skills)
│   └── template-v3.html     # CV template (linear skills + projects section)
├── resume-data/
│   ├── cv-base.md           # Full CV data (used by cv_generator)
│   ├── cv-summary           # Short summary (used by triage)
│   ├── personal-info.json   # Contact info for template
│   └── profile.jpg          # Photo for CV sidebar
├── tests/
│   ├── test_cv_adapter_flow.py
│   └── test_cv_generation.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Setup

### Prerequisites
- Python 3.10+
- A Telegram bot (via [@BotFather](https://t.me/BotFather))
- Anthropic API key

### Environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=your_chat_id
CV_SUMMARY_PATH=resume-data/cv-summary
TELEGRAM_SECRET_TOKEN=optional_webhook_secret
DOMAIN=yourdomain.example.com
```

### Local development

```bash
# Create and activate virtualenv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the scraping pipeline
python -m triage.main

# Run the webhook server
uvicorn cv_adapter.api:app --host 0.0.0.0 --port 8000

# Run tests
python -m pytest tests/ -v
```

### Runtime data files

These JSON files are read/written at runtime. Create them before first run:

```bash
echo '{}' > seen_jobs.json
echo '{}' > pending_jobs.json
echo '[]' > triage_feedback.json
```

## Docker deployment

```bash
# Build and start (webhook + nginx + certbot)
docker compose up -d

# Run the scraping pipeline (one-off)
docker compose run --rm triage

# View logs
docker compose logs -f cv-adapter
```

The `docker-compose.yml` runs three services:
- **cv-adapter**: FastAPI webhook server
- **nginx**: Reverse proxy with SSL (required for Telegram webhooks)
- **certbot**: Auto-renews Let's Encrypt certificates

Runtime data files must be volume-mounted — container filesystem is ephemeral.

## Configuration

Edit `triage/config.py` to customize:
- **Search queries**: sites, terms, locations
- **Hard filters**: excluded title keywords, blacklisted companies, minimum salary
- **Keyword scoring**: core/secondary/bonus stacks and weights
- **Triage threshold**: minimum Claude score to trigger notification

## Roadmap

- [ ] SQLite/PostgreSQL for shared job storage and feedback persistence
- [ ] React PWA dashboard for managing offers, filters, feedback, interacting easily with the API, and CV history from mobile
- [ ] Multi-user support with authentication and per-user configuration
- [ ] Automated filter suggestions based on accumulated negative feedback patterns
- [ ] Parametrize job queries such as search terms, dates, etc..
- [ ] Implement Ports and Adapters to decouple sources such as JobSpy from the service, and being able to easily change or add sources.
- [ ] Implement Ports and Adapters in AI triage and writing, so they're decoupled from the logic, and can also be easily interchanged and replaced by other AI providers.
