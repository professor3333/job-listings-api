"""Phase 5: /sources, /runs, /stats, and /jobs/{id}/changes."""

from __future__ import annotations

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

    def test_is_a_bare_array_not_an_envelope(self, client: TestClient) -> None:
        """Deliberate inconsistency with /jobs: nothing here needs paging."""
        assert isinstance(client.get("/sources").json(), list)


class TestRuns:
    def test_paginated_newest_first(self, client: TestClient) -> None:
        body = client.get("/runs").json()
        assert body["total"] == 4
        assert [r["id"] for r in body["items"]] == [4, 3, 2, 1]

    def test_no_duration_is_reported(self, client: TestClient) -> None:
        """The upstream bug this API refuses to launder.

        Build 2 stamps `finished_at` from the same value as `started_at`, so a
        computed duration would be 0.0 for every completed run. Publishing that
        would be confidently wrong; omitting it and exposing both timestamps
        lets a client see the problem for itself.
        """
        run = client.get("/runs").json()["items"][-1]
        assert "duration_seconds" not in run
        assert run["started_at"] == run["finished_at"]

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
