"""Consistency between the two halves of a paginated answer.

`total` and `items` are supposed to answer the same question. Read outside a
shared snapshot they can answer two, and the dangerous direction is silent: a
`total` that is too low makes a client stop paginating early and lose rows with
no error, no empty page, and nothing to notice.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from jobsapi import repository
from jobsapi.config import Settings
from jobsapi.db import connect, read_snapshot
from jobsapi.errors import JobNotFound
from jobsapi.repository import _SORT_COLUMNS
from jobsapi.schemas import JobFilters, SortField


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = connect(settings)
    try:
        yield connection
    finally:
        connection.close()


class TestReadSnapshot:
    def test_both_queries_see_one_transaction(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The count must not be a second, independent read transaction."""
        seen: list[bool] = []
        real = repository.count_jobs

        def spy(c: sqlite3.Connection, filters: JobFilters) -> int:
            seen.append(c.in_transaction)
            return real(c, filters)

        monkeypatch.setattr(repository, "count_jobs", spy)
        repository.jobs_page(conn, JobFilters())
        assert seen == [True]

    def test_the_page_is_read_before_the_count(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Order is load-bearing if the snapshot is ever removed.

        Page first means a residual skew makes `total` too high — a phantom
        empty page, which is visible — rather than too low, which loses rows in
        silence.
        """
        calls: list[str] = []
        real_list, real_count = repository.list_jobs, repository.count_jobs

        def list_spy(c: sqlite3.Connection, filters: JobFilters):  # type: ignore[no-untyped-def]
            calls.append("page")
            return real_list(c, filters)

        def count_spy(c: sqlite3.Connection, filters: JobFilters) -> int:
            calls.append("count")
            return real_count(c, filters)

        monkeypatch.setattr(repository, "list_jobs", list_spy)
        monkeypatch.setattr(repository, "count_jobs", count_spy)
        repository.jobs_page(conn, JobFilters())
        assert calls == ["page", "count"]

    def test_the_transaction_is_released(self, conn: sqlite3.Connection) -> None:
        repository.jobs_page(conn, JobFilters())
        assert conn.in_transaction is False

    def test_the_transaction_is_released_when_the_body_raises(
        self, conn: sqlite3.Connection
    ) -> None:
        """A 404 raised inside the snapshot must not leak a held SHARED lock."""
        with pytest.raises(JobNotFound):
            repository.job_changes_page(conn, 999_999, limit=20, offset=0)
        assert conn.in_transaction is False

    def test_a_deferred_begin_is_legal_on_a_read_only_connection(
        self, conn: sqlite3.Connection
    ) -> None:
        """`BEGIN IMMEDIATE` would not be — it asks for a write lock.

        This is the reason the snapshot is deferred rather than immediate, and
        it is a property of the connection (`mode=ro` + `query_only`), not a
        style choice.
        """
        with read_snapshot(conn):
            assert conn.in_transaction is True
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("BEGIN IMMEDIATE")

    def test_stats_reads_one_snapshot(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Six statements, four of them independent counts."""
        seen: list[bool] = []
        real = repository.count_runs

        def spy(c: sqlite3.Connection) -> int:
            seen.append(c.in_transaction)
            return real(c)

        monkeypatch.setattr(repository, "count_runs", spy)
        repository.stats(conn)
        assert seen == [True]

    def test_the_endpoints_still_answer(self, client: TestClient) -> None:
        """The snapshot is invisible from outside — same bodies as before."""
        for path in ("/jobs", "/runs", "/stats", "/jobs/1/changes"):
            assert client.get(path).status_code == 200
        assert client.get("/jobs/999999/changes").status_code == 404


class TestSortAllowlistIsComplete:
    """The map's completeness is the property the indirection is paid for.

    A `SortField` member added without a `_SORT_COLUMNS` entry passes validation
    and then raises `KeyError` on a live request — a 500, which the hardening
    table forbids. That must fail in the suite instead.
    """

    def test_every_member_has_a_column(self) -> None:
        assert set(_SORT_COLUMNS) == set(SortField)

    @pytest.mark.parametrize("member", list(SortField))
    def test_every_member_actually_sorts(
        self, client: TestClient, member: SortField
    ) -> None:
        response = client.get("/jobs", params={"sort": member.value})
        assert response.status_code == 200, response.text
