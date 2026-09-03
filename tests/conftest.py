"""Test fixtures. Builds a real SQLite file per test — never touches the live database.

The suite must pass with the wifi off and with the scraper's `jobs.db` deleted.
Nothing here reads a configured path; every test gets its own temporary file with
a handful of hand-written rows, including the awkward ones.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobsapi.config import Settings, get_settings
from jobsapi.logging_config import JsonFormatter
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


# Runs, chosen to reproduce the two states the real data actually contains:
# a finished run, and one stuck at `running` because the scraper died without
# ever writing `finished_at`. Note finished_at == started_at on the completed
# ones — that is Build 2's bug, faithfully reproduced so the API's refusal to
# report a duration is tested against the real shape rather than an idealised one.
RUNS: list[tuple] = [
    (
        1,
        "arbeitnow",
        "2026-08-30T03:45:08+00:00",
        "2026-08-30T03:45:08+00:00",
        "ok",
        2,
        1,
        8,
        1,
    ),
    (
        2,
        "greenhouse:anthropic",
        "2026-08-31T03:45:35+00:00",
        "2026-08-31T03:45:35+00:00",
        "ok",
        1,
        1,
        8,
        1,
    ),
    # Run 3 is the post-fix era: a real elapsed time, so `duration_seconds` has
    # a positive case to prove and not just nulls. Runs 1 and 2 keep the
    # identical timestamps that the upstream bug produced, and run 4 never
    # finished. All three are the shapes the field has to tell apart.
    (
        3,
        "python_org",
        "2026-08-31T03:45:40+00:00",
        "2026-08-31T03:45:44.250000+00:00",
        "partial",
        1,
        1,
        8,
        1,
    ),
    (4, "arbeitnow", "2026-09-01T03:45:08+00:00", None, "running", None, 1, 8, None),
]

# One small change and one huge one, so truncation is exercised rather than
# assumed. The real table holds description diffs up to 30,646 characters.
_BIG = "x" * 5_000
CHANGES: list[tuple] = [
    (1, 1, "2026-08-30T03:45:08+00:00", "salary_raw", "80k-100k", "90k-120k"),
    (2, 1, "2026-08-31T03:45:08+00:00", "description", _BIG, _BIG + "y"),
    (3, 2, "2026-08-31T03:45:08+00:00", "title", "Support Eng", "Support Engineer"),
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
        conn.executemany(f"INSERT INTO runs VALUES ({', '.join('?' * 9)})", RUNS)
        conn.executemany(
            f"INSERT INTO job_changes VALUES ({', '.join('?' * 6)})", CHANGES
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _capturing_logs() -> Iterator[list[dict]]:
    """Collect structured log output as parsed dicts.

    A capturing *handler* rather than `capsys`, because `configure_logging`
    binds `sys.stdout` when the app is built — so whether capsys sees anything
    would depend on fixture ordering. Attaching a handler inside the block is
    order-independent, and it exercises the real `JsonFormatter` rather than
    assuming what it wrote.
    """
    records: list[dict] = []
    formatter = JsonFormatter()

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(json.loads(formatter.format(record)))

    handler = _Capture()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield records
    finally:
        root.removeHandler(handler)


@pytest.fixture
def capture_logs() -> Callable[[], Iterator[list[dict]]]:
    """Usage: `with capture_logs() as records: ...`"""
    return _capturing_logs


@pytest.fixture(autouse=True)
def _never_the_real_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """No test may reach the developer's real jobs.db, even by accident.

    Autouse and unconditional. Without it, a test that forgets to inject
    `Settings` silently falls back to `get_settings()` and the default path —
    which passes on a machine where the scraper's database happens to exist and
    fails everywhere else. That is exactly how Phase 1's tests broke when the
    Phase 2 startup check landed: green locally, red on CI, for a reason that had
    nothing to do with the code under test.

    Pointing the environment at a path that cannot exist turns that mistake into
    an immediate, obvious failure instead of a machine-dependent one.
    """
    monkeypatch.setenv("JOBSAPI_DB_PATH", str(tmp_path / "must-be-injected.db"))

    # The same guard for the *write* database, and it matters more here. An
    # un-injected read path fails loudly the moment it cannot find a file. An
    # un-injected write path succeeds: `appdb.connect` creates what is missing,
    # so the suite quietly built a real database under the developer's home
    # directory and every test passed. Caught by looking, not by a failure —
    # which is the whole argument for pointing the environment somewhere
    # harmless rather than trusting each test to inject settings.
    monkeypatch.setenv("JOBSAPI_APP_DB_PATH", str(tmp_path / "app-must-be-injected.db"))
    monkeypatch.delenv("JOBSAPI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def schema_sql() -> str:
    """The DDL, for tests that need to build a deliberately wrong database."""
    return SCHEMA


@pytest.fixture
def runs_only_source_client(tmp_path: Path) -> Iterator[TestClient]:
    """A client whose database has a source with a run row and no jobs.

    The asymmetry `/sources` depends on and no other fixture produces: the
    standard five rows give every source both a job and a run, and so does the
    real dataset — all eight sources appear in both tables.
    """
    path = tmp_path / "runs-only.db"
    build_database(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO runs (id, source, started_at, status) VALUES (?, ?, ?, ?)",
            (99, "lever:ghost", "2026-09-01T00:00:00+00:00", "ok"),
        )
        conn.commit()
    finally:
        conn.close()
    settings = Settings(db_path=path, app_db_path=tmp_path / "runs-only-app.db")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def empty_client(tmp_path: Path) -> Iterator[TestClient]:
    """A client over a database with the right schema and no rows at all.

    The state every aggregate has to survive and no fixture otherwise produces:
    `/stats` divides by `COUNT(*)` to report coverage, and on an empty table that
    denominator is zero.
    """
    path = tmp_path / "empty.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    settings = Settings(db_path=path, app_db_path=tmp_path / "empty-app.db")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def database_with_posted_at(tmp_path: Path) -> Callable[[str], Path]:
    """A fixture database with one chosen `posted_at` value in it.

    The values counterpart to `schema_sql`: that one exists for tests that need
    a deliberately wrong *schema*, this one for a schema that is perfectly right
    while the data in it has stopped being what the contract says. The value is
    written by `UPDATE` after a normal build rather than by editing a positional
    row tuple, so the test names the column instead of counting to it.
    """

    def build(value: str) -> Path:
        path = tmp_path / "posted-at.db"
        build_database(path)
        conn = sqlite3.connect(path)
        try:
            conn.execute("UPDATE jobs SET posted_at = ? WHERE id = 1", (value,))
            conn.commit()
        finally:
            conn.close()
        return path

    return build


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A fresh, populated database file for one test."""
    path = tmp_path / "jobs.db"
    build_database(path)
    return path


@pytest.fixture
def app_db_path(tmp_path: Path) -> Path:
    """A fresh application database per test.

    Only the path: the file itself is created by the lifespan, so every test
    also exercises `appdb.ensure_schema` for free — the same trick the `client`
    fixture already plays with the read database's startup check.
    """
    return tmp_path / "app.db"


@pytest.fixture
def settings(db_path: Path, app_db_path: Path) -> Settings:
    """Settings pointing at the fixture databases, not the environment.

    Constructed directly rather than via `get_settings()`, which is `lru_cache`d
    and reads the real environment. A test that went through the cache would
    leak configuration between tests.
    """
    return Settings(db_path=db_path, app_db_path=app_db_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient whose app was built against the fixture database.

    Used as a context manager so the lifespan runs — which means every test also
    exercises the startup schema check, for free.
    """
    with TestClient(create_app(settings)) as test_client:
        yield test_client
