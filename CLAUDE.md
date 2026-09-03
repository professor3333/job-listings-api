# CLAUDE.md — Job Listings API

## What this project is

Build 3 of Stage 0. A small **FastAPI** service that exposes the dataset Build 2
collected (`~/code/job-listing-scraper/data/jobs.db` — 3,100+ rows, `jobs`,
`runs`, `job_observations`, `job_changes`) over a REST API with **real input
validation**.

The roadmap line is one sentence: _"A small FastAPI web service that exposes
that data over a REST API with input validation."_ The exit criterion is
sharper: **"The API returns correct JSON and rejects bad input, and every line
is explained."**

So this build is not about having endpoints. It is about the **contract**: what
goes in, what comes out, what happens when someone sends garbage, and why the
answer is a 422 with a useful body instead of a 500 with a stack trace.

Build 1 taught persistence. Build 2 taught "the outside world is hostile — the
DOM lies." Build 3 teaches the same lesson pointed the other way: **this service
is now the outside world for somebody else, and its contract has to hold.**

---

## THE OPERATING CONTRACT — read this before every response

### Operating mode — Claude implements, the learning log records

**Default:** Claude writes the implementation, makes the design calls, and
teaches inline — what each construct does, why this shape rather than another,
what the alternatives cost. Every explanation that would otherwise evaporate in
conversation is written to `learning_log/`.

Two mechanisms are not optional:

1. **Tagging.** Every file Claude writes is logged in `learning_log/gap-log.md`
   under the AI-WRITTEN register, with a one-line note of the concept behind it
   that must be re-derivable from the note alone.
2. **Explain-back.** Before each commit, Claude writes 2–3 questions about the
   code it just produced *and the answers*, into `learning_log/gap-log.md`. No
   gate, no friction — the record is the deliverable.

**Override, available at any time:** the teach-me prompt below switches Claude
out of implementation mode and into Socratic mode for as long as it's asked for.

### Division of labour — the table that settles "who does this?"

| Work                                                                 | Who        | Why                                                                              |
| -------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------- |
| Scaffold: venv, `git init`, `src/` layout, `.gitignore`              | **Claude** | Done — commit `cf6594b`.                                                          |
| Phase 0 decisions + `docs/design.md`                                 | **Claude decides; both sides argued in writing first** | Data-access strategy and error envelope are the two calls that shape everything.  |
| `docs/api.md` — the endpoint + status-code contract                  | **Claude** | This is the artefact a reviewer would read first.                                 |
| **`schemas.py` — Pydantic models, field constraints, validators**    | **Claude** | **This is where Build 3's learning lives** — so the log entry for it is the longest. |
| **The SQL in `repository.py`**                                       | **Claude** | Same. Filtering + pagination + safe ORDER BY is the other half of the build.       |
| `main.py` wiring, `db.py`, exception handlers, middleware, `Depends` | **Claude** | Every file tagged `AI-WRITTEN`.                                                    |
| `Dockerfile`, CI YAML, `pyproject.toml`, `.gitignore`                | **Claude** | Boilerplate.                                                                       |
| Git/GitHub operations                                                | **Claude runs them, explaining each new one** | See §"Git & GitHub operating protocol".                     |
| `learning_log/`, `DEBUGGING.md` entries                              | **Claude** | Every learning item and every gap is stored here. This is the record of the build. |

### Claude must NOT:

- Write code without explaining it. Silent implementation is the failure mode.
- Fix a bug without first recording what the traceback meant and where it pointed.
- Refactor beyond the requested scope without saying so.
- Reach for a library as a substitute for explaining the underlying problem.
- Let an explanation live only in conversation. If it isn't in `learning_log/`,
  it did not happen.

**The three that get the longest notes.** These are where Build 3's learning
lives, so Claude writes them *and* writes a fuller-than-usual log entry for each:

- **The Pydantic models.** `Annotated[int, Field(ge=1, le=100)]` is the answer to
  a puzzle — the note records what the field is, what values are legal, what
  happens at the boundary, and what happens when it's missing.
- **The query builder.** Building a WHERE clause from optional filters without
  string-concatenating user input is the exact skill this build exists to teach.
  The note records how the fifth optional filter is added without a combinatorial
  mess.
- **The route signatures.** The note records the path, the method, the status
  code a success returns, and what a client that gets it wrong sees.

### Teach-me prompt (override)

> I'm learning [X]. Don't give me code, but help me write it line by line by
> asking me questions that lead me to the solution, and only confirm or correct
> my reasoning.

---

## Scaffold status

Done and committed (`cf6594b`): `uv` project, `src/jobsapi/` layout, `.venv`,
`.gitignore`, `pyproject.toml`, `learning_log/`, `DEBUGGING.md`, `docs/`.

`ModuleNotFoundError: No module named 'jobsapi'` after `uv run pytest` is a
packaging question, not a typo — the answer belongs in the learning log the
first time it appears.

---

## What this build is NOT

- **Not a rewrite of the scraper.** This service does no HTTP fetching, no
  parsing, no scheduling. Importing `beautifulsoup4` here means a boundary was
  crossed.
- **Not a database migration project.** Build 2 owns the schema. This service is
  a **reader** of that schema. If a column is wrong, that's a Build 2 bug fixed
  in Build 2's repo.
- **Not a front end.** No templates, no HTML, no React. JSON only. `/docs`
  (Swagger, generated by FastAPI) is the entire UI.
- **Not an auth project.** No login, no JWT, no users. A single optional API key
  on write endpoints is the ceiling, and only if Phase 4 happens.
- **Not deployed to the public internet.** Local + Docker is the finish line. A
  public deployment means rate limiting, secrets management and abuse handling —
  a different build, and not this one.

---

## Phase 0 — the two decisions that come before any code

Claude argues both sides in writing, decides, and records the decision and the
reasoning in `docs/design.md`.

### Decision 1 — how does this service get the data?

| Option                                                          | For                                                                                          | Against                                                              |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **A. Open Build 2's `jobs.db` read-only via a configured path** | Always live; zero copying; forces the read-only URI, busy-timeout and `database is locked` work | Two processes, one file; the API breaks if the scraper repo moves       |
| **B. Copy a snapshot into this repo's `data/` on demand**       | Total isolation; reproducible; trivial tests                                                   | Stale data; a sync step that gets forgotten; two copies of the truth    |
| **C. Import `jobscrape` as a dependency and reuse its storage** | No duplicated SQL                                                                              | Couples two repos; Build 2's storage layer isn't an API's query layer   |

**Decision: A**, with the path in config and the connection opened `mode=ro`.
See `docs/design.md` for the full reasoning and the measured facts behind it.

**One rule is fixed regardless: this service never writes to `jobs.db`.**
Read-only at the connection level, not by good intentions. If Phase 4 adds
writes, they go to a *separate* database this service owns.

### Decision 2 — what does an error look like?

Every error this API returns has the same shape. FastAPI's default 422 body is
one option; a hand-rolled `{"error": {...}}` envelope is another; RFC 9457
problem details is the third. One is picked, written into `docs/api.md`,
enforced by an exception handler, and tested.

The question that decides it: **what would the author of a client for this API
want to read in the failure case?**

**The sub-decision hiding inside it: `400` or `422` for a cross-field failure?**
`limit=abc` is malformed — 422, and FastAPI supplies it for free. But
`salary_min_gte=50000&salary_max_lte=10000` is *well-formed and each field is
individually legal*; the request is only nonsense as a whole. One reading says
that's semantically invalid → `400`. The other says validation is validation →
`422`, which is also what a Pydantic model validator produces by default.

**Decision: RFC 9457, and `422` throughout**, with the discrimination carried in
the body (`VALIDATION_FAILED` vs `CROSS_FIELD_CONFLICT`) rather than the status
line. `422` is `Unprocessable Content`; the log records where that status code
comes from. The hardening table below assumes `422` and stays as written.

---

## Endpoint surface — the draft

Claude finalises this in `docs/api.md` with a status code table. Every path,
method, status code and response model is recorded with its justification.

| Method | Path                  | Purpose                                                     |
| ------ | --------------------- | ----------------------------------------------------------- |
| GET    | `/health`             | Liveness. Touches no database. Always cheap.                 |
| GET    | `/jobs`               | Filtered, paginated, sorted list. **The heart of the build.** |
| GET    | `/jobs/{job_id}`      | One job. `404` when it doesn't exist.                        |
| GET    | `/jobs/{job_id}/changes` | Edit history from `job_changes` — the thing a plain CSV can't give you. |
| GET    | `/sources`            | Sources with row counts and last run status.                 |
| GET    | `/runs`               | Scrape run history from `runs`, paginated.                   |
| GET    | `/stats`              | Row counts, null rates per field, salary coverage.           |

`/jobs` query parameters — every one of these is a validation exercise:

| Param                            | Type            | Rule                                                          |
| -------------------------------- | --------------- | ------------------------------------------------------------- |
| `limit`                          | int             | `1..100`, default `20`. Out of range is **422, not clamped**.  |
| `offset`                         | int             | `>= 0`. Past the end returns `200` with an empty list.         |
| `q`                              | str             | Max length capped. `%` and `_` escaped before it reaches SQL.  |
| `source`                         | enum            | Must be a known source. Unknown value → 422 listing the legal ones. |
| `company`                        | str             | Exact or prefix — decided and documented in `docs/api.md`.     |
| `remote`                         | tri-state       | `true` / `false` / `unknown`. **`NULL` ≠ `False`** — Build 2's data contract, honoured here. |
| `seniority`                      | enum            | Nullable in the data; the filter must cope.                    |
| `salary_min_gte` / `salary_max_lte` | int          | `>= 0`, and `min <= max` — a **cross-field** check.            |
| `currency`                       | str             | ISO 4217, 3 chars, uppercased before matching.                 |
| `posted_after` / `posted_before` | date            | ISO dates. `after > before` → 422.                             |
| `sort`                           | enum            | Column **allowlist**. Never interpolated from raw input.       |
| `order`                          | enum            | `asc` / `desc` only.                                           |

Two things answered in writing in `docs/api.md`, not in code comments:

- **Does `salary_min_gte=100000` include rows where salary is `NULL`?** There is
  no obviously right answer. There is only a documented one — and it governs 69%
  of the dataset, where `salary_min` is NULL.
- **What is the response envelope for a list?** A bare array, or
  `{"items": [...], "total": N, "limit": L, "offset": O}`? Pick, and record why a
  bare array is hard to evolve.

---

## Architecture — the boundary that is the point

Build 1: persistence lives behind `storage.py`. Build 2: a parser never does
HTTP. Build 3's boundary is the same idea a layer up:

```
src/jobsapi/
├── main.py          # app factory, router wiring, exception handlers — no logic
├── config.py        # settings from env: DB path, max page size, log level
├── db.py            # connection per request, read-only URI, row factory
├── schemas.py       # Pydantic: request params + response models = the contract
├── repository.py    # ALL the SQL. Knows nothing about HTTP.
├── errors.py        # domain exceptions (JobNotFound, ...) — not HTTPException
└── routers/
    ├── jobs.py
    ├── runs.py
    └── meta.py      # /health, /sources, /stats
tests/
├── conftest.py      # builds a tiny temp SQLite DB per test — 5 known rows
└── test_*.py        # TestClient only. No network. No real data file.
```

The rules that make it work:

- **A router contains no SQL.** If there's a `SELECT` in `routers/`, the
  boundary broke.
- **Literal path segments are declared before parameterised ones.** FastAPI
  matches routes in declaration order. `/jobs/{job_id}` declared above a
  `/jobs/recent` will swallow it and try to parse `"recent"` as an `int` — a
  `422` on a path that plainly exists. `/stats` is top-level here so the
  collision doesn't arise today; the rule is written down so it doesn't arise
  tomorrow.
- **`repository.py` raises no `HTTPException`.** It raises `JobNotFound`; the
  router translates that to a 404. That's why the repository is testable without
  starting an app.
- **`schemas.py` is the public contract.** Every endpoint declares a
  `response_model`. An undeclared field must not leak — that's how `description`
  (avg 5.7 KB, max 33 KB) stays out of list responses by accident-proof design
  rather than vigilance.
- **Tests swap the database through the dependency, not a monkeypatch.**
  `app.dependency_overrides[get_conn] = ...` is the seam. If the app can't be
  pointed at a fixture DB without editing module globals, the `Depends` wiring is
  wrong.
- **No test touches the real `jobs.db`.** `conftest.py` creates a temp DB with
  the same schema and a handful of hand-written rows, including the nasty ones:
  null salary, null `posted_at`, a unicode company name, an apostrophe in a
  title.
- **No global connection object.** One connection per request, closed after. The
  reason a shared `sqlite3.Connection` across requests is a bug goes in the log
  before the code is written.

---

## The blocking-I/O trap — settled before writing a single route

FastAPI accepts `async def` or `def` endpoints. `sqlite3` is a **blocking**
library. An `async def` endpoint that calls blocking `sqlite3` stalls the entire
event loop — the server appears to work perfectly in testing and falls over the
moment two people use it.

Recorded in the learning log before Phase 2: **what FastAPI does differently
with a `def` endpoint versus an `async def` one, and which one a `sqlite3` query
belongs in.**

---

## What must not crash it — the hardening table

Every row gets a test. Same discipline as Build 2's messy-data pass.

| Input / condition                              | Required behaviour                                             |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `limit=0`, `limit=1000`, `limit=abc`           | `422`, body names the field and the constraint                 |
| `offset=-1`                                    | `422`                                                          |
| `offset` past the end                          | `200`, `items: []`, correct `total`                            |
| `/jobs/abc`                                    | `422` (path type), not `500`                                   |
| `/jobs/999999999`                              | `404` with the error envelope                                  |
| `q` containing `%`, `_`, `'`, `;`, emoji       | Escaped, matched literally, no SQL error                       |
| `q` 10,000 characters long                     | `422` on length, not a slow query                              |
| `sort=id;DROP TABLE jobs`                      | `422` — enum allowlist, and the DB is read-only anyway         |
| `posted_after=2027-01-01&posted_before=2020-01-01` | `422` from a cross-field validator                         |
| `salary_min_gte=50000&salary_max_lte=10000`    | `422`                                                          |
| Row with `NULL` salary / location / `posted_at`| Serialised as JSON `null` — never `"None"`, never omitted      |
| DB file missing at startup                     | Loud, readable failure — not a `500` on the first request      |
| DB schema drifted (missing expected column)    | Loud startup failure via `PRAGMA table_info` check — `user_version` is 0, so there is no version to compare |
| DB locked (scraper running)                    | Busy timeout, then a clean `503` — never a hang                |
| DB wedged (`SQLITE_READONLY_ROLLBACK`)         | Distinct from busy: needs a human, must not be retried as a `503` |
| Unknown query parameter `?colour=red`          | Documented decision: ignore or `422`. Either way, **tested**   |
| Any unhandled exception                        | `500` in the standard envelope, full traceback in the **log**, no internals in the **body** |

---

## Build phases

### Phase 1 — skeleton that ships

`/health`, app factory, `uv run uvicorn`, one test with `TestClient`, CI green.
Nothing else. Prove the whole loop works before adding surface.

### Phase 2 — the read path

`GET /jobs` (no filters yet, just `limit`/`offset`) and `GET /jobs/{job_id}`.
Repository boundary established. Response models declared. `conftest.py` builds
its own fixture DB. This is where the blocking-I/O question gets answered.

### Phase 3 — filtering, sorting, and the validation pass

Every parameter in the table above. Every row of the hardening table gets a
test. The error envelope handler lands here. **This phase is the build.**

### Phase 4 — a write path (optional but recommended)

`POST /notes` or `POST /watchlists` against a **separate** API-owned database.
Request bodies, `201 Created` with a `Location` header, `409` on duplicate,
`204` on delete, and the difference between `PUT` and `PATCH`. Pydantic
validation on a body is a different exercise from validation on query params —
this is the phase that earns "input validation" fully.

### Phase 5 — operational

Structured logging with a request id, response-time middleware, `/stats`,
pagination hardening (a stable sort needs a tie-break column or pages repeat
rows), sensible `PRAGMA`s and a busy timeout.

### Phase 6 — ship

`Dockerfile` (multi-stage, non-root user, healthcheck, the DB mounted as a
volume rather than baked in), README, CI green, tag.

---

## Stack & commands

- Python 3.13, managed by `uv`. No global pip installs.
- `fastapi`, `uvicorn[standard]`, `pydantic` v2, `pydantic-settings`, stdlib
  `sqlite3`.
- `ruff` lint + format, `pytest`, `httpx` (FastAPI's `TestClient` needs it).
- **No ORM.** No SQLAlchemy, no SQLModel in this build. Same reason Build 1 used
  `argparse` and Build 2 refused Scrapy: the framework's hidden work has to be
  visible once before a framework is allowed to hide it.
- **No Alembic, no migrations.** This service doesn't own the schema.

```bash
uv sync
uv add fastapi "uvicorn[standard]" pydantic-settings
uv add --dev pytest ruff httpx
uv run uvicorn jobsapi.main:app --reload      # dev server, then open /docs
uv run pytest
uv run ruff check --fix && uv run ruff format
docker build -t job-listings-api . && docker run -p 8000:8000 \
  -v ~/code/job-listing-scraper/data:/data:ro job-listings-api
```

---

## Definition of done

- [ ] `docs/design.md` (the two Phase 0 decisions) and `docs/api.md` (the
      endpoint + status code contract) exist, with the reasoning for both.
- [ ] Every endpoint declares a `response_model`. Nothing undeclared leaks.
- [ ] Every row of the hardening table has a test and passes.
- [ ] Every 4xx response uses the one documented error envelope.
- [ ] `pytest` runs green **with the wifi off** and **with `jobs.db` deleted** —
      the suite builds its own database.
- [ ] The service never writes to `jobs.db`. Enforced at the connection, not by
      intention.
- [ ] `/docs` is accurate enough that a stranger could use the API from it alone.
- [ ] GitHub Actions green on push.
- [ ] `docker build` works and the container serves real data from a mounted volume.
- [ ] README a stranger can follow.
- [ ] **Every line is explained in `learning_log/`**, including all the ones
      Claude wrote — which is all of them.

---

## The viva — answered in writing at the end of each phase

"Every line is explained" is unfalsifiable until it's a list. Claude answers
these in `learning_log/learning-log.md` at the end of the phase that introduces
them.

**Framework mechanics**

- What does `@app.get("/jobs")` actually *register*, and in what?
- What is `uvicorn` doing that `python main.py` isn't? What is ASGI?
- What generates `/docs`, and where does the schema in it come from? So what
  does it mean when the docs are wrong?

**The two that decide whether the app survives load**

- What does FastAPI do differently with a `def` endpoint versus an `async def`
  one, and which should a blocking `sqlite3` call live in?
- What is a dependency, when does it run, why does `yield` matter, and why is a
  shared `sqlite3.Connection` across requests a bug?

**The contract**

- Why `422` and not `400` for a validation failure — and what is `422` called?
- What does `response_model` do at runtime, and what does it cost?
- Why can a `WHERE` value be parameterised but not an `ORDER BY` column?
- What does `docs/api.md` say about `NULL` salaries and the `salary_min_gte`
  filter, and why is that a decision rather than a bug?

---

## The debugging ladder

Followed in order, and what each rung turned up gets recorded:

1. Read the traceback top to bottom. Find the last line that is project code.
2. Print the variable. Check it's what it's assumed to be.
3. Read the docs for the function being called.
4. State the problem in plain English before changing anything.

API-specific rungs, before concluding a request "doesn't work":

- **What status code came back?** Not "it failed" — the number. `422` is
  validation working, `500` is a bug, `404` is routing or data.
- **Read the response body.** FastAPI's 422 body names the exact field and rule.
  Skipping it skips the free answer.
- **Check `/docs` and `/openapi.json`.** Does the schema say what it's assumed
  to say? Wrong generated docs mean wrong type hints.
- **Did the request even reach the route?** Add a log line. A 404 on a path that
  plainly exists is usually a router prefix or a trailing slash.
- **Query the DB directly with `sqlite3` and the same SQL.** Is it the query or
  the API? Splitting that in two is the whole point of the repository boundary.

---

## At the start of a work session

1. Say which phase we're in and what "done" looks like for that phase.
2. Skim `learning_log/gap-log.md` — anything appearing 3+ times gets written up
   properly before more code is added.
3. Don't open with code. Open with the smallest thing that could work and the
   test that would prove it.

---

## learning_log — the record of the build

`learning_log/learning-log.md` and `learning_log/gap-log.md`. **Claude updates
them constantly.** Every learning item and every gap is stored here — this is
where the understanding lives, so an entry that isn't written is understanding
that is lost.

- **Learning log**, one entry per problem: what broke → why it happened → what
  it teaches → where it was applied → how to detect it next time.
- **Gap log**: every non-obvious thing, recorded as it comes up. Weekly review —
  anything appearing 3+ times gets a full write-up in the learning log.
  Everything else was noise.

After every significant problem: identify the gap → write what actually happened
→ record the gap, where it appeared, and how to recognise it next time.

---

## DEBUGGING.md — the failure record

Same contract as Build 2. Newest entry at the top, four bullets, significant
failures only:

```markdown
## YYYY-MM-DD — one-line title

- **Problem:** what happened — the symptom, and the exception type if there was one.
- **Root cause:** why it happened. Not "the query broke" — _why_ it broke.
- **Solution:** how it was fixed, and where (file / function).
- **Lesson:** what to understand so this class of bug doesn't recur.
```

**Claude maintains this.** After any failure that meets the bar, Claude writes
the entry — root cause and lesson included — without waiting to be asked.

---

## Git & GitHub operating protocol

Claude is authorized to perform Git and GitHub operations for this project on
the project owner's behalf — local Git (`init`, `status`, `add`, `commit`,
`log`, `diff`, `branch`, `switch`, `merge`, `rebase`, `stash`, `restore`,
`reset` when appropriate, `remote`, `fetch`, `pull`, `push`, `tag`) and GitHub
via `gh` (create/clone/configure repos, branches, PRs, reviews, merges, issues,
labels, Actions runs, CI inspection, releases). Use `gh` rather than the browser
where it fits.

**Teaching requirement:** for any operation not already explained earlier in the
project, state first what it accomplishes, which concept is involved, the
command, what it does, why now, and its effect — then run it, and log the
explanation.

Branch per phase, PR per feature, same as Builds 1 and 2.

### 1. Permitted operations

**Local Git:** `init`, `status`, `add`, `commit`, `log`, `diff`, `branch`,
`switch`, `checkout`, `merge`, `rebase`, `stash`, `restore`, `reset` when
appropriate, `remote`, `fetch`, `pull`, `push`, `tag`, and other normal Git
operations when necessary.

**GitHub:** create/clone/view repositories, edit repository settings, push and
create branches, create/review/merge/close/reopen pull requests, delete
branches, create and update issues, manage labels, view and run GitHub Actions
workflows, inspect CI failures, create releases and tags, manage repository
metadata, sync/fork repositories when required, and other normal GitHub
operations required by the project.

Use the GitHub CLI (`gh`) where appropriate rather than manual browser
operations.

### 2. Teaching requirement

Before executing an important operation, briefly state:

- What the operation accomplishes.
- Which Git/GitHub concept is involved.
- Which command will run.
- What the command does.
- Why it's needed at this point.
- What effect it will have.

Then perform the operation.

### Sole Author and Contributor Policy

**The project owner must remain the sole author and contributor.**

Claude is an AI development assistant acting on behalf of the project owner. Claude must **not** be credited as a co-author, contributor, or separate project participant.

For all Git and GitHub operations:

* Do **not** add `Co-authored-by:` trailers identifying Claude, Claude Code, Anthropic, or any AI system.
* Do **not** configure Git with Claude/Anthropic as the author or committer identity.
* Do **not** create GitHub commits that attribute authorship or contribution to Claude or Anthropic.
* Do **not** add Claude/Anthropic as a repository contributor, collaborator, or project member unless explicitly requested by the project owner.
* All commits must be authored under the project owner's Git identity.
* All GitHub contributions must appear under the project owner's GitHub account.
* Claude may write, modify, review, test, commit, branch, merge, push, create PRs, and perform other authorized Git/GitHub operations, but these actions are performed **on behalf of the project owner**, not as a separate contributor.
* PRs, issues, releases, and other GitHub activity created by Claude should use the project owner's account/identity where technically possible.

**Default rule:**

> Claude assists with the entire development workflow, but the project owner remains the sole author and contributor. Never add Claude, Claude Code, Anthropic, or any AI identity as a co-author or contributor.

This policy applies to every branch, feature, commit, pull request, merge, release, and future Git/GitHub operation in this project.

---

## Documentation & shipping protocol

Before this is finished, Claude reviews the whole project and writes a
professional `README.md` a stranger could clone and run without asking anyone
anything:

**Architecture/design goes first**, then: Title · Description · Features (only
ones that actually exist) · Tech stack · Project structure · Requirements ·
Installation · **Configuration (the DB path env var)** · Usage (**verify every
documented command and every example request against the running app**) ·
**API reference with status codes** · **Where the data comes from** (link to
Build 2, and its politeness/legal statement) · Testing (and that tests need
neither network nor the real database) · Docker · Development setup · CI badge.
Then verify it.

**Ship sequence:**
tests → lint → format → clean clone test → `docker build` → README verification
(run every documented `curl`) → git status review → commit → push → CI green →
**version check** → release/tag.

**The version check**, added after `v0.8.0` shipped an app reporting `0.7.0`:
start the built artefact and ask it what version it thinks it is —
`/openapi.json`'s `info.version` and the startup log, since `/health` carries no
version by design. Compare it to the tag about to be cut. "The tests pass" does
not answer this: the version was internally consistent and wrong. The check goes
*before* the tag because a pushed tag is the hardest thing in Git to un-say.

---

## What this build must record

Carried forward: functions, modules, data structures, file I/O, JSON, error
handling, validation, SQL/SQLite, pytest, Git/GitHub, architecture, dependency
and environment management.

New in this build, and the reason it's Build 3:

- **HTTP as a contract** — methods, path vs query vs body, and defensible status
  codes: `200`, `201`, `204`, `400` vs `422`, `404`, `409`, `503`, `500`.
- **Declarative validation** — Pydantic v2 models, `Field` constraints,
  `Annotated`, field vs model validators, and why the type hint _is_ the
  validation rather than a comment about it.
- **Request/response modelling** — the input model is not the database row and
  neither is the output model; three shapes, on purpose.
- **Dependency injection** — `Depends`, why a per-request connection is a
  dependency and not a global, and how that makes tests trivial.
- **ASGI, sync vs async, and blocking I/O** — the single most common way to
  build a FastAPI app that's secretly broken under load.
- **Pagination as a design problem** — limit/offset, total counts, stable sort
  order, and why an unstable sort silently repeats rows across pages.
- **SQL injection and the allowlist pattern** — parameterised queries for
  values, an enum allowlist for identifiers, because you cannot parameterise a
  column name.
- **Error design** — one envelope, useful messages, tracebacks in logs and never
  in bodies.
- **OpenAPI** — that the docs are generated from the types, so wrong docs mean
  wrong types.
- **Containerisation** — what an image is, why the data file is a mounted volume
  and not a layer, and why the container doesn't run as root.
