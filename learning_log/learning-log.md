# Learning log — Build 3 (Job Listings API)

One entry per problem, written as the build proceeds. Newest at the top.

Template:

```
## YYYY-MM-DD — one-line title
- **What broke:**
- **Why it happened:**
- **What it teaches:**
- **Where it was applied:**
- **How to detect it next time:**
```

Two kinds of entry appear below. Most record something that actually failed.
A few record a failure that was *designed out* before it could happen — those
are marked, because the honest answer to "what broke" is "nothing yet, and that
is precisely the problem: this class of bug produces no error when it fires."

The viva follows the entries, in Part 2.

---

# Part 1 — Entries

## 2026-09-01 — A write path made the test suite pollute the developer's machine, silently

- **What broke:** `pytest` reported 153 passed and created a real database at
  `~/.local/share/jobsapi/app.db`. Nothing failed; nothing said so.
- **Why it happened:** the autouse fixture that points `JOBSAPI_DB_PATH` at an
  impossible path — written in Phase 2 precisely to stop tests reaching ambient
  state — knew nothing about `JOBSAPI_APP_DB_PATH`, added in Phase 4. Every
  `TestClient` therefore ran the lifespan against the default application
  database path.
- **What it teaches:** the same class of bug as Part 1 entry 4, inverted, and the
  inversion is the lesson. A read path that reaches ambient state **fails**
  when the resource is absent, which is how Phase 1's version was caught. A
  write path *creates* what is absent, so it succeeds — and a green suite is not
  evidence of anything. For code that writes, the question is not "did a test
  fail" but "what exists now that did not exist before". A guard against ambient
  resources also has to be *extended* whenever a new one is introduced; it is not
  written once.
- **Where it was applied:** `tests/conftest.py` — `_never_the_real_database` now
  redirects `JOBSAPI_APP_DB_PATH` into `tmp_path` and clears `JOBSAPI_API_KEY`;
  a new `app_db_path` fixture feeds `settings`.
- **How to detect it next time:** after adding any write, delete whatever the
  code could have created, run the suite, and look at the filesystem rather than
  the exit code. `ls` is the assertion that no test was going to make.

## 2026-09-01 — The obvious way to write a PATCH endpoint silently destroys data

- **What broke:** *Designed out.* Left alone, `PATCH {"name": "x"}` would have
  wiped the resource's `description` and returned `200`.
- **Why it happens:** a partial-update model has every field optional, so each
  one defaults to `None`. `model_dump()` then emits `{"name": "x",
  "description": None}` — indistinguishable from a client that explicitly asked
  to clear the description. The endpoint writes both columns and the data is
  gone, with a success status and nothing in any log.
- **What it teaches:** for a partial update, "absent" and "explicitly null" are
  two different instructions, and a plain `str | None = None` cannot represent
  the difference. Pydantic keeps the distinction in `model_fields_set`, which
  records the keys the client actually sent; `model_dump(exclude_unset=True)` is
  what surfaces it. This is also the sharpest illustration of why `PUT` and
  `PATCH` need *different request models* rather than one with everything
  optional: for `PUT`, an omitted field genuinely does mean "clear it", and the
  same model cannot mean both.
- **Where it was applied:** `WatchlistPatch` versus `WatchlistReplace` in
  `schemas.py`; `patch_watchlist` in `routers/watchlists.py` passes
  `model_dump(exclude_unset=True)` to a repository that builds its SET clause
  from the keys present. Empty patches are a 422 rather than a no-op 200.
- **How to detect it next time:** the test is not "does PATCH change the field I
  sent" — that passes either way. It is "does PATCH leave the field I did *not*
  send alone", and it needs a resource with two populated fields to be visible
  at all.

## 2026-09-01 — Check-then-insert is a race the database is there to settle

- **What broke:** *Designed out.* `SELECT` for the name, and `INSERT` if nothing
  came back, is the obvious way to produce a 409 — and two concurrent requests
  can both find nothing and both insert.
- **Why it happens:** the check and the write are two statements with a gap
  between them, and nothing holds a lock across it. The window is small and
  therefore the bug is rare, intermittent, and impossible to reproduce on
  demand — the worst combination. Under SQLite's default isolation the duplicate
  simply lands.
- **What it teaches:** uniqueness is the database's job because the database is
  the only participant that can serialise the decision. The correct shape is to
  attempt the write and translate the constraint violation:
  `sqlite3.IntegrityError` becomes a domain `DuplicateResource`, which the
  handler turns into a 409. The translation must be **narrow** — matching the
  specific constraint — or a genuine bug in the module's own SQL gets reported
  to the client as a conflict it can do nothing about.
- **Where it was applied:** `create_watchlist`, `replace_watchlist`,
  `update_watchlist` and `add_item` in `watchlist_repository.py`, each checking
  which constraint failed before deciding between 409, 404 and re-raising.
- **How to detect it next time:** any `SELECT` whose only purpose is to decide
  whether a following `INSERT` is allowed. If a constraint could enforce the
  same rule, the `SELECT` is a race wearing a check's clothing.

## 2026-09-01 — SQLite ignores foreign keys unless every connection asks for them

- **What broke:** *Designed out.* `ON DELETE CASCADE` in the schema does nothing
  by default: deleting a watchlist would leave its items behind as orphans, with
  no error anywhere.
- **Why it happens:** SQLite ships with foreign key enforcement **off** for
  backwards compatibility, and it is a per-*connection* setting, not a property
  of the file. So the constraint is parsed and stored and then not enforced —
  the schema looks correct under inspection and behaves as though the clause
  were a comment.
- **What it teaches:** a declared constraint is not an enforced one, and the
  difference here is a single `PRAGMA` that has to be on *every* connection the
  application opens. It generalises: a database's defaults are part of its
  contract, and the ones chosen for backwards compatibility are exactly the ones
  that will surprise you.
- **Where it was applied:** `PRAGMA foreign_keys = ON` in `appdb.connect`, which
  is why the cascade in `delete_watchlist` works at all.
- **How to detect it next time:** test the cascade against the *database*, not
  the API. `test_cascade_really_deleted_the_rows` opens the file afterwards and
  counts rows — an API-level check would have passed anyway, because the orphans
  are invisible through an endpoint that filters by watchlist id.

## 2026-09-01 — The recorded answer to "what does `include_router` do" was true of an older FastAPI

- **What broke:** Nothing in the service — a *record* broke. Phase 1's
  explain-back answer (gap-log, Q1) states that `app.include_router(...)`
  "copies those routes onto the `FastAPI` instance". Checking it against the
  installed version while writing this log: `[type(r) for r in app.routes]`
  returns four `starlette.routing.Route` objects (`/openapi.json`, `/docs`,
  `/docs/oauth2-redirect`, `/redoc`) and three `fastapi.routing._IncludedRouter`
  objects whose `.path` is `None`. There are no `APIRoute` objects on the app at
  all, so the sentence as written is false on FastAPI 0.141.1.
- **Why it happened:** The answer described the mechanism as it worked for years
  and was written from that model rather than from the installed source. FastAPI
  0.141.1 keeps a *reference* to the original router (`_IncludedRouter.original_router`)
  plus an `include_context` carrying the prefix, tags and dependencies, and
  computes the effective routes lazily — cached against
  `original_router._get_routes_version()` so a router mutated after inclusion is
  still picked up. The observable behaviour is the same; the mechanism is not.
- **What it teaches:** Two things. First, the *conclusions* drawn from the old
  model survive — a router is still an independent object that can be built and
  tested alone, and can still be mounted twice under different prefixes; that is
  now literally true rather than true by copying. Second, and more usefully:
  "every line is explained" decays. An explanation is pinned to a version, and a
  library can change the machinery under a correct-sounding sentence without any
  test going red. The check that caught this cost one line of Python.
- **Where it was applied:** Correction appended to gap-log Phase 1 Q1; the
  mechanism is stated for the installed version in Part 2, "Framework mechanics",
  Q1. Also re-verified while here: the declaration-order rule still holds on
  0.141.1 — a two-route app with `/jobs/{job_id}` declared above `/jobs/recent`
  returns **422** (`int_parsing`, `input: "recent"`) for `GET /jobs/recent`, and
  the same app with the literal declared first returns 200. The
  `_low_priority_routes` list that 0.141.1 adds is populated only from
  `_frontend_routes`, so it does not rescue a mis-ordered literal sibling.
- **How to detect it next time:** Before trusting a written explanation of a
  library's internals, run the one-liner that would show it — here,
  `[type(r).__name__ for r in app.routes]`. Explanations of *our* code are pinned
  by tests; explanations of someone else's code are pinned by nothing.

## 2026-09-01 — A config option on a subclass made the documented contract untrue on a sibling endpoint

- **What broke:** `docs/api.md` promises that unknown query parameters are
  rejected. `GET /jobs?colour=red` returned 422 as documented; `GET /runs?colour=red`
  returned **200**, silently ignoring the parameter. Caught by a test written for
  `/runs`, not by reading the code.
- **Why it happened:** `model_config = ConfigDict(extra="forbid")` was declared on
  `JobFilters`. `/runs` and `/jobs/{id}/changes` bind `Pagination`, the *base*
  class, which had no such config — so the rule existed on exactly one of the
  three list endpoints. Nothing about the code looked wrong: the option was
  present, spelled correctly, and doing exactly what it was asked to do on the
  class it was attached to.
- **What it teaches:** Where a configuration option *lives* is a contract
  decision, not a detail of placement. A rule stated once in prose
  ("unknown parameters are rejected") and enforced on one subclass out of three
  is a rule that is true of the documentation and false of the service. The fix
  is not vigilance about remembering to repeat the option — it is moving it to
  the single place every endpoint already inherits from, so the rule cannot be
  true in one place and false in another.
- **Where it was applied:** `src/jobsapi/schemas.py` — `extra="forbid"` moved to
  `Pagination`; `JobFilters` retains it, which is now redundant but harmless and
  keeps the intent legible at the point a reader is most likely to look.
- **How to detect it next time:** For every rule `docs/api.md` states in the
  singular ("errors use one envelope", "unknown parameters are rejected"), write
  the test against *every* endpoint the sentence covers, not the one it was
  written for. A promise made about the API is not tested by testing the route
  that motivated it.

## 2026-09-01 — A log assertion that could only pass if fixtures happened to run in the right order

- **What broke:** A Phase 5 test asserting that a request emits a JSON log line
  saw empty output under `capsys`, despite the line being emitted correctly when
  the server was run by hand.
- **Why it happened:** `logging.StreamHandler(sys.stdout)` resolves and stores
  the stream object **at construction time**. `configure_logging` runs inside
  `create_app`, so the handler captured whatever `sys.stdout` was at app-build
  time. `capsys` replaces `sys.stdout` afterwards; the handler kept writing to
  the original object, which the fixture was no longer watching. Whether the
  assertion could pass depended entirely on whether the app fixture was
  constructed before or after capture started — a property of fixture *ordering*,
  not of the code under test.
- **What it teaches:** A test whose outcome depends on the order two fixtures
  happen to run in is not testing what it claims to; it will pass, then fail on a
  day when something unrelated changes the ordering, and the failure will point
  nowhere near the cause. When the thing under test is the logging *pipeline*,
  the right seam is the pipeline's own extension point — a `logging.Handler`
  attached to the logger — not the process-global stream underneath it. That
  version is order-independent *and* exercises the real `JsonFormatter`, which
  the `capsys` version also did but by accident.
- **Where it was applied:** `tests/test_observability.py` — a list-collecting
  handler installed on the root logger for the duration of the test.
- **How to detect it next time:** Ask what the test would do if fixtures ran in
  the opposite order. If the answer is "fail", the seam is wrong. Any API that
  takes a stream, socket or file object *now* and uses it *later* has this shape:
  `StreamHandler`, `logging.basicConfig`, anything caching `sys.stdout`.

## 2026-09-01 — The test suite passed only because the developer's database existed

- **What broke:** `pytest` was green locally and failed on GitHub Actions with
  `SchemaContractError: Database file not found:
  /home/runner/code/job-listing-scraper/data/jobs.db`. Only the two Phase 1 tests
  failed; all 31 Phase 2 tests passed on both machines.
- **Why it happened:** Those two tests called `create_app()` with no arguments, so
  the app fell back to `get_settings()` and the default `db_path`. That was
  harmless while nothing opened the database — but Phase 2 added the startup
  schema check to the lifespan, and `TestClient` used as a context manager *runs
  the lifespan*. From that moment the Phase 1 tests depended on
  `~/code/job-listing-scraper/data/jobs.db` existing. It does on this machine. It
  does not on a runner. Note the shape: the code that broke the tests was added to
  a different file, in a different phase, and every test that was *supposed* to
  cover the new behaviour passed.
- **What it teaches:** "The suite passes" and "the suite is self-contained" are
  different claims, and the first hides the failure of the second for exactly as
  long as the developer's machine stays configured correctly. The definition of
  done already said `pytest` must be green *with `jobs.db` deleted* — that line
  was never executed, so it was not a property of the project, it was a wish. It
  also teaches where the seam belongs: `app.dependency_overrides[get_conn]` cannot
  redirect a startup check, because the lifespan runs *before* any dependency is
  resolved. Injecting `Settings` into `create_app` puts the seam somewhere that
  governs both paths.
- **Where it was applied:** `tests/test_health.py` now takes the `client` fixture.
  `tests/conftest.py` gained an autouse `_never_the_real_database` fixture that
  points `JOBSAPI_DB_PATH` at a path which cannot exist and clears the
  `get_settings` cache — so a future test that forgets to inject `Settings` fails
  immediately and identically everywhere. `create_app(settings)` is the seam.
- **How to detect it next time:** Make the ambient resource *unreachable* in the
  fixture rather than merely unused. A guard beats discipline, because it converts
  a machine-dependent failure into a deterministic one. Verified with
  `JOBSAPI_DB_PATH=/nonexistent/jobs.db uv run pytest`.

## 2026-09-01 — `ORDER BY posted_at DESC` is not a total order, and unstable pagination raises no error

- **What broke:** *Designed out, not observed.* Left alone, paging through
  `/jobs` would have shown some rows twice and skipped others, with a 200 on
  every request and nothing in any log.
- **Why it happens:** `posted_at` is a plain `YYYY-MM-DD` string, so thousands of
  rows share a value. SQL guarantees no order among rows that tie on the sort key
  — SQLite may resolve them differently between two queries depending on the plan
  it picks, and `LIMIT`/`OFFSET` slices a *sequence*, not a *set*. Two adjacent
  pages sliced from two different sequences overlap and gap. The symptom is a
  client that quietly receives duplicate ids and never sees a row that exists.
- **What it teaches:** Pagination is a design problem, not a clause. `LIMIT`/`OFFSET`
  is only correct on top of a **total** order, and a sort key with ties does not
  provide one. Appending a unique column — the primary key — is what makes the
  ordering total. This is also the clearest example in the build of a bug whose
  entire cost is paid by the client: nothing on the server is in an error state.
- **Where it was applied:** `_build_order` in `src/jobsapi/repository.py` emits
  `ORDER BY <column> <dir>, id <dir>` for every sort. The same tie-break is in
  `list_job_changes` (`observed_at` repeats across every change written by one
  run) and `list_runs` (`started_at` ties within a batch).
- **How to detect it next time:** For any `ORDER BY` that feeds `LIMIT`/`OFFSET`,
  ask whether the sort key is unique. If it is not, the query is wrong even though
  it returns rows. Recurred three times in this build — jobs, changes, runs —
  which is why it is written up rather than left in the gap log.

## 2026-09-01 — A read-only connection cannot recover a hot journal, so "locked" is two different failures

- **What broke:** *Designed out.* The naive handler — catch `sqlite3.OperationalError`,
  return 503, tell the client to retry — would send clients into an unbounded retry
  loop against a condition that no amount of retrying can clear.
- **Why it happens:** Two distinct conditions surface through the same exception
  type. `SQLITE_BUSY` means a writer holds the lock right now: transient, and
  retrying is the correct response. `SQLITE_READONLY_ROLLBACK` means a writer died
  mid-transaction and left a hot `-journal` behind; clearing it requires *rolling
  the journal back*, which is a **write**. A `mode=ro` connection cannot perform it,
  so the condition persists until a human or a read-write process intervenes.
  Their `str(e)` values are "database is locked" and "attempt to write a readonly
  database" — matching on that text is the wrong seam: it is unversioned and
  shared with unrelated causes.
- **What it teaches:** Retry advice is part of the contract, and getting it wrong
  turns one stuck database into a self-inflicted load problem. The discriminator
  must be the *code*, not the message: `exc.sqlite_errorname` (Python 3.11+) is
  the machine-readable one. And a `classify()` that returns `None` for anything
  unrecognised is deliberate — an unknown fault should surface as a 500, not be
  disguised as a known one.
- **Where it was applied:** `classify()` in `src/jobsapi/db.py` branches on
  `sqlite_errorname`; `DatabaseUnavailable` and `DatabaseWedged` in
  `src/jobsapi/errors.py`; handlers in `src/jobsapi/problems.py` return
  `DATABASE_BUSY` **with** `Retry-After: 1` and `DATABASE_UNAVAILABLE`
  **without** one, both as 503.
- **How to detect it next time:** Whenever an error handler is about to advise a
  retry, ask what would have to change for the retry to succeed, and whether this
  process can cause that change. If it cannot, the advice is a loop.

## 2026-09-01 — An enum member whose value contains a colon is not the member you wrote

- **What broke:** *Designed out, having been identified before the `source` enum
  was written.* `greenhouse:anthropic = "greenhouse:anthropic"` in a class body is
  not a syntax error and not the member it appears to be.
- **Why it happens:** Python parses it as an **annotated assignment** —
  `AnnAssign(target=greenhouse, annotation=anthropic)`. Without
  `from __future__ import annotations` it raises `NameError` when the class body
  executes. *With* that import, annotations are never evaluated, so the enum
  silently gains a member named `greenhouse` whose value is `greenhouse:anthropic`
  — and a second `greenhouse:*` line then raises
  `TypeError: 'greenhouse' already defined`, naming a key that appears nowhere in
  the source.
- **What it teaches:** The error message points at a name the author never typed,
  which is what makes it expensive. More generally: the enum *member name* and the
  *wire value* are separate things, and the class-body syntax quietly conflates
  them. When the wire value is not a valid Python identifier, the functional API
  is not a stylistic preference — it is the only correct form.
- **Where it was applied:** `src/jobsapi/schemas.py` —
  `Source = StrEnum("Source", {v.replace(":", "_"): v for v in SOURCE_VALUES})`,
  so `greenhouse_anthropic` is the member and `greenhouse:anthropic` is the value
  a client sends.
- **How to detect it next time:** Before writing an enum, check whether every
  value is a valid identifier. Colons, dots, hyphens and leading digits all force
  the functional API. `from __future__ import annotations` makes this failure
  *quieter*, not louder — worth knowing, since this project uses it widely.

## 2026-09-01 — WAL would make the containerised reader impossible, not easier

- **What broke:** *Designed out.* The obvious follow-up to Decision 1 — "ask
  Build 2 to `PRAGMA journal_mode=WAL` so readers stop hitting `SQLITE_BUSY`" —
  is wrong, and would have been discovered in Phase 6 with a Dockerfile already
  written.
- **Why it happens:** A reader of a WAL database must **create** the `-shm`
  shared-memory file, which requires write permission on the *containing
  directory*. The Phase 6 mount is `-v ~/code/job-listing-scraper/data:/data:ro`,
  which denies exactly that. Measured 2026-09-01: a WAL database, its directory
  made unwritable, opened `mode=ro` fails with **`SQLITE_READONLY_DIRECTORY`** —
  not `SQLITE_CANTOPEN`, and not something a busy timeout addresses. SQLite
  deletes `-wal`/`-shm` on clean close, so this is not a stale-file problem: even
  a pristine WAL database is unopenable under that mount.
- **What it teaches:** An optimisation that removes a *frequent, transient,
  already-handled* failure (`database is locked`, answered with a 503 and a
  retry) in exchange for a *total* one is a bad trade, and the trade is invisible
  unless the deployment target is considered at the same time as the query layer.
  The build phase where a decision is made is not always the phase where it is
  paid for.
- **Where it was applied:** `docs/design.md` — WAL is recorded as **declined**
  with the measurement, rather than deferred as a vague future improvement. The
  busy timeout is sized to the *mechanism* (the scraper takes an EXCLUSIVE lock
  only for the duration of a commit, not for the run) rather than to a measured
  window that could change: 5s of slack for a slow disk.
- **How to detect it next time:** Before adopting a storage-layer setting, ask
  what it requires of the *filesystem*, and re-ask under every environment the
  service will run in. "Works locally, impossible in the container" is a class of
  failure, not an accident.

---

# Part 2 — The viva

The questions CLAUDE.md sets, answered at the end of the phase that introduced
each. Every factual claim below was checked against the installed
FastAPI 0.141.1 and the real database on 2026-09-01, not recalled.

## Framework mechanics (Phase 1)

### What does `@app.get("/jobs")` actually register, and in what?

It builds an `APIRoute` and appends it to a `.routes` list — the decorator's work
is entirely at import time, and its return value is the undecorated function, so
the name in the module still refers to a plain callable you can call in a unit
test.

In this project the decorator is `@router.get(...)`, so the `APIRoute` lands on
the `APIRouter` object `jobs.router`, and the application knows nothing about it.
`app.include_router(jobs.router)` is the second step.

**What that second step does is version-dependent, and the version installed here
does not do what the Phase 1 note claimed.** On FastAPI 0.141.1,
`include_router` does *not* copy the routes onto the app. It appends a single
`fastapi.routing._IncludedRouter` holding `original_router` (a reference to the
router) and an `include_context` (the prefix, tags and dependencies applied at
inclusion). Effective routes are computed lazily by `effective_candidates()` and
cached against `original_router._get_routes_version()`. Inspecting the app shows
this directly: `app.routes` contains four `starlette.routing.Route` objects for
the docs endpoints and three `_IncludedRouter` objects with `path=None` — and no
`APIRoute` at all.

The conclusions the old model supported are unchanged, and are now true more
literally: a router is an independent object that can be imported and tested on
its own, and the same router can be mounted twice under different prefixes.

The `APIRoute` itself is where FastAPI stores what it derived from the signature:
the path, the methods, the dependant tree, and the `response_field` built from
the return annotation or `response_model`.

### What is `uvicorn` doing that `python main.py` isn't? What is ASGI?

`python main.py` executes a module and exits. Nothing in `main.py` opens a
socket, so there is no server — `app` is just an object.

**ASGI** is the interface between a web server and a Python application: the
async successor to WSGI. An ASGI application is a callable
`async def app(scope, receive, send)` — `scope` is a dict describing the
connection (type, method, path, headers), `receive` is an awaitable that yields
incoming events, and `send` is an awaitable that takes outgoing ones. That is the
entire contract, and it is why it supports what WSGI's single request-in /
response-out function could not: WebSockets, streaming and long-lived
connections all fall out of "a stream of events" naturally. `FastAPI` is an ASGI
application, which is why `uvicorn jobsapi.main:app` needs nothing from us but
the import path.

**uvicorn** supplies everything that is not the application: it runs the asyncio
event loop, binds and listens on the socket, parses HTTP/1.1 (via `httptools`
under `uvicorn[standard]`), translates each request into a `scope` plus events,
calls the app, writes the response back, handles keep-alive and graceful
shutdown, and — under `--reload` — watches files and restarts the process. The
concurrency model matters for this build: **one process, one event loop**, which
is exactly why a blocking call inside `async def` stalls every other request in
the process rather than just the one making it.

### What generates `/docs`, and where does the schema come from? So what does it mean when the docs are wrong?

`/docs` is a Starlette route serving a small HTML page that loads Swagger UI and
points it at `/openapi.json`. It contains no information about this API. All the
content comes from `/openapi.json`, which FastAPI generates by walking the routes
and reading, for each one: the path and method, the parameter models, and the
`response_model` / return annotation — turning each Pydantic model into a JSON
Schema in `components.schemas`.

So the docs are a *projection of the type hints*. Nothing is written twice, which
means nothing can disagree — and the corollary is the important half: **wrong
docs are not a documentation bug, they are a wrong type.** If `/docs` says a
field is `str` when the service always returns `"ok"`, the fix is
`Literal["ok"]` in the model, not a note in the docs. This is why
`tests/test_health.py` asserts on `/openapi.json` rather than trusting it: the
happy-path test passes either way, but the schema assertion fails when the
declaration weakens, which is the thing that can actually regress silently.

The same reasoning is why `main.py` declares `PROBLEM_RESPONSES` app-wide. Left
alone, the generated docs would advertise FastAPI's `HTTPValidationError` for
every 422 — a body this service never sends — and "the docs are generated from
the types" would quietly stop being true for errors, which are exactly the part a
client author most needs to read.

## The two that decide whether the app survives load (Phase 2)

### What does FastAPI do differently with a `def` endpoint versus an `async def` one, and which should a blocking `sqlite3` call live in?

An `async def` endpoint is awaited **directly on the event loop**. A plain `def`
endpoint is dispatched to a threadpool via `run_in_threadpool` (anyio's worker
threads) and awaited from the loop.

`sqlite3` is a blocking library: `conn.execute(...)` occupies its thread until
the C call returns and yields to nothing. Inside `async def`, that thread is *the
event loop*, so for the duration of the query the process cannot progress any
other request — including ones that would not have touched the database at all.
Inside a plain `def`, it occupies a worker thread and the loop stays free.

So every endpoint here that touches `sqlite3` is plain `def`, and `/health` is
`async def` because it performs no I/O whatsoever and therefore has nothing to
gain from a threadpool hop. **The rule is about what the body does, not about
house style** — which is the exact point on which the two spellings look like a
matter of taste and are not.

This is the most dangerous item in the build because the failure is invisible in
development: single-user testing shows an app that works perfectly. It surfaces
only under concurrency, as latency on endpoints that have nothing to do with the
slow one.

### What is a dependency, when does it run, why does `yield` matter, and why is a shared `sqlite3.Connection` across requests a bug?

A dependency is a callable FastAPI resolves *before* the endpoint and passes in
as an argument — here `conn: Annotated[sqlite3.Connection, Depends(get_conn)]`.
FastAPI builds a dependency tree per route at startup and walks it per request,
following the same sync/async rule as endpoints: a `def` dependency also runs in
the threadpool. Results are cached within a single request, so two dependencies
asking for the same connection get one.

`yield` makes it a **generator dependency**, which turns it into setup/teardown:
everything before `yield` runs on the way in, everything after runs on the way
out — including when the endpoint raised. That is what makes `conn.close()` in
the `finally` an actual guarantee rather than a hope, and it is the entire reason
this is a dependency rather than a module-level global.

A shared connection would be wrong in three independent ways. **Threading:** a
`def` endpoint runs in a threadpool, so concurrent requests would use one
connection object from several threads at once — which is what
`check_same_thread` exists to prevent. (Setting `check_same_thread=False` here is
safe *only* because the connection is per-request and never shared; the same flag
on a global is precisely the bug the check catches.) **Serialisation:** SQLite
locks per connection, so every request would queue behind one lock, converting a
concurrent server into a sequential one. **State leakage:** transaction state,
`row_factory` and any PRAGMA are properties of the *connection*, so one request's
half-finished state would be visible to an unrelated caller.

The seam this creates is what makes the tests trivial:
`app.dependency_overrides[get_conn] = ...` swaps the database with no module
globals touched. With one exception, recorded above: an override cannot reach the
startup schema check, because the lifespan runs before any dependency is
resolved. That is why `create_app` takes `Settings`.

## The contract (Phases 2–3)

### Why `422` and not `400` for a validation failure — and what is `422` called?

`422` is **Unprocessable Content** (RFC 9110 §15.5.21; it was "Unprocessable
Entity" in WebDAV, RFC 4918). Its definition is precisely this situation: the
syntax was understood and the content type was understood, but the instructions
could not be followed.

That covers both kinds of failure this API rejects. `limit=abc` is malformed.
`salary_min_gte=50000&salary_max_lte=10000` is well-formed, and each field is
individually legal — only the pair is nonsense. The temptation is to call the
second one `400`, on the grounds that it is "semantically" rather than
"syntactically" invalid, but `400 Bad Request` is the *generic* client error, and
422 already means "well-formed but not processable".

The practical argument decides it. A `@model_validator` produces 422 for free.
Getting 400 instead would require either raising `HTTPException(400)` inside the
route — dragging validation out of `schemas.py` and breaking the boundary this
build exists to establish — or re-classifying `RequestValidationError` by
inspecting `loc` in the handler. Both cost real code to move a distinction into
the status line that a client cannot branch on any better there.

So the status stays 422 and the discrimination is carried in the body, where it
is machine-readable: `code: "VALIDATION_FAILED"` versus
`code: "CROSS_FIELD_CONFLICT"`. The handler distinguishes them by checking for a
Pydantic error `type` of `cross_field_conflict`, which is why the validator
raises `PydanticCustomError` rather than a bare `ValueError` — a `ValueError`
arrives as `type: "value_error"` and is indistinguishable from anything else.

### What does `response_model` do at runtime, and what does it cost?

At runtime FastAPI calls `serialize_response`, which runs
`field.validate(response_content, {}, loc=("response",))` and then
`field.serialize(...)`. Two consequences: the response is **validated** against
the declared model (a mismatch is a `ResponseValidationError` — a 500, not a
corrupt body), and it is **filtered** to the declared fields.

The filtering is the load-bearing part. Verified against the real database by
handing the route's `response_field` a raw dict containing both `content_hash`
and a 33,000-character `description`: the serialised output contains exactly the
twelve `JobSummary` fields and neither of those keys. So `description` staying
out of list responses is structural — it holds even if a future query starts
selecting it — rather than a rule someone has to remember.

The cost is smaller than it looks, and not where I expected. Measured on 100 real
rows, 300 iterations:

| step | ms |
| --- | --- |
| the SQL query itself | 0.147 |
| our own `JobPage` construction | 0.176 |
| `response_model` re-validation | **0.0008** |
| re-validation + serialize | 0.109 |

Re-validation is essentially free — 0.0008 ms — because Pydantic v2 defaults to
`revalidate_instances="never"`, so validating a value that is *already an
instance of the model* returns the identical object (confirmed:
`field.validate(page)[0] is page` is `True`). The full pass only runs when the
endpoint returns something else: handing the same field a plain dict costs
0.0855 ms, a hundredfold difference. Returning a constructed model from the route
is therefore both the clearer style and the cheaper one.

The real cost is the serialization pass (0.109 ms — comparable to the query), and
one detail worth noting: for a `def` endpoint, `serialize_response` dispatches
`field.validate` to the threadpool too, so the sync/async decision governs
response handling as well as the endpoint body.

### Why can a `WHERE` value be parameterised but not an `ORDER BY` column?

Because a bound parameter is a **value**, and the database plans the statement
before the values are supplied. `WHERE salary_min >= ?` compiles to a plan with a
placeholder; binding `50000` fills a slot in an already-compiled statement, which
is why the value can never be executed as SQL — that is the actual mechanism
behind "parameterised queries prevent injection", not escaping.

`ORDER BY ?` is not the same shape. The column is an **identifier**: it takes
part in planning — index selection, whether a sort step is needed at all — so it
must be known at compile time. SQLite will accept the syntax and bind a *value*
there, which then sorts every row by the same constant and silently returns
unordered results. The same constraint applies to table names and to `PRAGMA`
arguments, which is why `db.py` formats the busy timeout into the statement with
an explicit `int()` — and why that is safe: the value comes from our settings,
never from a request.

Since it cannot be parameterised, the identifier must be **chosen**, not passed:
`SortField` is a six-member enum, and `_SORT_COLUMNS` maps each member to a
literal column name written in our own source. `?sort=id;DROP TABLE jobs` is a
422 from enum validation and never reaches the repository. Note that
`content_hash` is rejected too, despite being a real column — the allowlist
defines the *public contract*, not merely what is safe to interpolate. The
read-only connection and `PRAGMA query_only = 1` are a second, independent layer;
neither is relied on to make the first one unnecessary.

### What does `docs/api.md` say about NULL salaries and `salary_min_gte`, and why is that a decision rather than a bug?

It says: **NULL values never satisfy a filter.** `salary_min_gte=100000` returns
only rows with a recorded `salary_min` of at least 100000; rows where
`salary_min` is NULL are excluded, as are undated rows under `posted_after` /
`posted_before`.

Mechanically this is SQL's three-valued logic: `NULL >= 100000` evaluates to
NULL, which is not TRUE, so `WHERE` drops the row. No code implements it.

It is a decision rather than a bug because the mechanism is not the
justification. A filter on a value cannot be satisfied by the *absence* of that
value — "pays at least 100k" is a claim the data does not make about a row with
no salary — and the alternative reading ("don't hide rows just because we lack
data") is defensible enough that leaving it to be inferred from SQL semantics
would be a failure of documentation. The stakes make that concrete: `salary_min`
is NULL in 69% of the dataset, so the choice governs most of the corpus.
Verified against the real database at the time of writing: `salary_min_gte=0`
returned 977 of 3,105 rows, exactly the non-NULL count.

The same reasoning produces the opposite answer one field over. `remote` is
tri-state, and `remote=unknown` maps to `IS NULL` rather than `= 0`, because
there NULL is not missing data to be filtered past — it is the scraper recording
that it never established the fact, and collapsing it to `false` would invent
data. 1,129 of 3,105 rows are in that state. Two fields, two opposite treatments
of NULL, both documented: which is the point. The dataset does not tell you what
NULL means; the contract does.

---

# Part 3 — The register: the concept behind each file

The AI-WRITTEN register in `gap-log.md` carries a one-line concept per file, and
an entry leaves that list only once the concept is written up here. This part
closes the remaining ten. Each claim below was checked against the machine
rather than recalled — two of the one-liners turned out to be wrong, and both
corrections are recorded in place.

## `pyproject.toml` — the `src/` layout, and what `uv sync` actually installs

**Correction first.** The register's one-liner said `uv sync` installs the
project as an "editable wheel, **not** a path on `sys.path`". That is backwards.
Inspecting the venv:

```
.venv/lib/python3.13/site-packages/jobsapi.pth          -> /…/job-listings-api/src
.venv/lib/python3.13/site-packages/jobsapi-0.6.0.dist-info/
    direct_url.json -> {"url": "file:///…", "dir_info": {"editable": true}}
```

It is *precisely* a path on `sys.path` — a `.pth` file containing the absolute
path to `src/`, which Python appends at interpreter start. `import jobsapi`
resolves to `…/job-listings-api/src/jobsapi/__init__.py`: the working tree, so an
edit takes effect with no reinstall.

**Why a build backend is needed at all.** With a `src/` layout the package is not
in the current directory, so it is not importable by accident. That is the point:
`pytest` run from the repo root cannot pick up `src/jobsapi` implicitly, which is
what makes `ModuleNotFoundError: No module named 'jobsapi'` the *correct* first
result and the install step a real one. `[build-system] requires = ["uv_build"]`
declares who turns this directory into an installable distribution;
`uv sync` runs it.

**The half of the one-liner that was right** is that this is not merely
`PYTHONPATH=src`. There is a `dist-info` directory alongside the `.pth`, so
`jobsapi` is a *recorded distribution* with a version and metadata, discoverable
by `importlib.metadata` and uninstallable as a unit. A bare `PYTHONPATH` gives
imports without any of that.

**And the distinction has a consumer.** The Dockerfile runs
`uv sync --locked --no-dev --no-editable`, which produces the other shape
entirely. Verified in a clean clone:

```
site-packages/jobsapi/          <- the package, copied
direct_url.json -> {"dir_info": {"editable": false}}
no jobsapi.pth
import jobsapi -> …/site-packages/jobsapi/__init__.py
```

That is what lets the runtime stage copy `/app/.venv` and leave the source tree
behind. Editable for development because an edit should take effect immediately;
non-editable for the image because a `.pth` pointing at a build-stage path would
be a dangling reference in the final container.

## `.gitignore` — ignoring `*.db` in a repo whose whole job is reading a database

Three independent reasons, only the first of which is about size.

**It is not this repository's data.** Build 2 owns the database. Committing it
would create a second copy of the truth that drifts from the first the next time
the scraper runs, and `docs/design.md` rejected the snapshot approach for exactly
that reason. The path is configuration; the file is somebody else's.

**Git cannot store it usefully.** A 64 MB SQLite file is a binary blob that
changes throughout on every write, so each commit stores a fresh copy forever.
The current `.git` is **1.0 MB**. Two committed snapshots would make the clone
120× larger permanently, because history cannot be shrunk by a later deletion.

**It contains someone else's copyrighted text.** Full job descriptions —
19.3 MB of them — are the employers' words, and Build 2's own statement keeps
them local. A public repository is publication.

The rule is enforced rather than remembered: `data/`, `*.db`, `*.db-wal` and
`*.db-shm` are all ignored, checked directly —

```
data/demo.db  -> .gitignore:21:data/     foo.db      -> .gitignore:22:*.db
data/jobs.db  -> .gitignore:21:data/     foo.db-wal  -> .gitignore:23:*.db-wal
```

— and `git log --all -- '*.db' data/` returns nothing, so no database has ever
been committed at any point in this repository's history. `.dockerignore`
repeats the same four patterns for the same reason, one layer out.

## `.github/workflows/ci.yml` (the `check` job) — what `--locked` refuses

`uv sync --locked` **fails rather than re-resolving** when `uv.lock` and
`pyproject.toml` disagree. Demonstrated by loosening one bound in a throwaway
clone:

```
$ uv sync --locked --all-groups
Resolved 32 packages in 300ms
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
hint: To update the lockfile, run `uv lock`.
```

Plain `uv sync` would have quietly updated the lockfile and installed a different
dependency set than the one tested locally. In CI that is the whole ballgame: a
green run against silently re-resolved dependencies is a green run for a
configuration nobody has. `--locked` converts "CI resolved something slightly
different" from an invisible event into a build failure with the fix in the
message.

**Why no network and no `jobs.db` on the runner is the point.** A CI runner is
the only environment guaranteed not to have the developer's conveniences, which
makes it the standing proof of two Definition-of-Done lines: that `pytest` is
green with the wifi off, and green with `jobs.db` deleted. This is not
hypothetical — it is exactly how the Phase 1 tests were caught depending on the
developer's filesystem (Part 1, entry 4). The runner did not cause that bug; it
was the only place that could see it.

## `.github/workflows/ci.yml` (the `docker` job) — verifying by querying, not by building

A successful `docker build` proves the Dockerfile parses and its commands exit 0.
It proves nothing about whether the resulting container *serves*. The gap between
those two is where the interesting failures live: a wrong `CMD`, a `PATH` that
does not reach the venv, a `USER` that cannot read the mounted file, an
`ENV` default pointing somewhere nothing is mounted.

So the job builds the image and then interrogates a running container: `/health`
answers; `/jobs` returns rows **from the mounted volume**; `?limit=0` is still a
422 inside the image; `id -u` is 1001; and a write against `/data/jobs.db` is
refused.

That last assertion is the one worth explaining. It opens a *plain read-write*
`sqlite3` connection from inside the container rather than asking the API,
because the API has no write path — that is the entire premise of the build — so
asking it would prove nothing about the mount. The application's own guarantee
is already doubly enforced in code (`mode=ro` on the URI, `PRAGMA query_only`);
this tests the layer *underneath* both. Delete `:ro` from the documented
`docker run` and every application-level assertion still passes while this one
fails.

The job exists because this machine has no container runtime at all, so the
image cannot be built where it was written. That is a limitation, but the
substitute is not a lesser check: it runs on every push, and it verifies
behaviour a local `docker build` never would have.

## `Dockerfile` — three decisions

**The build toolchain lives in a stage that never ships.** The builder needs
`uv`, the lockfile and the source; the runtime needs an interpreter and a
virtualenv. Only `/app/.venv` crosses the `COPY --from=builder` boundary. The
size argument is real, but the better one is that a compiler, a package manager
and a lockfile which are *not in the image* cannot be used by anything that later
gets into the image.

**The database is a volume, never a layer.** Baking a 64 MB snapshot in would
make the image stale the moment the scraper next runs, would put employers'
copyrighted description text into an artefact that gets pushed to a registry, and
would contradict Decision 1's "a path, not a policy". `ENV JOBSAPI_DB_PATH=/data/jobs.db`
expresses that as a default, so `-v …/data:/data:ro` is all a user supplies.

**Exec-form `CMD`.** `CMD ["uvicorn", …]` makes uvicorn PID 1, so it receives
`SIGTERM` from `docker stop` and shuts down gracefully. The shell form
(`CMD uvicorn …`) puts `/bin/sh` at PID 1, and sh does not forward signals to its
child — the container would hit the 10-second timeout and be `SIGKILL`ed on every
single stop. The failure is invisible in development and shows up as dropped
in-flight requests on every deploy.

Two smaller ones with the same character. `PYTHONUNBUFFERED=1`, because Python
block-buffers stdout when it is not a tty — which is exactly the container case —
so without it the structured log lines this service is careful to emit would sit
in a buffer instead of reaching the log collector. And the healthcheck uses
`urllib` rather than `curl`, because the slim image has no curl and installing
one would be a package that exists solely to be a dependency of the healthcheck.

## `.dockerignore` — why a build context matters even when no `COPY` references it

The entire build context is uploaded to the daemon *before* any instruction runs.
A 64 MB database in `data/` would be transferred on every build even though no
`COPY` mentions it — pure latency, repeated.

The sharper reason is the failure mode. This Dockerfile copies specific paths, so
today a stray database could not enter a layer. But `COPY . .` is the single most
common Dockerfile edit anyone makes, and the moment someone writes it, the
database is baked into the image and pushed to a registry with no error anywhere.
`.dockerignore` makes that edit safe in advance rather than relying on whoever
makes it noticing. It repeats `.gitignore`'s four database patterns for exactly
this reason: the two files answer the same question about two different
publication channels.

## `scripts/make_demo_db.py` — why a reader ships a schema-creating script

The service is a reader and does not own the schema, so a script that *creates*
tables looks like a boundary violation. It is not one, because nothing in
`src/jobsapi/` imports it and no code path in the service can reach it. It is a
fixture generator that happens to live in the repository.

It exists because **without it neither audience can run the service at all.** A
stranger who clones this repo has no `jobs.db`; a CI runner has no scraper. The
alternative is a README whose first instruction is "obtain a 64 MB database from
another project", which makes the quickstart untestable and the container smoke
test impossible.

**Stdlib-only** because both callers precede an install: CI runs it with the
runner's bare `python3` before the image even starts. A dependency would make the
fallback require the thing it is a fallback for.

**The schema is copied, not imported**, for the same reason `tests/conftest.py`
copies it: importing `jobscrape` would couple two deliberately separate
repositories, and Build 3 would then fail to build whenever Build 2's package did.
The copy is not trusted to stay correct — `db.verify_schema` compares the real
database's columns at startup, so drift is a loud refusal to start rather than a
silently wrong answer.

The rows are chosen to be awkward on purpose: a null salary, a null `remote`, a
unicode company, an apostrophe and a literal `%` in a title, a null `posted_at`.
A demo built from five tidy rows would demonstrate none of the decisions this
build spent its time on.

## `src/jobsapi/repository.py` (Phase 5) — `substr()` in SQL, and the LEFT JOIN

**Truncating in SQL rather than in the response model.** The response model runs
*after* the data has been read, so filtering there still pays to pull every byte
off disk and into Python. Measured across the whole `job_changes` table:

| | bytes into Python | wall time |
| --- | --- | --- |
| raw `old_value, new_value` | **36.2 MB** | 40.0 ms |
| `substr(…, 1, 200)` + `length(…)` | **1.32 MB** | 46.7 ms |

**Note what this does and does not buy.** It is a 27× reduction in bytes crossing
the boundary and *not* a speed win — the `substr` version is marginally slower in
wall time, because SQLite still reads the pages and now does per-row work as
well. The win is memory and payload, which is the thing that scales with
concurrency: 36 MB of Python string objects per request is what falls over with
ten callers, not 6 ms of CPU. Claiming this as an optimisation for *speed* would
have been wrong, and measuring is what showed it.

Per request the effect is starker. The worst single job today is id 88, whose
four changes hold **187.9 KiB** of raw values and serialise to **1.8 KiB** — with
`old_length`/`new_length` reporting the true sizes and `truncated: true` saying
that something was cut, so nothing is hidden from the client.

**Why `/sources` needs a LEFT JOIN.** It counts jobs per source and attaches the
outcome of that source's most recent run. An inner join would drop any source
missing either side — a source with jobs but no run row, or a run row but no jobs
— and the row would simply vanish, which for an endpoint whose job is *inventory*
is the worst possible failure: silent under-reporting that looks like a complete
answer.

**Honest caveat:** neither case exists in the data today. All eight sources appear
in both tables, so the LEFT JOIN is currently indistinguishable from an inner
join at runtime. It is defensive, not load-bearing — and worth keeping, because
the situations it guards are ordinary (a scrape that starts and writes no rows; a
source retired from the scraper while its jobs remain), and the cost of being
wrong is a missing row rather than an error.

## `src/jobsapi/routers/runs.py` — why `RunSummary` has no `duration_seconds`

Both timestamps are present, so the subtraction is available and obvious. It is
omitted because Build 2 writes `finished_at` from the same value as `started_at`,
making the result 0.0 for essentially every run.

**A correction to the register's one-liner, which said "every completed run".**
Measured: `finished_at == started_at` in **62 of 63** finished runs. The
exception is run 55 — `status: "failed"`, started `03:45:08.131882`, finished
`03:45:12`, a real 3.9-second duration. So the bug is in the *success* path only;
the failure path stamps a genuine timestamp.

That refinement makes the case for omitting the field stronger, not weaker. A
uniformly zero column is obviously broken and a client would distrust it
immediately. A column that reads 0.0 for every successful run and 3.9 for a
failed one looks *plausible* — it invites the conclusion that successful scrapes
are instantaneous, which is false and unfalsifiable from the API. Publishing a
confidently wrong number is worse than publishing none, because a wrong number
suppresses the question.

So both timestamps are returned raw and the client can see the equality itself.
The fix belongs in Build 2, which owns the write path; this service is a reader
and does not launder its source's bugs.

## `README.md` — why every documented command was executed before being written

Because documentation is the one artefact with no test. `pytest` covers the code
and CI covers the build, but nothing anywhere fails when a README says
`--port 8080` and the app listens on 8000. It rots silently and is read first —
by the person least able to tell that it is wrong.

So every command in it was run, and every example request was issued against a
live server: the demo-database build, the `uvicorn` invocation, all nine `curl`s,
`/docs` and `/openapi.json`, the two `pytest` variants, and the lint pair. Then
the whole thing again from a clean clone, which is the only way to catch a step
that works solely because of state already sitting on the development machine.

**This was not ceremony — it found two real defects.** `Settings` carried
`default_page_size` and `max_page_size` that nothing read, so
`JOBSAPI_MAX_PAGE_SIZE=500` did precisely nothing; and `pyproject.toml` said
version `0.1.0` while the running app reported `0.5.0`. Neither is the kind of
bug a test catches, because nothing *fails* when a setting is ignored or a
version string disagrees. Both were found by the act of writing down what was
true and then checking. The dead settings were removed rather than implemented,
since the `1..100` bound is a `Field` constraint that `/openapi.json` publishes —
making it configurable would let a deployment's real limit differ from what its
own docs promise.
