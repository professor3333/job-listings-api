"""Meta endpoints: liveness now, /sources and /stats in later phases."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


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
