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

- 2026-09-01 — **SQLite foreign keys are OFF by default, per connection.**
  `ON DELETE CASCADE` is parsed, stored, and then ignored unless every
  connection issues `PRAGMA foreign_keys = ON`. The schema looks correct under
  inspection while orphaning rows in practice. — Phase 4, `appdb.py`.

- 2026-09-01 — **`model_dump(exclude_unset=True)` is what makes PATCH safe.**
  Without it every unsent optional field arrives as its default `None` and a
  partial update wipes the fields it did not mention, with a 200.
  `model_fields_set` is where Pydantic keeps the difference between absent and
  explicitly null. — Phase 4, `routers/watchlists.py`.

- 2026-09-01 — **`INSERT ... RETURNING` avoids the `lastrowid` window.** The
  inserted row comes back from the same statement rather than from a follow-up
  `SELECT` keyed on `cursor.lastrowid`. — Phase 4, `watchlist_repository.py`.

- 2026-09-01 — **A `Depends` attached to an `APIRouter` runs for every route on
  it and discards its return value.** That is the shape for a dependency that
  exists only to raise — a route added later cannot forget it. — Phase 4,
  `security.py`.

- 2026-09-01 — **`response_class=Response` is needed for a real 204.** FastAPI's
  default `JSONResponse` writes `null` into the body of a 204, which some
  clients reject. — Phase 4, `routers/watchlists.py`.

- 2026-09-01 — **A guard against ambient state has to be extended, not merely
  written.** `_never_the_real_database` covered `JOBSAPI_DB_PATH` and knew
  nothing about `JOBSAPI_APP_DB_PATH`, so the suite silently created a database
  in the developer's home directory and passed. A read path fails when its
  resource is missing; a write path creates it. See DEBUGGING.md. — Phase 4.

- 2026-09-02 — **A tool can be installed and still be invisible to a shell that
  started before it.** `command -v docker` failed and a scripted sweep of
  `/usr/local/bin`, `/opt/homebrew/bin` and `/Applications` found nothing, while
  OrbStack was in fact installed and its daemon running — `/usr/local/bin/docker`
  existed the whole time. A login shell (`zsh -lic`) found it immediately, as did
  `ps` and the daemon socket at `/var/run/docker.sock`. The lesson is about
  evidence, not PATH: "my check found nothing" is weaker than it feels, and
  reporting it as "nothing is installed" states a conclusion the check cannot
  support. Cross-check with a *different mechanism* — a login shell, the package
  manager, the process table — before asserting absence. — Phase 6 follow-up.

- 2026-09-04 — **A dataset-wide proportion is a weighted average, so it drifts
  when the source *mix* drifts even if every underlying rate holds.** `docs/api.md`
  said `salary_min` was NULL in ~70% of rows; the live answer was 74.6%. No rate
  changed: `arbeitnow` carries a salary on 9.09% of its rows against 38.96–100%
  for the Greenhouse sources, and its share of the dataset grew 63.6% → 74.0%.
  Re-weighting the unchanged per-source rates reproduces the drift exactly
  (0.74 × 9.09% + 0.26 × 71.8% = 25.4%, served 25.38%). "Prefer a proportion to
  a row count" is right and incomplete — the durable form is the per-source rate,
  or a claim true under any mix. — found diffing `docs/` against live `/stats`.

---

## AI-WRITTEN register

AI-written files, and the one-line concept behind each. An entry leaves this
list only once it has been written up in `learning-log.md`.

| Date | File | Concept to re-derive | Written up? |
| ---- | ---- | -------------------- | ----------- |
| 2026-09-01 | `pyproject.toml` | Why a `src/` layout needs a build backend at all, and what `uv sync` installs the project *as* — a `.pth` pointing at `src/` **plus** dist-info metadata (the original note had this backwards; `--no-editable` is what copies the package) | ☑ |
| 2026-09-01 | `.gitignore` | Why `data/` and `*.db` are ignored in a repo whose whole job is reading a database | ☑ |
| 2026-09-01 | `docs/design.md` | Both Phase 0 decisions and the measurements behind them: `mode=ro` + path-not-policy config, and why WAL is *declined* rather than deferred | ☑ |
| 2026-09-01 | `src/jobsapi/main.py` | Why an app *factory* rather than a module-level singleton, and what `include_router` does that the `@router.get` decorator did not | ☑ |
| 2026-09-01 | `src/jobsapi/routers/meta.py` | Why `/health` is `async def` while every sqlite3 endpoint must be plain `def` — the rule is about what the body does, not house style | ☑ |
| 2026-09-03 | `tests/test_appdb_snapshot.py` | Why the read-write snapshot needs its own tests rather than the read-only one's: the distinguishing behaviour is the *failure* path — a write inside a failing block must be rolled back, where the read-only version can safely end unconditionally | ☑ |
| 2026-09-03 | `tests/test_snapshot.py` | Why a snapshot must be asserted through its *mechanism* (`conn.in_transaction` during the second read) rather than its symptom — a fixture database has no concurrent writer, so the skew it prevents is unreachable in tests by construction | ☑ |
| 2026-09-01 | `tests/test_health.py` | Why `TestClient` is used as a context manager (lifespan events), and why the OpenAPI schema is asserted on rather than trusted | ☑ |
| 2026-09-01 | `.github/workflows/ci.yml` | What `uv sync --locked` refuses to do, and why CI having no network and no `jobs.db` is the point rather than a limitation | ☑ |
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
| 2026-09-01 | `src/jobsapi/repository.py` (Phase 5) | Why `substr()` belongs in the query and not in the response model, and why `/sources` needs a LEFT JOIN | ☑ |
| 2026-09-01 | `src/jobsapi/routers/runs.py` | Why `RunSummary` deliberately has no `duration_seconds` — `finished_at == started_at` in 62 of 63 finished runs, not all of them, which makes a computed duration *plausible* rather than obviously broken | ☑ |
| 2026-09-01 | `Dockerfile` | Why the build toolchain lives in a stage that never ships, why the database is a volume and not a layer, and why exec-form CMD matters for SIGTERM | ☑ |
| 2026-09-01 | `.dockerignore` | Why a build context that *could* contain a database is a problem even when no COPY references it | ☑ |
| 2026-09-01 | `scripts/make_demo_db.py` | Why a reader-only service ships a schema-creating script at all, and why it is stdlib-only | ☑ |
| 2026-09-01 | `.github/workflows/ci.yml` (docker job) | Why the Dockerfile is verified by querying a running container rather than by a successful build | ☑ |
| 2026-09-01 | `README.md` | Why every documented command was executed before being written down | ☑ |
| 2026-09-01 | `src/jobsapi/appdb.py` | Why the write database is a *second file* with inverted settings — read-write, WAL, foreign_keys ON, schema created here — and why WAL is right here and wrong for jobs.db | ☑ |
| 2026-09-01 | `src/jobsapi/watchlist_repository.py` | Why uniqueness is enforced by the constraint and translated, never by a prior SELECT, and why the translation must be narrow | ☑ |
| 2026-09-01 | `src/jobsapi/routers/watchlists.py` | 201+Location, 204 with an empty body, 409 vs 422, and why PUT and PATCH need different request models | ☑ |
| 2026-09-01 | `src/jobsapi/security.py` | Why one optional key in one dependency is the ceiling, and why a wrong key is 401 rather than 403 | ☑ |
| 2026-09-01 | `tests/test_watchlists.py` | Why the cascade is asserted against the database and the read-only guarantee against the file's bytes | ☑ |
| 2026-09-04 | `docs/api.md` (figure-drift pass) | Why a quoted proportion needs a date *and* a mix: a dataset-wide rate is a weighted average, so it moves when one source outgrows the others while every per-source rate holds | ☑ |
| 2026-09-04 | `README.md` (figure-drift pass) | Why the stranger-facing prose states "roughly three quarters" where the reference doc states 74.6% on a date — a figure that cannot rot beats a figure that must be maintained | ☑ |

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

---

### Phase 4 — 2026-09-01

**Q1. `POST /watchlists` with a name that already exists is 409, but `limit=0`
is 422. Both are "the server would not do what I asked" — what separates them?**

Whether the request is wrong *on its own terms*. `limit=0` breaks a rule stated
in the schema and would be wrong at any moment, against any state, on any
deployment — the client must change the request. A duplicate name is a body
where every field is legal and which *would have succeeded a minute earlier*;
what refuses it is the current state of the collection. Telling that client to
fix its request would be a lie, because the request is fine — the available
names changed. 409 says "your request conflicts with reality", which is the
actionable distinction: pick another name, or accept the thing already exists.

**Q2. Why catch `IntegrityError` rather than SELECT first, when selecting first
gives a clearer message?**

Because selecting first does not work. The `SELECT` and the `INSERT` are two
statements with a gap and no lock held across it, so two concurrent requests can
both find nothing and both insert — rare, intermittent, and unreproducible on
demand. The `UNIQUE` constraint is the only participant that can serialise the
decision, so the code lets it decide and translates the result; the clear
message is reconstructed in the handler, which costs nothing.

The subtlety is that the translation must be **narrow**. Matching any
`IntegrityError` would report a genuine bug in this module's own SQL — a broken
NOT NULL, a mis-specified foreign key — to the client as a 409 it can do nothing
about. Each handler checks *which* constraint failed and re-raises anything it
does not recognise, so a real bug still surfaces as a 500.

**Q3. `PUT` and `PATCH` accept almost the same JSON. Why two models rather than
one with every field optional?**

Because the same absent field means opposite things. In a `PUT` body — a
complete new state — an omitted `description` means the resource has none, so it
is cleared. In a `PATCH` body — only what changes — the same omission means
"leave it alone". One model cannot carry both readings, and collapsing them is
exactly how a rename silently wipes a description.

What makes `PATCH` safe is `model_dump(exclude_unset=True)`, built on
`model_fields_set`, which records the keys the client actually sent. That is
also what lets `{"description": null}` mean "clear it" while omitting the key
means "keep it" — a distinction `description: str | None = None` cannot express
on its own, because both arrive as `None`.

**Q4. `watchlist_items.job_id` has no foreign key. Missing constraint, or
deliberate?**

Deliberate and unavoidable: the row it refers to lives in a different database
file, and SQLite constraints do not span databases. Referential integrity here
cannot be an invariant the engine maintains — only a check performed at write
time against the read-only connection, true at one moment rather than forever.

The design question is what to do when it stops being true. Hiding such items
would make a client's own saved data vanish unexplained; failing the request
would let one dead reference break the whole page. So the item comes back with
`job: null` and `job_missing: true`, and `DELETE` on it deliberately does not
consult `jobs.db` — the case where cleanup matters most is the case where the
source row is gone.

**Q5. The suite passed 153/153 while writing a database into the developer's
home directory. What does that say about the suite?**

That "all tests pass" and "the tests did nothing they should not" are separate
claims, and only the first is automated. The Phase 2 guard pointed
`JOBSAPI_DB_PATH` somewhere impossible and existed to catch precisely this — but
it named one variable, and Phase 4 added another.

The asymmetry is the lesson. A *read* path that reaches ambient state fails when
the resource is absent, which is how the Phase 1 version was caught loudly by
CI. A *write* path creates what is absent, so the identical mistake produces a
green run and a file on someone's disk. For anything that writes, the check is
not the exit code — it is looking at the filesystem afterwards and asking what
is there now that was not there before.


### Documentation fix — stale commit reference — 2026-09-02

**Q1. `git cat-file -t 9172d74` prints `commit`. Why is the reference still
broken?**

Because `cat-file` answers a different question from the one that matters. It
asks whether the object exists in *this clone's* object store; the useful
question is whether it is reachable from a branch anyone else can fetch. The
scaffold history was rewritten before the first push, so the pre-rewrite commit
survives locally — held alive by the reflog and not yet garbage-collected — while
`origin/main` never contained it.

`git merge-base --is-ancestor 9172d74 main` is the check that distinguishes the
two, and it exits non-zero. The failure mode is the nasty kind: the reference
verifies perfectly on the machine that wrote it and resolves to nothing on every
other machine. "It works locally" and "it is in the repository" are separate
claims, and only the second is what a reader gets.

**Q2. Why is setting the repository topics absent from this PR's diff?**

Because topics are not stored in the repository. They are metadata held by
GitHub against the repo record, reachable through the REST API — `gh repo edit
--add-topic` — and nothing in the working tree changes when they are set. So
there is no file to commit and no way to review the change in a diff.

The general shape is worth keeping: a project's state is split between what
version control tracks and what the forge holds beside it. Topics, description,
branch-protection rules, secrets and webhooks all live on the second side. None
of them survive `git clone`, none appear in a PR, and none are restored by
checking out an old tag — which is the argument for keeping anything
load-bearing in the tree, and for not expecting a repository to describe itself
completely.

**Q3. The `CLAUDE.md` fix is the reason this branch exists, and it is not in the
branch. Where did it go?**

Onto disk, and no further. `CLAUDE.md` is listed in `.git/info/exclude`, so it
has never been tracked — `git add -A` skips it silently and `git ls-files
--error-unmatch` denies knowing it.

`.git/info/exclude` is the third place an ignore rule can live, and the one that
behaves least like the others. `.gitignore` is committed and therefore shared;
a global `core.excludesFile` follows the user across repositories; `info/exclude`
is per-clone, inside `.git/`, and travels nowhere. Nothing in the tree records
that the rule exists, which is what makes it easy to trip over — the file looks
present and ordinary in the working directory and is absent from every clone.

So a third category joins Q2's two: tracked content, forge-held metadata, and
files that are deliberately local. The correct response to hitting the third was
to leave it alone. Force-adding with `git add -f` would have worked mechanically
and reversed a decision someone made on purpose.

### Documentation fix — dead links to a private repository — 2026-09-02

**Q1. The links were followed during the ship sequence and worked. Why were
they broken?**

Because they were followed from the account that owns the private repository.
GitHub answers a request for a private resource with `404`, not `403` — it will
not confirm that a repository exists to someone not entitled to know — so the
same URL is a working page for one viewer and a missing page for everyone else.
Nothing about the link's text or the browser's behaviour differs.

This is the general shape of the bug: **a link is a claim about what someone
else can see, and it cannot be tested from inside your own session.** Ambient
credentials silently widen what the tester can reach, so the check passes for
the one person who can never be the victim of its failing. The same trap
produced the Phase 2 defect, where the suite passed because the developer's
real database happened to be on the machine. Both are ambient state mistaken
for a property of the artefact.

The fix is to test the way a stranger arrives — unauthenticated:

    grep -ohE 'https://github\.com/\S+' README.md \
      | while read -r u; do curl -s -o /dev/null -w "%{http_code} $u\n" -L "$u"; done

**Q2. Three links were removed but the politeness statement survived. Why is
that the important half?**

Because the README was carrying a *responsibility* by reference. How the data
was acquired — `robots.txt` honoured, rate limits, no evasion, no personal data
— is a claim this repository makes about its own contents, and it was delegated
to a page no reader could open. Deleting the link alone would have left the
claim unsupported; restating the summary makes the public document answer for
itself.

The rule worth keeping: a public artefact may *credit* a private one, but must
never *depend* on it for content the public artefact is answerable for. Credit
is a courtesy and survives being unresolvable; a dependency is a hole.

### `/runs` gains `duration_seconds` — 2026-09-02

**Q1. The subtraction is one line of SQL. Why is it in `RunSummary` instead?**

Because SQLite has no date type, and the arithmetic would have to go through
`julianday()`, which returns a Julian day *number* — a float counting days.
Converting a microsecond back out of that means dividing by 86,400 and then
multiplying it back, and the format's precision is not spent where this field
needs it: the whole discrimination rests on telling "identical to the
microsecond" from "0.000001 apart".

By the time `RunSummary` is constructed, Pydantic has already parsed both
columns into timezone-aware `datetime` objects, where subtraction is exact and
returns a `timedelta`. So the value is derived where the types are richest.

The general rule this is an instance of: `repository.py` returns a projection
of stored columns, and anything *derived* belongs with the contract. Pushing
derivation into SQL would also have made the field impossible to test without a
database.

**Q2. `null` and `0.0` are both defensible for a legacy row. Why is `null`
right, given the arithmetic really does produce zero?**

Because the question the field answers is "how long did this run take", and for
those rows the honest answer is *not known* — the measurement was never taken.
`0.0` is the arithmetic result of subtracting a number from itself, which is a
different claim: it asserts the run took no time.

What settles it is that the wrong answer is unfalsifiable from inside the
response. A client seeing `0.0` on 62 of 71 runs has nothing to contradict it;
"scrapes are instantaneous" is a coherent reading, and the data agrees. A
client seeing `null` is told directly that the value is missing and cannot
accidentally average it, chart it, or sum it. **A confidently wrong number is
worse than an absent one, because absence announces itself and wrongness does
not.**

`0.0` would also poison aggregates in a way nulls do not: SQL and most chart
libraries skip nulls but happily average zeros.

**Q3. Why does the discriminator use `<=` rather than `==`, when the bug only
ever produced exact equality?**

`==` would be sufficient for the bug that exists. `<=` also covers a
`finished_at` that precedes its `started_at` — impossible from correct code,
reachable through a clock adjustment, a timezone handling error upstream, or a
hand-edited row.

The reasoning is about what each choice costs when it is wrong. With `==`, an
inverted pair serialises as a *negative* duration: a number that passes schema
validation, is not obviously absurd in a table, and pushes the problem onto
every client to defend against. With `<=`, the worst case is that a genuinely
anomalous row is reported as unknown — which is what it is. The two raw
timestamps remain in the response either way, so nothing is concealed; the
anomaly is still visible to anyone who looks, just not laundered into a
plausible-looking figure.

### Cutting `v0.8.0` — 2026-09-02

No new code. The decision worth recording is *when a tag moves*, because this
repo had already answered it the other way once and the two answers look
contradictory until the rule behind them is written down.

**Q1. `v0.6.0` was deliberately left pointing at a commit four documentation
commits behind `main`. Twelve commits later, `v0.8.0` was cut. What is the rule
that produces both answers?**

A tag names a version of the *contract*, not a state of the working tree. The
question is never "has anything changed since the last tag" — something always
has — it is "could a client tell?"

For `v0.6.0`, the answer was no: the commits after it corrected two docstrings
and some prose. A client consuming the API cannot observe either, so a new
version would name a distinction that does not exist, and retagging would move
a published reference for no gain.

For PR #14, the answer was yes: `duration_seconds` is a new field in the `/runs`
response body. Anyone who generated a client from `/openapi.json` at `v0.7.0`
has a model that no longer describes what the service returns. That is exactly
what a version number exists to communicate. **Documentation moves the tip of
the branch; a change to the contract moves the tag.**

The failure mode being avoided is the untagged feature — twelve commits where
the newest release quietly does not match `main`, so "which version has the
duration field?" has no answer anyone can look up.

**Q2. Why `0.8.0` and not `0.7.1`?**

Under semantic versioning the minor is for additive, backwards-compatible
change and the patch is for fixes that alter no interface. `duration_seconds`
adds a field without removing or renaming one — every `v0.7.0` client keeps
working, because a JSON parser ignores keys it was not expecting. So: additive,
compatible, minor.

`0.7.1` would have claimed nothing new is there, which is precisely the thing a
consumer needs to know. The nullability is not what decides this — a nullable
new field is still a new field.

The leading `0.` is doing real work too: it signals the contract is not yet
frozen, which is honest for a build whose `source` enum is still coupled to
another repository's data.

**Q3. `git tag -a` rather than a bare `git tag`. What is the difference, and
why does it matter here?**

A lightweight tag is a ref — a file containing a commit id, and nothing else. An
annotated tag creates a real object in the database with a tagger, a date, a
message, and its own id, which the ref then points at.

The practical consequences: `git describe` prefers annotated tags; `git tag -n`
can show a message only if there is one; and the tag records *who* cut the
release and *when*, which a lightweight tag cannot, since its only content is
the commit it points to. `gh release create --verify-tag` also refuses to
invent a tag that does not already exist — the tag is pushed first, then the
release is attached to it, so the release notes can never end up describing a
tag nobody can check out.

For a release that a stranger might read months later, the message on the tag is
the only explanation that travels with a `git clone`. GitHub release notes live
on the website; the annotation lives in the repository.

### Re-derivation session — `schemas.py`, the query-parameter half — 2026-09-02

The first unaided re-derivation from the syllabus in `PROGRESS.md`, run in
teach-me mode: questions only, no implementation shown until each answer was
committed to. `Pagination` and `JobFilters` were reasoned out from the contract
rather than read. Four defects surfaced from the reasoning, none of which any
test was failing on — recorded here because *how* they surfaced is the
transferable part.

**Q1. Three of the four findings were invisible to a green test suite. What do
they have in common?**

Each is a disagreement between two artefacts that no single artefact can see.
The redundant `model_config` disagrees with the docstring above it. The absent
boundary test disagrees with `docs/api.md`'s published cap. The withdrawn
`pattern` disagrees with the enforced constraint. The hard-coded version
disagrees with the tag.

A test asserts one behaviour at one point. None of these is a wrong behaviour —
every endpoint answered correctly throughout — so there is no request that
returns the wrong status code, and no traceback to read. They are wrong
*relations* between things, and the only way to find one is to hold both sides
up at once. Re-derivation does that structurally: predicting what the code must
be and then comparing puts two versions of the same claim side by side, which
is exactly the comparison a test never makes.

**Q2. The probe written to check whether a `yield` dependency is entered on a
422 printed `events=[]`, which looked like a clean answer. It was wrong. Why,
and what saved it?**

The override function's `request` parameter had no annotation. FastAPI
re-analyses an override's signature exactly like any dependency, so an
un-annotated parameter is not "the request" — it is a required *query
parameter* named `request`. Every request 422'd on the missing parameter before
reaching the endpoint, so the connection genuinely was never opened, and the
empty list was a true observation of the wrong experiment.

What saved it was a control that was supposed to pass: `?limit=1` returned 422
as well, which is impossible if the app is working. Without that case the
conclusion — "FastAPI skips dependencies when validation fails" — would have
been recorded as a verified fact, complete with evidence.

The general form: **an empty result is not evidence of absence until something
has proved the measurement can produce a non-empty one.** A probe needs a case
it must succeed at, or it is only testing itself.

**Q3. `?currency=usd` works, `?currency=dollars` is refused, and the schema
published neither rule. Why did the description survive when the pattern did
not?**

Because Pydantic distinguishes what it can still guarantee from what it cannot.
`pattern` is a machine-checkable claim about the input, and a `BeforeValidator`
may transform the input, so the claim is no longer true of what arrives on the
wire — Pydantic withdraws it rather than publish something false. `description`
is prose: it asserts nothing checkable, so a transform cannot falsify it and it
passes through untouched.

The consequence is that the surviving half is the half no client can enforce. A
human reading `/docs` sees "Case-insensitive; matched uppercase" and complies; a
generated client sees `{"type": "string"}` and permits anything. The
documentation degrades from a contract into advice, and it does so silently,
at exactly the point where the type system stopped being able to speak.

That is the sharpest available answer to the viva question *"what does it mean
when the docs are wrong?"* — here they were not wrong, they were **incomplete**,
which is worse, because incompleteness is not visible from the document itself.

### Read consistency and the sort-map completeness gap — 2026-09-03

**Q1. `jobs.db` is opened `mode=ro` with `PRAGMA query_only = 1`. Why does a
connection that cannot possibly write still need a transaction?**

Because a transaction does two separable jobs — making writes atomic, and fixing
what a reader sees — and only the first is irrelevant here. `mode=ro` constrains
what this connection may *do*; it says nothing about what it *sees* between two
statements. Python's `sqlite3` opens implicit transactions before DML only, so a
sequence of `SELECT`s runs in autocommit with one `SHARED` lock per statement,
taken and released. Two reads are therefore two views, and a scraper commit in
the gap makes them disagree.

The inversion is the thing to keep: read-only is not the case where you can stop
thinking about transactions, it is the case where nothing will start one for you.
A write path gets an implicit transaction whether or not the author thought about
it; a read path gets nothing unless it asks.

**Q2. Why is the snapshot a deferred `BEGIN` rather than `BEGIN IMMEDIATE`, and
what does the answer cost?**

`BEGIN IMMEDIATE` acquires a `RESERVED` lock — a write lock — immediately. This
connection is `mode=ro` with `query_only` on, so SQLite refuses it. Deferred is
the only form available, and it happens to be sufficient: in rollback-journal
mode a read transaction holds `SHARED` from the first read until the end, and
`SHARED` is what an `EXCLUSIVE` commit cannot coexist with.

The cost is that this service can now delay Build 2's commit for the span of two
queries instead of one. That is a widening of an existing window, not a new
hazard — each statement already held `SHARED` on its own. The reason the cost
cannot be avoided traces to Decision 1: WAL is the journal mode where readers
snapshot without blocking writers, and WAL was declined so the container could
mount the data directory read-only. The bill for that decision arrived here.

**Q3. The suite was green before this change and green after. What could the
tests have caught, and what could they never have caught?**

They could never have caught the defect. `conftest.py` builds a temporary
database with no concurrent writer, so the interleaving that produces the skew
cannot occur — the failing case is unreachable by construction, not merely
untested. No amount of assertion on response bodies would have found it.

What is testable is the *mechanism*: that the count runs while
`conn.in_transaction` is true, that the transaction is released afterwards, that
it is released even when the body raises, and that `BEGIN IMMEDIATE` is genuinely
refused on this connection so the deferred form is documented as forced rather
than preferred. That is the general move — when the symptom is unreachable in the
test environment, assert the property that prevents it instead.

The same session found the mirror-image case in `_SORT_COLUMNS`: a defect that is
unreachable *today* because the map happens to be complete, and becomes a `500`
the moment someone adds an enum member. There the completeness assertion is one
line, `set(_SORT_COLUMNS) == set(SortField)`, and it converts a future live
failure into a present test failure.

### An empty text filter becomes a 422 — 2026-09-03

**Q1. Why does this fix belong in `schemas.py` rather than in `_build_where`,
given the bug is visible in `_build_where`?**

Because the question is what the API *accepts*, not what the SQL builder does
with what it accepted. Changing the truthiness test to `is not None` would have
made the service apply `LIKE '%%'` for an empty term — a different answer, still
chosen unilaterally, and still not written anywhere. The contract is the only
place where "an empty search is not a search" can be *stated* rather than
implemented, and stating it is what puts `minLength: 1` into `/openapi.json`
where a generated client can enforce it.

The general form: when a value's legality is in question, the fix goes where
legality is declared. A repair in the consumer leaves the published contract
still permitting the thing.

**Q2. `docs/api.md` already contained the reasoning for this decision. Why did
it not prevent the defect?**

Because principles do not apply themselves. The document rejects unknown
parameters on the grounds that a request silently returning unfiltered results
is worse than an error, since the client believes it filtered. `?q=` is that
sentence exactly — but the two cases look nothing alike from outside: one is a
parameter the service has never heard of, the other a parameter it knows well
carrying an empty value. The shared structure is only visible once both are
described in terms of *what the client is led to believe*.

So auditing a document against its own principles is separate work from writing
it, and it is the work that finds this class of bug.

**Q3. `currency` was enforced but unpublished; `minLength` here is enforced *and*
published. What is the actual rule?**

Pydantic publishes a constraint only while it can still guarantee the constraint
describes what arrives on the wire. `currency` carries a `BeforeValidator` that
uppercases, so `pattern` no longer describes the input and Pydantic withdraws it.
`q` and `company` carry no validator, so nothing intervenes between the wire
value and the check, and `minLength` survives into the schema.

The rule is therefore not "constraints are published" but "constraints are
published where no transform precedes them". Which means the *thesis* of this
build — the docs are generated from the types — holds with a condition attached,
and the condition is invisible from the document. That is why the test asserts
the published schema and not only the status code: the two can disagree, and this
build has already shipped one release where they did.

### The image that did not shrink — 2026-09-03

**Q1. Two size figures for one unchanged recipe, taken a day apart. What is the
first question, and why is "what changed in the Dockerfile" the wrong one?**

The first question is *what quantity is each number*. "What changed" presumes a
change occurred, and that presumption survives contact with the evidence because
a plausible culprit is nearly always available — here, `.dockerignore` gaining
`.venv` would have explained the gap almost exactly (266 − 58.7 ≈ 207 MB, the
right order for a dev virtualenv in one `COPY` layer). The arithmetic would have
supported a conclusion that was false.

What killed it was history: `git log -- Dockerfile .dockerignore` shows the last
touch on 2026-09-01, *before* the larger measurement, with `.venv` and `data/`
already excluded. The explanation was ruled out by the record rather than by
argument.

**Q2. The old command was never written down. Why did that not block the
investigation?**

Because a local probe existed that needed no history at all: build the image, ask
Docker its size, then measure the actual filesystem inside a running container.
`.Size` reported 58,673,663 bytes while `du -sx /` measured 196 MB of files — and
no image built `FROM python:3.13-slim` can hold 196 MB of files in 58 MB of
filesystem. The reported figure is therefore not a filesystem size, proved today,
on this machine, without recovering anything.

The general move: prefer the hypothesis that can be tested now over the one that
requires reconstructing a configuration that is gone.

**Q3. So what was actually defective?**

The record. Docker had moved to the containerd image store, which reports
compressed sizes, and the figure written down had no way to say what it was — so
the toolchain changed underneath it silently and the number kept looking like a
number. Five commands report five different quantities for one image. Writing
`266 MB` without writing which command produced it makes the value
unfalsifiable: it cannot be reproduced, and it cannot be compared.

The same failure shape as the version check that this build already paid for:
`v0.8.0` was internally consistent and wrong, and only an external reading of the
artefact could tell. Here too, the artefact had to be asked directly.

### Re-derivation session — `routers/jobs.py` — 2026-09-03

**Q1. `GET /jobs` and `GET /jobs/{job_id}` read the same table and return
different shapes. Why two response models rather than one with `description`
optional?**

Three reasons, and the first is about this dataset rather than design taste.
`description` is NULL in **0.76%** of rows, so `null` already means "the scraper
recorded no description". In a merged model, `null` on a list item would mean
"not sent" and `null` on a detail response would mean "not recorded" — identical
JSON, no way for a client to tell them apart. The sentinel is taken.

Second, one model plus `response_model_exclude` makes the omission a per-route
flag that a refactor can drop, and nothing fails when it does; the response just
gets heavier. Two models make it structurally unavailable — `JobSummary` has no
field to put it in. Third, `/openapi.json` would advertise one schema for both, so
a generated client gets a `description` attribute that is permanently `None` on
list items and `/docs` cannot say which endpoint populates it.

**Q2. `response_model` keeps `description` out of a list response. What does it
actually save, and what does it not?**

Only the serialisation and the wire. The disk read and the Python objects are
avoided one layer down, by `_SUMMARY_COLUMNS` not selecting the column. If the
repository selected `description` and the model dropped it, the service would
have paid to read **21.7 MB** off disk, build the strings and hand them to
Pydantic purely to discard them.

The model is the guarantee; the query is the saving; they are not substitutes.
`list_job_changes` makes the same argument in the other direction — it truncates
with `substr()` in SQL rather than in the response model, for exactly this reason.

At runtime `response_model` does two things at two different times: at startup it
supplies the route's 200 schema for `/openapi.json`, and per request it
*validates* the returned value into the model, drops undeclared fields, then
dumps. Not a serialisation step — a validation step. A value that does not fit
raises `ResponseValidationError` → 500, which is the right code: the server broke
its own published contract. On a 100-item page that is 100 model constructions
and ~1,200 field validations.

**Q3. A future `/jobs/recent` declared below `/jobs/{job_id}` is swallowed. What
does the client actually see, and why can the generated docs not help?**

A **422 naming `job_id`** — a parameter the client never sent — on a path that
`/docs` lists. The parameterised route matches first (Starlette takes the first
full match in declaration order, with no specificity ranking), `"recent"` is
validated against `int ≥ 1`, and validation fails before the handler runs.

`/docs` cannot help because both routes are registered: the schema is correct
about what exists and says nothing about which one answers. An ordering bug is
invisible to a document generated from types.

Worth recording that the `int` annotation is what makes this loud. Typed `str`,
the same shadowing returns a 404 for a job named "recent", or a 200 of the wrong
shape — a silent mis-route. The typed path parameter earns its place twice.

### Closing the application-database snapshot — 2026-09-03

**Q1. `db.read_snapshot` already existed and did the right thing. Why was
importing it into the write path the wrong move?**

Because its correctness argument does not travel. It ends its transaction
unconditionally and suppresses any error from doing so, and that is sound
*because the connection cannot write*: ending a transaction that wrote nothing
discards nothing, so a failure there is tidy-up noise. Put the same three lines
on a read-write connection and a swallowed `COMMIT` failure becomes data loss
reported to the client as success.

The scoping note in that docstring existed for precisely this moment — it was
written when the function was, on the grounds that the pattern is right in one
file and wrong one file over, which is the kind of thing that gets copied. It
earned itself a day later.

**Q2. Why was this the cheaper of the two open threads, when it looked like the
same work?**

Because the cost that made the `jobs.db` version a judgment call is absent here.
That was a locking trade, and it exists only because `jobs.db` is
`journal_mode=delete`: a read transaction holds `SHARED`, so a consistent read
makes Build 2's commit wait. The application database is WAL, where readers
snapshot without blocking the writer — the property `design.md` §1 named as
unavailable for `jobs.db` and gave up to keep the bind mount read-only.

The thread had been recorded as if it inherited that difficulty. Re-deriving why
the first one was hard is what showed the second one was not.

**Q3. What is different about the 404 race on `/watchlists/{id}/jobs` compared
with `/jobs/{id}/changes`?**

Only who the competing writer is, and it changes how likely the race is rather
than whether it exists. For `jobs.db` it is Build 2's scraper, an external
process committing a few dozen times a day. Here it is **this service answering
another request** — a `DELETE /watchlists/{id}` arriving between the existence
check and the count is an ordinary interleaving, not a rare one.

The consequence is the same either way: the endpoint would report a 200 with a
total of zero for a watchlist that no longer exists, collapsing "it is gone" into
"it is empty" — the same two facts the sub-resource exists to keep apart.

### Re-derivation — `schemas.py` response models — 2026-09-03

**Q1. Every response field is a type. Why is exactly one of them a liability,
and what makes it invisible to the check that already exists?**

Because one type is *narrower than its column*. Ten of the eleven `JobSummary`
fields are as wide as or wider than what SQLite can hand back: `str | None`
accepts any TEXT, `int | None` any INTEGER, and `datetime` accepts a bare date
(it reads as midnight). `posted_at: date` is the exception — it rejects a value
SQLite is perfectly happy to store, and Pydantic v2 is explicit about it:
`"Datetimes provided to dates should have zero time"`.

`PRAGMA table_info` cannot see this because it is not a schema fact. The column
is present, correctly named, and TEXT — which is precisely the affinity that
promises nothing about the values. `verify_schema` checks the shape of the
container while this drift happens inside it.

Worth recording what the check does *not* cover: `remote: bool | None` is a
second narrowing, since a stored `2` would fail the same way. It is left
unguarded because the column is Build 2's own tri-state boolean and only ever
holds NULL/0/1 (verified: 1,212 / 2,785 / 227 rows), whereas `posted_at`'s
format is a *string convention* with nothing enforcing it.

**Q2. The bad row is one row out of 4,224. Why is the blast radius the whole
page, and why does that turn a documentation note into a code change?**

Because `JobPage.items` is `list[JobSummary]`, and a list validates as a unit.
There is no partial success: the page either builds or it does not. So one
malformed value takes out every request whose page contains it — and under the
default `sort=posted_at desc` a newly-inserted bad row sorts to page one, where
everybody lands.

That asymmetry is what settled it. The other couplings in this build (the
`source` enum, `LIKE`'s ASCII case-folding) degrade *locally* — one filter
returns nothing, one query misses an accent — so documenting the bound is a
proportionate response. This one converts a single upstream write into a
service that answers 500 to its main endpoint, so it earns a gate.

**Q3. The gate is admittedly incomplete. Why ship a check that cannot promise
what it appears to promise?**

It is a startup sample: a row written after boot still fails when served. The
honest claim is narrow — *drift already in the file is named at startup instead
of surfacing as a 500 on whichever page is unlucky* — and the docstring says so
in those words rather than implying a per-request guarantee.

That is the same trade `verify_schema` already makes and never states: a column
dropped after startup is equally invisible to it. Two failure modes, one loud at
boot and one still latent, is strictly better than two latent — and the cost is
one covering-index search on `idx_jobs_posted`, `LIMIT 1`, 6.1 ms for both gates
together against the real 4,224-row database.

The related discipline: the GLOB pattern is a *bound parameter*, not an
f-string, even though it is a module constant and interpolating it would be
safe. A GLOB pattern is a value, and this build's rule is that values go through
placeholders — the exception that is safe today is the example someone copies
tomorrow.

### Re-derivation — `repository.py` Phase 5 — 2026-09-03

**Q1. `/sources` joins two tables and counts rows. What is the trap in that
sentence, and what disarms it here?**

Fan-out. `FROM jobs j JOIN runs r ON r.source = j.source` produces one row per
*(job, run)* pair, so `COUNT(*)` would report jobs × runs — a source with 500
jobs and 12 runs reporting 6,000. The count is wrong by a factor nobody can spot
from the outside, because it is still a plausible number.

What disarms it is that the join condition is `r.id = (SELECT MAX(id) FROM runs
WHERE source = j.source)` — a correlated subquery matching **exactly one** run
row per source, so the grain of the result stays one row per job and `COUNT(*)`
counts jobs. The `LEFT` is a second, separate guarantee: it keeps a source whose
subquery returns NULL.

The general rule worth carrying: an aggregate over a join is only meaningful if
you can say what one row of the joined result *is*. Here it is "one job, plus
that source's latest run", which is countable. "One job-run pair" is not.

**Q2. The docstring claimed the LEFT JOIN protects a source with runs and no
jobs. Why is that false, and why did it survive review?**

Because a LEFT JOIN preserves rows from the **driving** table, and the driving
table is `jobs`. A source with run rows and no jobs contributes nothing to
`FROM jobs`, so there is no row to preserve and no group to emit — it is absent
regardless of the join type. The claim describes a RIGHT JOIN, or a driving
table this query does not have.

It survived because it was never false *in observation*. All eight real sources
appear in both tables, and the fixture's four do too, so every test and every
manual check agreed with the wrong sentence and the right one equally. This is
the second time in this build that a claim was protected by data rather than by
being true — the first was the `/sources` LEFT JOIN itself, already recorded as
"defensive, not load-bearing". Same query, same blind spot, one level down.

The fix is a test that constructs the state reality does not provide: a run row
for `lever:ghost`, a source with no jobs, asserted absent.

**Q3. `/stats` takes a snapshot so its six reads agree. What does that
guarantee, and what does it not?**

It guarantees they all describe **one state of the database** — no scraper
commit lands between the fourth read and the fifth, so the counts cannot be from
four different worlds.

It does not guarantee they describe that state *consistently*. `remote` is
reported twice by two different queries — as a coverage row from the SUM-per-
field scan, and as the tri-state split from its own SELECT — and a snapshot makes
them see identical rows while saying nothing about whether the two expressions
compute the same thing. Nothing checked that `coverage.remote.missing` equals
`remote_unknown`, that `present + missing` equals `total_jobs`, or that the
ratio matches its own numerator. Those are the invariants a client assumes
without being told.

Snapshot isolation is about *when* the reads happen. Agreement is about *what
they compute*, and only an assertion covers that. Four tests now do.

The empty database is the same gap from the other end: `coverage` divides by
`COUNT(*)`, and `SUM` over no rows is NULL rather than 0. Both guards existed —
`if total else 0.0`, and `or 0` — and neither was exercised by any test, so the
code was right by intention rather than by evidence.

---

## 2026-09-03 — explain-back: tracking `CLAUDE.md` (reverted the same day)

No code changed here, so the questions are about the mechanism that hid the
file rather than about a construct.

**The change this describes was reverted at the owner's instruction (PR #32).**
`CLAUDE.md` is untracked again and stays that way. The mechanism below is still
correct and still worth knowing — it is *why* the file had been invisible to
every other clone — but the conclusion drawn from it, that tracking was
therefore the right fix, was not the owner's call to make on their behalf. The
file is their working notes. Publishing to a public repo is one-way, and the
question to ask first was "do you want this published", not "is it safe to
publish", which is the only one that got asked. Recorded rather than deleted,
because a reversed decision with its reasoning intact is worth more than a
clean log.

**Q1. `.gitignore` and `.git/info/exclude` both cause `git status` to stay
quiet. What is the difference, and which one caused the file to go missing for
everyone else?**

`.gitignore` is a tracked file, so its rules are part of the repository and
every clone gets them. `.git/info/exclude` lives inside `.git/`, which is never
committed — nothing in `.git/info/` can be pushed, fetched, or cloned. Its
rules are therefore per-clone and invisible to everybody else.

`CLAUDE.md` was excluded through the second one, and that is precisely why the
symptom was confusing rather than obvious. On the authoring machine the file
exists, opens, and is quietly ignored, so the repository *looks* complete. On
any other clone the file was never sent, so it does not exist at all. There is
no error on either side, and the two views disagree without either of them
reporting anything — which is the same failure shape as PR #13, where the
README's links resolved fine from an account that could see the private repo.

The general rule: `.gitignore` for anything every clone should ignore (build
output, `.venv`), `.git/info/exclude` only for something local to *this*
working copy that no collaborator should be told about.

**Q2. Removing the exclude entry did not add the file. Why not, and would
leaving the entry in place have blocked the `git add`?**

Because an ignore rule and the index are separate mechanisms. Ignore rules only
decide whether an **untracked** path is reported by `git status` and picked up
by a wildcard `git add`; they never move anything into the index by themselves.
Removing the line made the path visible, and `git add CLAUDE.md` is what
actually staged it.

And no, the entry would not have blocked it: `git add` on an explicitly named
path ignores the ignore rules — it is only wildcards that skip ignored files,
and even then `-f` overrides. More to the point, ignore rules stop applying
entirely once a path is tracked, so leaving the line in would have been inert
*and* misleading: a future reader would read `CLAUDE.md` in the exclude file and
conclude the file is untracked, which is exactly the wrong conclusion. The entry
was removed because a rule with no effect still carries a claim.

**Q3. Why check for private URLs before tracking a file that had been on disk
for three days?**

Because the repository is public and the file was written under the assumption
that nobody else would read it. Its exclude comment said "never published", and
prose written for an audience of one records things — internal paths, private
repo links, working credentials — that prose written for strangers does not.
Publishing is the moment those assumptions become wrong, and it is one-way: a
pushed commit is in the history whether or not a later commit removes it.

This project has already paid for skipping that check once. PR #13 fixed three
README links pointing at the private `job-listing-scraper`, shipped in `v0.6.0`
and missed by two full ship sequences, because a link is only tested by
following it from an account that cannot see the target. The scan here was
clean — no links at all, no credentials, and the `~/code/...` paths are
tilde-relative rather than absolute — but the cost of running it was one grep
against a known-expensive class of mistake.

---

## 2026-09-03 — explain-back: untracking, and purging from history

Covers PRs #32 and #33. Still no code — the questions are about Git's object
model, which is what the day actually exercised.

**Q1. `git rm --cached CLAUDE.md` is documented as removing a file from the
index while leaving it on disk. The file was deleted from disk anyway. Where
did the guarantee stop applying?**

It never applied outside the branch it ran on. `--cached` removes the path from
the index of the commit being built, so the *branch* records a deletion while
the working tree keeps the file — true, and it held: after the commit the file
was still there, 32,782 bytes.

The loss happened at `git switch main && git pull`. On `main` the path was
still **tracked**, because the untracking commit lived only on the feature
branch. Pulling the merge brought in a commit that deletes a tracked path, and
deleting a tracked path is a working-tree operation — Git removes the file,
which is exactly what it should do. Nothing malfunctioned. The mental model was
just one branch too narrow: `--cached` protects the copy in the tree where it
runs, not a copy on some other branch that has not seen the deletion yet.

The general shape: a working-tree file is safe from a *staging* command and not
from a *checkout*. `git rm --cached` is the first; every branch switch, pull,
reset and merge is the second.

**Q2. `filter-repo --invert-paths --path CLAUDE.md` rewrote 71 commits when 2
contained the file, and the trees either side were byte-identical. What changed,
and why does one commit's change reach commits that predate the file?**

The signature. GitHub signs the merge commits it creates, and a commit object
contains a `gpgsig` header alongside its tree, parents, author and message.
`filter-repo` strips signatures unconditionally — it must, because a signature
is computed over the commit's bytes and a rewritten commit has different bytes,
so the only alternative to dropping it is keeping one that no longer verifies.

Dropping a header changes the object, and a commit's SHA is the hash of its
full contents. So a signed commit gets a new SHA even when its tree is
untouched. And a commit names its parents *by SHA*, so the moment one ancestor's
id changes, every descendant's contents change too, and the rewrite walks
forward through the whole graph. The earliest signed commit therefore sets the
blast radius — which here was a merge from days before the file existed.

Trees are shared and content-addressed, which is why `ceddeae…` was identical
on both sides: the *contents* of that commit's snapshot never changed. Only the
envelope did. The lesson is that "which commits contain the file" is the wrong
question; "which commits' bytes change, plus everything downstream" is the right
one.

**Q3. The purge succeeded and the file is still downloadable from GitHub. Is
that a failed rewrite?**

No — it is the difference between a repository and a host. The rewrite did what
it claims: no ref in the repository reaches a tree containing the file, which
`git rev-list --all --objects | grep` confirms. Git never *deletes* on a
force-push; it repoints a ref and leaves the orphaned objects for garbage
collection.

GitHub then declines to collect them. It keeps unreachable objects served by
SHA, and `refs/pull/31/head` is a real ref that keeps the old commits reachable
on its side no matter what `main` looks like — which is why the pull request
still renders the full diff. Verified rather than assumed: the API returned all
32,782 bytes from both `af3bd18` and the pull ref after the push.

So a purge is two operations against two systems, and only the first is Git's.
The second is a request to the host. The practical consequence is that a rewrite
is not a remediation for a leaked credential — rotating it is — because the
window between push and purge is unbounded and the object stays fetchable
throughout.

---

## 2026-09-04 — explain-back: the drifted figures in `docs/api.md` and `README.md`

**Q1. `docs/design.md` states the rule these edits enforce — "figures quoted
anywhere in `docs/` are snapshots and carry the date they were taken" — and
`docs/design.md` was not edited. Why is the file that states the convention the
one file left alone?**

Because it is the only one already complying, and its figures are load-bearing
in a way the others' are not. Its tables open with "Taken 2026-09-01 **at Phase
0** … left as measured — the decisions they justify were made against them."
That is a dated snapshot doing exactly what the convention asks, and the numbers
are evidence for a decision that was actually made against them. Refreshing them
would falsify the record: Decision 1 was argued against a 58 MB file with 3,105
rows, and rewriting those to today's values would make the reasoning look as
though it had considered data that did not exist yet.

So the two files split by *purpose*, not by age. `design.md` is a decision record
— its figures are historical and must be frozen. `api.md` is a reference a client
reads to predict the live service — its figures describe the present and must
either track it or say when they were taken. The same number is correct frozen in
one file and stale in the other, which is why "update the figures in `docs/`" was
the wrong instruction to give myself and "update the figures that claim to
describe now" was the right one.

**Q2. `salary_min` NULL went 69% → 70.4% → 74.6% while no source changed how
often it reports a salary. Where did 4 points come from?**

From the weights, not the rates. The dataset-wide figure is a weighted average of
per-source rates, and one source's share grew.

`arbeitnow` carries `salary_min` on 9.09% of its rows; every Greenhouse source
runs 38.96% to 100%. `arbeitnow`'s share of the dataset went from 63.6% to 74.0%
in three days, so the cheapest rows crowded out the richest ones. Re-weighting
the unchanged rates predicts the observed value: 0.74 × 9.09% + 0.26 × 71.8% =
25.4% present, against 25.38% served. Nothing about salary reporting changed —
the composition did.

That share is independently checkable, which is what makes this more than a
story: `remote` is non-NULL on `arbeitnow` rows and only those (3,531 of 3,531,
and 3,531 non-NULL dataset-wide). So the documented `remote` coverage of 63.64%
*was* `arbeitnow`'s share at the time it was written, and the 74.01% now served
is its share today. The stale figure recorded the mix that caused the drift.

The correction to the earlier lesson: `design.md` concluded "the absolute numbers
moved by roughly 13% in a day. **The proportions did not**." True over that day,
and it stopped being true over three. A proportion is stabler than a count, not
stable — and one interval is not a trend.

**Q3. Both files now say the same thing in different words: `api.md` says
"74.6% on 2026-09-04", `README.md` says "roughly three quarters" and no date.
Why is the inconsistency deliberate?**

Because they have different maintenance costs and different readers. A dated
precise figure is honest but must be re-measured or it becomes exactly the defect
being fixed here; a rounded claim needs no maintenance because "roughly three
quarters" survives the next scrape and the one after it.

`api.md` is the reference someone reads next to the running service, so precision
earns its keep — and the date plus "compare against `/stats`, never against this
table" tells the reader which of the two to trust when they disagree. `README.md`
is read once by a stranger deciding whether the project is worth their time; a
figure to two decimal places tells them nothing extra and quietly commits the
project to maintaining it in a third place.

This is the `v0.8.0` version-drift lesson one layer up — a duplicated fact is
fixed by deletion, not by diligence. Deletion is unavailable here, since a
reference doc that shows no numbers teaches less than one that does, so the next
best thing is to keep one authoritative copy (`/stats`, computed at request
time), date the copy that must exist, and round the copy that does not need to be
exact. The remaining risk is only that the dated table ages, and it now says so
in its own text.
