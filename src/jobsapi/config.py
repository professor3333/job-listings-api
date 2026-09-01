"""Settings, read from the environment with a `JOBSAPI_` prefix."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for one running instance.

    The database path is a *path, not a policy*. Decision 1 in docs/design.md
    chose "open the source database read-only"; it did not choose *which* file.
    Pointing this at a snapshot instead of the live scraper database is therefore
    a deployment choice made at runtime, and no code branches on it.
    """

    model_config = SettingsConfigDict(env_prefix="JOBSAPI_", extra="ignore")

    db_path: Path = Path.home() / "code" / "job-listing-scraper" / "data" / "jobs.db"

    # How long SQLite waits on a lock before giving up. The scraper takes an
    # EXCLUSIVE lock only for the duration of a commit, so a few hundred ms
    # would do; 5s is slack for a slow disk. Exceeding it raises SQLITE_BUSY,
    # which is transient and becomes a 503 -- never a hang.
    busy_timeout_ms: int = Field(default=5_000, ge=0)

    # There is deliberately no `max_page_size` setting. The 1..100 bound on
    # `limit` is part of the *published contract*: it is compiled into
    # `Pagination` as a Field constraint, so `/openapi.json` states it and a
    # generated client enforces it. An env var could set a deployment's real
    # bound to something the schema does not say, which would make the docs
    # lie — and "the docs are generated from the types" is the property this
    # build is built on. The bound lives in `schemas.py` as a constant.

    log_level: str = "INFO"

    # Page cache for one connection, in KiB when negative (SQLite's convention:
    # a negative value means KiB, a positive one means pages). 8 MiB is generous
    # for a 58 MB database and costs nothing when unused.
    cache_size_kib: int = Field(default=-8_000)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings, read from the environment once.

    Cached because reading the environment on every request is wasted work and
    would let configuration change under a running process. Tests do not call
    this -- they construct `Settings` directly and hand it to `create_app`.
    """
    return Settings()
