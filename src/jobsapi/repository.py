"""All the SQL. Knows nothing about HTTP.

Every value reaching SQLite does so as a bound parameter. Every *identifier* —
column names, sort direction — is a literal written here, never interpolated
from a request. Values can be parameterised; identifiers cannot, which is why
Phase 3's `sort` parameter will be an enum allowlist rather than a string.
"""

from __future__ import annotations

import sqlite3

from jobsapi.errors import JobNotFound

# Explicit column lists, never `SELECT *`. Two reasons: a `SELECT *` would start
# returning any column Build 2 adds tomorrow, and the list endpoint must not
# fetch `description` at all — filtering it out at serialisation time would
# still have paid to read ~18 MB off disk.
_SUMMARY_COLUMNS = """
    id, source, title, company, url,
    location, remote, salary_min, salary_max, currency, seniority, posted_at
"""

_DETAIL_COLUMNS = f"""
    {_SUMMARY_COLUMNS},
    source_id, salary_raw, description, first_seen, last_seen
"""


def count_jobs(conn: sqlite3.Connection) -> int:
    """Total rows, for the page envelope.

    A second query rather than a window function: `COUNT(*) OVER ()` would
    return the total on every row of the page, which is the same number
    repeated `limit` times. Two cheap queries beat one wasteful one.
    """
    return int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])


def list_jobs(conn: sqlite3.Connection, limit: int, offset: int) -> list[sqlite3.Row]:
    """One page of jobs, newest first.

    The ORDER BY carries a tie-break for a reason. `posted_at` is a plain
    `YYYY-MM-DD` date with only ~800 distinct values across 3,105 rows, so
    ordering by it alone leaves large groups of ties whose relative order SQLite
    may resolve differently between two queries. Pages would then silently
    repeat and skip rows. Appending the primary key makes the ordering total,
    which is what "stable pagination" actually requires.

    ISO dates sort correctly as text, so no conversion is needed. NULL
    `posted_at` sorts last under DESC, which is where "we never learned when
    this was posted" belongs.
    """
    return conn.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS}
        FROM jobs
        ORDER BY posted_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    """One job by id, or `JobNotFound`.

    Raises a domain error rather than returning None, so the caller cannot
    forget to check. Translating that into a 404 is the router's job — this
    module has no opinion about HTTP.
    """
    row = conn.execute(
        f"SELECT {_DETAIL_COLUMNS} FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise JobNotFound(job_id)
    return row
