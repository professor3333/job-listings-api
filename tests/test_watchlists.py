"""The write path: bodies, 201/204/404/409/422, and PUT versus PATCH."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from jobsapi.config import Settings
from jobsapi.main import create_app


def make(client: TestClient, name: str = "Backend roles", **kwargs) -> dict:
    """Create a watchlist and return it, failing loudly if that did not work."""
    response = client.post("/watchlists", json={"name": name, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Create — 201, Location, and the body contract
# --------------------------------------------------------------------------


def test_create_returns_201_with_a_location_header(client: TestClient) -> None:
    response = client.post(
        "/watchlists", json={"name": "Backend roles", "description": "EU only"}
    )

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"/watchlists/{body['id']}"
    assert body["name"] == "Backend roles"
    assert body["description"] == "EU only"
    assert body["item_count"] == 0


def test_the_location_header_actually_resolves(client: TestClient) -> None:
    """A Location that 404s is worse than no Location at all."""
    created = client.post("/watchlists", json={"name": "Remote"})

    followed = client.get(created.headers["Location"])

    assert followed.status_code == 200
    assert followed.json()["id"] == created.json()["id"]


def test_server_owned_fields_cannot_be_set_by_the_client(client: TestClient) -> None:
    """`id` is not in the request model, so sending it is a 422, not a silent win."""
    response = client.post("/watchlists", json={"name": "Mine", "id": 999})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "id"


def test_description_is_optional(client: TestClient) -> None:
    assert make(client, "No description")["description"] is None


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "x" * 81}, "name"),
        ({"name": "ok", "description": "d" * 501}, "description"),
        ({"name": 42}, "name"),
        ({"name": "ok", "colour": "red"}, "colour"),
    ],
)
def test_bad_bodies_are_422_naming_the_field(
    client: TestClient, body: dict, field: str
) -> None:
    response = client.post("/watchlists", json=body)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert field in [error["field"] for error in response.json()["errors"]]


def test_a_body_that_is_not_an_object_is_422(client: TestClient) -> None:
    response = client.post(
        "/watchlists", content=b"[1,2,3]", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422


def test_malformed_json_is_422_not_500(client: TestClient) -> None:
    response = client.post(
        "/watchlists",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# 409 — the state refuses, not the input
# --------------------------------------------------------------------------


def test_duplicate_name_is_409_with_the_duplicate_code(client: TestClient) -> None:
    make(client, "Backend roles")

    response = client.post("/watchlists", json={"name": "Backend roles"})

    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_RESOURCE"


def test_duplicate_detection_is_case_insensitive(client: TestClient) -> None:
    """COLLATE NOCASE on the column, so 'backend ROLES' is the same name."""
    make(client, "Backend roles")

    assert client.post("/watchlists", json={"name": "backend ROLES"}).status_code == 409


def test_a_duplicate_does_not_create_a_second_row(client: TestClient) -> None:
    make(client, "Backend roles")
    client.post("/watchlists", json={"name": "Backend roles"})

    assert client.get("/watchlists").json()["total"] == 1


# --------------------------------------------------------------------------
# PUT versus PATCH — the distinction this phase exists to teach
# --------------------------------------------------------------------------


def test_put_replaces_and_an_omitted_field_is_cleared(client: TestClient) -> None:
    created = make(client, "Backend roles", description="EU only")

    response = client.put(f"/watchlists/{created['id']}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["description"] is None, "PUT is a replacement, not a merge"


def test_patch_leaves_unmentioned_fields_alone(client: TestClient) -> None:
    """The bug this guards: every unsent field arriving as None and wiping data."""
    created = make(client, "Backend roles", description="EU only")

    response = client.patch(f"/watchlists/{created['id']}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["description"] == "EU only"


def test_patch_can_explicitly_clear_a_field(client: TestClient) -> None:
    """`{"description": null}` is a different instruction from omitting it."""
    created = make(client, "Backend roles", description="EU only")

    response = client.patch(f"/watchlists/{created['id']}", json={"description": None})

    assert response.json()["description"] is None
    assert response.json()["name"] == "Backend roles"


def test_an_empty_patch_is_422(client: TestClient) -> None:
    created = make(client)

    response = client.patch(f"/watchlists/{created['id']}", json={})

    assert response.status_code == 422
    assert "at least one field" in response.json()["detail"]


def test_put_is_idempotent(client: TestClient) -> None:
    created = make(client, "Backend roles")
    body = {"name": "Renamed", "description": "Twice"}

    first = client.put(f"/watchlists/{created['id']}", json=body)
    second = client.put(f"/watchlists/{created['id']}", json=body)

    assert first.status_code == second.status_code == 200
    assert first.json()["name"] == second.json()["name"]
    assert first.json()["description"] == second.json()["description"]


def test_put_requires_the_whole_body(client: TestClient) -> None:
    created = make(client)

    assert client.put(f"/watchlists/{created['id']}", json={}).status_code == 422


def test_put_to_a_missing_id_is_404_and_does_not_create(client: TestClient) -> None:
    """Upsert-on-PUT is legal HTTP and wrong here: ids are server-assigned."""
    response = client.put("/watchlists/999999", json={"name": "Ghost"})

    assert response.status_code == 404
    assert client.get("/watchlists").json()["total"] == 0


def test_renaming_onto_another_name_is_409(client: TestClient) -> None:
    make(client, "First")
    second = make(client, "Second")

    response = client.patch(f"/watchlists/{second['id']}", json={"name": "First"})

    assert response.status_code == 409


def test_updated_at_moves_but_created_at_does_not(client: TestClient) -> None:
    created = make(client)

    patched = client.patch(
        f"/watchlists/{created['id']}", json={"name": "Renamed"}
    ).json()

    assert patched["created_at"] == created["created_at"]
    assert patched["updated_at"] >= created["updated_at"]


# --------------------------------------------------------------------------
# Delete — 204, and what a repeat call says
# --------------------------------------------------------------------------


def test_delete_returns_204_with_no_body(client: TestClient) -> None:
    created = make(client)

    response = client.delete(f"/watchlists/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""


def test_deleting_twice_is_404_the_second_time(client: TestClient) -> None:
    created = make(client)
    client.delete(f"/watchlists/{created['id']}")

    assert client.delete(f"/watchlists/{created['id']}").status_code == 404


def test_deleting_a_watchlist_removes_its_items(client: TestClient) -> None:
    """ON DELETE CASCADE, which only works because foreign_keys is ON."""
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})

    client.delete(f"/watchlists/{created['id']}")
    again = make(client, "Reused")

    assert client.get(f"/watchlists/{again['id']}/jobs").json()["total"] == 0


def test_cascade_really_deleted_the_rows(settings: Settings) -> None:
    """Asserted against the database, not inferred from the API's answer."""
    with TestClient(create_app(settings)) as client:
        created = make(client)
        client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})
        client.delete(f"/watchlists/{created['id']}")

    conn = sqlite3.connect(settings.app_db_path)
    try:
        remaining = conn.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0]
    finally:
        conn.close()

    assert remaining == 0


# --------------------------------------------------------------------------
# Items — two databases in one request
# --------------------------------------------------------------------------


def test_adding_a_job_returns_201_and_the_job(client: TestClient) -> None:
    created = make(client)

    response = client.post(
        f"/watchlists/{created['id']}/jobs", json={"job_id": 1, "note": "apply"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["job_id"] == 1
    assert body["note"] == "apply"
    assert body["job"]["title"] == "Senior Python Engineer"


def test_adding_a_job_that_does_not_exist_is_404(client: TestClient) -> None:
    """Validated against the read-only database before anything is written."""
    created = make(client)

    response = client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 99999})

    assert response.status_code == 404
    assert client.get(f"/watchlists/{created['id']}/jobs").json()["total"] == 0


def test_adding_to_a_missing_watchlist_is_404(client: TestClient) -> None:
    assert client.post("/watchlists/999999/jobs", json={"job_id": 1}).status_code == 404


def test_adding_the_same_job_twice_is_409(client: TestClient) -> None:
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})

    response = client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})

    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_RESOURCE"


def test_item_count_reflects_the_items(client: TestClient) -> None:
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 2})

    assert client.get(f"/watchlists/{created['id']}").json()["item_count"] == 2


def test_listing_items_paginates_like_everything_else(client: TestClient) -> None:
    created = make(client)
    for job_id in (1, 2, 3):
        client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": job_id})

    page = client.get(f"/watchlists/{created['id']}/jobs?limit=2").json()

    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_removing_a_job_is_204_then_404(client: TestClient) -> None:
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})

    assert client.delete(f"/watchlists/{created['id']}/jobs/1").status_code == 204
    assert client.delete(f"/watchlists/{created['id']}/jobs/1").status_code == 404


def test_a_job_deleted_from_the_source_is_reported_not_hidden(
    client: TestClient, settings: Settings
) -> None:
    """The dangling reference no foreign key can prevent across two databases."""
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1, "note": "keep"})

    source = sqlite3.connect(settings.db_path)
    try:
        source.execute("DELETE FROM jobs WHERE id = 1")
        source.commit()
    finally:
        source.close()

    page = client.get(f"/watchlists/{created['id']}/jobs").json()

    assert page["total"] == 1, "the saved row must not vanish"
    assert page["items"][0]["job"] is None
    assert page["items"][0]["job_missing"] is True
    assert page["items"][0]["note"] == "keep"


def test_a_saved_job_can_be_removed_after_it_left_the_source(
    client: TestClient, settings: Settings
) -> None:
    """Cleanup must work precisely when the source row is gone."""
    created = make(client)
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})

    source = sqlite3.connect(settings.db_path)
    try:
        source.execute("DELETE FROM jobs WHERE id = 1")
        source.commit()
    finally:
        source.close()

    assert client.delete(f"/watchlists/{created['id']}/jobs/1").status_code == 204


# --------------------------------------------------------------------------
# The read database stays read-only
# --------------------------------------------------------------------------


def test_the_write_path_never_touches_jobs_db(
    client: TestClient, settings: Settings
) -> None:
    """The Phase 4 rule, asserted rather than trusted: writes go elsewhere."""
    before = settings.db_path.read_bytes()

    created = make(client, "Backend roles", description="EU only")
    client.post(f"/watchlists/{created['id']}/jobs", json={"job_id": 1})
    client.patch(f"/watchlists/{created['id']}", json={"name": "Renamed"})
    client.delete(f"/watchlists/{created['id']}")

    assert settings.db_path.read_bytes() == before


def test_the_two_databases_are_different_files(settings: Settings) -> None:
    assert settings.app_db_path != settings.db_path


# --------------------------------------------------------------------------
# The optional API key
# --------------------------------------------------------------------------


def test_writes_are_open_when_no_key_is_configured(client: TestClient) -> None:
    assert client.post("/watchlists", json={"name": "Open"}).status_code == 201


@pytest.fixture
def keyed_client(settings: Settings):
    with TestClient(create_app(settings.model_copy(update={"api_key": "s3cret"}))) as c:
        yield c


def test_a_configured_key_is_required(keyed_client: TestClient) -> None:
    response = keyed_client.post("/watchlists", json={"name": "Guarded"})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["WWW-Authenticate"].startswith("ApiKey")


def test_a_wrong_key_is_also_401_not_403(keyed_client: TestClient) -> None:
    """403 would imply an identity to forbid. There are no users here."""
    response = keyed_client.post(
        "/watchlists", json={"name": "Guarded"}, headers={"X-API-Key": "wrong"}
    )

    assert response.status_code == 401


def test_the_right_key_is_accepted(keyed_client: TestClient) -> None:
    response = keyed_client.post(
        "/watchlists", json={"name": "Guarded"}, headers={"X-API-Key": "s3cret"}
    )

    assert response.status_code == 201


def test_the_key_does_not_guard_the_public_dataset(keyed_client: TestClient) -> None:
    """Build 2's data stays readable; only user-created content is gated."""
    assert keyed_client.get("/jobs").status_code == 200
    assert keyed_client.get("/health").status_code == 200
