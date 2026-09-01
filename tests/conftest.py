"""Test fixtures. Builds a real SQLite file per test — never touches the live database.

The suite must pass with the wifi off and with the scraper's `jobs.db` deleted.
Nothing here reads a configured path; every test gets its own temporary file with
a handful of hand-written rows, including the awkward ones.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobsapi.config import Settings
from jobsapi.main import create_app

# Mirrors Build 2's schema. Copied rather than imported: this service is a
# *reader* of that schema and must not depend on the scraper's code. If the two
# drift apart, the startup check in db.verify_schema is what catches it.
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
"""

_SEEN = ("2026-08-01T00:00:00+00:00", "2026-08-31T03:45:00+00:00")

# Five rows, chosen so the nasty cases are always in play:
#   1 fully populated, remote=True
#   2 NULL salary/currency/location, remote=False   -> 69% of real rows look like this
#   3 remote=NULL (tri-state: unknown is not False), NULL seniority
#   4 unicode company and title
#   5 apostrophe in the title, NULL posted_at       -> sorts last under DESC
ROWS: list[tuple] = [
    (
        1,
        "arbeitnow",
        "a-1",
        "Senior Python Engineer",
        "Acme GmbH",
        "Berlin",
        1,
        90_000,
        120_000,
        "EUR",
        "90k-120k",
        "2026-08-30",
        "https://example.test/1",
        "A" * 40,
        *_SEEN,
        "h1",
        1,
        "senior",
    ),
    (
        2,
        "arbeitnow",
        "a-2",
        "Support Engineer",
        "Beta Ltd",
        None,
        0,
        None,
        None,
        None,
        None,
        "2026-08-29",
        "https://example.test/2",
        None,
        *_SEEN,
        "h2",
        1,
        "junior",
    ),
    (
        3,
        "greenhouse:anthropic",
        "g-1",
        "Research Engineer",
        "Gamma Inc",
        "Remote",
        None,
        150_000,
        200_000,
        "USD",
        "150k-200k",
        "2026-08-28",
        "https://example.test/3",
        "C" * 40,
        *_SEEN,
        "h3",
        1,
        None,
    ),
    (
        4,
        "greenhouse:figma",
        "g-2",
        "Ingénieur Logiciel",
        "Ürsprung Ähtäri Oy",
        "Zürich",
        1,
        None,
        None,
        None,
        None,
        "2026-08-27",
        "https://example.test/4",
        "D" * 40,
        *_SEEN,
        "h4",
        1,
        "staff",
    ),
    (
        5,
        "python_org",
        "p-1",
        "Developer's Advocate; 100% remote",
        "O'Reilly & Co",
        "Dublin",
        1,
        70_000,
        None,
        "GBP",
        "from 70k",
        None,
        "https://example.test/5",
        "E" * 40,
        *_SEEN,
        "h5",
        1,
        "lead",
    ),
]


def build_database(path: Path, rows: list[tuple] | None = None) -> None:
    """Create a fixture database at `path`.

    Written with a normal read-write connection: `mode=ro` is how the *service*
    opens the file, not a property of the file itself. Building it here and
    opening it read-only there is exactly the production arrangement.
    """
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            f"INSERT INTO jobs VALUES ({', '.join('?' * 19)})",
            ROWS if rows is None else rows,
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def schema_sql() -> str:
    """The DDL, for tests that need to build a deliberately wrong database."""
    return SCHEMA


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A fresh, populated database file for one test."""
    path = tmp_path / "jobs.db"
    build_database(path)
    return path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    """Settings pointing at the fixture database, not the environment.

    Constructed directly rather than via `get_settings()`, which is `lru_cache`d
    and reads the real environment. A test that went through the cache would
    leak configuration between tests.
    """
    return Settings(db_path=db_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient whose app was built against the fixture database.

    Used as a context manager so the lifespan runs — which means every test also
    exercises the startup schema check, for free.
    """
    with TestClient(create_app(settings)) as test_client:
        yield test_client
