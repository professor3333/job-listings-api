"""RFC 9457 problem details — one error shape for every failure.

Decision 2 in docs/design.md. FastAPI's defaults return *two* incompatible
shapes: `detail` is a list of objects for a validation error and a bare string
for an `HTTPException`. A client cannot write one error handler against that.
Everything here exists to make `detail` mean one thing.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from jobsapi.db import classify
from jobsapi.errors import DatabaseUnavailable, DatabaseWedged, JobNotFound
from jobsapi.schemas import Problem, ProblemDetail

# The media type is part of the standard, not decoration: it tells a client the
# body follows RFC 9457 without having to guess from its keys.
PROBLEM_MEDIA_TYPE = "application/problem+json"

# Machine-readable codes. Clients branch on these, never on `title` or `detail`,
# which are prose and may be reworded.
CODE_VALIDATION_FAILED = "VALIDATION_FAILED"
CODE_CROSS_FIELD_CONFLICT = "CROSS_FIELD_CONFLICT"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_DATABASE_BUSY = "DATABASE_BUSY"
CODE_DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"


def request_id(request: Request) -> str:
    """The id assigned by middleware, or a placeholder if it never ran.

    Carried in every problem body from the start, even though structured logging
    is Phase 5. It is the seam that ties a response a user is looking at to a
    line in the log — and retrofitting it later would mean changing the envelope
    after clients had already seen it.
    """
    return getattr(request.state, "request_id", "-")


def problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    code: str,
    errors: list[ProblemDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build one problem document. Every handler below funnels through here.

    Centralising construction is what makes the envelope a guarantee rather than
    a convention — there is no second place where a response body is shaped, so
    no handler can drift.
    """
    body = Problem(
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        code=code,
        errors=errors,
        request_id=request_id(request),
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _field_name(loc: tuple[Any, ...]) -> str:
    """Turn Pydantic's `loc` tuple into a name a client can act on.

    `("query", "limit")` becomes `limit`. The leading segment names *where* the
    value came from, which the client already knows.
    """
    parts = [str(p) for p in loc if p not in ("query", "path", "body")]
    return ".".join(parts) if parts else "request"


def register_handlers(app: FastAPI) -> None:
    """Attach every exception handler to `app`."""

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        """422 for anything Pydantic rejected — single-field or cross-field.

        The status is the same for both because both mean "this query is not
        answerable"; the distinction a client can act on lives in `code`.
        Choosing 400 for cross-field instead would have forced either raising
        HTTPException inside the route — dragging validation out of schemas.py
        and breaking the boundary — or re-classifying Pydantic errors by
        inspecting `loc`. Neither is worth the second status code.

        Pydantic's `loc` and `msg` are forwarded rather than discarded: they are
        the best part of FastAPI's default, and an envelope that threw them away
        would be a downgrade wearing a standard's clothes.
        """
        raw = exc.errors()
        cross_field = any(e.get("type") == "cross_field_conflict" for e in raw)
        details = [
            ProblemDetail(
                field=_field_name(e.get("loc", ())),
                rule=str(e.get("type", "invalid")),
                message=str(e.get("msg", "")),
            )
            for e in raw
        ]
        count = len(details)
        return problem_response(
            request,
            status=422,
            title="Validation failed",
            detail=(
                details[0].message
                if count == 1
                else f"{count} parameters failed validation."
            ),
            code=(CODE_CROSS_FIELD_CONFLICT if cross_field else CODE_VALIDATION_FAILED),
            errors=details,
        )

    @app.exception_handler(JobNotFound)
    async def _not_found(request: Request, exc: JobNotFound):
        """The repository raised a domain error; HTTP happens only here."""
        return problem_response(
            request,
            status=404,
            title="Job not found",
            detail=str(exc),
            code=CODE_NOT_FOUND,
        )

    @app.exception_handler(DatabaseUnavailable)
    async def _busy(request: Request, exc: DatabaseUnavailable):
        """Transient: the scraper holds the write lock. Retrying is right."""
        return problem_response(
            request,
            status=503,
            title="Database busy",
            detail="The database is locked by a writer. Retry shortly.",
            code=CODE_DATABASE_BUSY,
            headers={"Retry-After": "1"},
        )

    @app.exception_handler(DatabaseWedged)
    async def _wedged(request: Request, exc: DatabaseWedged):
        """Not transient — and deliberately no `Retry-After`.

        A hot journal can only be cleared by a writer. This service holds a
        read-only connection and can never roll it back, so advising a retry
        would send clients into a loop against a condition that cannot resolve.
        """
        return problem_response(
            request,
            status=503,
            title="Database unavailable",
            detail="The database requires operator attention and cannot be read.",
            code=CODE_DATABASE_UNAVAILABLE,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        """Covers routing 404s and anything raising HTTPException directly.

        Without this, `GET /nope` would still return `{"detail": "Not Found"}` —
        the second shape that made the default unusable.
        """
        return problem_response(
            request,
            status=exc.status_code,
            title=str(exc.detail),
            detail=str(exc.detail),
            code=CODE_NOT_FOUND if exc.status_code == 404 else CODE_INTERNAL_ERROR,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(sqlite3.Error)
    async def _sqlite(request: Request, exc: sqlite3.Error):
        """SQLite faults raised mid-query rather than at connect time."""
        domain = classify(exc)
        if isinstance(domain, DatabaseUnavailable):
            return await _busy(request, domain)
        if isinstance(domain, DatabaseWedged):
            return await _wedged(request, domain)
        return await _unhandled(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        """Last resort. The body says nothing; the log says everything.

        The response is built from a fixed template, so a traceback *cannot*
        reach a client even by accident — that guarantee is structural rather
        than a reminder to be careful. `request_id` is what lets an operator
        find the traceback that belongs to the failure a user is reporting.
        """
        return problem_response(
            request,
            status=500,
            title="Internal server error",
            detail="An unexpected error occurred.",
            code=CODE_INTERNAL_ERROR,
        )
