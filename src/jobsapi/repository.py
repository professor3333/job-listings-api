"""All the SQL. Knows nothing about HTTP.

Every *value* reaching SQLite does so as a bound parameter. Every *identifier* —
column names, sort direction — is a literal chosen from an allowlist written in
this file. That asymmetry is the whole lesson: `WHERE salary_min >= ?` can be
parameterised, `ORDER BY <column>` cannot, so the column has to come from a
fixed set rather than from a request.
"""

from __future__ import annotations

import sqlite3

from jobsapi.errors import JobNotFound
from jobsapi.schemas import (
    CHANGE_VALUE_MAX_LENGTH,
    JobFilters,
    Remote,
    SortField,
    SortOrder,
)

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

# API name -> real column. An explicit map rather than using the enum value
# directly, so the allowlist is visible in one place and a public parameter name
# can be renamed without renaming a column.
_SORT_COLUMNS: dict[SortField, str] = {
    SortField.posted_at: "posted_at",
    SortField.id: "id",
    SortField.company: "company",
    SortField.title: "title",
    SortField.salary_min: "salary_min",
    SortField.salary_max: "salary_max",
}

_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    """Neutralise LIKE wildcards so a search term matches literally.

    `%` and `_` are wildcards inside LIKE, so a user searching for "100%" would
    otherwise match everything beginning "100". The backslash must be escaped
    *first* — doing it last would re-escape the backslashes this function just
    added. Paired with `ESCAPE '\\'` in the SQL, which tells SQLite what the
    escape character is.

    This is not SQL injection defence — the value is still a bound parameter and
    can never be executed. It is correctness: making the search mean what the
    user typed.
    """
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


def _build_where(filters: JobFilters) -> tuple[str, list[object]]:
    """Assemble the WHERE clause from whichever filters were supplied.

    A list of conditions joined with AND, and a parallel list of parameters.
    This is the shape that scales: adding an eleventh filter is one more `if`
    appending to both lists, never a new branch multiplied against the existing
    ones. The alternative — a query string built by concatenation, or one
    hand-written SQL statement per combination of filters — is combinatorial and
    is how injection bugs get written.

    Both lists are built together so a condition and its parameters can never
    drift out of order.
    """
    clauses: list[str] = []
    params: list[object] = []

    if filters.q:
        pattern = f"%{_escape_like(filters.q)}%"
        clauses.append(
            f"(title LIKE ? ESCAPE '{_LIKE_ESCAPE}' "
            f"OR company LIKE ? ESCAPE '{_LIKE_ESCAPE}')"
        )
        params.extend([pattern, pattern])

    if filters.source is not None:
        clauses.append("source = ?")
        params.append(filters.source.value)

    if filters.company:
        # Prefix match, documented in docs/api.md. Case-insensitive because
        # SQLite's LIKE is ASCII-case-insensitive by default — which also means
        # it is *not* case-insensitive for "Ürsprung", a limitation worth
        # knowing rather than papering over.
        clauses.append(f"company LIKE ? ESCAPE '{_LIKE_ESCAPE}'")
        params.append(f"{_escape_like(filters.company)}%")

    if filters.remote is not None:
        # `unknown` is `IS NULL`, not `= 0`. NULL means the scraper never
        # established the fact; treating it as False would invent data.
        if filters.remote is Remote.unknown:
            clauses.append("remote IS NULL")
        else:
            clauses.append("remote = ?")
            params.append(1 if filters.remote is Remote.true else 0)

    if filters.seniority is not None:
        clauses.append("seniority = ?")
        params.append(filters.seniority.value)

    # NULL semantics, documented in docs/api.md: a row with no recorded salary
    # does NOT satisfy a salary filter. `NULL >= 100000` evaluates to NULL, which
    # is not true, so SQLite excludes it and that is the behaviour we want — a
    # filter on a value cannot be satisfied by the absence of that value. This
    # matters: `salary_min` is NULL in 69% of rows.
    if filters.salary_min_gte is not None:
        clauses.append("salary_min >= ?")
        params.append(filters.salary_min_gte)

    if filters.salary_max_lte is not None:
        clauses.append("salary_max <= ?")
        params.append(filters.salary_max_lte)

    if filters.currency is not None:
        clauses.append("currency = ?")
        params.append(filters.currency)

    # posted_at is stored as `YYYY-MM-DD` text, which compares correctly as a
    # string. Same NULL rule as salary: an undated row matches no date filter.
    if filters.posted_after is not None:
        clauses.append("posted_at >= ?")
        params.append(filters.posted_after.isoformat())

    if filters.posted_before is not None:
        clauses.append("posted_at <= ?")
        params.append(filters.posted_before.isoformat())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _build_order(filters: JobFilters) -> str:
    """ORDER BY, with a tie-break that makes pagination stable.

    Both halves come from our own code: the column via `_SORT_COLUMNS`, the
    direction from a two-member enum. Nothing here is interpolated from a
    request, which is why `?sort=id;DROP TABLE jobs` never reaches this
    function — it fails enum validation first.

    The trailing `id` is not decoration. Sorting by `company` or `posted_at`
    leaves large groups of tied rows whose relative order SQLite may resolve
    differently between two queries, so LIMIT/OFFSET paging would repeat some
    rows and skip others with no error anywhere. Appending the primary key makes
    the ordering total.
    """
    column = _SORT_COLUMNS[filters.sort]
    direction = "DESC" if filters.order is SortOrder.desc else "ASC"
    return f"ORDER BY {column} {direction}, id {direction}"


def count_jobs(conn: sqlite3.Connection, filters: JobFilters) -> int:
    """How many rows match — the filters, not the page.

    Uses the same `_build_where` as `list_jobs`, which is the point of factoring
    it out: a `total` computed from different criteria than the `items` would be
    a lie that no test of either query alone would catch.
    """
    where, params = _build_where(filters)
    sql = f"SELECT COUNT(*) FROM jobs {where}"
    return int(conn.execute(sql, params).fetchone()[0])


def list_jobs(conn: sqlite3.Connection, filters: JobFilters) -> list[sqlite3.Row]:
    """One page of matching jobs."""
    where, params = _build_where(filters)
    sql = f"""
        SELECT {_SUMMARY_COLUMNS}
        FROM jobs
        {where}
        {_build_order(filters)}
        LIMIT ? OFFSET ?
    """
    return conn.execute(sql, [*params, filters.limit, filters.offset]).fetchall()


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    """One job by id, or `JobNotFound`.

    Raises a domain error rather than returning None, so the caller cannot
    forget to check. Translating that into a 404 is the application's job — this
    module has no opinion about HTTP.
    """
    row = conn.execute(
        f"SELECT {_DETAIL_COLUMNS} FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise JobNotFound(job_id)
    return row


# --------------------------------------------------------------------------
# Change history
# --------------------------------------------------------------------------


def job_exists(conn: sqlite3.Connection, job_id: int) -> bool:
    """Cheaper than fetching the row when only existence matters.

    `/jobs/{id}/changes` must 404 for an unknown job rather than returning an
    empty list — an empty list means "this job has never changed", which is a
    different fact from "this job does not exist".
    """
    return (
        conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        is not None
    )


def count_job_changes(conn: sqlite3.Connection, job_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM job_changes WHERE job_id = ?", (job_id,)
    ).fetchone()
    return int(row[0])


def list_job_changes(
    conn: sqlite3.Connection, job_id: int, limit: int, offset: int
) -> list[sqlite3.Row]:
    """Edit history, newest first, with values truncated in SQL.

    `substr()` and `length()` run in the database so a 30 KB description diff is
    never read into Python only to be thrown away. Truncating in the response
    model instead would still have paid to move 32.8 MB across the boundary for
    a table-wide query.

    The `id` tie-break is here for the same reason as everywhere else:
    `observed_at` repeats across every change recorded by a single run.
    """
    return conn.execute(
        """
        SELECT
            observed_at,
            field,
            substr(old_value, 1, ?) AS old_value,
            substr(new_value, 1, ?) AS new_value,
            length(old_value)       AS old_length,
            length(new_value)       AS new_length
        FROM job_changes
        WHERE job_id = ?
        ORDER BY observed_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (
            CHANGE_VALUE_MAX_LENGTH,
            CHANGE_VALUE_MAX_LENGTH,
            job_id,
            limit,
            offset,
        ),
    ).fetchall()


# --------------------------------------------------------------------------
# Runs and sources
# --------------------------------------------------------------------------


def count_runs(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])


def list_runs(conn: sqlite3.Connection, limit: int, offset: int) -> list[sqlite3.Row]:
    """Run history, newest first.

    No `duration_seconds` column is computed. Build 2 writes `finished_at` from
    the same value as `started_at`, so every completed run would report 0.0 —
    a confidently wrong number is worse than an absent one.
    """
    return conn.execute(
        """
        SELECT id, source, status, started_at, finished_at,
               rows_parsed, pages_fetched, page_cap
        FROM runs
        ORDER BY started_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every source that has jobs, with the outcome of its most recent run.

    A LEFT JOIN because a source may have jobs but no run row, or a run row and
    no jobs — neither should make the source vanish from this list. The
    correlated subquery picks the latest run per source by id, which is
    monotonic here where `started_at` ties within a batch.
    """
    return conn.execute(
        """
        SELECT
            j.source                AS source,
            COUNT(*)                AS job_count,
            r.id                    AS last_run_id,
            r.status                AS last_run_status,
            r.started_at            AS last_run_started_at,
            r.finished_at           AS last_run_finished_at,
            r.rows_parsed           AS last_run_rows_parsed
        FROM jobs j
        LEFT JOIN runs r
               ON r.id = (SELECT MAX(id) FROM runs WHERE source = j.source)
        GROUP BY j.source, r.id, r.status, r.started_at, r.finished_at, r.rows_parsed
        ORDER BY j.source
        """
    ).fetchall()


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------

# Nullable columns worth reporting coverage for. Named explicitly rather than
# discovered from PRAGMA table_info, so adding a column to Build 2's schema does
# not silently change this service's public response shape.
_COVERAGE_FIELDS = (
    "location",
    "remote",
    "salary_min",
    "salary_max",
    "currency",
    "salary_raw",
    "posted_at",
    "description",
    "seniority",
)


def stats(conn: sqlite3.Connection) -> dict[str, object]:
    """Dataset shape in one pass per concern.

    The coverage counts are built as a single SELECT with one SUM per field
    rather than one query per field: nine round trips over 3,105 rows would be
    nine full scans to answer one question.
    """
    sums = ", ".join(
        f"SUM(CASE WHEN {field} IS NULL THEN 0 ELSE 1 END) AS {field}"
        for field in _COVERAGE_FIELDS
    )
    row = conn.execute(f"SELECT COUNT(*) AS total, {sums} FROM jobs").fetchone()
    total = int(row["total"])

    coverage = [
        {
            "field": field,
            "present": int(row[field] or 0),
            "missing": total - int(row[field] or 0),
            "coverage": (int(row[field] or 0) / total) if total else 0.0,
        }
        for field in _COVERAGE_FIELDS
    ]

    remote = conn.execute(
        """
        SELECT
            SUM(CASE WHEN remote = 1 THEN 1 ELSE 0 END)    AS yes,
            SUM(CASE WHEN remote = 0 THEN 1 ELSE 0 END)    AS no,
            SUM(CASE WHEN remote IS NULL THEN 1 ELSE 0 END) AS unknown
        FROM jobs
        """
    ).fetchone()

    dates = conn.execute(
        "SELECT MIN(posted_at) AS earliest, MAX(posted_at) AS latest FROM jobs"
    ).fetchone()

    return {
        "total_jobs": total,
        "total_runs": count_runs(conn),
        "total_changes": int(
            conn.execute("SELECT COUNT(*) FROM job_changes").fetchone()[0]
        ),
        "sources": int(
            conn.execute("SELECT COUNT(DISTINCT source) FROM jobs").fetchone()[0]
        ),
        "coverage": coverage,
        "remote_true": int(remote["yes"] or 0),
        "remote_false": int(remote["no"] or 0),
        "remote_unknown": int(remote["unknown"] or 0),
        "earliest_posted_at": dates["earliest"],
        "latest_posted_at": dates["latest"],
    }
