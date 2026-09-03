# Design decisions — Job Listings API (Build 3)

Status: **Phase 0 — closed.** Both sides were argued in writing; the decisions
and their reasoning are recorded below.

---

## Measured facts about the source dataset

Taken 2026-09-01 **at Phase 0** from `~/code/job-listing-scraper/data/jobs.db`,
read-only. The figures below are a snapshot and are left as measured — the
decisions they justify were made against them.

| Fact | Value | Why it matters here |
| ---- | ----- | ------------------- |
| File size | 58 MB | Too big to vendor into this repo; big enough that a snapshot copy is a real step |
| `journal_mode` | **`delete`** (not WAL) | A writer takes an EXCLUSIVE lock; readers get `SQLITE_BUSY` during a scraper commit |
| `page_size` | 4096 | Baseline before any PRAGMA tuning in Phase 5 |
| Rows | jobs 3105 · runs 55 · job_observations 9975 · job_changes 3265 | `/jobs` needs pagination; `/runs` barely does |
| `description` | avg 5.7 KB, max 33 KB (~18 MB total) | Must not appear in list responses — `response_model` enforces this structurally |
| `currency` NULL | 1875 / 3105 | The `currency` filter meets NULL constantly |
| `remote` NULL | all `greenhouse:*` sources; never on `arbeitnow` | Tri-state filter is not decoration — NULL is the majority case for most sources |
| `posted_at` NULL | 0 rows | Today. The schema still permits NULL, so the code must not assume otherwise |
| Distinct sources | 8 (`arbeitnow`, `greenhouse:{airtable,anthropic,discord,duolingo,figma,gitlab}`, `python_org`) | The `source` filter enum has to come from the data, not a hardcoded list that rots |

**Re-measured at Phase 6, same day, after the scraper ran again:** file 64 MB;
jobs 3,498 · runs 63 · job_observations 12,052 · job_changes 3,592; `description`
avg 5.4 KB, max 33 KB (~19.3 MB); `currency` NULL 2,170 / 3,498; `salary_min`
NULL 70.4%; `job_changes` values 36.1 MB with a single value of 30,646
characters.

The absolute numbers moved by roughly 13% in a day. **The proportions did not**
— `salary_min` NULL went 69% → 70.4%, and every decision in this document rests
on a proportion or on a mechanism, not on a row count. That is the reason to
prefer "NULL in ~70% of rows, so the filter's NULL behaviour must be documented"
over "3,105 rows": the first survives the data growing and the second is stale
the next time the scraper runs. Figures quoted anywhere in `docs/` are snapshots
and carry the date they were taken.

---

## Decision 1 — how does this service get the data?

### Option A — open Build 2's `jobs.db` read-only via a configured path

**For**
- Always live. No sync step, no staleness, no second copy of the truth.
- Teaches the most: `file:...?mode=ro` URIs, SQLite locking, `busy_timeout`,
  PRAGMAs. These are the things the hardening table's "DB locked" row is about.
- Keeps this repo honest about being a *reader*. There is nothing here to write to.
- Matches the realistic Phase 6 shape: the database is a mounted volume, its path
  is an env var, the image contains code only.

**Against**
- Two processes, one file, and that file is in rollback-journal mode — so a
  scraper commit really does block readers. The `503` path is work, not theory.
- The API breaks if the scraper repo moves. (Mitigated: it's a config value with
  a loud startup check, not a hardcoded path.)
- **This service cannot switch the file to WAL.** `PRAGMA journal_mode=WAL` is a
  write to the database header; a `mode=ro` connection cannot run it. The fix
  lives in Build 2's repo. That is a genuine cross-repo dependency.
- **If Build 2 does switch to WAL, Phase 6 gets harder, not easier.** A reader of
  a WAL database must create the `-shm` shared-memory file, which requires write
  access to the *containing directory*. A `-v ...:/data:ro` mount then fails with
  `SQLITE_READONLY_DIRECTORY` (measured 2026-09-01, not `SQLITE_CANTOPEN`).
  SQLite deletes `-wal`/`-shm` on a clean close, so this is not about a stale
  file left behind: even a pristine WAL database is unopenable, because the
  reader must *create* `-shm` and cannot. A-plus-WAL trades `database is locked`
  for a container that cannot open the file at all.

### Option B — copy a snapshot into this repo's `data/` on demand

**For**
- Total isolation. No locking, no busy timeout, no `503` path.
- Reproducible: a given snapshot always answers the same way.

**Against**
- Stale by however long the sync is neglected, and the staleness is invisible —
  the API looks perfectly healthy while serving last week.
- Two copies of the truth.
- **The copy is not `cp`.** `cp` of a database mid-commit gives a torn file. The
  correct snapshot is `VACUUM INTO 'data/jobs.db'` or `.backup`, both of which
  take a consistent read lock. So "just copy it" is already a thing that has to
  be understood, and it belongs in the README as a command.
- Teaches the least of the three. It removes the exact problems this build was
  meant to expose.
- Does nothing for tests either way — `conftest.py` builds its own fixture DB
  regardless of this decision.

### Option C — import `jobscrape` as a dependency and reuse its storage layer

**For**
- No duplicated SQL.

**Against**
- Couples two repos at the code level. A Build 2 refactor breaks Build 3's tests.
- The premise is wrong: Build 2's storage layer is a **writer's** layer — upsert,
  hash comparison, change detection. An API needs a **query** layer — optional
  filters, allowlisted sort, pagination, counts. Sharing them means one module
  serving two opposed access patterns.
- Hides the SQL that this build exists to write.

### Recommendation

**A**, with the path in config and the connection opened `mode=ro`. The
`journal_mode=delete` finding strengthens this rather than weakening it: the
hardening table's "DB locked → clean 503, never a hang" row stops being a
theoretical test and becomes one reproducible on demand by running the scraper
in another terminal. Neither B nor C allows that test to be written honestly.

### DECISION

**A — open Build 2's `jobs.db` read-only at a configured path.**

The config takes a *path, not a policy*: `JOBSAPI_DB_PATH` defaults to the live
file, and the connection is opened `mode=ro` unconditionally. That collapses the
argument — B stops being a rejected option and becomes a deployment fallback
already owned, selectable at runtime with no code branching on it.

**WAL is deliberately not requested from Build 2 yet.** The obvious follow-up
("ask Build 2 to `PRAGMA journal_mode=WAL`") is wrong at this stage, because it
breaks Phase 6. A reader of a WAL database must *create* the `-shm` shared-memory
file, which needs write access to the containing directory — exactly what
`-v ~/code/job-listing-scraper/data:/data:ro` denies. Measured 2026-09-01:

```
WAL db + chmod -w on its directory + mode=ro open
  -> OperationalError: attempt to write a readonly database
  -> sqlite_errorname = SQLITE_READONLY_DIRECTORY
```

SQLite deletes `-wal`/`-shm` on a clean close, so this is not about a stale file
left behind: even a pristine WAL database is unopenable under that mount. WAL
would trade `database is locked` for a container that cannot open the file at
all. If the issue is ever filed upstream, it carries this reasoning rather than a
bare "please enable WAL".

**What is done instead:** `PRAGMA busy_timeout` on every connection, and error
handling that branches on the *code*, never on a substring of the message:

```python
e.sqlite_errorname == "SQLITE_BUSY"  # transient -> 503 + Retry-After
e.sqlite_errorname == "SQLITE_READONLY_ROLLBACK"  # wedged   -> needs a human, do not retry
```

Those two conditions want different responses and `str(e)` cannot separate them.
`sqlite_errorname` is available on Python 3.11+ (verified here on 3.13.15,
SQLite 3.53.1).

**Why the lock risk is acceptable.** Run *duration* is not lock *duration* — a
scrape is mostly HTTP fetching, which holds no lock; only the commits take
`EXCLUSIVE`. Observed over four days: 1, 8, 12 and 34 runs, and the one complete
automated batch (2026-08-31) ran 03:45:08→03:45:40, 32 seconds wall clock. The
write *frequency* is Build 2's to set, not this service's, so the resilience is
sized to the mechanism rather than to a measured window that could change
tomorrow.

**Schema drift.** `user_version` and `application_id` are both `0`, so there is
no version to compare against. A startup check runs `PRAGMA table_info(jobs)` and
fails loudly if an expected column is absent — turning silent drift into the
hardening table's existing "loud, readable failure at startup" row.

**Fixed regardless of the choice:** this service never writes to `jobs.db`.
Enforced at the connection (`mode=ro`), not by intention. Any Phase 4 write path
goes to a separate database this service owns.

> **Phase 4 happened, and the rule held.** Watchlists are written to
> `JOBSAPI_APP_DB_PATH`, a different file created and owned by this service, with
> the settings inverted throughout: read-write rather than `mode=ro`, WAL rather
> than `delete`, `foreign_keys` ON, and a schema this service creates rather than
> merely verifies. `jobs.db` gained a second enforcement (`PRAGMA query_only`)
> rather than losing one, and a test reads the file's bytes before and after a
> full create/update/delete cycle to prove they are unchanged. The full write
> contract is in `api.md`.
>
> Note that WAL — **declined** above for `jobs.db` — is used for the application
> database. The objection there was that a WAL *reader* must create a `-shm`
> file, which the read-only bind mount forbids; that database is on a writable
> volume and this process is its writer, so the objection does not apply. The
> same setting is right in one place and wrong in the other, which is why "use
> WAL" is not advice.

> **Addendum, 2026-09-03 — the second entry in this ledger: read consistency.**
> The section above reasons about whether this service can *get* a lock. It did
> not ask how many separate read transactions one request takes. The answer was
> "as many as it issues statements": Python's `sqlite3` opens implicit
> transactions before DML only, so a sequence of `SELECT`s runs in autocommit
> and each takes and releases its own `SHARED` lock. `GET /jobs` is two such
> reads — the page and the count — and `GET /stats` is six.
>
> A scraper commit landing between them yields two individually-correct,
> mutually inconsistent answers. The failure has no signal: a `total` that is
> too low makes a client stop paginating early and drop rows, with no error and
> no empty page. `api.md` §6 justifies the list envelope on the grounds that a
> bare array has nowhere to put `total`; a `total` that can disagree with
> `items` undermines the reason the shape was chosen.
>
> **Decision: take the transaction, accept the contention.** Reads that must
> agree are wrapped in `db.read_snapshot` — `/jobs`, `/runs`,
> `/jobs/{job_id}/changes` and `/stats`.
>
> *The lock cost is smaller than it first appears.* Each statement already takes
> `SHARED` for its own duration, so this service could already delay a commit;
> the snapshot does not create that hazard, it widens the window by the gap
> between two statements, and that gap is in-process Python assembling a
> parameter list — no I/O, no network. Set against the sizing above (1–34 runs a
> day, a complete batch running 32 seconds wall clock, and only the commits
> taking `EXCLUSIVE`), the marginal exposure is sub-millisecond against queries
> that are themselves milliseconds.
>
> *The failure modes are asymmetric.* Losing the race produces `SQLITE_BUSY` →
> `503` with `Retry-After` — a path that already exists, is already classified
> by `sqlite_errorname`, is already documented and already tested. Decision 2 is
> an argument that loud and documented beats quiet and plausible; keeping a
> silent inconsistency to avoid a loud handled failure would contradict it.
>
> *`BEGIN` is deferred, and that is forced.* `BEGIN IMMEDIATE` asks for a write
> lock, which `mode=ro` plus `PRAGMA query_only = 1` refuses. Deferred is also
> sufficient: in rollback-journal mode a read transaction holds `SHARED` from
> the first read until the end, which is what excludes the writer.
>
> *And the trade itself traces back to the WAL decision above.* WAL is the mode
> where a consistent read costs the writer nothing — readers snapshot without
> blocking. WAL is exactly what was given up to keep the bind mount read-only.
> So the choice here is not free-standing: consistent-and-blocking, or
> skewed-and-documented, and the third option was spent in Phase 6.
>
> **Not covered:** the application database. `/watchlists` reads a count and a
> page separately too, but that file is WAL, this process is its only writer,
> and the external-writer mechanism motivating this change does not apply.
> Recorded as an open thread rather than folded in, because wrapping reads there
> interleaves with the write path's implicit transactions and deserves its own
> reasoning.

---

## Decision 2 — what does an error look like?

### The problem, stated concretely

Out of the box FastAPI returns **two incompatible shapes**:

```jsonc
// 422 from request validation (RequestValidationError)
{"detail": [{"type": "int_parsing", "loc": ["query", "limit"],
             "msg": "Input should be a valid integer, ...", "input": "abc"}]}

// 404 from HTTPException(404, "Job not found")
{"detail": "Job not found"}
```

`detail` is a list of objects in one and a bare string in the other. A client
cannot write a single error handler. That asymmetry is the whole reason this is
a decision rather than a default.

### Option 1 — keep FastAPI's defaults

**For:** zero code. The 422 body is genuinely excellent — it names the field via
`loc` and the rule via `msg`. `/openapi.json` describes it correctly for free.

**Against:** the two shapes above. Also fails the Definition-of-Done line
"every 4xx response uses the one documented error envelope" — there isn't one.

### Option 2 — hand-rolled `{"error": {...}}` envelope

**For:** one shape, chosen deliberately, for every 4xx and 5xx. Easy to document
in `docs/api.md`, easy to assert in tests. It controls what a client reads.

**Against:** two exception handlers to write and maintain
(`RequestValidationError`, `HTTPException`, plus a catch-all for `Exception`).
If Pydantic's `loc` and `msg` are not deliberately forwarded into the envelope,
the best part of the default is thrown away and the 422 gets *less* useful.

**Hidden cost:** `/openapi.json` still advertises `HTTPValidationError` for 422
unless `responses=` is overridden on the routes. The generated docs would then
describe a body the app never sends — and "what does it mean when the docs are
wrong?" is a viva question that has to be answered.

### Option 3 — RFC 9457 problem details

**For:** one shape, and it's a *standard* one — `type`, `title`, `status`,
`detail`, `instance`, plus extension members for the field-level errors. Served
as `application/problem+json`. A stranger's client library may already know it.

**Against:** everything in Option 2's column, plus the media type, plus needing
to explain RFC 9457 to anyone who hasn't read it. Arguably more ceremony than a
7-endpoint read-only service needs.

### The sub-decision: `400` or `422` for a cross-field failure?

`422` is **Unprocessable Content** — RFC 9110 §15.5.21, where it landed after
being moved out of WebDAV and renamed from "Unprocessable Entity". Its meaning:
the syntax parsed and the content type was understood, but the *instructions
could not be followed*.

- `limit=abc` — malformed. 422, and FastAPI supplies it free.
- `salary_min_gte=50000&salary_max_lte=10000` — well-formed, each field legal,
  nonsense as a whole. The spec text above describes this precisely, which makes
  the "it's semantic, therefore 400" reading the weaker one.

**The practical asymmetry:** a Pydantic `@model_validator` produces `422`
automatically. Choosing `400` means either raising `HTTPException(400)` by hand
inside the route — which drags validation out of `schemas.py` and into
`routers/`, breaking the boundary this architecture exists to hold — or catching
`RequestValidationError` and re-mapping only the model-level errors by
inspecting `loc`. Both are real code that would have to be defended.

**Consistency argument for 422:** `limit=abc` and `posted_after > posted_before`
both mean "this query is not answerable." One status code for one category is
easier to document, easier to test, and easier to explain.

### DECISION

**RFC 9457 problem details, served as `application/problem+json`, with `422` for
every validation failure including cross-field.**

The deciding argument over the hand-rolled envelope is explainability: the exit
criterion is that every line can be explained, and an adopted vocabulary is
easier to explain than an invented one because the explanation has a citation.
Option 2's objection — that the field-level `errors` array has to be hand-rolled
anyway — argues *for* 9457, not against it: the standardised 80% comes free and
only the part nobody has standardised is invented.

**The dead-`type`-URI problem is avoided, not accepted.** RFC 9457 states that an
absent `type`, or `about:blank`, means "no semantics beyond the status code". So
every problem starts as `about:blank`, and a member is promoted to a real
relative URI (`/errors/cross-field-conflict`) only once there is somewhere to
serve it. No dead links ship on day one, and five types don't have to be invented
up front.

**Shape:**

```jsonc
// Content-Type: application/problem+json
{
  "type":     "about:blank",
  "title":    "Validation failed",
  "status":   422,
  "detail":   "1 query parameter is invalid",
  "instance": "/jobs?limit=0",
  "code":     "VALIDATION_FAILED",        // or CROSS_FIELD_CONFLICT
  "errors":   [{"field": "limit", "rule": "ge", "constraint": 1, "got": "0"}],
  "request_id": "01J..."
}
```

**`422` throughout, with the discrimination in the body.** `code` separates
`VALIDATION_FAILED` from `CROSS_FIELD_CONFLICT` without moving the status line.
This keeps validation inside `schemas.py` where a `@model_validator` already
produces `422` for free — the `400` alternative would require either raising
`HTTPException(400)` inside a route (dragging validation into `routers/` and
breaking the boundary this architecture exists to hold) or re-classifying
`RequestValidationError` by inspecting `loc`. The hardening table in the project brief
assumes `422` and therefore stays exactly as written.

**Two obligations this creates:**

- `responses=` is declared once, app-wide, so `/openapi.json` advertises the
  problem shape rather than FastAPI's `HTTPValidationError`. Otherwise the
  generated docs describe a body the app never sends.
- Pydantic's `loc` and `msg` are forwarded into `errors[]`. Not doing so throws
  away the single best property of FastAPI's default.

`request_id` is carried from the start even though structured logging is Phase 5
— it is the seam that ties a response body to a log line, and retrofitting it
later means changing the envelope after clients have seen it.

Next: write this shape into `docs/api.md`, enforce it with exception handlers for
`RequestValidationError`, `StarletteHTTPException`, `JobNotFound` and a catch-all
`Exception`, and test each one.
