"""Connection guarantees: read-only, loud at startup, and usable without an app."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobsapi import repository
from jobsapi.config import Settings
from jobsapi.db import check_database, classify, connect
from jobsapi.errors import (
    DatabaseUnavailable,
    DatabaseWedged,
    JobNotFound,
    SchemaContractError,
)
from jobsapi.main import create_app


class TestReadOnly:
    """ "The service never writes to jobs.db" — enforced, not intended."""

    def test_writes_are_refused_by_sqlite_itself(self, settings: Settings) -> None:
        conn = connect(settings)
        try:
            with pytest.raises(sqlite3.OperationalError) as caught:
                conn.execute("DELETE FROM jobs")
            assert caught.value.sqlite_errorname == "SQLITE_READONLY"
        finally:
            conn.close()

    def test_a_missing_file_is_not_silently_created(self, tmp_path: Path) -> None:
        """The failure mode a plain sqlite3.connect(path) would hide.

        Without `mode=ro`, a wrong path creates an empty database and the API
        cheerfully serves zero jobs forever.
        """
        missing = tmp_path / "nope.db"
        with pytest.raises(sqlite3.OperationalError):
            connect(Settings(db_path=missing))
        assert not missing.exists()


class TestStartupChecks:
    def test_missing_database_fails_loudly_at_startup(self, tmp_path: Path) -> None:
        """Not a 500 on the first unlucky request."""
        with pytest.raises(SchemaContractError, match="not found"):
            check_database(Settings(db_path=tmp_path / "absent.db"))

    def test_schema_drift_is_caught_by_name(
        self, tmp_path: Path, schema_sql: str
    ) -> None:
        """`user_version` is 0 in the source database, so columns are the only check."""
        path = tmp_path / "drifted.db"
        conn = sqlite3.connect(path)
        conn.executescript(schema_sql.replace("seniority    TEXT", "grade        TEXT"))
        conn.close()

        with pytest.raises(SchemaContractError, match="seniority"):
            check_database(Settings(db_path=path))

    def test_app_refuses_to_start_against_a_bad_database(self, tmp_path: Path) -> None:
        app = create_app(Settings(db_path=tmp_path / "absent.db"))
        with pytest.raises(SchemaContractError), TestClient(app):
            pass


class TestErrorClassification:
    """Branch on the error code, never on the message text."""

    @pytest.mark.parametrize(
        ("errorname", "expected"),
        [
            ("SQLITE_BUSY", DatabaseUnavailable),
            ("SQLITE_BUSY_SNAPSHOT", DatabaseUnavailable),
            ("SQLITE_READONLY_ROLLBACK", DatabaseWedged),
        ],
    )
    def test_known_conditions_map_to_domain_errors(
        self, errorname: str, expected: type
    ) -> None:
        exc = sqlite3.OperationalError("some message")
        exc.sqlite_errorname = errorname
        assert isinstance(classify(exc), expected)

    def test_unknown_conditions_are_not_disguised(self) -> None:
        """Returning None keeps an unrecognised fault a 500 instead of a fake 503."""
        exc = sqlite3.OperationalError("no such table: jobs")
        exc.sqlite_errorname = "SQLITE_ERROR"
        assert classify(exc) is None


class TestRepositoryBoundary:
    """The repository runs without an app — that is the point of the boundary."""

    def test_queries_need_no_http(self, settings: Settings) -> None:
        conn = connect(settings)
        try:
            assert repository.count_jobs(conn) == 5
            assert len(repository.list_jobs(conn, limit=2, offset=0)) == 2
            assert repository.get_job(conn, 1)["title"] == "Senior Python Engineer"
        finally:
            conn.close()

    def test_missing_row_raises_a_domain_error_not_an_http_one(
        self, settings: Settings
    ) -> None:
        conn = connect(settings)
        try:
            with pytest.raises(JobNotFound) as caught:
                repository.get_job(conn, 999_999)
            assert caught.value.job_id == 999_999
        finally:
            conn.close()
