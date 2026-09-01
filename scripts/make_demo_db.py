"""Build a small demo database with Build 2's schema.

This service is a *reader*. It does not own the schema and does not create the
database it serves — Build 2 does. This script exists for the two cases where
Build 2's `jobs.db` is not available and something still has to run:

  * a stranger who cloned this repo and wants to see the API work;
  * CI, which has no scraper and no 58 MB database, but does need to prove the
    container serves real rows from a mounted volume.

It is a development convenience, never imported by `src/jobsapi/`, and nothing
in the service depends on it existing.

The schema below is *copied* from Build 2, for the same reason `tests/conftest.py`
copies it: depending on the scraper's code would couple two repos that are
deliberately separate. `db.verify_schema` is what catches the two drifting apart.

    uv run python scripts/make_demo_db.py data/demo.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SCHEMA = """
CREATE TABLE jobs (
    id           INTEGER PRIMARY KEY,
    source       TEXT    NOT NULL,
    source_id    TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    company      TEXT    NOT NULL,
    location     TEXT,
    remote       INTEGER,
    salary_min   INTEGER,
    salary_max   INTEGER,
    currency     TEXT,
    salary_raw   TEXT,
    posted_at    TEXT,
    url          TEXT    NOT NULL,
    description  TEXT,
    first_seen   TEXT    NOT NULL,
    last_seen    TEXT    NOT NULL,
    content_hash TEXT    NOT NULL,
    hash_version INTEGER NOT NULL DEFAULT 1,
    seniority    TEXT,
    UNIQUE (source, source_id)
);
CREATE INDEX idx_jobs_source_lastseen ON jobs(source, last_seen);
CREATE INDEX idx_jobs_posted          ON jobs(posted_at);

CREATE TABLE runs (
    id            INTEGER PRIMARY KEY,
    source        TEXT    NOT NULL,
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    status        TEXT    NOT NULL,
    rows_parsed   INTEGER,
    rules_version INTEGER NOT NULL DEFAULT 1,
    page_cap      INTEGER,
    pages_fetched INTEGER
);
CREATE INDEX idx_runs_source_status ON runs(source, status, started_at);

CREATE TABLE job_changes (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES jobs(id),
    observed_at TEXT    NOT NULL,
    field       TEXT    NOT NULL,
    old_value   TEXT,
    new_value   TEXT
);
CREATE INDEX idx_changes_job ON job_changes(job_id, observed_at);
"""

_SEEN = {
    "first_seen": "2026-08-01T00:00:00+00:00",
    "last_seen": "2026-08-31T03:45:00+00:00",
}

# Named columns rather than 19 positional values, because a demo database is
# something a stranger reads before they trust the service. Deliberately
# includes the awkward rows, so a demo exercises the decisions this build
# documented rather than only the happy path: a NULL salary (the majority case
# in the real data), a NULL `remote` (tri-state — unknown is not false), a
# unicode company, an apostrophe in a title, and a NULL `posted_at`.
JOBS: list[dict] = [
    {
        "id": 1,
        "source": "arbeitnow",
        "source_id": "a-1",
        "title": "Senior Python Engineer",
        "company": "Acme GmbH",
        "location": "Berlin",
        "remote": 1,
        "salary_min": 90_000,
        "salary_max": 120_000,
        "currency": "EUR",
        "salary_raw": "90k-120k",
        "posted_at": "2026-08-30",
        "url": "https://example.test/1",
        "description": "Builds and runs the platform APIs. " * 4,
        "content_hash": "h1",
        "hash_version": 1,
        "seniority": "senior",
        **_SEEN,
    },
    {
        # No salary, no location, no description — what ~70% of real rows look like.
        "id": 2,
        "source": "arbeitnow",
        "source_id": "a-2",
        "title": "Support Engineer",
        "company": "Beta Ltd",
        "location": None,
        "remote": 0,
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "salary_raw": None,
        "posted_at": "2026-08-29",
        "url": "https://example.test/2",
        "description": None,
        "content_hash": "h2",
        "hash_version": 1,
        "seniority": "junior",
        **_SEEN,
    },
    {
        # remote IS NULL — the scraper never established the fact.
        "id": 3,
        "source": "greenhouse:anthropic",
        "source_id": "g-1",
        "title": "Research Engineer",
        "company": "Gamma Inc",
        "location": "Remote",
        "remote": None,
        "salary_min": 150_000,
        "salary_max": 200_000,
        "currency": "USD",
        "salary_raw": "150k-200k",
        "posted_at": "2026-08-28",
        "url": "https://example.test/3",
        "description": "Research engineering. " * 6,
        "content_hash": "h3",
        "hash_version": 1,
        "seniority": "senior",
        **_SEEN,
    },
    {
        # Non-ASCII company and title: SQLite's LIKE is case-insensitive for
        # ASCII only, so `company=ürsprung` does NOT match "Ürsprung AG".
        "id": 4,
        "source": "greenhouse:anthropic",
        "source_id": "g-2",
        "title": "Ingénieur Données",
        "company": "Ürsprung AG",
        "location": "Zürich",
        "remote": 1,
        "salary_min": 110_000,
        "salary_max": 140_000,
        "currency": "CHF",
        "salary_raw": "110k-140k",
        "posted_at": "2026-08-27",
        "url": "https://example.test/4",
        "description": None,
        "content_hash": "h4",
        "hash_version": 1,
        "seniority": "staff",
        **_SEEN,
    },
    {
        # An apostrophe, a literal '%' for the LIKE-escaping demo, a NULL
        # posted_at (sorts last under the default DESC), and no seniority.
        "id": 5,
        "source": "python_org",
        "source_id": "p-1",
        "title": "Developer's Advocate (100% remote)",
        "company": "Delta Co",
        "location": None,
        "remote": 1,
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "salary_raw": None,
        "posted_at": None,
        "url": "https://example.test/5",
        "description": None,
        "content_hash": "h5",
        "hash_version": 1,
        "seniority": None,
        **_SEEN,
    },
]

RUNS: list[dict] = [
    {
        "id": 1,
        "source": "arbeitnow",
        "started_at": "2026-08-31T03:40:00+00:00",
        "finished_at": "2026-08-31T03:40:00+00:00",
        "status": "ok",
        "rows_parsed": 2,
        "rules_version": 1,
        "page_cap": 5,
        "pages_fetched": 1,
    },
    {
        "id": 2,
        "source": "greenhouse:anthropic",
        "started_at": "2026-08-31T03:42:00+00:00",
        "finished_at": "2026-08-31T03:42:00+00:00",
        "status": "ok",
        "rows_parsed": 2,
        "rules_version": 1,
        "page_cap": 5,
        "pages_fetched": 1,
    },
    {
        # Still running, so finished_at is NULL — which is also what a run that
        # died without writing it looks like. /sources reports this as-is.
        "id": 3,
        "source": "python_org",
        "started_at": "2026-08-31T03:45:00+00:00",
        "finished_at": None,
        "status": "running",
        "rows_parsed": None,
        "rules_version": 1,
        "page_cap": 5,
        "pages_fetched": 1,
    },
]

# One long value on purpose: it is what makes `/jobs/1/changes` demonstrate the
# truncation contract (`truncated: true` with the true length reported).
CHANGES: list[dict] = [
    {
        "id": 1,
        "job_id": 1,
        "observed_at": "2026-08-20T03:00:00+00:00",
        "field": "salary_max",
        "old_value": "110000",
        "new_value": "120000",
    },
    {
        "id": 2,
        "job_id": 1,
        "observed_at": "2026-08-25T03:00:00+00:00",
        "field": "description",
        "old_value": "old " * 400,
        "new_value": "new " * 400,
    },
    {
        "id": 3,
        "job_id": 3,
        "observed_at": "2026-08-26T03:00:00+00:00",
        "field": "seniority",
        "old_value": None,
        "new_value": "senior",
    },
]


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    """Named placeholders, so a column is matched by name and never by position."""
    cols = ", ".join(rows[0])
    placeholders = ", ".join(f":{c}" for c in rows[0])
    conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", rows)


def build(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        _insert(conn, "jobs", JOBS)
        _insert(conn, "runs", RUNS)
        _insert(conn, "job_changes", CHANGES)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo.db")
    build(target)
    print(
        f"Wrote {target} — {len(JOBS)} jobs, {len(RUNS)} runs, {len(CHANGES)} changes."
    )
