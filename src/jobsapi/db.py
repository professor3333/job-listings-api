"""Connection handling. One connection per request, read-only, never shared."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from jobsapi.config import Settings
from jobsapi.errors import (
    DatabaseUnavailable,
    DatabaseWedged,
    JobsAPIError,
    SchemaContractError,
)

# The columns this service actually reads. `user_version` is 0 in the source
# database, so there is no schema version to compare against; verifying the
# columns exist is the only drift check available.
REQUIRED_JOB_COLUMNS = frozenset(
    {
        "id",
        "source",
        "source_id",
        "title",
        "company",
        "location",
        "remote",
        "salary_min",
        "salary_max",
        "currency",
        "salary_raw",
        "posted_at",
        "url",
        "description",
        "first_seen",
        "last_seen",
        "seniority",
    }
)


def classify(exc: sqlite3.Error) -> JobsAPIError | None:
    """Map a SQLite error to a domain error, by *code* and never by message.

    `str(exc)` for these two conditions is "database is locked" and "attempt to
    write a readonly database" — but matching on message text is the wrong seam:
    it is unversioned, localised in principle, and shared by unrelated causes.
    `sqlite_errorname` (Python 3.11+) is the actual discriminator.

    Returns None when the error is not one this service has a considered
    response for, so the caller can let it surface as a 500 rather than
    disguising an unknown fault as a known one.
    """
    name = getattr(exc, "sqlite_errorname", "") or ""
    if name.startswith("SQLITE_BUSY"):
        return DatabaseUnavailable(str(exc))
    if name == "SQLITE_READONLY_ROLLBACK":
        return DatabaseWedged(str(exc))
    return None


def connect(settings: Settings) -> sqlite3.Connection:
    """Open a read-only connection to the configured database.

    `mode=ro` is enforced at the connection, not by intention: the URI form is
    the only way to ask SQLite itself to refuse writes. A plain
    `sqlite3.connect(path)` would happily create an empty database if the path
    were wrong, which is exactly the silent failure the hardening table forbids.

    `check_same_thread=False` because FastAPI runs sync dependencies and sync
    endpoints in a threadpool, and the dependency that opens this connection may
    land on a different worker thread from the endpoint that uses it. That is
    safe *only* because the connection is created per request and never shared
    between them — the same reason a module-level connection would be a bug.
    """
    uri = f"{settings.db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(settings.busy_timeout_ms)}")
    return conn


def verify_schema(conn: sqlite3.Connection) -> None:
    """Fail loudly if the source schema has drifted out from under this service.

    `PRAGMA table_info` returns one row per column. Comparing against the set
    this service reads converts silent drift — a renamed column quietly
    returning NULL forever — into a refusal to start.
    """
    present = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if not present:
        raise SchemaContractError("Table 'jobs' is missing from the database.")
    missing = REQUIRED_JOB_COLUMNS - present
    if missing:
        raise SchemaContractError(
            f"Table 'jobs' is missing expected column(s): {', '.join(sorted(missing))}."
        )


def check_database(settings: Settings) -> None:
    """Startup gate: the database must exist, open read-only, and match.

    Called from the application lifespan so that a bad configuration is a
    startup failure with a readable message, rather than a 500 on whichever
    unlucky request arrives first.
    """
    if not settings.db_path.exists():
        raise SchemaContractError(f"Database file not found: {settings.db_path}")
    conn = connect(settings)
    try:
        verify_schema(conn)
    finally:
        conn.close()


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Per-request connection dependency.

    A generator dependency: everything before `yield` runs on the way in,
    everything after runs on the way out — even if the endpoint raised. That is
    what guarantees the connection is closed, and it is why this is a dependency
    rather than a global. A single shared `sqlite3.Connection` would serialise
    every request behind one lock and leak transaction state between unrelated
    callers.
    """
    settings: Settings = request.app.state.settings
    try:
        conn = connect(settings)
    except sqlite3.Error as exc:
        raise (classify(exc) or exc) from exc
    try:
        yield conn
    finally:
        conn.close()
