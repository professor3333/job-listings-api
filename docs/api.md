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
| POST   | `/watchlists`      | `201`  | `Watchlist`    | `Location` header. `409` on a duplicate name. |
| GET    | `/watchlists`      | `200`  | `WatchlistPage` | Paginated. |
| GET    | `/watchlists/{id}` | `200`  | `Watchlist`    | `404` when the id matches no row. |
| PUT    | `/watchlists/{id}` | `200`  | `Watchlist`    | Full replacement. `404`; never creates. |
| PATCH  | `/watchlists/{id}` | `200`  | `Watchlist`    | Partial update. `422` on an empty body. |
| DELETE | `/watchlists/{id}` | `204`  | *(none)*       | `404` if already gone. Cascades to items. |
| POST   | `/watchlists/{id}/jobs` | `201` | `WatchlistEntry` | `404` for an unknown job, `409` if already on the list. |
| GET    | `/watchlists/{id}/jobs` | `200` | `WatchlistEntryPage` | Job details joined in from the read database. |
| DELETE | `/watchlists/{id}/jobs/{job_id}` | `204` | *(none)* | `404` if the job is not on the list. |

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
| `201` | A resource was created | Carries a `Location` header naming it. |
| `204` | A delete succeeded | Success with deliberately no representation to send. |
| `401` | A write endpoint was called without a valid `X-API-Key`, when one is configured | Not `403`: that means *authenticated but forbidden*, and there is no identity here to forbid. |
| `409` | A uniqueness constraint refused the write | Not `422`: the body was valid and would have succeeded a moment earlier. What refused it is the current *state*, not the input. |
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

`errors[].field` names the parameter, with its *location* stripped: Pydantic
reports `("query", "limit")` and `("path", "job_id")`, and both are flattened to
the bare name. So `GET /jobs/abc` returns `field: "job_id"`, not
`"path.job_id"` — the name a client can act on, without framework vocabulary in
it. The cost is that two parameters sharing a name in different locations would
be indistinguishable in the body; no endpoint here has that shape.

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

`JobSummary` **omits `description`** (average 5.3 KB, maximum 33.0 KB, 21.7 MB
across the table — measured 2026-09-03 over 4,224 rows; it was 5.7 KB average at
Phase 0 and the argument is unchanged). A page of 100 would otherwise be roughly
half a megabyte nobody asked for. It is served only by `GET /jobs/{job_id}`.
`content_hash` and `hash_version` are never served — they are Build 2's
bookkeeping.

The omission is enforced twice, and the two are not substitutes: `_SUMMARY_COLUMNS`
does not select the column, which is what avoids reading ~21.7 MB off disk and
building the strings, and `JobSummary` has no field to put it in, which is what
makes the omission structural rather than a flag someone can drop.

### Query parameters

| Param | Type | Rule | Default |
| ----- | ---- | ---- | ------- |
| `limit` | int | `1..100`. Out of range is **`422`, not clamped**. | `20` |
| `offset` | int | `>= 0`. Past the end returns `200` with `items: []`. | `0` |
| `q` | str | 1–200 chars. Substring of **title or company**, case-insensitive. `%` and `_` matched literally. Empty is `422`. | — |
| `source` | enum | One of the 8 known sources. | — |
| `company` | str | 1–200 chars. **Prefix** match, case-insensitive. Empty is `422`. | — |
| `remote` | enum | `true` / `false` / `unknown`. | — |
| `seniority` | enum | `intern`,`junior`,`senior`,`staff`,`lead`,`principal`,`head`,`director`. | — |
| `salary_min_gte` | int | `>= 0`. Matches `salary_min >= value`. | — |
| `salary_max_lte` | int | `>= 0`. Matches `salary_max <= value`. | — |
| `currency` | str | ISO 4217, 3 letters, `^[A-Za-z]{3}$`. Case-insensitive, matched uppercase. | — |
| `posted_after` | date | ISO `YYYY-MM-DD`, inclusive. | — |
| `posted_before` | date | ISO `YYYY-MM-DD`, inclusive. | — |
| `sort` | enum | `posted_at`,`id`,`company`,`title`,`salary_min`,`salary_max`. | `posted_at` |
| `order` | enum | `asc` / `desc`. | `desc` |

### The two `currency` patterns

`currency` is normalised to uppercase before it is validated, so two different
patterns are true of it and the distinction is deliberate:

| | pattern | what it describes |
| --- | --- | --- |
| published in `/openapi.json` | `^[A-Za-z]{3}$` | what a **client may send** |
| enforced after normalisation | `^[A-Z]{3}$` | what the **filter matches on** |

The published one is the looser of the two because `?currency=usd` is accepted.
Publishing the enforced pattern instead would tell a generated client that a
request this API honours is invalid.

This is stated here because the schema could not state it alone. Pydantic
withdraws `pattern` from the generated schema whenever a `BeforeValidator` is
attached — the declared constraint stops being true of the raw input, so it is
dropped rather than published falsely. Until this was corrected,
`/openapi.json` described `currency` as an unconstrained string while the
service refused `dollars`: a rule enforced but unpublished, which a generated
client can only discover by being rejected. The pattern is now republished
explicitly via `json_schema_extra`.

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

This is not a corner case: `salary_min` is NULL in **~70%** of rows (69% at
Phase 0, 70.4% re-measured at Phase 6 — the proportion is what is stable, not
the row count). The same rule applies to `posted_after`/`posted_before` against
a NULL `posted_at`.

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

### Decision: an empty text filter is `422`, not "no filter"

**`?q=` and `?company=` return `422`.** Both are well-formed, both pass a
max-length check, and both used to return `200` with the *unfiltered* list —
the filter was dropped on the way to the SQL and nothing said so.

That is the same failure as `?limt=5` in the decision above, arriving by a
different route: a request that silently returns unfiltered results is worse
than an error, because the client believes it filtered. Accepting empty-as-
absent would have left this document arguing against the service's own
behaviour one section later.

A text filter must carry a term. Note the line this draws: it is *"is there a
term"*, not *"is the term useful"* — `?q=%20` is a legal one-character search
for a space and still returns `200`.

**This is a behaviour change**, `200` → `422`, and it is made deliberately
before `1.0`. A client sending an empty `q` was not getting a filtered result
before and is not losing one now; it is being told that what it sent was never
a search.

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

A source with jobs but no run row still appears, with null run fields. The
converse does **not** hold and the asymmetry is deliberate: a source with run
rows and no jobs does not appear at all. This endpoint answers "what is in the
dataset", and a scrape that yielded nothing is visible on `/runs` instead.

---

## `GET /runs`

Paginated run history, newest first.

**`duration_seconds` is nullable, and null means *unknown*, never zero.**

Until 2026-09-02, Build 2 stamped both ends of a run from a single clock
reading, so 62 of the first 63 finished runs recorded `finished_at` exactly
equal to `started_at`. That was fixed upstream
(`job-listing-scraper@1aead71`), and every run since carries a real elapsed
time — but the fix could not be retroactive. The lost measurements are gone,
so the table permanently holds two eras and this endpoint has to tell them
apart.

The discriminator is **exact equality of the two timestamps**. Identical to the
microsecond is the bug's signature, not a plausible measurement of work that
fetched pages over a network. A run still in progress is null as well, having
no end to measure from. `finished_at` *earlier* than `started_at` is null too:
it is not a duration either, and no client should have to defend against a
negative number.

Reporting `0.0` was the alternative and is why this field did not exist until
now. A confident zero is worse than an absent value: nothing else in the
response contradicts it, so a reader concludes scrapes are instantaneous. Both
timestamps stay in the response, so a client can always check the arithmetic
rather than trust the derived field.

The value is computed in `RunSummary`, not in SQL. By then both columns are
`datetime` objects and the subtraction is exact; `julianday()` would convert to
a float day number and lose the microseconds the whole discrimination rests on.

`rules_version` is not served. It is Build 2's bookkeeping — which parser rules
produced the run — in the same family as `content_hash` and `hash_version` on
`/jobs`, and means nothing to a client of this API. The columns served are `id`,
`source`, `status`, `started_at`, `finished_at`, `rows_parsed`, `pages_fetched`
and `page_cap`, plus the derived `duration_seconds`.

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

The second coupling is `posted_at`. It is served as a `date`, which is the one
response field declared **narrower** than the column it reads: `jobs.posted_at`
is TEXT, and TEXT holds anything. Every one of the 4,224 rows is a bare
`YYYY-MM-DD` today (measured 2026-09-03), so the narrowing is honest — but if
Build 2 ever writes a timestamp there, Pydantic refuses it with *"Datetimes
provided to dates should have zero time"* and the row becomes unservable.

The failure would not be confined to that row. `items` is validated as a list,
so one malformed value fails the **whole page** — every page containing it is a
`500` on data that plainly exists, and `PRAGMA table_info` cannot see it coming
because the column is present and correctly named.

So the startup gate checks the values as well as the columns: `verify_posted_at_shape`
samples for the first `posted_at` that is not a bare ISO date and refuses to
start, naming the value. It is a **startup sample, not a per-request guarantee** —
a row inserted after startup still fails when it is served. What it converts is
drift that is already in the file: a named refusal at boot instead of a 500 on
whichever page is unlucky. Cost is one covering-index search on `idx_jobs_posted`
(6.1 ms for both startup gates against the real database).

Widening the field to `datetime` was the alternative and was declined: it would
change `/openapi.json` from `format: date` to `format: date-time` for every
client, to accommodate data that does not exist.

The gate covers three endpoints, not one. `posted_at` is served by `/jobs` and
`/jobs/{job_id}`, and `/stats` reports `MIN(posted_at)` and `MAX(posted_at)` as
dates — so the same drift would fail the dataset-shape endpoint too, where a
client has no page to skip past.

---

## The write path (Phase 4)

Everything above reads Build 2's dataset. Everything below writes to a
**separate database this service owns**. The two never mix: `jobs.db` is opened
`mode=ro` with `PRAGMA query_only`, and no code path in the write endpoints can
reach it with a writable handle.

| | read database | write database |
| --- | --- | --- |
| setting | `JOBSAPI_DB_PATH` | `JOBSAPI_APP_DB_PATH` |
| owner | Build 2 | this service |
| mode | `mode=ro` + `query_only` | read-write |
| journal | `delete` (WAL declined — see `design.md`) | **WAL** |
| schema | verified at startup, never created | created at startup if absent |
| `user_version` | 0, so drift is detected by comparing columns | 1 |

### Decision: `409`, not `422`, for a duplicate

`POST /watchlists` with a name that already exists is a `409 Conflict`. The body
parsed, every field was legal, and the *identical* request would have succeeded
a minute earlier. What refuses it is the state of the collection, so telling the
client to fix its request would be a lie — the fix is to pick another name.

`422` stays for bodies that are wrong on their own terms: a missing `name`, a
`name` of 81 characters, an unknown field, a `job_id` of `0`.

### Decision: the duplicate check is the constraint, not a prior `SELECT`

The insert is attempted and `sqlite3.IntegrityError` is translated into the
`409`. Reading first and then inserting is a time-of-check-to-time-of-use race:
two concurrent requests can both find nothing and both proceed. The `UNIQUE`
constraint is the only participant that can actually serialise the decision, so
it makes it.

Name comparison is case-insensitive (`COLLATE NOCASE` on the column), so
`Backend Roles` and `backend roles` are the same watchlist.

### Decision: `PUT` replaces, `PATCH` merges

This is the distinction the phase exists to teach, and it is visible in the
request models rather than in the handler.

- **`PUT`** takes the *complete new state*. An omitted `description` therefore
  **clears** it — the client has described a resource that has none. `PUT` is
  idempotent: sending the same body twice leaves the same state, which is what
  makes it safe to retry after a timeout.
- **`PATCH`** takes *only what changes*. An omitted `description` is left alone;
  an explicit `{"description": null}` clears it. The mechanism is Pydantic's
  `model_fields_set` via `model_dump(exclude_unset=True)` — without it every
  unsent field would arrive as its default `None` and a rename would silently
  wipe the description.
- **`PATCH {}`** is a `422`, not a successful no-op. It asks for a change and
  names none; answering `200` would tell the client an update was applied.

### Decision: `PUT` to a missing id is `404`, not an upsert

HTTP permits `PUT` to create at a client-chosen URL. It is wrong here because
ids are **server-assigned**: a client cannot know a valid id for a resource that
does not exist, so a `PUT` to one is a mistake rather than an instruction.

### Decision: `DELETE` on something already gone is `404`

`204` on the first call, `404` on the second. `DELETE` remains idempotent in the
sense HTTP requires — repeating it does not change the *effect*, the resource
stays absent — but the second response reports honestly what it found. A `204`
would claim to have deleted something that was not there.

Deleting a watchlist removes its items through `ON DELETE CASCADE`, which works
only because `PRAGMA foreign_keys = ON` is set on every connection. SQLite
leaves foreign keys **off** by default; without that line the clause parses,
does nothing, and orphans rows silently.

### Decision: a job reference can dangle, and is reported rather than hidden

`watchlist_items.job_id` has no foreign key and **cannot have one** — the row it
refers to lives in a different database file, and SQLite constraints do not span
databases. Existence is checked at write time against the read-only connection,
which makes it true at one moment rather than an invariant.

So a job removed from `jobs.db` afterwards leaves an item pointing at nothing.
`GET /watchlists/{id}/jobs` returns that item with `job: null` and
`job_missing: true` rather than dropping it, because the client saved it
deliberately and needs to see it to clean it up. `DELETE` on such an item still
works, and deliberately does not consult `jobs.db` — the one case where cleanup
matters most is the case where the source row is gone.

The job details on that endpoint are joined **in Python**, not in SQL: two
database files cannot be joined on one connection without `ATTACH`, and
attaching `jobs.db` to the read-write connection would put a writable handle on
the file this service promises never to write. One query for the page of items,
then one batched `WHERE id IN (...)` — not one query per row.

### The optional API key

Unset by default, and then the write endpoints are open — correct for a service
on localhost holding nothing sensitive. Set `JOBSAPI_API_KEY` and every
`/watchlists` request must carry `X-API-Key`.

Missing key and wrong key both return `401` with
`WWW-Authenticate: ApiKey realm="jobsapi"`. `403` would mean *authenticated but
forbidden*, which implies an identity to forbid; there is one shared secret and
no users, so every failure is "not authenticated". (`ApiKey` is not an
IANA-registered scheme; the header is sent because RFC 9110 requires one on a
`401`, and naming the scheme is more useful than omitting it.)

The key guards `/watchlists` only. Build 2's public dataset stays readable —
what is gated is user-created content.
