# Gap log — Build 3 (Job Listings API)

Every non-obvious thing is recorded here as it comes up, and the build keeps
moving. Weekly review: anything appearing 3+ times is a real gap and gets a full
write-up in `learning-log.md`. Everything else was noise.

Format: `- YYYY-MM-DD — the concept — where it came up`

## Open gaps

- 2026-09-01 — **A read-only SQLite connection cannot recover a hot journal.**
  Rollback-journal recovery is a *write*. A `mode=ro` connection meeting a
  crashed writer's `-journal` fails with `SQLITE_READONLY_ROLLBACK` (516), which
  is *wedged, needs a human* — categorically different from `SQLITE_BUSY`, which
  is *transient, retry*. `str(e)` is "attempt to write a readonly database" and
  "database is locked" respectively, but matching on message text is the wrong
  seam: branch on `e.sqlite_errorname` (Python 3.11+). — Phase 0, Decision 1.

- 2026-09-01 — **WAL is not free for a containerised reader.** A WAL reader must
  *create* the `-shm` shared-memory file, which needs write access to the
  *containing directory*. `-v ...:/data:ro` denies it → `SQLITE_READONLY_DIRECTORY`.
  SQLite deletes `-wal`/`-shm` on clean close, so this is not about a stale file:
  even a pristine WAL database is unopenable under that mount. Measured, not
  assumed. — Phase 0, Decision 1 / Phase 6.

- 2026-09-01 — **`greenhouse:anthropic = "..."` in a class body is an annotated
  assignment, not a syntax error.** It parses as `AnnAssign(target=greenhouse,
  annotation=anthropic)`. Without `from __future__ import annotations` it raises
  `NameError` at class-body execution; *with* it, annotations are never
  evaluated, so the enum silently gains a member named `greenhouse` whose value
  is `greenhouse:anthropic`. A second `greenhouse:*` member then raises
  `TypeError: 'greenhouse' already defined` — naming a key that appears nowhere
  in the source. Use the functional form; member name ≠ wire value. — will bite
  in Phase 3, `source` enum.

- 2026-09-01 — **FastAPI matches routes in declaration order.** A parameterised
  segment declared first swallows its literal siblings: `/jobs/{job_id}` above
  `/jobs/recent` tries to parse `"recent"` as `int` and returns `422` on a path
  that plainly exists. — Phase 2/3, `routers/jobs.py`.

- 2026-09-01 — **Run duration is not lock duration.** A scrape is mostly HTTP
  fetching, which holds no SQLite lock; only the commits take `EXCLUSIVE`. Sizing
  a busy timeout against wall-clock run length measures the wrong thing. — Phase
  0, Decision 1.

- 2026-09-01 — **A Pydantic model can be a query-parameter container.**
  `pagination: Annotated[Pagination, Query()]` binds `?limit=&offset=` to a model
  instead of loose arguments, which is what lets Phase 3's cross-field validators
  live in `schemas.py` rather than in the route. — Phase 2, `routers/jobs.py`.

- 2026-09-01 — **`tests/` is not a package, so `from .conftest import X` fails.**
  Relative imports need a parent package. Sharing a value out of `conftest.py` is
  done with a fixture, not an import — which is the idiomatic route anyway.
  — Phase 2, `tests/test_db.py`.

- 2026-09-01 — **ruff formats fenced Python inside Markdown.** `ruff format .`
  reformatted a ```python block in `docs/design.md`. Useful (docs cannot drift
  into invalid Python) but surprising the first time. — Phase 1.

- 2026-09-01 — **A startup check cannot be redirected by `dependency_overrides`.**
  Lifespan runs before any dependency is resolved, so a test that overrode only
  `get_conn` would still start against the real database. Injecting `Settings`
  into `create_app` puts the seam somewhere that governs both. — Phase 2,
  `main.py`.

- 2026-09-01 — **`TestClient` as a context manager runs the lifespan**, so any
  startup check becomes a dependency of every test that uses it. Adding a
  lifespan check retroactively broke Phase 1's tests, which had been constructing
  an app with default settings. See DEBUGGING.md. — Phase 2.

- 2026-09-01 — **`PydanticCustomError` keeps a machine-readable `type` on a
  model-level validator.** A bare `ValueError` in a `@model_validator` arrives as
  `type: "value_error"`, indistinguishable from other failures. Raising
  `PydanticCustomError("cross_field_conflict", ...)` lets the error handler tell a
  cross-field conflict from a single-field one without inspecting `loc`.
  — Phase 3, `schemas.py`.

- 2026-09-01 — **`model_config = ConfigDict(extra="forbid")` on a Query model
  makes unknown query parameters a 422.** That is what turns "ignore or reject
  `?colour=red`" from a wish into an enforced decision. — Phase 3.

- 2026-09-01 — **SQLite's `LIKE` is case-insensitive for ASCII only.** `company=acme`
  matches "Acme GmbH", but `ürsprung` does not match "Ürsprung". A real fix needs
  ICU or a normalised column; the limitation is documented rather than papered
  over. — Phase 3, `repository.py`.

- 2026-09-01 — **Escaping LIKE wildcards is correctness, not injection defence.**
  The value is already a bound parameter and can never execute. Escaping `%` and
  `_` is about making the search mean what the user typed — and the backslash must
  be escaped *first*, or it re-escapes the escapes just added. — Phase 3.

- 2026-09-01 — **A `ContextVar` survives `await` and the threadpool**, so a
  request id set in middleware is visible to a log call made anywhere in that
  request without threading a parameter through every signature. This is what
  makes correlated logging possible from inside `repository.py`. — Phase 5.

- 2026-09-01 — **`logging.StreamHandler(sys.stdout)` binds the stream at
  construction.** A test using `capsys` therefore sees nothing if the app was
  built before capture was active — fixture *ordering* silently decides whether
  the assertion can pass. Capturing with a `logging.Handler` instead is
  order-independent and exercises the real formatter. — Phase 5,
  `tests/test_observability.py`.

- 2026-09-01 — **`perf_counter` not `time()` for durations.** A wall clock
  adjusted mid-request can run backwards and yield a negative elapsed time; a
  monotonic clock cannot. — Phase 5.

- 2026-09-01 — **Truncate in SQL, not in the response model.** `substr()` and
  `length()` in the query mean a 30 KB value is never read into Python to be
  thrown away. Filtering at serialisation time would still have paid to move
  32.8 MB across the boundary. — Phase 5, `repository.py`.

- 2026-09-01 — **A config option on a subclass is a contract that drifts.**
  `extra="forbid"` sat on `JobFilters`, so `?colour=red` was 422 on `/jobs` and
  silently ignored on `/runs` — contradicting `docs/api.md`. Moving it to the
  shared `Pagination` base made the rule true everywhere at once. Caught by a
  test, not by reading. — Phase 5, `schemas.py`.

- 2026-09-01 — **The dataset figures in the docs are snapshots, and the scraper
  keeps running.** `docs/design.md` and `docs/api.md` cite 3,105 jobs; the source
  database holds 3,498 today. The *proportions* the decisions rest on are stable
  (`salary_min` NULL: 69% then, 70.4% now — 1,036 of 3,498 populated), which is
  the point: a decision justified by a proportion survives the data growing, one
  justified by a row count does not. Any figure quoted in prose needs the date it
  was measured. — Phase 5/6, `docs/`.

- 2026-09-01 — **Configuration that nothing reads is a promise the service does
  not keep.** `Settings` carried `default_page_size` and `max_page_size` from
  Phase 1; `schemas.py` used module constants instead, so setting
  `JOBSAPI_MAX_PAGE_SIZE=500` did nothing at all. Found while *documenting* the
  config for the README, not by any test — nothing fails when a setting is
  merely ignored. Removed rather than wired up, because a page-size bound is
  part of the published contract: it is a `Field` constraint that `/openapi.json`
  states, and an env var that changed the real bound would make the generated
  docs lie. — Phase 6, `config.py`.

---

## AI-WRITTEN register

AI-written files, and the one-line concept behind each. An entry leaves this
list only once it has been written up in `learning-log.md`.

| Date | File | Concept to re-derive | Written up? |
| ---- | ---- | -------------------- | ----------- |
| 2026-09-01 | `pyproject.toml` | Why a `src/` layout needs a build backend at all, and what `uv sync` installs the project *as* (editable wheel, not a path on `sys.path`) | ☐ |
| 2026-09-01 | `.gitignore` | Why `data/` and `*.db` are ignored in a repo whose whole job is reading a database | ☐ |
| 2026-09-01 | `docs/design.md` | Both Phase 0 decisions and the measurements behind them: `mode=ro` + path-not-policy config, and why WAL is *declined* rather than deferred | ☑ |
| 2026-09-01 | `src/jobsapi/main.py` | Why an app *factory* rather than a module-level singleton, and what `include_router` does that the `@router.get` decorator did not | ☑ |
| 2026-09-01 | `src/jobsapi/routers/meta.py` | Why `/health` is `async def` while every sqlite3 endpoint must be plain `def` — the rule is about what the body does, not house style | ☑ |
| 2026-09-01 | `tests/test_health.py` | Why `TestClient` is used as a context manager (lifespan events), and why the OpenAPI schema is asserted on rather than trusted | ☑ |
| 2026-09-01 | `.github/workflows/ci.yml` | What `uv sync --locked` refuses to do, and why CI having no network and no `jobs.db` is the point rather than a limitation | ☐ |
| 2026-09-01 | `src/jobsapi/config.py` | Why the DB location is a *path, not a policy*, and why `get_settings` is cached but tests never call it | ☑ |
| 2026-09-01 | `src/jobsapi/db.py` | Why `mode=ro` must be a URI (a plain connect *creates* a missing file), why `check_same_thread=False` is safe per-request but not globally, and why a generator dependency guarantees close | ☑ |
| 2026-09-01 | `src/jobsapi/errors.py` | Why the repository raises `JobNotFound` and not `HTTPException`, and why BUSY and READONLY_ROLLBACK are two classes rather than one | ☑ |
| 2026-09-01 | `src/jobsapi/schemas.py` | Three shapes on purpose: input model, list output, detail output — none of them the database row | ☑ |
| 2026-09-01 | `src/jobsapi/repository.py` | Why `ORDER BY posted_at DESC` alone silently repeats rows across pages, and why identifiers cannot be parameterised | ☑ |
| 2026-09-01 | `src/jobsapi/routers/jobs.py` | Why this file is plain `def` while `/health` is `async def` | ☑ |
| 2026-09-01 | `tests/conftest.py` | Why the fixture DB is *written* read-write and *read* read-only, and why the schema is copied rather than imported from Build 2 | ☑ |
| 2026-09-01 | `src/jobsapi/problems.py` | Why FastAPI's default `detail` (list for 422, string for 404) forces a custom envelope, and why every handler funnels through one builder | ☑ |
| 2026-09-01 | `src/jobsapi/schemas.py` (Phase 3) | The functional StrEnum for colon-bearing sources, `extra="forbid"`, and why cross-field rules need a model validator rather than field constraints | ☑ |
| 2026-09-01 | `src/jobsapi/repository.py` (Phase 3) | The clauses+params list pattern that makes an eleventh filter one `if` rather than a combinatorial explosion | ☑ |
| 2026-09-01 | `docs/api.md` | The three arguable decisions: NULLs never satisfy a filter, unknown params are rejected, `sort` is an allowlist | ☑ |
| 2026-09-01 | `src/jobsapi/logging_config.py` | Why a ContextVar carries the request id where a parameter cannot, and why logs go to stdout rather than a file | ☑ |
| 2026-09-01 | `src/jobsapi/repository.py` (Phase 5) | Why `substr()` belongs in the query and not in the response model, and why `/sources` needs a LEFT JOIN | ☐ |
| 2026-09-01 | `src/jobsapi/routers/runs.py` | Why `RunSummary` deliberately has no `duration_seconds` | ☐ |
| 2026-09-01 | `Dockerfile` | Why the build toolchain lives in a stage that never ships, why the database is a volume and not a layer, and why exec-form CMD matters for SIGTERM | ☐ |
| 2026-09-01 | `.dockerignore` | Why a build context that *could* contain a database is a problem even when no COPY references it | ☐ |
| 2026-09-01 | `scripts/make_demo_db.py` | Why a reader-only service ships a schema-creating script at all, and why it is stdlib-only | ☐ |
| 2026-09-01 | `.github/workflows/ci.yml` (docker job) | Why the Dockerfile is verified by querying a running container rather than by a successful build | ☐ |
| 2026-09-01 | `README.md` | Why every documented command was executed before being written down | ☐ |

---

## Explain-back questions (asked and answered before each commit)

### Phase 1 — 2026-09-01

**Q1. `@router.get("/health")` runs at import time. What does it register, and
with what — and why does the app still not have the route afterwards?**

It registers an `APIRoute` on the `APIRouter` *object* `meta.router`, appending
to that router's own `.routes` list. The application knows nothing about it yet.
`app.include_router(meta.router)` is the step that copies those routes onto the
`FastAPI` instance (applying any `prefix`, `tags` and dependencies as it goes).
That two-step split is why a router can be imported and unit-tested on its own,
and why the same router could be mounted twice under different prefixes.

> **Correction, 2026-09-01 (written while closing the learning log).** The
> "copies those routes onto the `FastAPI` instance" sentence is true of older
> FastAPI, not of the installed 0.141.1. `include_router` appends a single
> `fastapi.routing._IncludedRouter` holding a *reference* to the router plus the
> prefix/tags/dependencies, and computes effective routes lazily. `app.routes`
> here contains no `APIRoute` at all. The conclusions stand — see
> `learning-log.md`, Part 1 entry 1 and Part 2 "Framework mechanics" Q1.

**Q2. `/health` is `async def`, but the project rule says sqlite3 endpoints must
be plain `def`. Is that a contradiction?**

No — the rule is about what the function body does. FastAPI runs a plain `def`
endpoint in a threadpool (`run_in_threadpool`), so a blocking call inside it
occupies a worker thread and leaves the event loop free. An `async def` endpoint
runs *directly on the event loop*, so any blocking call inside it stalls every
other request in the process. `/health` performs no I/O whatsoever, so `async
def` is strictly cheaper — no threadpool hop. The moment a function touches
`sqlite3`, it must become plain `def`.

**Q3. `test_health_is_declared_in_the_openapi_schema` asserts on
`/openapi.json`. Why is that not testing FastAPI's code rather than ours?**

Because the schema is derived from *our* type hints. `Literal["ok"]` is what
makes the schema say `const: "ok"`; widening it to `str` would still pass the
happy-path test but would silently publish a weaker promise to every reader of
`/docs`. The assertion pins the contract, not the framework — it fails when our
declaration changes, which is the thing that can actually regress.

---

### Phase 2 — 2026-09-01

**Q1. `/health` is `async def` and `GET /jobs` is plain `def`. Which is the
mistake?**

Neither — the rule is about the body. FastAPI runs a plain `def` endpoint in a
threadpool, so a blocking `sqlite3` call there occupies a worker thread and the
event loop keeps accepting requests. An `async def` endpoint runs directly on the
loop, so the same call would stall *every* concurrent request in the process.
`/health` performs no I/O at all, so `async def` avoids a pointless threadpool
hop. Getting this backwards produces an app that tests perfectly and collapses
under two users.

**Q2. Why does `create_app` take `Settings` instead of tests calling
`app.dependency_overrides[get_conn]`?**

Because the startup schema check runs inside the lifespan, which executes
*before* any dependency is resolved. An override on `get_conn` cannot reach it,
so tests would have redirected their queries to the fixture database while still
starting up against the real one — passing for the wrong reason, or failing on a
machine where `jobs.db` is absent. Injecting settings puts the single seam
somewhere that governs both paths. `dependency_overrides` remains available; it
is just not the right lever for this.

**Q3. `ORDER BY posted_at DESC` looks like a total order. Why add `, id DESC`?**

Because it is not one. `posted_at` is a plain `YYYY-MM-DD` date, so thousands of
rows share a value, and SQLite is free to return tied rows in a different order
on each query. Paging through with LIMIT/OFFSET would then show some rows twice
and skip others — silently, with no error anywhere. Appending the primary key
makes the ordering total, which is what stable pagination actually requires.

**Q4. `check_same_thread=False` disables a safety check. What makes that safe?**

That the connection is created per request and never shared. FastAPI runs sync
dependencies and sync endpoints in a threadpool, and the dependency that opens
the connection may land on a different worker thread from the endpoint that uses
it — so the check would fire on correct code. It is safe *only* because of the
per-request lifetime; a module-level connection with the same flag would be the
exact bug the check exists to catch.

---

### Phase 3 — 2026-09-01

**Q1. `?sort=id;DROP TABLE jobs` returns 422. Which line of code stopped it, and
would escaping have been an acceptable alternative?**

The enum did, during request validation — `SortField` has no such member, so the
request never reaches `repository.py`. Escaping would not have been acceptable,
because a column name cannot be a bound parameter at all: `ORDER BY ?` is not
valid SQL. Values are parameterised; identifiers must be *chosen* from a fixed
set written in our own source. That is why `content_hash` is also rejected
despite being a real column — the allowlist defines the public contract, not
merely what is safe.

**Q2. Does `salary_min_gte=100000` return rows where `salary_min` is NULL, and
who decided?**

No, and it was a decision rather than a discovery. `NULL >= 100000` evaluates to
NULL, which is not true, so SQLite excludes the row — but the reason to keep that
behaviour is that a filter on a value cannot be satisfied by the *absence* of
that value. It governs 69% of the dataset, so it is documented in `docs/api.md`
rather than left to be inferred. Verified against the real database:
`salary_min_gte=0` returns 977 of 3,105 rows, exactly the non-NULL count.

**Q3. Why is a cross-field failure 422 and not 400, given it is "well-formed but
semantically invalid"?**

Because 422 *is* "well-formed but semantically invalid" — RFC 9110 §15.5.21:
syntax parsed, content type understood, instructions could not be followed. And
because the alternative costs real code: a `@model_validator` produces 422 for
free, whereas 400 would require raising `HTTPException(400)` inside the route —
dragging validation out of `schemas.py` and breaking the boundary — or
re-classifying `RequestValidationError` by inspecting `loc`. The distinction a
client can act on is carried by `code: CROSS_FIELD_CONFLICT` instead.

**Q4. What breaks if the `errors[]` array is dropped from the envelope?**

The single best property of FastAPI's default. Pydantic's `loc` names the exact
parameter and `msg` states the rule; without forwarding them the client learns
only "validation failed" and must guess which of fourteen parameters was wrong.
RFC 9457 does not standardise field-level errors, so this array is the one part
that had to be invented — which is an argument *for* adopting the standard, not
against it: the other 80% came free.

---

### Phase 5 — 2026-09-01

**Q1. The 500 body says nothing on purpose. What makes that defensible rather
than merely unhelpful?**

That the traceback is written to the log against the same `request_id` the body
carries. Until Phase 5 it was not written *anywhere* — the handler built a safe
body and discarded the exception, which made every 500 unresolvable. Both halves
are needed: an opaque body without a logged traceback is negligence, and a
traceback in the body is a leak. `test_traceback_reaches_the_log_but_not_the_body`
asserts them together for that reason.

**Q2. Why does `/jobs/{id}/changes` truncate in SQL rather than in the response
model, when the response model already controls what is sent?**

Because the response model runs after the data has been read. `job_changes`
holds 32.8 MB of description diffs, single values up to 30,646 characters;
truncating at serialisation would still have paid to pull them off disk and into
Python. `substr()` and `length()` in the query mean the large value never
crosses the boundary — the true size is reported as a number instead. Measured:
job 72's six changes are ~92 KB of raw values and 3.4 KB of response.

**Q3. `/sources` returns a bare array while `/jobs` returns an envelope. Is that
an inconsistency worth fixing?**

No — the envelope exists to make paging expressible. There are eight sources and
there will not be thousands, so there is no `total` worth carrying and no next
page to describe. Adding an envelope for symmetry would be ceremony. The
inconsistency is between *situations*, not between careless decisions, and it is
documented in `docs/api.md` so a reader does not have to guess which it is.

**Q4. `/runs` omits `duration_seconds` even though both timestamps are present.
Why not compute it?**

Because Build 2 stamps `finished_at` from the same value as `started_at`, so it
would be `0.0` for every completed run. Publishing a computed number that is
always wrong is worse than omitting it: the client cannot tell the difference
between "this run took no time" and "this field is broken". Returning both
timestamps raw lets the client see the equality for itself. The fix belongs in
Build 2's repo — this service is a reader and does not launder its source's
bugs.

---

### Phase 6 — 2026-09-01

**Q1. The Dockerfile could not be built on the machine that wrote it. Why is a
CI job an acceptable answer rather than a workaround?**

Because the claim in the Definition of Done is not "a Dockerfile exists", it is
"`docker build` works and the container serves real data from a mounted volume"
— and that is a claim about a *running container*, which a local build would
also only partly establish. The CI job builds the image and then queries it:
`/health` answers, `/jobs` returns rows from the mounted volume, `?limit=0` is
still a 422 inside the image, the process is uid 1001, and a write to
`/data/jobs.db` is refused. That is strictly more than "it built on my laptop",
and it re-runs on every push rather than once. The honest part is the
bookkeeping: the README and the PR both say the local build was never run.

**Q2. The smoke test opens its own read-write connection to `/data/jobs.db`
rather than asserting the API returns 503 on a write attempt. Why that shape?**

Because the API has no write path to test — that is the point of the build — so
asserting on its behaviour would prove nothing about the mount. The service's
own guarantee is already double-enforced in application code (`mode=ro` on the
URI, `PRAGMA query_only = 1`), and a test that exercised those would be testing
the same source file twice. Opening a *plain read-write* connection from inside
the container tests the layer underneath: the `:ro` bind mount itself. If
someone dropped `:ro` from the README's `docker run`, every application-level
assertion would still pass and this one would fail.

**Q3. `default_page_size` and `max_page_size` were removed rather than wired up.
What would wiring them up have cost?**

The property the whole build rests on. The `1..100` bound is a `Field`
constraint on `Pagination`, so it is compiled into `/openapi.json` and a
generated client enforces it before a request is sent. Constraints are
class-level and evaluated at import, so making the bound configurable would mean
either building the model dynamically per-process or moving the check into a
validator that reads settings — and in both cases a deployment could run with
`max=500` while its own `/docs` still promised 100. "The docs are generated from
the types, so wrong docs mean wrong types" stops being true the moment a value
can differ from what the type says. A setting nothing reads is a bug; a setting
that makes the published schema lie is a worse one.

**Q4. Why is `scripts/make_demo_db.py` stdlib-only, and why does it copy Build
2's schema instead of importing it?**

Stdlib-only because its two callers cannot assume an install: CI runs it with
the runner's bare `python3` before the image is even started, and a stranger may
run it before `uv sync` finishes being explained to them. Adding a dependency
would make the fallback need the thing it is a fallback for.

It copies the schema for the same reason `tests/conftest.py` does: importing
`jobscrape` would couple two repositories that are deliberately separate, and
this service is a *reader* of that schema, not a participant in it. The copy is
not left to rot on trust — `db.verify_schema` compares the real database's
columns at startup, so the two drifting apart is a loud refusal to start rather
than a silent wrong answer.
