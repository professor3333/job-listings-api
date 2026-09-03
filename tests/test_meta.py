"""Phase 5: /sources, /runs, /stats, and /jobs/{id}/changes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobsapi.schemas import CHANGE_VALUE_MAX_LENGTH


class TestSources:
    def test_lists_each_source_with_its_job_count(self, client: TestClient) -> None:
        by_source = {s["source"]: s for s in client.get("/sources").json()}
        assert by_source["arbeitnow"]["job_count"] == 2
        assert by_source["greenhouse:anthropic"]["job_count"] == 1
        assert set(by_source) == {
            "arbeitnow",
            "greenhouse:anthropic",
            "greenhouse:figma",
            "python_org",
        }

    def test_reports_the_most_recent_run_not_the_first(
        self, client: TestClient
    ) -> None:
        """arbeitnow has two runs; the newer one is still `running`."""
        by_source = {s["source"]: s for s in client.get("/sources").json()}
        assert by_source["arbeitnow"]["last_run_id"] == 4
        assert by_source["arbeitnow"]["last_run_status"] == "running"

    def test_an_unfinished_run_reports_null_finished_at(
        self, client: TestClient
    ) -> None:
        """A scraper that dies between transactions never writes finished_at.

        Reported as-is. This service cannot tell a live run from an abandoned
        one by querying — the discriminator is a `-journal` file on disk.
        """
        by_source = {s["source"]: s for s in client.get("/sources").json()}
        assert by_source["arbeitnow"]["last_run_finished_at"] is None

    def test_a_source_with_no_run_row_still_appears(self, client: TestClient) -> None:
        """The LEFT JOIN. greenhouse:figma has a job but no run."""
        by_source = {s["source"]: s for s in client.get("/sources").json()}
        assert by_source["greenhouse:figma"]["job_count"] == 1
        assert by_source["greenhouse:figma"]["last_run_id"] is None

    def test_a_source_with_runs_but_no_jobs_does_not_appear(
        self, runs_only_source_client: TestClient
    ) -> None:
        """The converse of the test above, and it goes the other way.

        `FROM jobs` is the driving table, so a LEFT JOIN preserves a source with
        jobs and no runs — not a source with runs and no jobs, which has nothing
        to group and vanishes. That asymmetry is the contract (`docs/api.md`:
        "one entry per source that has jobs"), and it is pinned here because the
        SQL reads as though the join were symmetric.
        """
        sources = {s["source"] for s in runs_only_source_client.get("/sources").json()}
        assert "lever:ghost" not in sources
        assert sources, "the sources that do have jobs are unaffected"

    def test_is_empty_on_an_empty_database(self, empty_client: TestClient) -> None:
        assert empty_client.get("/sources").json() == []

    def test_is_a_bare_array_not_an_envelope(self, client: TestClient) -> None:
        """Deliberate inconsistency with /jobs: nothing here needs paging."""
        assert isinstance(client.get("/sources").json(), list)


class TestRuns:
    def test_paginated_newest_first(self, client: TestClient) -> None:
        body = client.get("/runs").json()
        assert body["total"] == 4
        assert [r["id"] for r in body["items"]] == [4, 3, 2, 1]

    def _run(self, client: TestClient, run_id: int) -> dict:
        items = client.get("/runs").json()["items"]
        return next(r for r in items if r["id"] == run_id)

    def test_a_measured_run_reports_its_elapsed_seconds(
        self, client: TestClient
    ) -> None:
        """Run 3 finished 4.25s after it started, and says so."""
        assert self._run(client, 3)["duration_seconds"] == 4.25

    def test_legacy_zero_duration_rows_report_null_not_zero(
        self, client: TestClient
    ) -> None:
        """The upstream bug this API refuses to launder.

        Build 2 stamped both ends of a run from one clock reading until
        2026-09-02, so runs 1 and 2 carry identical timestamps. `0.0` is the
        arithmetic answer and the wrong one: nothing in the response would
        contradict it, and a client would conclude scrapes are instantaneous.
        Null says "unknown", which is true.
        """
        for run_id in (1, 2):
            run = self._run(client, run_id)
            assert run["started_at"] == run["finished_at"]
            assert run["duration_seconds"] is None

    def test_an_unfinished_run_reports_null_duration(self, client: TestClient) -> None:
        """No end to measure from — null for a different reason, same answer."""
        run = self._run(client, 4)
        assert run["finished_at"] is None
        assert run["duration_seconds"] is None

    def test_duration_is_declared_in_the_openapi_schema(
        self, client: TestClient
    ) -> None:
        """A computed field still has to appear in the contract.

        `response_model` generates the schema, so a field that exists only at
        runtime would make `/docs` lie about the shape of the response.
        """
        schema = client.get("/openapi.json").json()
        prop = schema["components"]["schemas"]["RunSummary"]["properties"]
        assert "duration_seconds" in prop
        assert prop["duration_seconds"]["readOnly"] is True

    def test_running_row_has_null_finished_at(self, client: TestClient) -> None:
        assert client.get("/runs").json()["items"][0]["finished_at"] is None

    def test_pagination_bounds_are_enforced(self, client: TestClient) -> None:
        assert client.get("/runs", params={"limit": 0}).status_code == 422
        assert client.get("/runs", params={"limit": 1000}).status_code == 422
        assert client.get("/runs", params={"colour": "red"}).status_code == 422


class TestStats:
    def test_counts(self, client: TestClient) -> None:
        body = client.get("/stats").json()
        assert body["total_jobs"] == 5
        assert body["total_runs"] == 4
        assert body["total_changes"] == 3
        assert body["sources"] == 4

    def test_tri_state_split_adds_up(self, client: TestClient) -> None:
        body = client.get("/stats").json()
        total = body["remote_true"] + body["remote_false"] + body["remote_unknown"]
        assert total == body["total_jobs"]
        assert body["remote_unknown"] == 1

    def test_coverage_explains_the_null_filter_semantics(
        self, client: TestClient
    ) -> None:
        """The honest counterpart to "NULLs never satisfy a filter".

        A client seeing salary_min populated in 3 of 5 rows understands why a
        salary filter returns little, instead of assuming the filter is broken.
        """
        coverage = {c["field"]: c for c in client.get("/stats").json()["coverage"]}
        assert coverage["salary_min"]["present"] == 3
        assert coverage["salary_min"]["missing"] == 2
        assert coverage["salary_min"]["coverage"] == 0.6
        assert coverage["location"]["missing"] == 1

    def test_date_range(self, client: TestClient) -> None:
        body = client.get("/stats").json()
        assert body["earliest_posted_at"] == "2026-08-27"
        assert body["latest_posted_at"] == "2026-08-30"


class TestStatsAddsUp:
    """The invariants inside one `/stats` body.

    `stats()` worries in its docstring about counts taken from four different
    states of the database, and takes a snapshot to prevent it — but nothing
    checked that the numbers agree *within* one response. These are the
    relationships a client would assume without being told, and the ones a
    future edit to one of the six queries would silently break.
    """

    def test_every_coverage_field_accounts_for_every_row(
        self, client: TestClient
    ) -> None:
        body = client.get("/stats").json()
        for field in body["coverage"]:
            assert field["present"] + field["missing"] == body["total_jobs"], field

    def test_the_coverage_ratio_matches_its_own_counts(
        self, client: TestClient
    ) -> None:
        body = client.get("/stats").json()
        for field in body["coverage"]:
            expected = field["present"] / body["total_jobs"]
            assert field["coverage"] == pytest.approx(expected), field

    def test_the_remote_split_and_remote_coverage_are_the_same_fact(
        self, client: TestClient
    ) -> None:
        """`remote` is reported twice, by two different queries.

        Its coverage row comes from the SUM-per-field scan; the tri-state split
        comes from a separate SELECT. "Missing" and "unknown" are the same rows
        counted two ways, so they must agree — and if they ever stop agreeing,
        one of the two queries changed and the other did not.
        """
        body = client.get("/stats").json()
        coverage = {c["field"]: c for c in body["coverage"]}
        assert coverage["remote"]["missing"] == body["remote_unknown"]
        assert (
            coverage["remote"]["present"] == body["remote_true"] + body["remote_false"]
        )


class TestStatsOnAnEmptyDatabase:
    """Coverage divides by `COUNT(*)`. The guard existed; nothing exercised it."""

    def test_does_not_divide_by_zero(self, empty_client: TestClient) -> None:
        response = empty_client.get("/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["total_jobs"] == 0
        assert all(field["coverage"] == 0.0 for field in body["coverage"])
        assert all(
            field["present"] == field["missing"] == 0 for field in body["coverage"]
        )

    def test_reports_null_dates_rather_than_inventing_a_range(
        self, empty_client: TestClient
    ) -> None:
        """`MIN`/`MAX` over no rows is NULL, and null is the honest answer."""
        body = empty_client.get("/stats").json()
        assert body["earliest_posted_at"] is None
        assert body["latest_posted_at"] is None

    def test_the_tri_state_split_is_zero_not_null(
        self, empty_client: TestClient
    ) -> None:
        """`SUM` over no rows is NULL, not 0 — which is why the code coalesces.

        Without the `or 0`, an empty table would fail the response model on a
        non-nullable int rather than reporting three zeroes.
        """
        body = empty_client.get("/stats").json()
        assert (
            body["remote_true"] == body["remote_false"] == body["remote_unknown"] == 0
        )

    def test_an_empty_jobs_page_is_still_a_well_formed_envelope(
        self, empty_client: TestClient
    ) -> None:
        assert empty_client.get("/jobs").json() == {
            "items": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }


class TestJobChanges:
    def test_lists_changes_newest_first(self, client: TestClient) -> None:
        body = client.get("/jobs/1/changes").json()
        assert body["total"] == 2
        assert [c["field"] for c in body["items"]] == ["description", "salary_raw"]

    def test_large_values_are_truncated_with_true_lengths(
        self, client: TestClient
    ) -> None:
        """30 KB on disk becomes 200 characters on the wire, visibly.

        The whole point of a response model that is not the database row.
        """
        change = client.get("/jobs/1/changes").json()["items"][0]
        assert change["field"] == "description"
        assert len(change["old_value"]) == CHANGE_VALUE_MAX_LENGTH
        assert change["old_length"] == 5_000
        assert change["new_length"] == 5_001
        assert change["truncated"] is True

    def test_small_values_are_not_marked_truncated(self, client: TestClient) -> None:
        change = client.get("/jobs/1/changes").json()["items"][1]
        assert change["old_value"] == "80k-100k"
        assert change["new_value"] == "90k-120k"
        assert change["truncated"] is False

    def test_a_job_with_no_changes_is_an_empty_list(self, client: TestClient) -> None:
        """Exists, never changed — a 200 with nothing in it."""
        response = client.get("/jobs/3/changes")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    def test_an_unknown_job_is_404_not_an_empty_list(self, client: TestClient) -> None:
        """ "Never changed" and "does not exist" are different facts.

        Collapsing them would leave the endpoint unable to answer either.
        """
        response = client.get("/jobs/999999/changes")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_non_integer_job_id_is_422(self, client: TestClient) -> None:
        assert client.get("/jobs/abc/changes").status_code == 422

    def test_route_does_not_collide_with_the_detail_route(
        self, client: TestClient
    ) -> None:
        """`/jobs/1` and `/jobs/1/changes` differ in segment count, so both resolve."""
        assert client.get("/jobs/1").json()["id"] == 1
        assert "items" in client.get("/jobs/1/changes").json()
