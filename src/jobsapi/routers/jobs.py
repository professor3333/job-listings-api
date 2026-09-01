"""Job endpoints. No SQL here — if a SELECT appears in this file, the boundary broke."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from jobsapi import repository
from jobsapi.db import get_conn
from jobsapi.errors import JobNotFound
from jobsapi.schemas import (
    CHANGE_VALUE_MAX_LENGTH,
    JobChangePage,
    JobDetail,
    JobFilters,
    JobPage,
    Pagination,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=JobPage,
    summary="List jobs",
    description=(
        "Filtered, sorted, paginated list. Unknown query parameters are "
        "rejected with 422. An offset past the end returns an empty `items` "
        "array with the correct `total` — not a 404."
    ),
)
def list_jobs(
    filters: Annotated[JobFilters, Query()],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> JobPage:
    """Plain `def`, not `async def` — the central lesson of this build.

    `sqlite3` is a blocking library. FastAPI runs a plain `def` endpoint in a
    threadpool, so the blocking read occupies a worker thread and the event loop
    stays free to accept other requests. Declaring this `async def` would run it
    directly on the event loop, where every SQLite call would stall *every*
    concurrent request in the process — an app that tests perfectly and collapses
    under two users.

    Note how little this function does: validation already happened in
    `JobFilters`, and the SQL lives in the repository. A route that grows logic
    is a route that has started doing someone else's job.
    """
    return JobPage(
        items=[dict(row) for row in repository.list_jobs(conn, filters)],
        total=repository.count_jobs(conn, filters),
        limit=filters.limit,
        offset=filters.offset,
    )


# Declared after the list route, and before any literal sibling added later.
# FastAPI matches in declaration order, so a future `/jobs/recent` must go ABOVE
# this one — otherwise this route swallows it and tries to parse "recent" as an
# int, returning 422 for a path that plainly exists.
@router.get(
    "/{job_id}",
    response_model=JobDetail,
    summary="Get one job",
)
def get_job(
    job_id: Annotated[int, Path(ge=1, description="Primary key from the jobs table.")],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> JobDetail:
    """Typing `job_id` as `int` is what makes `/jobs/abc` a 422 rather than a 500.

    The path parameter is validated before this function is entered, so the
    repository is never called with something that cannot be an id. `JobNotFound`
    is raised by the repository and translated to a 404 by the problem handler —
    this function never mentions a status code.
    """
    return JobDetail.model_validate(dict(repository.get_job(conn, job_id)))


# Declared after `/jobs/{job_id}`, which is safe because the paths differ in
# segment count — `/jobs/1` cannot match `/jobs/{job_id}/changes`. The ordering
# rule that matters is between a parameterised segment and a *literal sibling at
# the same depth*, which is not the case here.
@router.get(
    "/{job_id}/changes",
    response_model=JobChangePage,
    summary="Edit history for one job",
    description=(
        "Field-level changes recorded by the scraper, newest first. Values are "
        "truncated to 200 characters; `old_length` and `new_length` report the "
        "true sizes and `truncated` says whether anything was cut."
    ),
)
def list_job_changes(
    job_id: Annotated[int, Path(ge=1)],
    pagination: Annotated[Pagination, Query()],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> JobChangePage:
    """404 for an unknown job, rather than an empty list.

    An empty list means "this job exists and has never changed" — a different
    fact from "this job does not exist". Collapsing the two would make the
    endpoint unable to answer either question.
    """
    if not repository.job_exists(conn, job_id):
        raise JobNotFound(job_id)

    rows = repository.list_job_changes(
        conn, job_id, limit=pagination.limit, offset=pagination.offset
    )
    items = []
    for row in rows:
        data = dict(row)
        old_len, new_len = data.get("old_length"), data.get("new_length")
        data["truncated"] = any(
            length is not None and length > CHANGE_VALUE_MAX_LENGTH
            for length in (old_len, new_len)
        )
        items.append(data)

    return JobChangePage(
        items=items,
        total=repository.count_job_changes(conn, job_id),
        limit=pagination.limit,
        offset=pagination.offset,
    )
