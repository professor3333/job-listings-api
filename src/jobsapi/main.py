"""Application factory, router wiring and exception handlers. No business logic."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jobsapi.config import Settings, get_settings
from jobsapi.db import check_database, classify
from jobsapi.errors import (
    DatabaseUnavailable,
    DatabaseWedged,
    JobNotFound,
)
from jobsapi.routers import jobs, meta


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Verify the database before the first request, not during it.

    "DB file missing at startup -> loud, readable failure" is a hardening-table
    row, and this is where it is enforced. Checking here means a misconfigured
    path kills the process with a readable message; checking lazily would turn
    it into a 500 on whichever request happened to arrive first.
    """
    check_database(app.state.settings)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fresh application, optionally against explicit settings.

    Settings are injected here rather than swapped later with
    `dependency_overrides`, because the startup check above runs *inside the
    lifespan* — before any dependency is resolved. A dependency override cannot
    reach it, so tests that pointed only `get_conn` at a fixture database would
    still have started up against the real one. Injecting settings moves the
    single seam to a place that governs both.
    """
    app = FastAPI(
        title="Job Listings API",
        version="0.2.0",
        summary="Read-only REST API over the job-listing-scraper dataset.",
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()

    app.include_router(meta.router)
    app.include_router(jobs.router)

    @app.exception_handler(JobNotFound)
    async def _job_not_found(request: Request, exc: JobNotFound) -> JSONResponse:
        """Domain error -> HTTP, at the application edge.

        The repository raised `JobNotFound`; nothing below this line knew what a
        404 was. Phase 3 replaces this body with the RFC 9457 problem-details
        envelope chosen in docs/design.md — the shape is a placeholder, the
        boundary is not.
        """
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DatabaseUnavailable)
    async def _db_busy(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
        """Transient: the writer holds the lock. Retrying is the right advice."""
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is busy, try again shortly."},
            headers={"Retry-After": "1"},
        )

    @app.exception_handler(DatabaseWedged)
    async def _db_wedged(request: Request, exc: DatabaseWedged) -> JSONResponse:
        """Not transient: a hot journal needs a human. No Retry-After on purpose.

        Advising a retry here would send clients into a loop against a condition
        that cannot resolve itself — a read-only connection can never roll back
        the journal that is blocking it.
        """
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is unavailable and requires attention."},
        )

    @app.exception_handler(sqlite3.Error)
    async def _sqlite_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
        """Catch SQLite faults raised mid-query rather than at connect time.

        Re-classified by error code. Anything unrecognised stays a 500 with a
        body that says nothing about internals — the traceback belongs in the
        log, never in the response.
        """
        domain = classify(exc)
        if isinstance(domain, DatabaseUnavailable):
            return await _db_busy(request, domain)
        if isinstance(domain, DatabaseWedged):
            return await _db_wedged(request, domain)
        raise exc

    return app


# The ASGI callable uvicorn imports: `uvicorn jobsapi.main:app`.
app = create_app()
