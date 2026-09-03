"""Phase 3: the error envelope — one shape for every failure."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from jobsapi.config import Settings
from jobsapi.main import create_app
from jobsapi.problems import PROBLEM_MEDIA_TYPE

REQUIRED_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id"}


def assert_is_a_problem(response, *, status: int, code: str) -> dict:
    """Every 4xx and 5xx must satisfy this, without exception."""
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert set(body) >= REQUIRED_KEYS
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == "about:blank"
    assert body["request_id"]
    return body


class TestOneShapeEverywhere:
    """The failure the default could not avoid: `detail` meaning two things."""

    def test_validation_error(self, client: TestClient) -> None:
        body = assert_is_a_problem(
            client.get("/jobs", params={"limit": 0}),
            status=422,
            code="VALIDATION_FAILED",
        )
        assert body["errors"][0]["field"] == "limit"

    def test_not_found(self, client: TestClient) -> None:
        assert_is_a_problem(client.get("/jobs/999999999"), status=404, code="NOT_FOUND")

    def test_unrouted_path(self, client: TestClient) -> None:
        """Starlette's own 404.

        This is the one that used to escape the envelope entirely as
        `{"detail": "Not Found"}` — the second shape that made the default
        impossible to write one client handler against.
        """
        assert_is_a_problem(client.get("/nope"), status=404, code="NOT_FOUND")

    def test_detail_is_always_a_string(self, client: TestClient) -> None:
        """The actual bug being fixed.

        FastAPI's default made `detail` a list of objects for a 422 and a bare
        string for a 404, so no client could write one error handler.
        """
        for path, params in [
            ("/jobs", {"limit": 0}),
            ("/jobs/999999999", {}),
            ("/nope", {}),
        ]:
            assert isinstance(client.get(path, params=params).json()["detail"], str)


class TestCrossFieldConflicts:
    """Well-formed, individually legal, nonsense as a pair."""

    def test_salary_range_inverted(self, client: TestClient) -> None:
        body = assert_is_a_problem(
            client.get(
                "/jobs", params={"salary_min_gte": 50_000, "salary_max_lte": 10_000}
            ),
            status=422,
            code="CROSS_FIELD_CONFLICT",
        )
        assert "50000" in body["errors"][0]["message"]

    def test_date_range_inverted(self, client: TestClient) -> None:
        assert_is_a_problem(
            client.get(
                "/jobs",
                params={"posted_after": "2027-01-01", "posted_before": "2020-01-01"},
            ),
            status=422,
            code="CROSS_FIELD_CONFLICT",
        )

    def test_equal_bounds_are_allowed(self, client: TestClient) -> None:
        """The boundary is inclusive: min == max is a legal, empty-ish query."""
        response = client.get(
            "/jobs", params={"salary_min_gte": 10_000, "salary_max_lte": 10_000}
        )
        assert response.status_code == 200

    def test_a_single_field_error_is_not_a_cross_field_conflict(
        self, client: TestClient
    ) -> None:
        """The codes must actually discriminate, or carrying both is pointless."""
        body = client.get("/jobs", params={"salary_min_gte": -1}).json()
        assert body["code"] == "VALIDATION_FAILED"


class TestFieldNaming:
    """`errors[].field` names the parameter with its location stripped.

    Pydantic reports `("query", "limit")` and `("path", "job_id")`. Both are
    flattened to the bare name, so a client acts on `job_id` rather than
    `path.job_id` — the name it can do something about, without framework
    vocabulary in it. Documented in `docs/api.md`; untested until now, and the
    distinction is invisible for query parameters, which is why it took a path
    parameter to surface it.
    """

    def test_a_path_parameter_is_named_without_its_location(
        self, client: TestClient
    ) -> None:
        body = client.get("/jobs/abc").json()
        assert body["code"] == "VALIDATION_FAILED"
        assert [e["field"] for e in body["errors"]] == ["job_id"]

    def test_a_query_parameter_is_named_the_same_way(self, client: TestClient) -> None:
        body = client.get("/jobs", params={"limit": 0}).json()
        assert [e["field"] for e in body["errors"]] == ["limit"]

    def test_a_sub_resource_path_parameter_too(self, client: TestClient) -> None:
        """`/jobs/abc/changes` fails on the same parameter, three segments in."""
        body = client.get("/jobs/abc/changes").json()
        assert [e["field"] for e in body["errors"]] == ["job_id"]


class TestUnknownParameters:
    """Documented decision: reject, do not ignore."""

    def test_unknown_query_parameter_is_422(self, client: TestClient) -> None:
        body = assert_is_a_problem(
            client.get("/jobs", params={"colour": "red"}),
            status=422,
            code="VALIDATION_FAILED",
        )
        assert any("colour" in e["field"] for e in body["errors"])

    def test_a_typo_does_not_silently_return_everything(
        self, client: TestClient
    ) -> None:
        """The reasoning behind the decision, as a test.

        `?limt=5` ignored would return 20 rows and the client would believe it
        asked for 5. Rejecting makes the mistake visible.
        """
        assert client.get("/jobs", params={"limt": 5}).status_code == 422


class TestInternalErrors:
    def test_traceback_never_reaches_the_body(self, client: TestClient) -> None:
        """A 500 says nothing about internals. The log gets the traceback."""
        app = client.app

        @app.get("/boom")
        def _boom() -> None:
            raise RuntimeError("secret internal detail: /etc/passwd")

        with TestClient(app, raise_server_exceptions=False) as fresh:
            response = fresh.get("/boom")

        body = assert_is_a_problem(response, status=500, code="INTERNAL_ERROR")
        serialised = str(body)
        assert "secret internal detail" not in serialised
        assert "RuntimeError" not in serialised
        assert "Traceback" not in serialised


class TestRequestId:
    def test_echoed_in_a_header_and_the_body(self, client: TestClient) -> None:
        response = client.get("/jobs/999999999")
        assert response.headers["X-Request-ID"] == response.json()["request_id"]

    def test_unique_per_request(self, client: TestClient) -> None:
        first = client.get("/jobs").headers["X-Request-ID"]
        second = client.get("/jobs").headers["X-Request-ID"]
        assert first != second


class TestDatabaseFailures:
    def test_busy_becomes_503_with_retry_after(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SQLITE_BUSY is transient, so advising a retry is correct."""
        from jobsapi import repository

        def _busy(*args, **kwargs):
            exc = sqlite3.OperationalError("database is locked")
            exc.sqlite_errorname = "SQLITE_BUSY"
            raise exc

        monkeypatch.setattr(repository, "list_jobs", _busy)
        with TestClient(create_app(settings), raise_server_exceptions=False) as c:
            response = c.get("/jobs")

        assert_is_a_problem(response, status=503, code="DATABASE_BUSY")
        assert response.headers["Retry-After"] == "1"

    def test_wedged_becomes_503_without_retry_after(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hot journal cannot be cleared by retrying a read-only connection.

        Advising a retry here would send clients into a loop against a condition
        that can only be resolved by a human, which is why the two SQLite states
        map to different responses rather than one generic 503.
        """
        from jobsapi import repository

        def _wedged(*args, **kwargs):
            exc = sqlite3.OperationalError("attempt to write a readonly database")
            exc.sqlite_errorname = "SQLITE_READONLY_ROLLBACK"
            raise exc

        monkeypatch.setattr(repository, "list_jobs", _wedged)
        with TestClient(create_app(settings), raise_server_exceptions=False) as c:
            response = c.get("/jobs")

        assert_is_a_problem(response, status=503, code="DATABASE_UNAVAILABLE")
        assert "Retry-After" not in response.headers


class TestOpenApiMatchesReality:
    def test_the_problem_schema_is_published(self, client: TestClient) -> None:
        """Wrong generated docs mean wrong types — so the docs are asserted on."""
        schema = client.get("/openapi.json").json()
        assert "Problem" in schema["components"]["schemas"]
        responses = schema["paths"]["/jobs"]["get"]["responses"]
        assert PROBLEM_MEDIA_TYPE in responses["422"]["content"]

    def test_every_filter_is_documented(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        names = {p["name"] for p in schema["paths"]["/jobs"]["get"]["parameters"]}
        assert {
            "limit",
            "offset",
            "q",
            "source",
            "company",
            "remote",
            "seniority",
            "salary_min_gte",
            "salary_max_lte",
            "currency",
            "posted_after",
            "posted_before",
            "sort",
            "order",
        } <= names
