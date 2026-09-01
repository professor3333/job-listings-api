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
