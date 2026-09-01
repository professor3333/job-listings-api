"""Phase 5: structured logging, request correlation, timing, and PRAGMAs."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from jobsapi.config import Settings
from jobsapi.db import connect
from jobsapi.main import create_app


def access_lines(records: list[dict]) -> list[dict]:
    return [r for r in records if r["logger"] == "jobsapi.access"]


class TestStructuredLogging:
    def test_every_line_is_one_json_object(
        self, client: TestClient, capture_logs
    ) -> None:
        """Greppable *and* queryable — the reason for JSON over prose."""
        with capture_logs() as records:
            client.get("/jobs")
        assert records
        for line in records:
            assert {"ts", "level", "logger", "message", "request_id"} <= set(line)

    def test_an_access_line_carries_method_path_status_and_duration(
        self, client: TestClient, capture_logs
    ) -> None:
        with capture_logs() as records:
            client.get("/jobs", params={"limit": 2})
        access = access_lines(records)
        assert access
        http = access[-1]["http"]
        assert http["method"] == "GET"
        assert http["path"] == "/jobs"
        assert http["status"] == 200
        assert http["query"] == "limit=2"
        assert isinstance(http["duration_ms"], int | float)
        assert http["duration_ms"] >= 0

    def test_the_logged_id_matches_the_response_header(
        self, client: TestClient, capture_logs
    ) -> None:
        """Correlation is the point: a header a user can quote finds the line."""
        with capture_logs() as records:
            response = client.get("/jobs")
        assert (
            access_lines(records)[-1]["request_id"]
            == (response.headers["X-Request-ID"])
        )

    def test_failed_requests_are_logged_too(
        self, client: TestClient, capture_logs
    ) -> None:
        with capture_logs() as records:
            client.get("/jobs", params={"limit": 0})
        assert access_lines(records)[-1]["http"]["status"] == 422


class TestTiming:
    def test_response_time_header_is_present_and_numeric(
        self, client: TestClient
    ) -> None:
        value = client.get("/jobs").headers["X-Response-Time-ms"]
        assert float(value) >= 0

    def test_timing_uses_a_monotonic_clock(self, client: TestClient) -> None:
        """`perf_counter`, not `time()`.

        A wall clock adjusted mid-request can run backwards and produce a
        negative duration; a monotonic one cannot. Asserting non-negativity is
        the observable half of that choice.
        """
        for _ in range(5):
            assert float(client.get("/jobs").headers["X-Response-Time-ms"]) >= 0


class TestTracebackHandling:
    def test_traceback_reaches_the_log_but_not_the_body(
        self, settings: Settings, capture_logs
    ) -> None:
        """The two halves of the bargain, asserted together.

        The body of a 500 says nothing useful on purpose. That is only
        defensible if the traceback is written somewhere — otherwise the failure
        is unresolvable. `request_id` is what joins the body a user reports to
        the line an operator needs.
        """
        app = create_app(settings)

        @app.get("/boom")
        def _boom() -> None:
            raise RuntimeError("secret internal detail")

        with (
            capture_logs() as records,
            TestClient(app, raise_server_exceptions=False) as fresh,
        ):
            response = fresh.get("/boom")

        assert response.status_code == 500
        assert "secret internal detail" not in response.text
        assert "Traceback" not in response.text

        errors = [r for r in records if r["logger"] == "jobsapi.errors"]
        assert errors, "the traceback was written nowhere"
        assert "secret internal detail" in errors[-1]["exception"]
        assert "Traceback" in errors[-1]["exception"]
        assert errors[-1]["request_id"] == response.json()["request_id"]


class TestConnectionPragmas:
    def test_query_only_refuses_writes_independently_of_mode_ro(
        self, settings: Settings
    ) -> None:
        """Two independent guarantees, so removing one does not remove both."""
        conn = connect(settings)
        try:
            assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("UPDATE jobs SET title = 'x'")
        finally:
            conn.close()

    def test_busy_timeout_is_applied(self, settings: Settings) -> None:
        conn = connect(settings)
        try:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == (
                settings.busy_timeout_ms
            )
        finally:
            conn.close()

    def test_temp_store_is_memory(self, settings: Settings) -> None:
        """A container with a read-only filesystem cannot spill a sort to disk."""
        conn = connect(settings)
        try:
            assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2
        finally:
            conn.close()
