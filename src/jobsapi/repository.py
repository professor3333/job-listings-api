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
from jobsapi.schemas import JobFilters, Remote, SortField, SortOrder

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
