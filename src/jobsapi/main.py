"""Application factory, router wiring and middleware. No business logic."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from jobsapi.appdb import ensure_schema
from jobsapi.config import Settings, get_settings
from jobsapi.db import check_database
from jobsapi.logging_config import configure_logging, request_id_var
from jobsapi.problems import PROBLEM_MEDIA_TYPE, register_handlers
from jobsapi.routers import jobs, meta, runs, watchlists
from jobsapi.schemas import Problem

# The version is read from installed package metadata rather than written here.
# It was hard-coded, which meant `pyproject.toml` and this line were two copies
# of one fact: the app reported 0.7.0 for the whole of the v0.8.0 tag, in its
# startup log and in `/openapi.json`. One source cannot disagree with itself.
try:
    API_VERSION = _package_version("jobsapi")
except PackageNotFoundError:  # pragma: no cover - only when not installed
    API_VERSION = "0.0.0+unknown"


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
    401: {
        "model": Problem,
        "description": "A valid X-API-Key header is required.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
    404: {
        "model": Problem,
        "description": "Resource not found.",
        "content": {PROBLEM_MEDIA_TYPE: {}},
    },
    409: {
        "model": Problem,
        "description": "The request conflicts with the current state.",
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


_access_log = logging.getLogger("jobsapi.access")
_log = logging.getLogger("jobsapi")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Verify the database before the first request, not during it.

    "DB file missing at startup -> loud, readable failure" is a hardening-table
    row, and this is where it is enforced. Checking lazily would turn a
    misconfigured path into a 500 on whichever request happened to arrive first.
    """
    settings: Settings = app.state.settings
    check_database(settings)

    # The read database must already exist and is only verified; the write
    # database is created if absent, because this service owns it. Doing it here
    # rather than lazily means the first write never races the first request.
    ensure_schema(settings)
    _log.info(
        "startup",
        extra={
            "db_path": str(settings.db_path),
            "app_db_path": str(settings.app_db_path),
            "api_key_required": settings.api_key is not None,
            "version": app.version,
        },
    )
    yield
    _log.info("shutdown")


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
        version=API_VERSION,
        summary="Read-only REST API over the job-listing-scraper dataset.",
        description=(
            "Errors use RFC 9457 problem details "
            "(`application/problem+json`) with a machine-readable `code`."
        ),
        lifespan=lifespan,
        responses=PROBLEM_RESPONSES,
    )
    app.state.settings = settings or get_settings()
    configure_logging(app.state.settings.log_level)

    @app.middleware("http")
    async def _observe(request: Request, call_next) -> Response:
        """Tag, time, and log every request.

        The id is set in *two* places on purpose: `request.state` for the
        exception handlers, which have the request in hand, and a ContextVar for
        the log formatter, which does not. The ContextVar is what lets a log
        line written deep inside the repository carry the id without every
        function signature growing a parameter.

        Timing uses `perf_counter`, not `time()` — a monotonic clock cannot go
        backwards when the system clock is adjusted, which is the difference
        between a plausible duration and a negative one.
        """
        rid = uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        started = perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        _access_log.info(
            "request",
            extra={
                "http": {
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "status": response.status_code,
                    "duration_ms": round(elapsed_ms, 1),
                },
                "request_id": rid,
            },
        )
        return response

    register_handlers(app)
    app.include_router(meta.router)
    app.include_router(jobs.router)
    app.include_router(runs.router)
    app.include_router(watchlists.router)
    return app


# The ASGI callable uvicorn imports: `uvicorn jobsapi.main:app`.
app = create_app()
