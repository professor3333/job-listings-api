"""The hardening table, row by row.

Each case below corresponds to a row of "What must not crash it" in the project
brief. Some are asserted in more detail elsewhere; this file exists so the table
can be checked off against something, and so a removed guarantee fails a test
whose name says which guarantee it was.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobsapi.problems import PROBLEM_MEDIA_TYPE
from jobsapi.schemas import Q_MAX_LENGTH


class TestOversizedInput:
    def test_a_10000_character_q_is_rejected_on_length(
        self, client: TestClient
    ) -> None:
        """422 on the length rule — not a slow query, and not a truncated one.

        The cap is enforced before any SQL runs, so a hostile client cannot make
        the database do work by sending a huge search term. Truncating instead
        would silently answer a different question than the one asked.
        """
        response = client.get("/jobs", params={"q": "a" * 10_000})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert body["errors"][0]["field"] == "q"

    def test_the_boundary_is_inclusive(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"q": "a" * Q_MAX_LENGTH}).status_code == 200
        assert (
            client.get("/jobs", params={"q": "a" * (Q_MAX_LENGTH + 1)}).status_code
            == 422
        )

    def test_an_oversized_company_is_also_capped(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"company": "x" * 10_000}).status_code == 422


class TestEveryErrorUsesTheEnvelope:
    """ "Every 4xx response uses the one documented error envelope" — asserted.

    A definition-of-done line is only true if something checks it. This sweeps
    every failure mode reachable through the HTTP surface and requires the same
    media type and the same keys from all of them.
    """

    CASES = [
        ("/jobs", {"limit": 0}, 422),
        ("/jobs", {"limit": 1000}, 422),
        ("/jobs", {"limit": "abc"}, 422),
        ("/jobs", {"offset": -1}, 422),
        ("/jobs", {"q": "a" * 10_000}, 422),
        ("/jobs", {"sort": "id;DROP TABLE jobs"}, 422),
        ("/jobs", {"order": "sideways"}, 422),
        ("/jobs", {"source": "linkedin"}, 422),
        ("/jobs", {"currency": "EURO"}, 422),
        ("/jobs", {"posted_after": "not-a-date"}, 422),
        ("/jobs", {"colour": "red"}, 422),
        ("/jobs", {"salary_min_gte": 50_000, "salary_max_lte": 10_000}, 422),
        ("/jobs", {"posted_after": "2027-01-01", "posted_before": "2020-01-01"}, 422),
        ("/jobs/abc", {}, 422),
        ("/jobs/0", {}, 422),
        ("/jobs/999999999", {}, 404),
        ("/nope", {}, 404),
    ]

    @pytest.mark.parametrize(("path", "params", "status"), CASES)
    def test_shape_is_identical(
        self, client: TestClient, path: str, params: dict, status: int
    ) -> None:
        response = client.get(path, params=params)
        assert response.status_code == status
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        body = response.json()
        assert {"type", "title", "status", "detail", "instance", "code"} <= set(body)
        assert body["status"] == status
        assert isinstance(body["detail"], str)


class TestReadOnlySurface:
    """The service exposes no way to change anything."""

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_write_methods_are_not_allowed(
        self, client: TestClient, method: str
    ) -> None:
        response = getattr(client, method)("/jobs")
        assert response.status_code == 405
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


class TestNullSerialisation:
    def test_nulls_are_json_null_never_the_string_none(
        self, client: TestClient
    ) -> None:
        """`"None"` in a response body means a Python object leaked through str()."""
        raw = client.get("/jobs").text
        assert '"None"' not in raw
        assert "null" in raw

    def test_absent_values_are_present_as_null_not_omitted(
        self, client: TestClient
    ) -> None:
        """A missing key and a null value are different contracts.

        Omitting the key would force clients to distinguish "no salary recorded"
        from "this API version does not send salary".
        """
        row = next(i for i in client.get("/jobs").json()["items"] if i["id"] == 2)
        for field in ("location", "salary_min", "salary_max", "currency"):
            assert field in row
            assert row[field] is None
