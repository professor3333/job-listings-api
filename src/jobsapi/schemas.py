"""The public contract: what a request may contain, and what a response returns.

Three shapes on purpose. `Pagination` is the *input* model. `JobSummary` is the
list *output*. `JobDetail` is the single-resource output. None of them is the
database row — the row has `content_hash` and `hash_version` in it, which are
Build 2's business and no client's.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

# Bounds live here rather than in the route signature so the contract is
# readable in one file. `le=100` is a real refusal, not a clamp: asking for 500
# and silently receiving 100 teaches a client that its request was honoured.
LIMIT_MIN = 1
LIMIT_MAX = 100
LIMIT_DEFAULT = 20


class Pagination(BaseModel):
    """Query parameters for any paginated list.

    A model rather than two loose arguments because Phase 3 adds ten more
    filters to this same endpoint, and because a model is where a cross-field
    validator can live. `limit=0` and `offset=-1` are 422s produced by these
    constraints, not by hand-written checks in the route.
    """

    limit: Annotated[int, Field(ge=LIMIT_MIN, le=LIMIT_MAX)] = LIMIT_DEFAULT
    offset: Annotated[int, Field(ge=0)] = 0


class JobSummary(BaseModel):
    """One job as it appears in a list.

    `description` is deliberately absent. It averages 5.7 KB and reaches 33 KB,
    so a page of 100 would be several megabytes of payload nobody asked for.
    Leaving it undeclared means it cannot leak even if a future query starts
    selecting it — the response model filters the output, so this is structural
    rather than a rule someone has to remember.
    """

    id: int
    source: str
    title: str
    company: str
    url: str

    # Every one of these is NULL somewhere in the real data, so every one is
    # optional. `remote` is the tri-state: True, False, or None meaning
    # "unknown" — 1,129 of 3,105 rows. None is not False, and conflating them
    # would invent a fact the scraper never established.
    location: str | None = None
    remote: bool | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    seniority: str | None = None
    posted_at: date | None = None


class JobDetail(JobSummary):
    """One job, in full. The only place `description` is served."""

    source_id: str
    salary_raw: str | None = None
    description: str | None = None
    first_seen: datetime
    last_seen: datetime


class JobPage(BaseModel):
    """A page of jobs, with the numbers needed to request the next one.

    An envelope rather than a bare `[...]` array. A bare array has nowhere to
    put `total`, so a client cannot render "page 2 of 9" or know it has reached
    the end without requesting an empty page. It is also unextendable: adding a
    field later would change the response's *type*, breaking every client, while
    adding a key to an object does not.
    """

    items: list[JobSummary]
    total: int
    limit: int
    offset: int
