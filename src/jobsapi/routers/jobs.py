"""Job endpoints. No SQL here — if a SELECT appears in this file, the boundary broke."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from jobsapi import repository
from jobsapi.db import get_conn
from jobsapi.schemas import JobDetail, JobPage, Pagination

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=JobPage,
    summary="List jobs",
    description="Paginated list, newest first. An offset past the end returns an "
    "empty `items` array with the correct `total` — not a 404.",
)
def list_jobs(
    pagination: Annotated[Pagination, Query()],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> JobPage:
    """Plain `def`, not `async def` — and that is the whole lesson of this phase.

    `sqlite3` is a blocking library. FastAPI runs a plain `def` endpoint in a
    threadpool, so the blocking read occupies a worker thread and the event loop
    stays free to accept other requests. Declaring this `async def` would run it
    directly on the event loop, where every SQLite call would stall *every*
    concurrent request in the process — an app that tests perfectly and collapses
    under two users.

    /health is `async def` precisely because it does no I/O at all. The rule is
    about what the body does, not about a house style.
    """
    rows = repository.list_jobs(conn, limit=pagination.limit, offset=pagination.offset)
    return JobPage(
        items=[dict(row) for row in rows],
        total=repository.count_jobs(conn),
        limit=pagination.limit,
        offset=pagination.offset,
    )


# Declared after the list route, and before any literal sibling that may be added
# later. FastAPI matches in declaration order, so a future `/jobs/recent` must go
# ABOVE this one — otherwise this route swallows it and tries to parse "recent"
# as an int, returning 422 for a path that plainly exists.
@router.get(
    "/{job_id}",
    response_model=JobDetail,
    summary="Get one job",
    responses={404: {"description": "No job with that id."}},
)
def get_job(
    job_id: Annotated[int, Path(ge=1, description="Primary key from the jobs table.")],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> JobDetail:
    """Typing `job_id` as `int` is what makes `/jobs/abc` a 422 rather than a 500.

    The path parameter is validated before this function is entered, so the
    repository is never called with something that cannot be an id. `JobNotFound`
    is raised by the repository and translated to a 404 by the application's
    exception handler — this function does not mention HTTP status codes.
    """
    return JobDetail.model_validate(dict(repository.get_job(conn, job_id)))
