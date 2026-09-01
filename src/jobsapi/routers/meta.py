"""Meta endpoints: liveness now, /sources and /stats in later phases."""

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from jobsapi import repository
from jobsapi.db import get_conn
from jobsapi.schemas import SourceSummary, Stats


class Health(BaseModel):
    """The /health response contract.

    `Literal["ok"]` rather than `str` on purpose: it makes the OpenAPI schema say
    the body is always exactly {"status": "ok"}, so /docs documents the real
    contract instead of "some string". A wider type here would be a wider promise.
    """

    status: Literal["ok"]


router = APIRouter(tags=["meta"])


@router.get(
    "/health",
    response_model=Health,
    summary="Liveness check",
    description="Returns a fixed body. Touches no database and no filesystem.",
)
async def health() -> Health:
    """Liveness only — deliberately not readiness.

    `async def` is correct *here* because this function performs no I/O at all,
    so it can run directly on the event loop with no threadpool hop. Every
    endpoint that touches sqlite3 must be plain `def` instead: sqlite3 blocks,
    and a blocking call inside `async def` stalls the whole event loop. The rule
    is about what the body does, not about a house style.

    This says "the process is up and serving", not "the database is reachable" —
    a health check that fails because Build 2's scraper wedged its database would
    be reporting on Build 2's liveness, not this service's. The database signal
    belongs on /sources, where a caller asking about sources expects to hear
    about the data.
    """
    return Health(status="ok")


@router.get(
    "/sources",
    response_model=list[SourceSummary],
    summary="Sources with row counts and last run status",
    description=(
        "One entry per source that has jobs, with how its most recent run "
        "ended. A status of `running` may mean a run is in progress *or* that "
        "one died without writing `finished_at` — this service cannot tell the "
        "difference by querying."
    ),
)
def list_sources(
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> list[SourceSummary]:
    """A bare array here, unlike `/jobs`.

    Deliberate inconsistency, and the reason is bounded cardinality: there are
    eight sources and there will not be thousands, so there is nothing to
    paginate and no `total` worth carrying. An envelope exists to make paging
    expressible; where paging is meaningless the envelope is ceremony.
    """
    return [
        SourceSummary.model_validate(dict(row)) for row in repository.list_sources(conn)
    ]


@router.get(
    "/stats",
    response_model=Stats,
    summary="Dataset shape: counts, coverage, and the tri-state split",
    description=(
        "Per-field coverage is what makes the API's NULL semantics legible: "
        "a filter on a field is only as useful as the fraction of rows that "
        "actually carry it."
    ),
)
def get_stats(conn: Annotated[sqlite3.Connection, Depends(get_conn)]) -> Stats:
    """Aggregates, shaped into a response rather than dumped as rows.

    The coverage numbers are the honest counterpart to the documented decision
    that NULLs never satisfy a filter: a client that sees `salary_min` is
    populated in 31% of rows understands why a salary filter returns so little,
    without having to guess whether the filter is broken.
    """
    return Stats.model_validate(repository.stats(conn))
