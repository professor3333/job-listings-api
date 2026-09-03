"""Scrape run history."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from jobsapi import repository
from jobsapi.db import get_conn
from jobsapi.schemas import Pagination, RunPage

router = APIRouter(prefix="/runs", tags=["meta"])


@router.get(
    "",
    response_model=RunPage,
    summary="List scrape runs",
    description=(
        "Run history, newest first. `duration_seconds` is null when the run "
        "has not finished, or when its timestamps are identical — the "
        "signature of an upstream bug, fixed on 2026-09-02, that stamped both "
        "ends of a run from one clock reading. Null means unknown, never zero. "
        "Both timestamps are returned raw so a client can check the arithmetic."
    ),
)
def list_runs(
    pagination: Annotated[Pagination, Query()],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> RunPage:
    """Plain `def` — blocking sqlite3, same rule as every other query endpoint."""
    rows, total = repository.runs_page(
        conn, limit=pagination.limit, offset=pagination.offset
    )
    return RunPage(
        items=[dict(row) for row in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
