"""The hardening table, row by row.

Each case below corresponds to a row of "What must not crash it" in the project
brief. Some are asserted in more detail elsewhere; this file exists so the table
can be checked off against something, and so a removed guarantee fails a test
whose name says which guarantee it was.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from jobsapi.problems import PROBLEM_MEDIA_TYPE
from jobsapi.schemas import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    LIMIT_MIN,
    Q_MAX_LENGTH,
    WIRE_CURRENCY_PATTERN,
    JobFilters,
    Pagination,
)


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


class TestTheLimitCapIsPinnedAtItsBoundary:
    """The cap is a published number, so something must hold it to that number.

    Before these tests the suite proved only that `limit=1000` was refused and
    `limit=0` was refused. Every value between 21 and 999 would have passed the
    entire suite, so the cap could have drifted to any of them — including by
    accident — without a single failure. Testing far from a boundary does not
    test the boundary.
    """

    def test_the_cap_itself_is_accepted(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"limit": LIMIT_MAX}).status_code == 200

    def test_one_past_the_cap_is_refused(self, client: TestClient) -> None:
        response = client.get("/jobs", params={"limit": LIMIT_MAX + 1})
        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "limit"

    def test_the_floor_itself_is_accepted(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"limit": LIMIT_MIN}).status_code == 200

    def test_one_below_the_floor_is_refused(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"limit": LIMIT_MIN - 1}).status_code == 422

    def test_the_cap_is_the_number_the_contract_publishes(self) -> None:
        """Deliberately hard-coded, and the only test here that is.

        Importing `LIMIT_MAX` everywhere proves the code agrees with itself,
        which it always will. It cannot notice the constant being changed to
        250 — every other test in this class would follow it happily. Only a
        literal can hold the value to what `docs/api.md` promises a client.
        """
        assert (LIMIT_MIN, LIMIT_MAX, LIMIT_DEFAULT) == (1, 100, 20)

    def test_the_default_applies_when_the_key_is_absent(
        self, client: TestClient
    ) -> None:
        body = client.get("/jobs").json()
        assert body["limit"] == LIMIT_DEFAULT

    def test_an_empty_value_is_not_the_default(self, client: TestClient) -> None:
        """`?limit=` is the empty string, not an absent key.

        The two look alike to a client and resolve differently: an absent key
        takes the default, an empty one fails coercion. Asserting it stops the
        distinction being "fixed" into a default later.
        """
        assert client.get("/jobs?limit=").status_code == 422


class TestTheGeneratedSchemaPublishesWhatIsEnforced:
    """`/openapi.json` is the contract a generated client compiles against.

    A constraint the service enforces but the schema omits cannot be honoured
    by any client: it discovers the rule by being refused. That is the inverse
    of the failure this build is built to avoid, and it is not hypothetical —
    a `BeforeValidator` makes Pydantic withdraw `pattern` from the schema.
    """

    @staticmethod
    def _query_param(client: TestClient, path: str, name: str) -> dict:
        spec = client.get("/openapi.json").json()
        for parameter in spec["paths"][path]["get"]["parameters"]:
            if parameter["name"] == name:
                return parameter
        raise AssertionError(f"{name} is not a documented parameter of {path}")

    def test_currency_publishes_a_pattern(self, client: TestClient) -> None:
        schema = str(self._query_param(client, "/jobs", "currency")["schema"])
        assert "pattern" in schema

    def test_the_published_pattern_accepts_what_the_service_accepts(
        self, client: TestClient
    ) -> None:
        """The wire pattern, not the post-normalisation one.

        Publishing `^[A-Z]{3}$` would be a second lie in the other direction:
        it would tell a client that `usd` is invalid, when this API accepts it.
        """
        published = re.compile(WIRE_CURRENCY_PATTERN)
        for accepted in ("usd", "USD", "uSd"):
            assert published.match(accepted)
            assert client.get("/jobs", params={"currency": accepted}).status_code == 200

    def test_the_published_pattern_refuses_what_the_service_refuses(
        self, client: TestClient
    ) -> None:
        published = re.compile(WIRE_CURRENCY_PATTERN)
        for refused in ("dollars", "us", " usd "):
            assert not published.match(refused)
            assert client.get("/jobs", params={"currency": refused}).status_code == 422

    def test_the_limit_bounds_are_published(self, client: TestClient) -> None:
        schema = self._query_param(client, "/jobs", "limit")["schema"]
        assert schema.get("maximum") == LIMIT_MAX
        assert schema.get("minimum") == LIMIT_MIN


class TestUnknownParametersAreRefusedOnEveryListEndpoint:
    """`extra="forbid"` is declared once, on `Pagination`, and inherited.

    It lived on `JobFilters` once, which meant `?colour=red` was a 422 on
    `/jobs` and silently ignored on `/runs`. These tests pin the rule to every
    endpoint that paginates, so a copy re-appearing on one subclass cannot go
    unnoticed again.
    """

    @pytest.mark.parametrize("path", ["/jobs", "/runs"])
    def test_an_unknown_parameter_is_refused(
        self, client: TestClient, path: str
    ) -> None:
        response = client.get(path, params={"colour": "red"})
        assert response.status_code == 422
        error = response.json()["errors"][0]
        assert error["field"] == "colour"
        assert error["rule"] == "extra_forbidden"

    def test_the_rule_lives_on_the_base(self) -> None:
        """Asserted on `Pagination`, which is the placement that matters.

        There is no runtime way to tell "inherited" from "restated": Pydantic's
        metaclass merges `model_config` down the MRO and writes the result onto
        every subclass, so it is present in `JobFilters.__dict__` either way.
        What *is* detectable is the rule leaving the base — the failure that
        actually shipped once, taking `/runs` with it.
        """
        assert Pagination.model_config["extra"] == "forbid"
        assert JobFilters.model_config["extra"] == "forbid"


class TestEmptyTextFilters:
    """An empty text filter is refused, not silently dropped.

    Before `min_length=1` these returned 200 with the unfiltered list: the
    parameter validated, the repository's truthiness test discarded it, and
    nothing told the client its filter had not applied. That is the failure
    `docs/api.md` already rejects for unknown parameters, reached by a
    different route.
    """

    @pytest.mark.parametrize("field", ["q", "company"])
    def test_empty_is_refused(self, client: TestClient, field: str) -> None:
        response = client.get("/jobs", params={field: ""})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert [e["field"] for e in body["errors"]] == [field]

    @pytest.mark.parametrize("field", ["q", "company"])
    def test_the_bound_is_published_not_merely_enforced(
        self, client: TestClient, field: str
    ) -> None:
        """The counterpart to the `currency` finding.

        There a `BeforeValidator` made Pydantic withdraw `pattern` from the
        generated schema, so the rule was enforced and unpublished. These two
        fields carry no validator, so `minLength` survives into
        `/openapi.json` — a generated client can refuse an empty search
        without asking the server.
        """
        spec = client.get("/openapi.json").json()
        params = spec["paths"]["/jobs"]["get"]["parameters"]
        schema = next(p["schema"] for p in params if p["name"] == field)
        string_branch = next(b for b in schema["anyOf"] if b.get("type") == "string")
        assert string_branch["minLength"] == 1

    def test_a_whitespace_term_is_still_a_term(self, client: TestClient) -> None:
        """The bound asks whether a term was sent, not whether it is useful.

        `?q=%20` is a one-character search for a space. It is legal, it reaches
        the SQL, and it matches whatever contains a space — unlike `?q=`, which
        was never a search at all.
        """
        assert client.get("/jobs", params={"q": " "}).status_code == 200
