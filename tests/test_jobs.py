"""Phase 2: the read path — GET /jobs and GET /jobs/{job_id}."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestListJobs:
    def test_returns_the_page_envelope(self, client: TestClient) -> None:
        body = client.get("/jobs").json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert body["total"] == 5
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert len(body["items"]) == 5

    def test_newest_first_with_nulls_last(self, client: TestClient) -> None:
        """Row 5 has a NULL posted_at and must sort last under DESC, not first."""
        ids = [item["id"] for item in client.get("/jobs").json()["items"]]
        assert ids == [1, 2, 3, 4, 5]

    def test_description_never_appears_in_a_list(self, client: TestClient) -> None:
        """The reason JobSummary omits it — 5.7 KB average, 33 KB worst case.

        Structural, not vigilance: even if the query started selecting it, the
        response model would drop it.
        """
        for item in client.get("/jobs").json()["items"]:
            assert "description" not in item

    def test_pagination_does_not_repeat_or_skip(self, client: TestClient) -> None:
        """The tie-break in ORDER BY is what makes this true.

        Ordering by `posted_at` alone leaves ties whose order SQLite may resolve
        differently per query, so pages would overlap. Walking the whole table
        two rows at a time must yield each id exactly once.
        """
        seen: list[int] = []
        for offset in (0, 2, 4):
            page = client.get("/jobs", params={"limit": 2, "offset": offset}).json()
            seen.extend(item["id"] for item in page["items"])
        assert seen == [1, 2, 3, 4, 5]
        assert len(set(seen)) == len(seen)

    def test_offset_past_the_end_is_empty_not_404(self, client: TestClient) -> None:
        """An empty result is a successful answer to a reasonable question."""
        response = client.get("/jobs", params={"offset": 999})
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 5

    def test_nulls_serialise_as_json_null(self, client: TestClient) -> None:
        """Never the string "None", never a silently omitted key."""
        row = next(i for i in client.get("/jobs").json()["items"] if i["id"] == 2)
        for field in ("location", "salary_min", "salary_max", "currency"):
            assert field in row
            assert row[field] is None

    def test_remote_is_tri_state(self, client: TestClient) -> None:
        """NULL is "unknown" and must not collapse into False."""
        by_id = {i["id"]: i for i in client.get("/jobs").json()["items"]}
        assert by_id[1]["remote"] is True
        assert by_id[2]["remote"] is False
        assert by_id[3]["remote"] is None

    def test_unicode_and_apostrophes_survive(self, client: TestClient) -> None:
        by_id = {i["id"]: i for i in client.get("/jobs").json()["items"]}
        assert by_id[4]["company"] == "Ürsprung Ähtäri Oy"
        assert by_id[4]["title"] == "Ingénieur Logiciel"
        assert by_id[5]["company"] == "O'Reilly & Co"
        assert by_id[5]["title"] == "Developer's Advocate; 100% remote"

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"limit": 0}, "limit"),
            ({"limit": 101}, "limit"),
            ({"limit": 1000}, "limit"),
            ({"limit": "abc"}, "limit"),
            ({"offset": -1}, "offset"),
            ({"offset": "abc"}, "offset"),
        ],
    )
    def test_out_of_range_is_422_and_names_the_field(
        self, client: TestClient, params: dict, field: str
    ) -> None:
        """Rejected, never clamped.

        Silently turning limit=1000 into 100 would teach a client that its
        request was honoured. The body must name the offending field so the
        caller can fix it without guessing.
        """
        response = client.get("/jobs", params=params)
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert any(e["field"] == field for e in body["errors"])

    def test_boundaries_are_inclusive(self, client: TestClient) -> None:
        assert client.get("/jobs", params={"limit": 1}).status_code == 200
        assert client.get("/jobs", params={"limit": 100}).status_code == 200
        assert client.get("/jobs", params={"offset": 0}).status_code == 200


class TestGetJob:
    def test_returns_the_full_record(self, client: TestClient) -> None:
        body = client.get("/jobs/1").json()
        assert body["id"] == 1
        assert body["title"] == "Senior Python Engineer"
        assert body["source_id"] == "a-1"
        assert body["description"] == "A" * 40
        assert body["first_seen"].startswith("2026-08-01T00:00:00")

    def test_internal_columns_never_leak(self, client: TestClient) -> None:
        """`content_hash` and `hash_version` are Build 2's business."""
        body = client.get("/jobs/1").json()
        assert "content_hash" not in body
        assert "hash_version" not in body

    def test_missing_id_is_404(self, client: TestClient) -> None:
        assert client.get("/jobs/999999999").status_code == 404

    def test_non_integer_id_is_422_not_500(self, client: TestClient) -> None:
        """Typing the path parameter as int is what buys this."""
        response = client.get("/jobs/abc")
        assert response.status_code == 422
        assert any(e["field"] == "job_id" for e in response.json()["errors"])

    def test_null_posted_at_serialises_as_null(self, client: TestClient) -> None:
        assert client.get("/jobs/5").json()["posted_at"] is None
