"""The public contract: what a request may contain, and what a response returns.

Three shapes on purpose. `JobFilters` is the *input* model. `JobSummary` is the
list *output*. `JobDetail` is the single-resource output. None of them is the
database row — the row has `content_hash` and `hash_version` in it, which are
Build 2's business and no client's.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

# Bounds live here rather than in the route signature so the contract is
# readable in one file. `le=100` is a real refusal, not a clamp: asking for 500
# and silently receiving 100 teaches a client that its request was honoured.
LIMIT_MIN = 1
LIMIT_MAX = 100
LIMIT_DEFAULT = 20

Q_MAX_LENGTH = 200
COMPANY_MAX_LENGTH = 200


# --------------------------------------------------------------------------
# Allowlists
# --------------------------------------------------------------------------

# Built with the *functional* StrEnum API because these values contain colons,
# and `greenhouse:anthropic = "..."` in a class body does not mean what it looks
# like. Python parses it as an annotated assignment — target `greenhouse`,
# annotation `anthropic` — so under `from __future__ import annotations` it would
# silently define a member called `greenhouse`, and a second one would raise
# `TypeError: 'greenhouse' already defined`. The member name and the wire value
# differ here by necessity, not by preference.
SOURCE_VALUES = (
    "arbeitnow",
    "greenhouse:airtable",
    "greenhouse:anthropic",
    "greenhouse:discord",
    "greenhouse:duolingo",
    "greenhouse:figma",
    "greenhouse:gitlab",
    "python_org",
)

# This list is coupled to Build 2's data. If the scraper adds a source, this
# service rejects it with a 422 until the tuple above is updated — a loud,
# documented failure rather than a filter that silently matches nothing.
Source = StrEnum("Source", {v.replace(":", "_"): v for v in SOURCE_VALUES})


class Seniority(StrEnum):
    """The levels Build 2 actually assigns. NULL in ~49% of rows."""

    intern = "intern"
    junior = "junior"
    senior = "senior"
    staff = "staff"
    lead = "lead"
    principal = "principal"
    head = "head"
    director = "director"


class Remote(StrEnum):
    """Tri-state, because the underlying column is tri-state.

    `unknown` is not a synonym for `false`. 1,129 of 3,105 rows have NULL here,
    meaning the scraper never established the fact — asserting those are on-site
    would invent data. `unknown` maps to `IS NULL`, not to `= 0`.
    """

    true = "true"
    false = "false"
    unknown = "unknown"


class SortField(StrEnum):
    """The allowlist. A column name cannot be a bound parameter.

    `?sort=id;DROP TABLE jobs` is a 422 because it is not a member of this enum
    — not because anything downstream escapes it. Values are parameterised;
    identifiers are chosen from a fixed set written in our own source.
    """

    posted_at = "posted_at"
    id = "id"
    company = "company"
    title = "title"
    salary_min = "salary_min"
    salary_max = "salary_max"


class SortOrder(StrEnum):
    asc = "asc"
    desc = "desc"


def _upper(value: Any) -> Any:
    """Normalise currency before validation, so `usd` and `USD` both work."""
    return value.upper() if isinstance(value, str) else value


Currency = Annotated[
    str,
    BeforeValidator(_upper),
    Field(
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 code. Case-insensitive; matched uppercase.",
    ),
]


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class Pagination(BaseModel):
    """Paging, shared by every list endpoint.

    `extra="forbid"` lives here rather than on `JobFilters` so the rule is the
    same on every list endpoint. It was on the subclass first, which meant
    `?colour=red` was a 422 on `/jobs` and silently ignored on `/runs` — an
    inconsistency `docs/api.md` already promised did not exist. A contract
    stated once and enforced in one place cannot drift between endpoints.
    """

    model_config = ConfigDict(extra="forbid")

    limit: Annotated[int, Field(ge=LIMIT_MIN, le=LIMIT_MAX)] = LIMIT_DEFAULT
    offset: Annotated[int, Field(ge=0)] = 0


class JobFilters(Pagination):
    """Every query parameter `GET /jobs` accepts.

    `extra="forbid"` is a deliberate, documented choice: `?colour=red` is a 422
    rather than being ignored. The reasoning is that a typo — `?limt=5` — that
    silently returns unfiltered results is a worse failure than an error
    message, because the client believes it filtered. The cost is that clients
    sending unknown parameters break when they would otherwise have been
    tolerated; for a read-only service with a generated client contract, that
    trade is worth making.
    """

    model_config = ConfigDict(extra="forbid")

    q: Annotated[str | None, Field(max_length=Q_MAX_LENGTH)] = None
    source: Source | None = None
    company: Annotated[str | None, Field(max_length=COMPANY_MAX_LENGTH)] = None
    remote: Remote | None = None
    seniority: Seniority | None = None
    salary_min_gte: Annotated[int | None, Field(ge=0)] = None
    salary_max_lte: Annotated[int | None, Field(ge=0)] = None
    currency: Currency | None = None
    posted_after: date | None = None
    posted_before: date | None = None
    sort: SortField = SortField.posted_at
    order: SortOrder = SortOrder.desc

    @model_validator(mode="after")
    def _check_ranges(self) -> "JobFilters":
        """Cross-field rules — the ones no single field can catch.

        `salary_min_gte=50000&salary_max_lte=10000` is well-formed and each field
        is individually legal; only the pair is nonsense. That is precisely what
        `422 Unprocessable Content` means, so the status stays 422 and the
        *body* carries the distinction via a `CROSS_FIELD_CONFLICT` code.

        `PydanticCustomError` rather than a bare `ValueError` so the error keeps
        a machine-readable `type`, which is what the problem handler branches on.
        """
        if (
            self.salary_min_gte is not None
            and self.salary_max_lte is not None
            and self.salary_min_gte > self.salary_max_lte
        ):
            raise PydanticCustomError(
                "cross_field_conflict",
                "salary_min_gte ({lo}) must not exceed salary_max_lte ({hi}).",
                {"lo": self.salary_min_gte, "hi": self.salary_max_lte},
            )
        if (
            self.posted_after is not None
            and self.posted_before is not None
            and self.posted_after > self.posted_before
        ):
            raise PydanticCustomError(
                "cross_field_conflict",
                "posted_after ({lo}) must not be later than posted_before ({hi}).",
                {"lo": str(self.posted_after), "hi": str(self.posted_before)},
            )
        return self


# --------------------------------------------------------------------------
# Response models
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Meta / operational response models
# --------------------------------------------------------------------------

# `job_changes` stores full before/after values, and `description` diffs reach
# 30 KB each — 32.8 MB across the table. A job with six recorded changes would
# be ~180 KB of response if the values were served verbatim, so they are
# truncated and the true lengths reported alongside. This is the clearest case
# in the build of "the response model is not the database row": 30 KB on disk
# becomes 200 characters on the wire, deliberately and visibly.
CHANGE_VALUE_MAX_LENGTH = 200


class JobChange(BaseModel):
    """One recorded edit to a job, with values truncated by design."""

    observed_at: datetime
    field: str
    old_value: str | None = None
    new_value: str | None = None
    old_length: int | None = None
    new_length: int | None = None
    truncated: bool = False


class JobChangePage(BaseModel):
    items: list[JobChange]
    total: int
    limit: int
    offset: int


class RunSummary(BaseModel):
    """One scrape run.

    Deliberately carries no `duration_seconds`. Build 2 stamps `finished_at`
    from the same value as `started_at` on the success path — equal in 62 of 63
    finished runs, the exception being a `failed` run with a real 3.9s duration.
    A computed field would therefore read 0.0 for every successful run and
    plausibly non-zero for a failed one: not obviously broken, just quietly
    wrong, which is the harder kind to notice. The two timestamps are exposed
    raw so a client can see the equality itself. Filed as a Build 2 bug, not
    worked around here.
    """

    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    rows_parsed: int | None = None
    pages_fetched: int | None = None
    page_cap: int | None = None


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class SourceSummary(BaseModel):
    """A source, how many jobs it produced, and how its last run ended.

    `last_run_status` can be `running` indefinitely: a scraper that dies between
    transactions never writes `finished_at`. That is reported as-is rather than
    guessed at — this service cannot distinguish a live run from an abandoned one
    by querying, because the discriminator is a `-journal` file on disk, not a
    row.
    """

    source: str
    job_count: int
    last_run_id: int | None = None
    last_run_status: str | None = None
    last_run_started_at: datetime | None = None
    last_run_finished_at: datetime | None = None
    last_run_rows_parsed: int | None = None


class FieldCoverage(BaseModel):
    """How often a nullable field is actually populated."""

    field: str
    present: int
    missing: int
    coverage: float = Field(description="Fraction populated, 0.0 to 1.0.")


class Stats(BaseModel):
    """Dataset shape. The numbers that make the NULL decisions legible."""

    total_jobs: int
    total_runs: int
    total_changes: int
    sources: int
    coverage: list[FieldCoverage]
    remote_true: int
    remote_false: int
    remote_unknown: int
    earliest_posted_at: date | None = None
    latest_posted_at: date | None = None


class ProblemDetail(BaseModel):
    """One field-level failure inside a problem document."""

    field: str
    rule: str
    message: str


class Problem(BaseModel):
    """RFC 9457 problem details — the single error shape for every 4xx and 5xx.

    Declared as a model so it appears in `/openapi.json`. Without that, the
    generated docs would keep advertising FastAPI's `HTTPValidationError` and
    describe a body this service never sends.
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"type": "about:blank", "status": 422}}
    )

    # RFC 9457 says an absent `type`, or "about:blank", carries no semantics
    # beyond the status code. Starting there means no dead documentation links
    # ship on day one; a member is promoted to a real URI only once there is
    # somewhere to serve it.
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    code: str
    errors: list[ProblemDetail] | None = None
    request_id: str
