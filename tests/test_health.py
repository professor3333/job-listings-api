"""Phase 1: prove the whole loop works — app factory, router, response model."""

from fastapi.testclient import TestClient

from jobsapi.main import create_app


def test_health_returns_ok() -> None:
    """The happy path, asserted on the exact body rather than just the status.

    `TestClient` speaks to the ASGI app in-process — no socket, no port, no
    running server, so this passes with the wifi off. It is used as a context
    manager because that is what triggers the app's startup and shutdown
    lifespan events; from Phase 2 those will matter (the schema contract check
    runs at startup), and a test that skips them would not exercise the same
    code path the real server does.
    """
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_health_is_declared_in_the_openapi_schema() -> None:
    """The generated docs are only as correct as the type hints that produce them.

    /docs is rendered from /openapi.json, which FastAPI derives from the route
    signature and the `response_model`. Asserting on the schema here means a
    later change that widens the contract — dropping the response model, or
    loosening `Literal["ok"]` to `str` — fails a test instead of silently
    publishing a wrong promise to every reader of /docs.
    """
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()

    health = schema["paths"]["/health"]["get"]
    ref = health["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    model = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]

    assert model["properties"]["status"]["const"] == "ok"
    assert model["required"] == ["status"]
