"""Phase 3: every query parameter on GET /jobs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def ids(response) -> list[int]:
    return [item["id"] for item in response.json()["items"]]


class TestTextSearch:
    def test_q_matches_title_or_company(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"q": "Engineer"})) == [1, 2, 3]
        assert ids(client.get("/jobs", params={"q": "Acme"})) == [1]

    def test_q_is_case_insensitive(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"q": "engineer"})) == [1, 2, 3]

    @pytest.mark.parametrize("term", ["%", "_", "'", ";", "100%", "🙂"])
    def test_wildcards_and_punctuation_match_literally(
        self, client: TestClient, term: str
    ) -> None:
        """`%` must not become "match everything", and `'` must not break SQL.

        Row 5's title contains "100% remote", so searching "100%" finds exactly
        it — proving the wildcard was escaped rather than interpreted. The
        apostrophe and semicolon are bound parameters and can never be executed.
        """
        response = client.get("/jobs", params={"q": term})
        assert response.status_code == 200
        if term == "%":
            # Literal '%' appears only in row 5, not in all five rows.
            assert ids(response) == [5]
        if term == "100%":
            assert ids(response) == [5]
        if term == "🙂":
            assert ids(response) == []

    def test_total_reflects_the_filter_not_the_table(self, client: TestClient) -> None:
        """A `total` computed without the WHERE clause would be a silent lie."""
        body = client.get("/jobs", params={"q": "Acme"}).json()
        assert body["total"] == 1
        assert len(body["items"]) == 1


class TestScalarFilters:
    def test_source(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"source": "arbeitnow"})) == [1, 2]

    def test_source_with_a_colon(self, client: TestClient) -> None:
        """The functional-StrEnum case: member name != wire value."""
        r = client.get("/jobs", params={"source": "greenhouse:anthropic"})
        assert ids(r) == [3]

    def test_unknown_source_is_422_listing_the_legal_values(
        self, client: TestClient
    ) -> None:
        response = client.get("/jobs", params={"source": "linkedin"})
        assert response.status_code == 422
        assert "arbeitnow" in response.json()["errors"][0]["message"]

    def test_company_is_a_prefix_match(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"company": "Acme"})) == [1]
        assert ids(client.get("/jobs", params={"company": "Ac"})) == [1]
        # Prefix, not substring: "cme" must not match "Acme GmbH".
        assert ids(client.get("/jobs", params={"company": "cme"})) == []

    def test_seniority(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"seniority": "senior"})) == [1]

    def test_currency_is_uppercased_before_matching(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"currency": "eur"})) == [1]
        assert ids(client.get("/jobs", params={"currency": "EUR"})) == [1]

    @pytest.mark.parametrize("bad", ["EURO", "US", "12", ""])
    def test_malformed_currency_is_422(self, client: TestClient, bad: str) -> None:
        assert client.get("/jobs", params={"currency": bad}).status_code == 422


class TestRemoteTriState:
    """NULL is not False — the data contract Build 2 established, honoured here."""

    def test_true(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"remote": "true"})) == [1, 4, 5]

    def test_false(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"remote": "false"})) == [2]

    def test_unknown_selects_nulls_only(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"remote": "unknown"})) == [3]

    def test_the_three_states_partition_the_table(self, client: TestClient) -> None:
        """Every row falls into exactly one bucket, and none is double-counted."""
        found = sorted(
            ids(client.get("/jobs", params={"remote": state}))
            for state in ("true", "false", "unknown")
        )
        flat = sorted(i for group in found for i in group)
        assert flat == [1, 2, 3, 4, 5]

    def test_unknown_is_not_a_synonym_for_false(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"remote": "false"})) != ids(
            client.get("/jobs", params={"remote": "unknown"})
        )


class TestSalaryFilters:
    def test_min_gte(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"salary_min_gte": 90_000})) == [1, 3]

    def test_max_lte(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"salary_max_lte": 120_000})) == [1]

    def test_rows_with_no_salary_are_excluded(self, client: TestClient) -> None:
        """The documented answer to "does a NULL salary satisfy a salary filter?"

        No. `NULL >= 50000` is NULL, which is not true, so SQLite excludes the
        row — and that is the behaviour we want: a filter on a value cannot be
        satisfied by the absence of that value. Rows 2 and 4 have no salary and
        must never appear, whatever the threshold.
        """
        for threshold in (0, 1, 50_000, 999_999):
            assert 2 not in ids(
                client.get("/jobs", params={"salary_min_gte": threshold})
            )
            assert 4 not in ids(
                client.get("/jobs", params={"salary_min_gte": threshold})
            )

    def test_negative_salary_is_422(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"salary_min_gte": -1}).status_code == 422


class TestDateFilters:
    def test_posted_after(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"posted_after": "2026-08-29"})) == [1, 2]

    def test_posted_before(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"posted_before": "2026-08-28"})) == [
            3,
            4,
        ]

    def test_a_range(self, client: TestClient) -> None:
        response = client.get(
            "/jobs",
            params={"posted_after": "2026-08-28", "posted_before": "2026-08-29"},
        )
        assert ids(response) == [2, 3]

    def test_null_posted_at_matches_no_date_filter(self, client: TestClient) -> None:
        """Row 5 has no date. Same NULL rule as salary."""
        assert 5 not in ids(client.get("/jobs", params={"posted_after": "1900-01-01"}))

    @pytest.mark.parametrize("bad", ["not-a-date", "2026-13-01", "01-01-2026"])
    def test_malformed_date_is_422(self, client: TestClient, bad: str) -> None:
        assert client.get("/jobs", params={"posted_after": bad}).status_code == 422


class TestSorting:
    def test_default_is_newest_first(self, client: TestClient) -> None:
        assert ids(client.get("/jobs")) == [1, 2, 3, 4, 5]

    def test_sort_and_order(self, client: TestClient) -> None:
        assert ids(client.get("/jobs", params={"sort": "id", "order": "asc"})) == [
            1,
            2,
            3,
            4,
            5,
        ]
        assert ids(client.get("/jobs", params={"sort": "id", "order": "desc"})) == [
            5,
            4,
            3,
            2,
            1,
        ]

    def test_sorting_by_a_tied_column_is_still_deterministic(
        self, client: TestClient
    ) -> None:
        """All five rows share no company, but the tie-break must still apply.

        Requesting the same page twice must give the same answer — the property
        that makes pagination safe.
        """
        first = ids(client.get("/jobs", params={"sort": "company"}))
        second = ids(client.get("/jobs", params={"sort": "company"}))
        assert first == second

    @pytest.mark.parametrize(
        "bad_sort",
        ["id;DROP TABLE jobs", "content_hash", "description", "1", "id--"],
    )
    def test_sort_is_an_allowlist(self, client: TestClient, bad_sort: str) -> None:
        """Rejected by the enum before any SQL is built.

        `content_hash` and `description` are real columns and still rejected —
        the allowlist is about the public contract, not merely about safety.
        """
        response = client.get("/jobs", params={"sort": bad_sort})
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_FAILED"

    def test_bad_order_is_422(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"order": "sideways"}).status_code == 422


class TestCombinedFilters:
    def test_filters_are_anded_together(self, client: TestClient) -> None:
        response = client.get("/jobs", params={"source": "arbeitnow", "remote": "true"})
        assert ids(response) == [1]

    def test_filters_apply_to_pagination_and_total(self, client: TestClient) -> None:
        body = client.get(
            "/jobs", params={"q": "Engineer", "limit": 2, "offset": 0}
        ).json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

    def test_a_filter_matching_nothing_is_200_not_404(self, client: TestClient) -> None:
        response = client.get("/jobs", params={"company": "Nonexistent"})
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
