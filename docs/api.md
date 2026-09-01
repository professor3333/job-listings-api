# API contract — Job Listings API

The generated reference is `/docs` (Swagger) and `/openapi.json`. This file
records the parts a generated document cannot express: **why** each status code
was chosen, and what the deliberately-arguable decisions are.

Base URL in development: `http://127.0.0.1:8000`

---

## Endpoints

| Method | Path               | Status | Response model | Notes |
| ------ | ------------------ | ------ | -------------- | ----- |
| GET    | `/health`          | `200`  | `Health`       | Liveness. Touches no database and no filesystem. |
| GET    | `/jobs`            | `200`  | `JobPage`      | Filtered, sorted, paginated. |
| GET    | `/jobs/{job_id}`   | `200`  | `JobDetail`    | `404` when the id matches no row. |
| GET    | `/jobs/{job_id}/changes` | `200` | `JobChangePage` | Edit history. `404` for an unknown job. |
| GET    | `/sources`         | `200`  | `list[SourceSummary]` | Bare array — bounded cardinality. |
| GET    | `/runs`            | `200`  | `RunPage`      | Paginated run history. |
| GET    | `/stats`           | `200`  | `Stats`        | Counts, coverage, tri-state split. |

Every response carries `X-Request-ID` and `X-Response-Time-ms`.

### Why `/health` touches no database

It reports on *this service*, not on the data behind it. A health check that
went red because the scraper wedged its database would be reporting Build 2's
liveness — and would take this service out of rotation for a fault it neither
caused nor can fix. The database signal belongs on `/sources`, where a caller
asking about sources expects to hear about data.

---

## Status codes, and why each one

| Code | When | Why not something else |
| ---- | ---- | ---------------------- |
| `200` | Success, **including an empty list** | An empty result is a correct answer to a reasonable question. `404` would mean "this endpoint does not exist". |
| `404` | `/jobs/{id}` where the id matches no row | The *resource* is absent. Never used for an empty collection. |
| `405` | A write method against a read-only path | The path exists; the method does not apply to it. |
| `422` | Any input the service will not act on | See below — this is the deliberate call. |
| `500` | An unhandled fault | Body says nothing; the traceback goes to the log with a `request_id`. |
| `503` | The database is locked or wedged | The service is fine; its dependency is not. |

### The `400` vs `422` decision

**Everything invalid is `422`, including cross-field conflicts.** The
discrimination a client can act on lives in the body's `code`, not in the status
line.

`422 Unprocessable Content` (RFC 9110 §15.5.21) means the syntax parsed and the
content type was understood, but the instructions could not be followed. That
describes `salary_min_gte=50000&salary_max_lte=10000` exactly: well-formed, each
field individually legal, nonsense as a pair.

The argument for `400` on cross-field failures is real — it is "semantically
invalid but well-formed". It was rejected on cost. A Pydantic `@model_validator`
produces `422` for free; choosing `400` would require either raising
`HTTPException(400)` inside the route — which drags validation out of
`schemas.py` and into `routers/`, breaking the boundary the architecture exists
to hold — or catching `RequestValidationError` and re-classifying model-level
errors by inspecting `loc`. Both are real code to maintain and defend, in
exchange for a distinction the `code` field already carries.

### `503`: two different failures, two different answers

| Condition | SQLite code | Response | `Retry-After` |
| --------- | ----------- | -------- | ------------- |
| Scraper holds the write lock | `SQLITE_BUSY` | `503` `DATABASE_BUSY` | **Yes** — transient |
| Writer died, hot journal left | `SQLITE_READONLY_ROLLBACK` | `503` `DATABASE_UNAVAILABLE` | **No** — needs a human |

Rolling back a hot journal is a *write*. This service holds a read-only
connection and can never do it, so advising a retry would send clients into a
loop against a condition that cannot resolve itself. Classification is by
`sqlite_errorname`, never by matching on the message text.

---

## Error envelope — RFC 9457 problem details

Every `4xx` and `5xx` returns the same shape, served as
`application/problem+json`.

```jsonc
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 422,
  "detail": "Input should be greater than or equal to 1",
  "instance": "/jobs",
  "code": "VALIDATION_FAILED",
  "errors": [
    { "field": "limit", "rule": "greater_than_equal",
      "message": "Input should be greater than or equal to 1" }
  ],
  "request_id": "4f1c…"
}
```

**Branch on `code`, never on `title` or `detail`** — those are prose and may be
reworded.

| `code` | Status | Meaning |
| ------ | ------ | ------- |
| `VALIDATION_FAILED` | `422` | One or more parameters are individually invalid. |
| `CROSS_FIELD_CONFLICT` | `422` | Each field is legal; the combination is not. |
| `NOT_FOUND` | `404` | No such resource. |
| `DATABASE_BUSY` | `503` | Locked by a writer. Retry. |
| `DATABASE_UNAVAILABLE` | `503` | Needs operator attention. Do not retry. |
| `INTERNAL_ERROR` | `500` | Unhandled fault. |

`type` is `about:blank` throughout. RFC 9457 states that an absent `type`, or
`about:blank`, carries no semantics beyond the status code — so starting there
ships no dead documentation links. A member is promoted to a real URI
(`/errors/cross-field-conflict`) only once there is somewhere to serve it.

`request_id` also appears in the `X-Request-ID` response header. It is the only
thing connecting the deliberately uninformative body of a `500` to the traceback
in the log.

### Why not FastAPI's default

The default returns **two incompatible shapes**: `detail` is a list of objects
for a validation error and a bare string for an `HTTPException`. A client cannot
write one error handler against a field whose type depends on which layer
failed. Pydantic's `loc` and `msg` are still forwarded into `errors[]` — they
are the best part of the default, and an envelope that discarded them would be a
downgrade wearing a standard's clothes.

---

## `GET /jobs`

### Response

```jsonc
{ "items": [ /* JobSummary */ ], "total": 3105, "limit": 20, "offset": 0 }
```

An envelope rather than a bare array. A bare array has nowhere to put `total`,
so a client cannot render "page 2 of 9" or know it has reached the end without
requesting an empty page — and adding a field later would change the response's
*type*, breaking every client, where adding a key to an object does not.

`JobSummary` **omits `description`** (average 5.7 KB, maximum 33 KB). A page of
100 would otherwise be several megabytes nobody asked for. It is served only by
`GET /jobs/{job_id}`. `content_hash` and `hash_version` are never served — they
are Build 2's bookkeeping.

### Query parameters

| Param | Type | Rule | Default |
| ----- | ---- | ---- | ------- |
| `limit` | int | `1..100`. Out of range is **`422`, not clamped**. | `20` |
| `offset` | int | `>= 0`. Past the end returns `200` with `items: []`. | `0` |
| `q` | str | ≤ 200 chars. Substring of **title or company**, case-insensitive. `%` and `_` matched literally. | — |
| `source` | enum | One of the 8 known sources. | — |
| `company` | str | ≤ 200 chars. **Prefix** match, case-insensitive. | — |
| `remote` | enum | `true` / `false` / `unknown`. | — |
| `seniority` | enum | `intern`,`junior`,`senior`,`staff`,`lead`,`principal`,`head`,`director`. | — |
| `salary_min_gte` | int | `>= 0`. Matches `salary_min >= value`. | — |
| `salary_max_lte` | int | `>= 0`. Matches `salary_max <= value`. | — |
| `currency` | str | ISO 4217, 3 letters. Case-insensitive, matched uppercase. | — |
| `posted_after` | date | ISO `YYYY-MM-DD`, inclusive. | — |
| `posted_before` | date | ISO `YYYY-MM-DD`, inclusive. | — |
| `sort` | enum | `posted_at`,`id`,`company`,`title`,`salary_min`,`salary_max`. | `posted_at` |
| `order` | enum | `asc` / `desc`. | `desc` |

Filters combine with **AND**.

### Cross-field rules

- `salary_min_gte` must not exceed `salary_max_lte`
- `posted_after` must not be later than `posted_before`

Both bounds are inclusive, so `min == max` is legal. Violations return `422`
with `code: "CROSS_FIELD_CONFLICT"`.

### Decision: NULL values never satisfy a filter

**`salary_min_gte=100000` does *not* return rows where `salary_min` is NULL.**

There is no obviously right answer, only a documented one. The reasoning: a
filter on a value cannot be satisfied by the *absence* of that value — a row
with no recorded salary is not evidence of a salary above the threshold. This
also falls out of SQL for free (`NULL >= 100000` is NULL, which is not true), so
the documented behaviour and the natural implementation agree.

This is not a corner case: `salary_min` is NULL in **69%** of rows. The same
rule applies to `posted_after`/`posted_before` against a NULL `posted_at`.

To find rows with no recorded value, use the tri-state filter where one exists —
`remote=unknown`. There is currently **no** way to ask for "salary not recorded"
or "seniority not recorded"; if that is needed, it should be an explicit
parameter rather than a reinterpretation of these ones.

### Decision: unknown query parameters are rejected

**`?colour=red` returns `422`.** Ignoring unknown parameters is the more
forgiving choice and was rejected: a typo like `?limt=5` silently returning
unfiltered results is a worse failure than an error, because the client believes
it filtered. The cost is that a client sending parameters this version does not
know about will break — an acceptable trade for a read-only service whose
clients can regenerate from `/openapi.json`.

### Decision: `sort` is an allowlist, not a column name

`?sort=id;DROP TABLE jobs` returns `422` because the value is not a member of
the enum — not because anything downstream escapes it.

Values in SQL can be bound parameters; **identifiers cannot**. `ORDER BY ?` is
not valid SQL, so the column must be chosen from a fixed set written in the
service's own source. `content_hash` and `description` are real columns and are
still rejected: the allowlist defines the public contract, not merely what is
safe.

Sorting always appends the primary key as a tie-break. Without it, ordering by a
column with many repeated values (`posted_at` has ~800 distinct values across
3,105 rows) leaves ties whose order SQLite may resolve differently between
queries, so paging with `limit`/`offset` would silently repeat some rows and skip
others.

### Examples

```bash
curl 'http://127.0.0.1:8000/jobs?limit=5'
curl 'http://127.0.0.1:8000/jobs?source=greenhouse:anthropic&remote=unknown'
curl 'http://127.0.0.1:8000/jobs?q=engineer&seniority=senior&sort=company&order=asc'
curl 'http://127.0.0.1:8000/jobs?salary_min_gte=100000&currency=usd'
curl 'http://127.0.0.1:8000/jobs?posted_after=2026-08-01&posted_before=2026-08-31'
```

---

## `GET /jobs/{job_id}`

`job_id` is typed as an integer `>= 1`, so `/jobs/abc` is a `422` from path
validation rather than a `500` from the database. A well-formed id that matches
no row is a `404` carrying the standard envelope.

Returns `JobDetail`: every `JobSummary` field plus `source_id`, `salary_raw`,
`description`, `first_seen`, `last_seen`.

```bash
curl 'http://127.0.0.1:8000/jobs/1'
curl -i 'http://127.0.0.1:8000/jobs/999999999'   # 404, application/problem+json
```

---

---

## `GET /jobs/{job_id}/changes`

Field-level edits recorded by the scraper, newest first, paginated.

**Values are truncated to 200 characters by design.** `job_changes` stores full
before/after values, and `description` diffs reach 30,646 characters — 32.8 MB
across the table. One real job (id 72) has six recorded changes which would be
roughly 92 KB of response served verbatim; truncated, it is 3.4 KB.

`old_length` and `new_length` report the *true* sizes and `truncated` says
whether anything was cut, so a client is never misled about what it received.
Truncation happens in SQL (`substr`), not in the response model — filtering
afterwards would still have paid to read the full values off disk.

```jsonc
{ "items": [ { "observed_at": "2026-08-31T03:45:08Z", "field": "description",
               "old_value": "…200 chars…", "new_value": "…200 chars…",
               "old_length": 7669, "new_length": 7691, "truncated": true } ],
  "total": 6, "limit": 20, "offset": 0 }
```

An unknown `job_id` is a **`404`, not an empty list**: "this job has never
changed" and "this job does not exist" are different facts, and collapsing them
would leave the endpoint unable to answer either.

---

## `GET /sources`

One entry per source that has jobs, with the outcome of its most recent run.

Returns a **bare array**, deliberately unlike `/jobs`. There are eight sources
and there will not be thousands, so there is nothing to paginate and no `total`
worth carrying. An envelope exists to make paging expressible; where paging is
meaningless it is ceremony.

`last_run_status` may be `running` indefinitely — a scraper that dies between
transactions never writes `finished_at`. That is reported as-is. This service
cannot distinguish a live run from an abandoned one by querying, because the
discriminator is a `-journal` file on disk, not a row.

A source with jobs but no run row still appears, with null run fields.

---

## `GET /runs`

Paginated run history, newest first.

**No duration is reported.** Build 2 stamps `finished_at` from the same value as
`started_at`, so every completed run shows zero elapsed. A computed
`duration_seconds` would be `0.0` for all of them — confidently wrong. Both
timestamps are returned raw so a client can see the problem for itself. This is
an upstream bug to fix in Build 2's repo, not to launder here.

---

## `GET /stats`

Counts, per-field coverage, the `remote` tri-state split, and the `posted_at`
date range.

Coverage is the honest counterpart to the NULL-filter decision above: a client
seeing `salary_min` populated in 31% of rows understands why a salary filter
returns little, rather than assuming the filter is broken. Real values:

| Field | Coverage |
| ----- | -------- |
| `posted_at` | 100.00% |
| `description` | 99.19% |
| `location` | 97.84% |
| `remote` | 63.64% |
| `seniority` | 50.82% |
| `currency` / `salary_raw` | 39.61% |
| `salary_min` | 31.47% |
| `salary_max` | 29.02% |

---

## Observability

Every response carries:

| Header | Meaning |
| ------ | ------- |
| `X-Request-ID` | Correlation id, also in every problem body as `request_id`. |
| `X-Response-Time-ms` | Server-side duration, measured with a monotonic clock. |

Logs are one JSON object per line on stdout, each carrying `request_id`. A `500`
body deliberately says nothing; the traceback is written to the log against the
same id, which is what makes the opaque body defensible rather than merely
unhelpful.

---

## Known coupling

`source` is a static allowlist in `schemas.py`. If Build 2 begins scraping a new
board, this service rejects that source with `422` until the tuple is updated.
That is deliberate — a static enum keeps `/openapi.json` accurate and avoids a
database round-trip during validation — but it is a coupling to remember, and
the reason `SOURCE_VALUES` carries a comment saying so.
