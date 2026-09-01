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

---

## AI-WRITTEN register

AI-written files, and the one-line concept behind each. An entry leaves this
list only once it has been written up in `learning-log.md`.

| Date | File | Concept to re-derive | Written up? |
| ---- | ---- | -------------------- | ----------- |
| 2026-09-01 | `pyproject.toml` | Why a `src/` layout needs a build backend at all, and what `uv sync` installs the project *as* (editable wheel, not a path on `sys.path`) | ☐ |
| 2026-09-01 | `.gitignore` | Why `data/` and `*.db` are ignored in a repo whose whole job is reading a database | ☐ |
| 2026-09-01 | `docs/design.md` | Both Phase 0 decisions and the measurements behind them: `mode=ro` + path-not-policy config, and why WAL is *declined* rather than deferred | ☐ |
| 2026-09-01 | `src/jobsapi/main.py` | Why an app *factory* rather than a module-level singleton, and what `include_router` does that the `@router.get` decorator did not | ☐ |
| 2026-09-01 | `src/jobsapi/routers/meta.py` | Why `/health` is `async def` while every sqlite3 endpoint must be plain `def` — the rule is about what the body does, not house style | ☐ |
| 2026-09-01 | `tests/test_health.py` | Why `TestClient` is used as a context manager (lifespan events), and why the OpenAPI schema is asserted on rather than trusted | ☐ |
| 2026-09-01 | `.github/workflows/ci.yml` | What `uv sync --locked` refuses to do, and why CI having no network and no `jobs.db` is the point rather than a limitation | ☐ |
| 2026-09-01 | `src/jobsapi/config.py` | Why the DB location is a *path, not a policy*, and why `get_settings` is cached but tests never call it | ☐ |
| 2026-09-01 | `src/jobsapi/db.py` | Why `mode=ro` must be a URI (a plain connect *creates* a missing file), why `check_same_thread=False` is safe per-request but not globally, and why a generator dependency guarantees close | ☐ |
| 2026-09-01 | `src/jobsapi/errors.py` | Why the repository raises `JobNotFound` and not `HTTPException`, and why BUSY and READONLY_ROLLBACK are two classes rather than one | ☐ |
| 2026-09-01 | `src/jobsapi/schemas.py` | Three shapes on purpose: input model, list output, detail output — none of them the database row | ☐ |
| 2026-09-01 | `src/jobsapi/repository.py` | Why `ORDER BY posted_at DESC` alone silently repeats rows across pages, and why identifiers cannot be parameterised | ☐ |
| 2026-09-01 | `src/jobsapi/routers/jobs.py` | Why this file is plain `def` while `/health` is `async def` | ☐ |
| 2026-09-01 | `tests/conftest.py` | Why the fixture DB is *written* read-write and *read* read-only, and why the schema is copied rather than imported from Build 2 | ☐ |

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

### Open item deferred to Phase 3

`GET /nope` and the 404 from `/jobs/999999999` still return FastAPI's default
`{"detail": ...}`. Decision 2 requires RFC 9457 problem details for *every* 4xx.
The boundary is already right — the repository raises `JobNotFound` and an
exception handler translates it — but the body shape is a placeholder until the
Phase 3 handlers land.
