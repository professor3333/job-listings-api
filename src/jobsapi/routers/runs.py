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
        "Run history, newest first. No duration is reported: the source data "
        "stamps `finished_at` from the same value as `started_at`, so every "
        "completed run would show zero elapsed. Both timestamps are returned "
        "raw so a client can see that for itself."
    ),
)
def list_runs(
    pagination: Annotated[Pagination, Query()],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> RunPage:
    """Plain `def` — blocking sqlite3, same rule as every other query endpoint."""
    return RunPage(
        items=[
            dict(row)
            for row in repository.list_runs(
                conn, limit=pagination.limit, offset=pagination.offset
            )
        ],
        total=repository.count_runs(conn),
        limit=pagination.limit,
        offset=pagination.offset,
    )
