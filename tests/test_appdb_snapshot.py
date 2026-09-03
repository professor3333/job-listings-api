"""The application database's read snapshot — the same guarantee, a different shape.

`db.read_snapshot` and `appdb.read_snapshot` solve one problem and are
deliberately not one function. The difference is that this connection can write,
which changes what is safe to do when the block fails.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from jobsapi import appdb, watchlist_repository
from jobsapi.appdb import read_snapshot
from jobsapi.config import Settings
from jobsapi.errors import WatchlistNotFound

NOW = "2026-09-03T00:00:00Z"


@pytest.fixture
def app_conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    appdb.ensure_schema(settings)
    conn = appdb.connect(settings)
    try:
        yield conn
    finally:
        conn.close()


class TestReadSnapshot:
    def test_both_reads_see_one_transaction(
        self, app_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[bool] = []
        real = watchlist_repository.count_watchlists

        def spy(conn: sqlite3.Connection) -> int:
            seen.append(conn.in_transaction)
            return real(conn)

        monkeypatch.setattr(watchlist_repository, "count_watchlists", spy)
        watchlist_repository.watchlists_page(app_conn, limit=20, offset=0)
        assert seen == [True]

    def test_the_page_is_read_before_the_count(
        self, app_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        real_list = watchlist_repository.list_watchlists
        real_count = watchlist_repository.count_watchlists

        def list_spy(conn: sqlite3.Connection, **kw):  # type: ignore[no-untyped-def]
            calls.append("page")
            return real_list(conn, **kw)

        def count_spy(conn: sqlite3.Connection) -> int:
            calls.append("count")
            return real_count(conn)

        monkeypatch.setattr(watchlist_repository, "list_watchlists", list_spy)
        monkeypatch.setattr(watchlist_repository, "count_watchlists", count_spy)
        watchlist_repository.watchlists_page(app_conn, limit=20, offset=0)
        assert calls == ["page", "count"]

    def test_the_transaction_is_released(self, app_conn: sqlite3.Connection) -> None:
        watchlist_repository.watchlists_page(app_conn, limit=20, offset=0)
        assert app_conn.in_transaction is False

    def test_the_404_gate_is_inside_the_snapshot(
        self, app_conn: sqlite3.Connection
    ) -> None:
        """And the transaction is released on that path too."""
        with pytest.raises(WatchlistNotFound):
            watchlist_repository.items_page(app_conn, 999_999, limit=20, offset=0)
        assert app_conn.in_transaction is False

    def test_a_failed_block_rolls_back_rather_than_commits(
        self, app_conn: sqlite3.Connection
    ) -> None:
        """The difference from `db.read_snapshot`, and the reason it is not shared.

        That one ends its transaction unconditionally and suppresses failures,
        which is safe only because the connection cannot write. Here a write
        inside a failing block must be discarded, never committed: committing a
        half-finished change is the failure mode a read-only connection cannot
        have.
        """
        with pytest.raises(RuntimeError), read_snapshot(app_conn):
            app_conn.execute(
                "INSERT INTO watchlists (name, created_at, updated_at) "
                "VALUES (?, ?, ?)",
                ("should not survive", NOW, NOW),
            )
            raise RuntimeError("boom")

        assert app_conn.in_transaction is False
        remaining = app_conn.execute(
            "SELECT COUNT(*) FROM watchlists WHERE name = ?", ("should not survive",)
        ).fetchone()[0]
        assert remaining == 0

    def test_a_successful_block_is_committed(
        self, app_conn: sqlite3.Connection
    ) -> None:
        """The success path ends with END, so anything inside it persists."""
        with read_snapshot(app_conn):
            app_conn.execute(
                "INSERT INTO watchlists (name, created_at, updated_at) "
                "VALUES (?, ?, ?)",
                ("survives", NOW, NOW),
            )
        assert app_conn.in_transaction is False
        kept = app_conn.execute(
            "SELECT COUNT(*) FROM watchlists WHERE name = ?", ("survives",)
        ).fetchone()[0]
        assert kept == 1


class TestTheWritePathIsUndisturbed:
    """Reads now open explicit transactions; writes still use the implicit one."""

    def test_a_write_after_a_read_still_works(self, client: TestClient) -> None:
        assert client.get("/watchlists").status_code == 200
        created = client.post("/watchlists", json={"name": "after a read"})
        assert created.status_code == 201, created.text
        assert client.get("/watchlists").json()["total"] == 1

    def test_the_full_cycle_still_works(self, client: TestClient) -> None:
        made = client.post("/watchlists", json={"name": "cycle"}).json()
        wid = made["id"]
        assert (
            client.post(f"/watchlists/{wid}/jobs", json={"job_id": 1}).status_code
            == 201
        )
        listed = client.get(f"/watchlists/{wid}/jobs").json()
        assert listed["total"] == 1
        assert client.delete(f"/watchlists/{wid}").status_code == 204
        assert client.get(f"/watchlists/{wid}/jobs").status_code == 404
