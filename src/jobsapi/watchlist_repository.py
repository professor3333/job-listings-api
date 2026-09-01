"""All the SQL for the application-owned database. Knows nothing about HTTP.

Same boundary as `repository.py`, and the same rules: values are bound
parameters, identifiers are literals from this file, and nothing here raises an
`HTTPException`. The difference is that these functions *write*, which
introduces two concerns the read path never had — when to commit, and what to do
when a constraint refuses.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from jobsapi.errors import (
    DuplicateResource,
    WatchlistItemNotFound,
    WatchlistNotFound,
)

_COLUMNS = "id, name, description, created_at, updated_at"

# Every watchlist row is returned with a live count of its items rather than a
# stored counter. A denormalised `item_count` column would need updating on
# every insert and delete, and would be wrong the first time one of those paths
# forgot. The subquery costs a cheap index lookup against idx_items_job's table.
_SELECT = f"""
    SELECT {_COLUMNS},
           (SELECT COUNT(*) FROM watchlist_items i WHERE i.watchlist_id = w.id)
               AS item_count
    FROM watchlists w
"""


def _now() -> str:
    """A single UTC timestamp format, written once.

    `datetime.now(UTC)` rather than `utcnow()`, which returns a naive datetime
    that lies about its zone and is deprecated for exactly that reason.
    """
    return datetime.now(UTC).isoformat()


def create_watchlist(
    conn: sqlite3.Connection, *, name: str, description: str | None
) -> sqlite3.Row:
    """Insert a watchlist and return it, or raise `DuplicateResource`.

    The duplicate check is the UNIQUE constraint, not a SELECT first. Checking
    then inserting is a time-of-check-to-time-of-use race — two concurrent
    requests can both find nothing and both insert — and the database is the
    only participant that can actually serialise the decision. So the insert is
    attempted and `IntegrityError` is translated.

    `RETURNING` gives the inserted row without a second query and without
    `lastrowid`, so there is no window in which another writer could confuse the
    two.
    """
    now = _now()
    try:
        row = conn.execute(
            f"""
            INSERT INTO watchlists (name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            RETURNING {_COLUMNS}, 0 AS item_count
            """,
            (name, description, now, now),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        # Narrow: only the name's UNIQUE constraint should become a 409. Any
        # other integrity failure is a bug in this module and must not be
        # disguised as a client error.
        if "watchlists.name" in str(exc):
            raise DuplicateResource(
                f"A watchlist named {name!r} already exists."
            ) from exc
        raise
    conn.commit()
    return row


def get_watchlist(conn: sqlite3.Connection, watchlist_id: int) -> sqlite3.Row:
    row = conn.execute(f"{_SELECT} WHERE w.id = ?", (watchlist_id,)).fetchone()
    if row is None:
        raise WatchlistNotFound(watchlist_id)
    return row


def count_watchlists(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0])


def list_watchlists(
    conn: sqlite3.Connection, *, limit: int, offset: int
) -> list[sqlite3.Row]:
    """Newest first, with the same `, id` tie-break as every other listing.

    `created_at` is an ISO string with microseconds so ties are unlikely — but
    "unlikely" is not "impossible", and two watchlists created in the same
    microsecond would page unstably. The tie-break costs nothing.
    """
    return conn.execute(
        f"{_SELECT} ORDER BY w.created_at DESC, w.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()


def replace_watchlist(
    conn: sqlite3.Connection, watchlist_id: int, *, name: str, description: str | None
) -> sqlite3.Row:
    """PUT: every column the client owns is overwritten, including with NULL.

    That is what makes this a replacement rather than an update. `description`
    is set to whatever the body said — and an absent `description` in a PUT body
    means "this resource has none", so it is written as NULL.
    """
    try:
        row = conn.execute(
            f"""
            UPDATE watchlists
               SET name = ?, description = ?, updated_at = ?
             WHERE id = ?
            RETURNING {_COLUMNS}
            """,
            (name, description, _now(), watchlist_id),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        if "watchlists.name" in str(exc):
            raise DuplicateResource(
                f"A watchlist named {name!r} already exists."
            ) from exc
        raise
    if row is None:
        raise WatchlistNotFound(watchlist_id)
    conn.commit()
    return get_watchlist(conn, watchlist_id)


def update_watchlist(
    conn: sqlite3.Connection, watchlist_id: int, changes: dict[str, object]
) -> sqlite3.Row:
    """PATCH: write only the columns the client actually sent.

    `changes` comes from `model_dump(exclude_unset=True)`, so a key is present
    only if the client named it. That is what lets `{"description": null}` clear
    the field while `{}` — already rejected as a 422 — would have changed
    nothing. The SET clause is built from an allowlist of column names, the same
    pattern as `ORDER BY`: the *values* are bound, the *identifiers* are chosen.
    """
    allowed = {"name", "description"}
    unknown = set(changes) - allowed
    if unknown:  # pragma: no cover - the request model already forbids extras
        raise ValueError(f"Not updatable: {', '.join(sorted(unknown))}")

    assignments = ", ".join(f"{column} = ?" for column in changes)
    params = [*changes.values(), _now(), watchlist_id]
    try:
        cursor = conn.execute(
            f"UPDATE watchlists SET {assignments}, updated_at = ? WHERE id = ?",
            params,
        )
    except sqlite3.IntegrityError as exc:
        if "watchlists.name" in str(exc):
            raise DuplicateResource(
                f"A watchlist named {changes.get('name')!r} already exists."
            ) from exc
        raise
    if cursor.rowcount == 0:
        raise WatchlistNotFound(watchlist_id)
    conn.commit()
    return get_watchlist(conn, watchlist_id)


def delete_watchlist(conn: sqlite3.Connection, watchlist_id: int) -> None:
    """Remove a watchlist. Its items go with it, via ON DELETE CASCADE.

    The cascade only happens because `PRAGMA foreign_keys = ON` is set on every
    connection in `appdb.connect`. Without it SQLite parses the clause, ignores
    it, and leaves orphaned rows behind with no error — which is why that PRAGMA
    is load-bearing rather than tidiness.
    """
    cursor = conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
    if cursor.rowcount == 0:
        raise WatchlistNotFound(watchlist_id)
    conn.commit()


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def add_item(
    conn: sqlite3.Connection, watchlist_id: int, *, job_id: int, note: str | None
) -> sqlite3.Row:
    """Put a job on a watchlist. The composite primary key rejects duplicates.

    Note what is *not* here: any check that `job_id` exists. It cannot be a
    foreign key, because that row lives in the other database — so the caller
    validates it against the read-only connection before calling this. The
    separation is deliberate: this module owns one database and does not reach
    into another.
    """
    try:
        row = conn.execute(
            """
            INSERT INTO watchlist_items (watchlist_id, job_id, note, added_at)
            VALUES (?, ?, ?, ?)
            RETURNING job_id, note, added_at
            """,
            (watchlist_id, job_id, note, _now()),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if "FOREIGN KEY" in message:
            # The watchlist itself is gone — a 404, not a 409.
            raise WatchlistNotFound(watchlist_id) from exc
        if "watchlist_items" in message:
            raise DuplicateResource(
                f"Job {job_id} is already on watchlist {watchlist_id}."
            ) from exc
        raise
    conn.commit()
    return row


def remove_item(conn: sqlite3.Connection, watchlist_id: int, job_id: int) -> None:
    cursor = conn.execute(
        "DELETE FROM watchlist_items WHERE watchlist_id = ? AND job_id = ?",
        (watchlist_id, job_id),
    )
    if cursor.rowcount == 0:
        raise WatchlistItemNotFound(watchlist_id, job_id)
    conn.commit()


def count_items(conn: sqlite3.Connection, watchlist_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM watchlist_items WHERE watchlist_id = ?",
            (watchlist_id,),
        ).fetchone()[0]
    )


def list_items(
    conn: sqlite3.Connection, watchlist_id: int, *, limit: int, offset: int
) -> list[sqlite3.Row]:
    """The saved rows, newest first — job details are joined in by the caller.

    There is no JOIN to `jobs` available here: the two tables are in different
    database files opened on different connections, and SQLite cannot join
    across them without ATTACH. Attaching Build 2's database to this read-write
    connection would put a writable handle on a file this service promises never
    to write, so the join happens in Python instead — two queries and a dict.
    """
    return conn.execute(
        """
        SELECT job_id, note, added_at
        FROM watchlist_items
        WHERE watchlist_id = ?
        ORDER BY added_at DESC, job_id DESC
        LIMIT ? OFFSET ?
        """,
        (watchlist_id, limit, offset),
    ).fetchall()
