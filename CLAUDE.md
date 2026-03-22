# Job Triage

Daily job scraping pipeline + Telegram bot with CV generation webhook.

## Project structure

```
├── triage/                  # Pipeline package
│   ├── main.py              # Entry: scrape → filter → triage → notify (legacy, being decomposed)
│   ├── config.py            # Search queries, filters, Claude model config (legacy)
│   ├── scraper.py           # JobSpy → list[dict] (legacy, replaced by FetchService)
│   ├── filters.py           # Dedup, hard filter, keyword score (legacy, replaced by services)
│   ├── triage.py            # Claude Haiku evaluation
│   ├── notify.py            # Telegram send + inline 👍/👎/CV buttons
│   └── service/             # Decoupled pipeline services
│       ├── fetch/
│       │   ├── service.py   # FetchService: fetch → dedup → hard filter → save
│       │   └── criteria.py  # SearchCriteria + HardFilters
│       └── score/
│           ├── service.py   # ScoreService: keyword score → pending_triage / below_threshold
│           └── criteria.py  # ScoreCriteria (core/secondary/bonus stacks + threshold)
├── cv_adapter/              # CV generation + feedback webhook (FastAPI)
│   ├── api.py               # POST /webhook — handles all Telegram callbacks
│   └── cv_generator.py      # Claude Sonnet + Jinja2 → WeasyPrint → PDF
├── model/                   # Domain model (dataclasses)
│   └── job.py               # Job, TriageResult, Feedback
├── ports/                   # Port interfaces (ABC)
│   └── job_repository.py    # JobRepository abstract contract
├── store/                   # Adapters (persistence implementations)
│   └── repository.py        # SqliteJobRepository (implements JobRepository port)
├── resume-data/
│   ├── cv-base.md           # Full CV data (used by cv_generator)
│   └── cv-summary           # Short summary (used by triage)
├── tests/
│   ├── service/
│   │   ├── fetch/
│   │   │   └── test_fetch_service.py   # FetchService: dedup, hard filters, status
│   │   └── score/
│   │       └── test_score_service.py   # ScoreService: keyword scoring, threshold, batch
│   ├── test_job_repository_port.py     # Contract tests + InMemoryJobRepository
│   ├── test_sqlite_adapter.py          # SQLite adapter runs contract suite
│   ├── test_cv_adapter_flow.py         # Webhook + feedback integration tests
│   └── test_cv_generation.py
├── docker-compose.yml       # cv-adapter, nginx, certbot
└── Dockerfile
```

## Architecture: Ports & Adapters

- `ports/job_repository.py` — ABC defining the persistence contract (save, get_by_id, update_triage, etc.)
- `store/repository.py` — `SqliteJobRepository` implements the port (current adapter)
- Domain modules (`triage/`, `cv_adapter/`) depend on the port, not the adapter
- Composition roots (`triage/main.py`, `cv_adapter/api.py`) inject `SqliteJobRepository`
- Contract tests in `test_job_repository_port.py` run with `InMemoryJobRepository`; any new adapter inherits `TestJobRepositoryContract` and overrides the `repo` fixture

## Pipeline services

Pipeline is being decomposed into independent services, each with a `job_repo: JobRepository` dependency:

1. **FetchService** (`triage/service/fetch/`) — fetch → dedup → hard filter → save as `unscored`
2. **ScoreService** (`triage/service/score/`) — load `unscored` → keyword score → update to `pending_triage` or `below_threshold`
3. Triage + Notify — not yet migrated to services

Job statuses: `unscored` → `pending_triage` / `below_threshold` → `triaged` → `notified`

## Runtime data

- `data/jobs.db` — SQLite database (single flat `jobs` table with triage/feedback inlined)
- Docker mounts `./data:/app/data` directory + `DB_PATH=/app/data/jobs.db` env var
- SQLite creates the DB file automatically if it doesn't exist (no more `touch` needed)

## Key design decisions

- Telegram callback_data prefixes: `up:`, `dn:`, `dr:`, `cv:` + DB integer ID
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
# On VPS — ensure data directory exists before first deploy
mkdir -p data

# Deploy
docker compose up -d
```

Container filesystem is ephemeral — `data/` must be volume-mounted in docker-compose.yml.

## .env variables

- ANTHROPIC_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- CV_SUMMARY_PATH (path to resume-data/cv-summary)
- TELEGRAM_SECRET_TOKEN (optional, webhook security)
- DOMAIN (used by nginx)
