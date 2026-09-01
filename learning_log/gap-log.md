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

### Open item deferred to Phase 3

`GET /nope` currently returns FastAPI's default `{"detail": "Not Found"}`.
Decision 2 requires RFC 9457 problem details for *every* 4xx. The exception
handlers that enforce it land in Phase 3, not here.
