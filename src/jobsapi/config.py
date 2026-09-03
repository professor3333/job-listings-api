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

    # The database this service OWNS and writes to (Phase 4). A separate file
    # from `db_path`, which is never written: the write path cannot reach the
    # read path because they are different files. Defaults under the user's data
    # directory rather than the working directory, so the location does not
    # depend on where the process was started. The container overrides it to a
    # writable volume — `/data` there is mounted read-only.
    app_db_path: Path = Path.home() / ".local" / "share" / "jobsapi" / "app.db"

    # Optional shared secret for the write endpoints. Unset (the default) leaves
    # them open, which is right for a service that runs on localhost and holds
    # nothing sensitive. Set it and every mutating request must carry
    # `X-API-Key`. This is the ceiling for this build: no users, no login, no
    # JWT — one key, checked in one dependency.
    api_key: str | None = None

    # Page cache for one connection, in KiB when negative (SQLite's convention:
    # a negative value means KiB, a positive one means pages). 8 MiB is generous
    # for a 58 MB database and costs nothing when unused.
    # Bounded, because safety and sensibility are separate obligations: any
    # Python int is grammatically safe to format into a PRAGMA, and most are
    # operationally absurd. SQLite spells "this many KiB" as a *negative*
    # cache_size and "this many pages" as a positive one — so `le=-1` is the
    # field's own name enforced. A positive value here would silently mean
    # pages, contradicting the `_kib` suffix. The floor caps the cache at 1 GiB.
    cache_size_kib: int = Field(default=-8_000, ge=-1_048_576, le=-1)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings, read from the environment once.

    Cached because reading the environment on every request is wasted work and
    would let configuration change under a running process. Tests do not call
    this -- they construct `Settings` directly and hand it to `create_app`.
    """
    return Settings()
