"""Application factory, router wiring and middleware. No business logic."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from jobsapi.config import Settings, get_settings
from jobsapi.db import check_database
from jobsapi.problems import PROBLEM_MEDIA_TYPE, register_handlers
from jobsapi.routers import jobs, meta
from jobsapi.schemas import Problem

# Declared once, app-wide, so /openapi.json advertises the problem shape instead
# of FastAPI's HTTPValidationError. Without this the generated docs would
# describe a body this service never sends — and "the docs are generated from
# the types" would quietly stop being true for errors.
PROBLEM_RESPONSES: dict[int | str, dict] = {
    422: {
        "model": Problem,
        "description": "Validation failed.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
    404: {
        "model": Problem,
        "description": "Resource not found.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
    503: {
        "model": Problem,
        "description": "Database unavailable.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
    500: {
        "model": Problem,
        "description": "Internal server error.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Verify the database before the first request, not during it.

    "DB file missing at startup -> loud, readable failure" is a hardening-table
    row, and this is where it is enforced. Checking lazily would turn a
    misconfigured path into a 500 on whichever request happened to arrive first.
    """
    check_database(app.state.settings)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fresh application, optionally against explicit settings.

    Settings are injected here rather than swapped later with
    `dependency_overrides`, because the startup check above runs *inside the
    lifespan* — before any dependency is resolved. A dependency override cannot
    reach it, so tests that pointed only `get_conn` at a fixture database would
    still have started up against the real one.
    """
    app = FastAPI(
        title="Job Listings API",
        version="0.3.0",
        summary="Read-only REST API over the job-listing-scraper dataset.",
        description=(
            "Errors use RFC 9457 problem details "
            "(`application/problem+json`) with a machine-readable `code`."
        ),
        lifespan=lifespan,
        responses=PROBLEM_RESPONSES,
    )
    app.state.settings = settings or get_settings()

    @app.middleware("http")
    async def _assign_request_id(request: Request, call_next) -> Response:
        """Tag every request, and echo the tag back.

        Set before routing so it is available to exception handlers — including
        the catch-all, where it is the only thing connecting the opaque body a
        client sees to the traceback in the log.
        """
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_handlers(app)
    app.include_router(meta.router)
    app.include_router(jobs.router)
    return app


# The ASGI callable uvicorn imports: `uvicorn jobsapi.main:app`.
app = create_app()
