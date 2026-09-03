"""Watchlist endpoints — the write path. No SQL here, same as every router.

This is where Phase 4's HTTP semantics live: `201` with a `Location`, `409` from
a uniqueness constraint, `204` with no body, and the difference between `PUT`
and `PATCH`.

Two connections are in play. `app_conn` is the read-write database this service
owns; `conn` is Build 2's read-only `jobs.db`, used only to check that a job id
exists and to decorate saved items with job details. A route that needs both
asks for both — the dependency system is what makes that a signature rather than
a global.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from jobsapi import repository, watchlist_repository
from jobsapi.appdb import get_app_conn
from jobsapi.db import get_conn
from jobsapi.schemas import (
    Pagination,
    Watchlist,
    WatchlistCreate,
    WatchlistEntry,
    WatchlistEntryPage,
    WatchlistItemCreate,
    WatchlistPage,
    WatchlistPatch,
    WatchlistReplace,
)
from jobsapi.security import RequireApiKey

# The key dependency is attached to the whole router rather than repeated on
# each mutating route, so a route added later cannot forget it. It is a no-op
# unless `JOBSAPI_API_KEY` is configured.
#
# It therefore also guards the GET routes here. That is the deliberate choice:
# a watchlist is user-created content, and if the key is set at all then reading
# what someone saved should need it as much as writing it. The read endpoints
# over Build 2's public dataset stay open either way.
router = APIRouter(
    prefix="/watchlists", tags=["watchlists"], dependencies=[RequireApiKey]
)


@router.post(
    "",
    response_model=Watchlist,
    status_code=status.HTTP_201_CREATED,
    summary="Create a watchlist",
    responses={409: {"description": "A watchlist with that name already exists."}},
)
def create_watchlist(
    body: WatchlistCreate,
    response: Response,
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Watchlist:
    """`201 Created`, with a `Location` header naming the new resource.

    A body parameter is declared simply by annotating it with a Pydantic model —
    FastAPI distinguishes it from a query parameter by the type, not by a
    decorator. `POST` is not idempotent, which is exactly why the id is assigned
    by the server: two identical POSTs are two distinct requests, and here the
    second is refused by the name's UNIQUE constraint rather than silently
    creating a twin.

    `Location` is the part most often skipped. Without it a client has to parse
    the body to discover where the thing it just created lives, which only works
    while the URL is derivable from a field — and stops working the moment it
    is not.
    """
    row = watchlist_repository.create_watchlist(
        app_conn, name=body.name, description=body.description
    )
    result = Watchlist.model_validate(dict(row))
    response.headers["Location"] = f"/watchlists/{result.id}"
    return result


@router.get("", response_model=WatchlistPage, summary="List watchlists")
def list_watchlists(
    pagination: Annotated[Pagination, Query()],
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> WatchlistPage:
    """Same envelope and the same `Pagination` model as every other listing."""
    rows, total = watchlist_repository.watchlists_page(
        app_conn, limit=pagination.limit, offset=pagination.offset
    )
    return WatchlistPage(
        items=[dict(row) for row in rows],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{watchlist_id}", response_model=Watchlist, summary="Get one watchlist")
def get_watchlist(
    watchlist_id: Annotated[int, Path(ge=1)],
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Watchlist:
    return Watchlist.model_validate(
        dict(watchlist_repository.get_watchlist(app_conn, watchlist_id))
    )


@router.put(
    "/{watchlist_id}",
    response_model=Watchlist,
    summary="Replace a watchlist",
    responses={409: {"description": "Another watchlist already has that name."}},
)
def replace_watchlist(
    watchlist_id: Annotated[int, Path(ge=1)],
    body: WatchlistReplace,
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Watchlist:
    """PUT replaces the whole resource — an omitted `description` clears it.

    PUT is **idempotent**: sending the same body twice leaves the same state, so
    a client that retries after a timeout cannot do damage. That is the property
    that makes replacement worth having alongside PATCH.

    It does *not* create when the id is absent. Upsert-on-PUT is legal in HTTP
    and wrong here, because ids are assigned by the server: a client cannot know
    a valid id for a resource that does not exist, so a PUT to a missing id is a
    mistake rather than an instruction. It returns 404.
    """
    return Watchlist.model_validate(
        dict(
            watchlist_repository.replace_watchlist(
                app_conn, watchlist_id, name=body.name, description=body.description
            )
        )
    )


@router.patch(
    "/{watchlist_id}",
    response_model=Watchlist,
    summary="Update part of a watchlist",
    responses={409: {"description": "Another watchlist already has that name."}},
)
def patch_watchlist(
    watchlist_id: Annotated[int, Path(ge=1)],
    body: WatchlistPatch,
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Watchlist:
    """PATCH changes only what the body names.

    `exclude_unset=True` is the whole mechanism: it emits only keys the client
    actually sent, so `{"description": null}` clears the description while
    omitting the key leaves it alone. Without it, every unsent field would
    arrive as its default `None` and a patch of the name would silently wipe the
    description — the single most common way a PATCH endpoint is written wrong.
    """
    changes = body.model_dump(exclude_unset=True)
    return Watchlist.model_validate(
        dict(watchlist_repository.update_watchlist(app_conn, watchlist_id, changes))
    )


@router.delete(
    "/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a watchlist",
)
def delete_watchlist(
    watchlist_id: Annotated[int, Path(ge=1)],
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Response:
    """`204 No Content` — success with nothing to say.

    Returning `{"deleted": true}` with a 200 would be inventing a body to carry
    information the status code already carries. 204 means the request
    succeeded and there is deliberately no representation to send; a client must
    not look for one.

    Deleting an id that does not exist is a **404**, not a silent 204. DELETE is
    still idempotent in the sense HTTP requires — the *effect* of repeating it is
    unchanged, the resource remains absent — but the second call is telling the
    truth about what it found rather than pretending it removed something.

    `response_class=Response` because the default `JSONResponse` would write
    `null` into a body that must be empty, which some clients reject.
    """
    watchlist_repository.delete_watchlist(app_conn, watchlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Items — jobs on a watchlist
# --------------------------------------------------------------------------


@router.post(
    "/{watchlist_id}/jobs",
    status_code=status.HTTP_201_CREATED,
    response_model=WatchlistEntry,
    summary="Add a job to a watchlist",
    responses={409: {"description": "That job is already on this watchlist."}},
)
def add_job(
    watchlist_id: Annotated[int, Path(ge=1)],
    body: WatchlistItemCreate,
    response: Response,
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> WatchlistEntry:
    """Both databases in one request: validate against one, write to the other.

    `job_id` cannot be a foreign key, because the row lives in a file this
    connection cannot see. So existence is checked here against the read-only
    connection — which makes it a check at a moment in time rather than an
    invariant. The job can be removed from `jobs.db` afterwards, and the entry
    then reports `job_missing: true` instead of disappearing.

    The order matters: the job is validated *before* the insert, so a bad
    `job_id` is a 404 about the job rather than a row written and rolled back.
    """
    job = repository.get_job(conn, body.job_id)  # raises JobNotFound -> 404
    watchlist_repository.get_watchlist(app_conn, watchlist_id)  # -> 404

    row = watchlist_repository.add_item(
        app_conn, watchlist_id, job_id=body.job_id, note=body.note
    )
    response.headers["Location"] = f"/watchlists/{watchlist_id}/jobs/{body.job_id}"
    return WatchlistEntry(
        job_id=row["job_id"],
        note=row["note"],
        added_at=row["added_at"],
        job=dict(job),
    )


@router.get(
    "/{watchlist_id}/jobs",
    response_model=WatchlistEntryPage,
    summary="The jobs on a watchlist",
)
def list_jobs(
    watchlist_id: Annotated[int, Path(ge=1)],
    pagination: Annotated[Pagination, Query()],
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> WatchlistEntryPage:
    """A join done in Python, because it cannot be done in SQL.

    The saved rows and the job details are in different database files, so there
    is no single connection that can see both — the alternative would be
    ATTACHing Build 2's database to this read-write connection, which would put
    a writable handle on the file this service promises never to write.

    Two queries and a dict lookup instead: one page of items, then one batched
    `WHERE id IN (...)` for their jobs. Not one query per row.
    """
    rows, total = watchlist_repository.items_page(
        app_conn, watchlist_id, limit=pagination.limit, offset=pagination.offset
    )
    jobs = repository.get_jobs_by_ids(conn, [int(row["job_id"]) for row in rows])

    items = []
    for row in rows:
        job = jobs.get(int(row["job_id"]))
        items.append(
            WatchlistEntry(
                job_id=row["job_id"],
                note=row["note"],
                added_at=row["added_at"],
                job=dict(job) if job is not None else None,
                job_missing=job is None,
            )
        )

    return WatchlistEntryPage(
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.delete(
    "/{watchlist_id}/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove a job from a watchlist",
)
def remove_job(
    watchlist_id: Annotated[int, Path(ge=1)],
    job_id: Annotated[int, Path(ge=1)],
    app_conn: Annotated[sqlite3.Connection, Depends(get_app_conn)],
) -> Response:
    """204, and a 404 when the job was not on the list.

    Deliberately does *not* consult `jobs.db`. Removing a saved entry must keep
    working for a job that has since been deleted from the source — otherwise
    the one case where a client most needs to clean up is the case that fails.
    """
    watchlist_repository.get_watchlist(app_conn, watchlist_id)
    watchlist_repository.remove_item(app_conn, watchlist_id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
