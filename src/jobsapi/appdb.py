"""The database this service *owns*, and writes to.

Two databases, deliberately. `db.py` opens Build 2's `jobs.db` read-only and
this service will never write to it — that rule predates Phase 4 and survives it.
Everything created here lives in a *separate* file with its own schema, so the
write path cannot reach the read path even by mistake. The guarantee is
structural: they are different files opened by different functions with
different modes.

Note the inversions from `db.py`, each of which has a reason:

* **read-write**, and the URI carries no `mode=ro`;
* **WAL** journal mode, which Phase 0 explicitly *declined* for `jobs.db`;
* **`PRAGMA foreign_keys = ON`**, which SQLite leaves off by default;
* **the schema is created here**, because this service owns it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from jobsapi.config import Settings

# This service owns this schema, so unlike `jobs.db` it carries a version. It is
# not a migration system — there is exactly one version and `CREATE TABLE IF NOT
# EXISTS` is idempotent. It exists so that a future change has something to
# compare against, which is precisely what Build 2's schema lacks (its
# `user_version` is 0, which is why `db.verify_schema` has to check columns).
APP_SCHEMA_VERSION = 1

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlists (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    job_id       INTEGER NOT NULL,
    note         TEXT,
    added_at     TEXT    NOT NULL,
    PRIMARY KEY (watchlist_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_items_job ON watchlist_items(job_id);
"""

# `watchlist_items.job_id` has NO foreign key, and cannot have one: the row it
# refers to lives in a different database file. SQLite constraints do not span
# databases, so referential integrity here is *not* something the engine can
# enforce. It is checked at write time against the read-only connection instead,
# which means it is a check at one moment rather than an invariant — a job can
# be removed from `jobs.db` later and leave an item pointing at nothing. The API
# reports such items rather than hiding them; see `docs/api.md`.


def connect(settings: Settings) -> sqlite3.Connection:
    """Open the read-write application database, creating the file if absent.

    A plain path rather than a `mode=ro` URI — the opposite of `db.connect`, and
    the asymmetry is the point. Creating the file on first use is correct here
    for the same reason it would be a bug there: this service owns this file, so
    an absent one means "not yet", whereas an absent `jobs.db` means the
    configuration is wrong.
    """
    settings.app_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.app_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # SQLite ships with foreign keys OFF for backwards compatibility, per
    # connection. Without this line the ON DELETE CASCADE below is decorative:
    # deleting a watchlist would silently orphan its items rather than remove
    # them, and no error would appear anywhere.
    conn.execute("PRAGMA foreign_keys = ON")

    # WAL here, though Phase 0 declined it for jobs.db. The objection there was
    # that a WAL *reader* must create a `-shm` file, which a read-only bind
    # mount forbids. This database is on a writable volume and this process is
    # the writer, so that objection does not apply — and WAL buys what it always
    # buys: readers do not block the writer and the writer does not block
    # readers. The same setting is right in one place and wrong in the other,
    # which is why "use WAL" is not advice.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {int(settings.busy_timeout_ms)}")

    # NORMAL rather than the FULL default: with WAL it fsyncs at checkpoints
    # rather than every commit. The failure it admits is losing the most recent
    # transactions on power loss — acceptable for user-created watchlists, and
    # it would not be for anything that had to be durable on acknowledgement.
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def ensure_schema(settings: Settings) -> None:
    """Create the application schema if it is not already there.

    Called from the lifespan, so the first request never races the first write.
    `CREATE TABLE IF NOT EXISTS` makes this idempotent; it is emphatically not a
    migration framework, and adding a column later will need one or a documented
    manual step. Recorded as a known limit rather than pretended away.
    """
    conn = connect(settings)
    try:
        conn.executescript(APP_SCHEMA)
        conn.execute(f"PRAGMA user_version = {APP_SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()


def get_app_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Per-request connection to the application database.

    Same generator-dependency shape as `db.get_conn`, and for the same reasons:
    the teardown runs even when the endpoint raised, and a shared connection
    would serialise every request behind one lock and leak transaction state.

    It does *not* commit on the way out. A dependency that committed would turn
    a half-finished handler into a half-written database — the commit belongs
    with the operation that knows it finished.
    """
    settings: Settings = request.app.state.settings
    conn = connect(settings)
    try:
        yield conn
    finally:
        conn.close()
