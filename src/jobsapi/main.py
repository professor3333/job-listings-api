"""Application factory and router wiring. No business logic lives here."""

from fastapi import FastAPI

from jobsapi.routers import meta


def create_app() -> FastAPI:
    """Build a fresh FastAPI application.

    A *factory* rather than a module-level `app = FastAPI()` singleton, because
    every test wants its own instance. Once Phase 2 adds
    `app.dependency_overrides[...]` to point the app at a fixture database, a
    shared global app would leak that override from one test into the next.
    Building a new app per test makes that impossible by construction rather
    than by teardown discipline.

    `@router.get(...)` did not register anything with *this* app — it registered
    the route on the `APIRouter` object at import time. `include_router` is what
    copies those routes onto the application, which is why a router can be
    imported, tested, and mounted under different prefixes independently.
    """
    app = FastAPI(
        title="Job Listings API",
        version="0.1.0",
        summary="Read-only REST API over the job-listing-scraper dataset.",
    )
    app.include_router(meta.router)
    return app


# The ASGI callable uvicorn imports: `uvicorn jobsapi.main:app`.
# uvicorn does not "run this script" — it imports this module, takes the object
# named `app`, and calls it per request with (scope, receive, send). That is the
# ASGI interface; the app itself never touches a socket.
app = create_app()
