import json
import os
import sqlite3
from datetime import datetime

from model import Job, TriageResult, Feedback
from ports import JobRepository

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_DB_PATH = os.path.join(_BASE_DIR, "jobs.db")


class SqliteJobRepository(JobRepository):
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or os.getenv("DB_PATH", _DEFAULT_DB_PATH)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                job_url TEXT NOT NULL UNIQUE,
                site TEXT NOT NULL,
                is_remote BOOLEAN NOT NULL DEFAULT 0,
                date_posted TEXT,
                status TEXT NOT NULL DEFAULT 'unscored',
                triage_score INTEGER,
                triage_reason TEXT,
                triage_missing_skills TEXT,
                triage_dealbreaker_gaps TEXT,
                triage_company_industry TEXT,
                triage_salary_min INTEGER,
                triage_salary_max INTEGER,
                triage_salary_currency TEXT,
                feedback_verdict TEXT,
                feedback_reason TEXT,
                feedback_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_job_url ON jobs(job_url);
        """)

    def close(self):
        self._conn.close()

    # --- Row <-> Domain mapping ---

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        triage = None
        if row["triage_score"] is not None:
            triage = TriageResult(
                score=row["triage_score"],
                reason=row["triage_reason"] or "",
                missing_skills=json.loads(row["triage_missing_skills"] or "[]"),
                dealbreaker_gaps=json.loads(row["triage_dealbreaker_gaps"] or "[]"),
                company_industry=row["triage_company_industry"] or "",
                salary_min=row["triage_salary_min"] or 0,
                salary_max=row["triage_salary_max"] or 0,
                salary_currency=row["triage_salary_currency"] or "EUR",
            )

        feedback = None
        if row["feedback_verdict"] is not None:
            feedback = Feedback(
                verdict=row["feedback_verdict"],
                reason=row["feedback_reason"],
                timestamp=datetime.fromisoformat(row["feedback_at"]),
            )

        return Job(
            id=row["id"],
            site_id=row["site_id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            description=row["description"],
            job_url=row["job_url"],
            site=row["site"],
            is_remote=bool(row["is_remote"]),
            date_posted=row["date_posted"],
            status=row["status"],
            triage=triage,
            feedback=feedback,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- Queries ---

    def save(self, job: Job) -> Job:
        """Insert a new job. Returns the job with its assigned id."""
        cursor = self._conn.execute(
            """INSERT INTO jobs
               (site_id, title, company, location, description, job_url,
                site, is_remote, date_posted, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.site_id, job.title, job.company, job.location,
                job.description, job.job_url, job.site, job.is_remote,
                job.date_posted, job.status,
                job.created_at.isoformat(timespec="seconds"),
            ),
        )
        self._conn.commit()
        job.id = cursor.lastrowid
        return job

    def save_batch(self, jobs: list[Job]) -> list[Job]:
        """Insert multiple jobs, skipping duplicates by job_url."""
        saved = []
        for job in jobs:
            if self.exists(job.job_url):
                continue
            saved.append(self.save(job))
        return saved

    def get_by_id(self, job_id: int) -> Job | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._row_to_job(row) if row else None

    def get_by_url(self, job_url: str) -> Job | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE job_url = ?", (job_url,)
        ).fetchone()
        return self._row_to_job(row) if row else None

    def exists(self, job_url: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jobs WHERE job_url = ?", (job_url,)
        ).fetchone()
        return row is not None

    def get_by_status(self, status: str) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_triage(self, job_id: int, triage: TriageResult):
        self._conn.execute(
            """UPDATE jobs SET
                triage_score = ?, triage_reason = ?,
                triage_missing_skills = ?, triage_dealbreaker_gaps = ?,
                triage_company_industry = ?,
                triage_salary_min = ?, triage_salary_max = ?,
                triage_salary_currency = ?, status = 'triaged'
               WHERE id = ?""",
            (
                triage.score, triage.reason,
                json.dumps(triage.missing_skills),
                json.dumps(triage.dealbreaker_gaps),
                triage.company_industry,
                triage.salary_min, triage.salary_max,
                triage.salary_currency, job_id,
            ),
        )
        self._conn.commit()

    def update_feedback(self, job_id: int, feedback: Feedback):
        self._conn.execute(
            """UPDATE jobs SET
                feedback_verdict = ?, feedback_reason = ?, feedback_at = ?
               WHERE id = ?""",
            (
                feedback.verdict, feedback.reason,
                feedback.timestamp.isoformat(timespec="seconds"),
                job_id,
            ),
        )
        self._conn.commit()

    def update_status(self, job_id: int, status: str):
        self._conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
        )
        self._conn.commit()

    def get_seen_urls(self) -> set[str]:
        """Return all known job URLs (replaces seen_jobs.json)."""
        rows = self._conn.execute("SELECT job_url FROM jobs").fetchall()
        return {r["job_url"] for r in rows}
