# Progress

Running status of the build. Updated by Claude as work lands.

**Last updated:** 2026-09-03
**Repo:** https://github.com/professor3333/job-listings-api (public)
**Local path:** `~/code/job-listings-api`
**Branch:** `main` — **Phases 1, 2, 3, 5, 6 shipped as v0.6.0**; **Phase 4 as v0.7.0**; **`/runs` duration as v0.8.0**; **re-derivation fixes as v0.8.1**; **read consistency and the empty-filter contract as v0.9.0**; **the application-database snapshot and the `posted_at` startup gate as v0.9.1**
**CI:** 🟢 green — 261 tests passing, lint and format clean, Docker image built
and smoke-tested on every push.
**Releases:** [v0.6.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.6.0)
· [v0.7.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.7.0)
· [v0.8.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.8.0)
· [v0.8.1](https://github.com/professor3333/job-listings-api/releases/tag/v0.8.1)
· [v0.9.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.9.0)
· [v0.9.1](https://github.com/professor3333/job-listings-api/releases/tag/v0.9.1)

Build 3 of Stage 0. A FastAPI service over the dataset Build 2 collected,
exposed as a REST API with real input validation. The exit criterion was **"the
API returns correct JSON and rejects bad input, and every line is explained."**

---

## Phase 0 — the two decisions before any code ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 0 | Scaffold: uv, `src/` layout, ruff, pytest, CI, `.gitignore` | `main` | ✅ done (`cf6594b`) |
| 1 | Decision 1 — how this service reaches the data | `main` | ✅ `docs/design.md` (`cf6594b`) |
| 2 | Decision 2 — what an error looks like | `main` | ✅ `docs/design.md` (`cf6594b`) |

Both options argued in writing before either was chosen, with the measurements
that decided them.

## Phase 1 — skeleton that ships ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | App factory, `/health`, `uvicorn`, one `TestClient` test, CI | `phase-1-skeleton` | ✅ merged (PR #1) |

## Phase 2 — the read path ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | `GET /jobs` with `limit`/`offset`, `GET /jobs/{job_id}` | `phase-2-read-path` | ✅ merged (PR #2) |
| 2 | Repository boundary; response models declared | `phase-2-read-path` | ✅ merged (PR #2) |
| 3 | `conftest.py` builds its own fixture DB | `phase-2-read-path` | ✅ merged (PR #2) |
| 4 | The blocking-I/O question answered: `def`, not `async def` | `phase-2-read-path` | ✅ merged (PR #2) |
| 5 | Stop the suite depending on the developer's real database | `phase-2-read-path` | ✅ `bfc2c51` — escaped defect, see DEBUGGING.md |

## Phase 3 — filtering, sorting, validation ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | All 12 query parameters, cross-field validators | `phase-3-filtering` | ✅ merged (PR #3) |
| 2 | RFC 9457 error envelope + every exception handler | `phase-3-filtering` | ✅ merged (PR #3) |
| 3 | Every row of the hardening table gets a test | `phase-3-filtering` | ✅ merged (PR #3) |

**This phase was the build**, per CLAUDE.md. The `sort` allowlist, the tri-state
`remote` filter and the LIKE escaping all landed here.

## Phase 5 — operational ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | Structured JSON logging with a request id (ContextVar) | `phase-5-operational` | ✅ merged (PR #4) |
| 2 | Response-time middleware, `X-Request-ID`, `X-Response-Time-ms` | `phase-5-operational` | ✅ merged (PR #4) |
| 3 | `PRAGMA`s and the busy timeout | `phase-5-operational` | ✅ merged (PR #4) |
| 4 | `/stats`, `/sources`, `/runs`, `/jobs/{id}/changes` | `phase-5-operational` | ✅ merged (PR #4) |
| 5 | Pagination hardening — a tie-break column on every sort | `phase-5-operational` | ✅ merged (PR #4) |

Run out of order, before Phase 4, because Phase 4 was optional and the read
surface was the deliverable.

## Phase 6 — ship ✅ COMPLETE

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | `Dockerfile` — multi-stage, non-root, healthcheck, DB as a volume | `phase-6-ship` | ✅ merged (PR #5) |
| 2 | `.dockerignore` | `phase-6-ship` | ✅ merged (PR #5) |
| 3 | `scripts/make_demo_db.py` — so a stranger and CI can run it at all | `phase-6-ship` | ✅ merged (PR #5) |
| 4 | CI job that builds the image and queries the running container | `phase-6-ship` | ✅ merged (PR #5) |
| 5 | README, architecture first | `phase-6-ship` | ✅ merged (PR #5) |
| 6 | The explain-back that should have preceded the commit | `phase-6-log` | ✅ merged (PR #6) |
| 7 | The last ten register write-ups | `register-writeups` | ✅ merged (PR #7) |
| 8 | Container verified on arm64 against the real dataset | `docker-verified` | ✅ merged (PR #9) |

## Phase 4 — a write path ✅ COMPLETE

Optional per CLAUDE.md, deferred past Phases 5 and 6, then done in full.

| # | Step | Branch | Status |
|---|------|--------|--------|
| 1 | `appdb.py` — a second database this service owns | `phase-4-write-path` | ✅ merged (PR #8) |
| 2 | Body models: create / replace / patch, three shapes | `phase-4-write-path` | ✅ merged (PR #8) |
| 3 | Nine `/watchlists` endpoints; 201+`Location`, 204, 409, 404, 422 | `phase-4-write-path` | ✅ merged (PR #8) |
| 4 | Optional `X-API-Key`, off unless configured | `phase-4-write-path` | ✅ merged (PR #8) |
| 5 | 44 tests, incl. the read database's bytes compared before/after | `phase-4-write-path` | ✅ merged (PR #8) |

---

## Ship sequence — Phase 6, run 2026-09-01

| Step | Result |
|------|--------|
| tests | ✅ 153 passed |
| lint | ✅ `ruff check` clean |
| format | ✅ `ruff format --check` clean |
| clean clone test | ✅ fresh clone → `uv sync` → 153 passed → demo DB → server → `/health`, `/jobs`, a 422 |
| README verification | ⚠️ every documented command and example request run against the live app — but **not the links**, three of which were dead; caught 2026-09-02, see DEBUGGING.md |
| `docker build` | ⚠️ not run locally at the time — no container runtime on the machine; covered by the new CI job |
| git status review | ✅ clean tree, branches deleted on merge, stale refs pruned |
| commit / push | ✅ PRs #5, #6, #7 |
| CI green | ✅ both jobs |
| release / tag | ✅ v0.6.0, annotated tag + GitHub release |

## Ship sequence — Phase 4, run 2026-09-01

| Step | Result |
|------|--------|
| tests | ✅ 197 passed (44 new) |
| tests with `jobs.db` absent | ✅ 197 passed |
| home directory clean afterwards | ✅ — it was **not**, first time round; see DEBUGGING.md |
| lint / format | ✅ clean |
| clean clone test | ✅ fresh clone → `uv sync` → 197 passed, home untouched |
| README verification | ✅ every new example run first; the PATCH/PUT pair documented from observed output |
| OpenAPI check | ✅ all 9 operations, 409 and 401 documented, `X-API-Key` in the schema |
| CI green | ✅ incl. the write path exercised inside the container |
| release / tag | ✅ v0.7.0, annotated tag + GitHub release |

## Local container verification — run 2026-09-02

CI only ever sees a five-row demo database on `linux/amd64`. This is the part it
structurally cannot check.

| Check | Result |
|-------|--------|
| image | ✅ `linux/arm64`, 266 MB — **quantity not recorded**, see the note below the v0.9.0 sequence |
| `/jobs` total | ✅ **3498** — the real dataset |
| `/sources` | ✅ all 8 |
| `/stats` | ✅ 3,498 jobs · 63 runs · 3,592 changes |
| `?limit=0` | ✅ 422 |
| write path | ✅ watchlist created, real job attached |
| `id -u` | ✅ 1001 |
| write to `/data/jobs.db` | ✅ refused |
| healthcheck | ✅ `healthy` |
| logs | ✅ JSON on stdout, unbuffered |
| `docker stop` | ✅ 0.64s, exit 0 — `SIGTERM` forwarded, not a `SIGKILL` after the timeout |

## Ship sequence — v0.8.0, run 2026-09-02

The `/runs` duration work (PR #14) landed after `v0.7.0` and sat untagged for
twelve commits. A new response field is a released change, not a documentation
edit — the reasoning that left `v0.6.0` alone does not extend to it.

| Step | Result |
|------|--------|
| tests | ✅ 200 passed (3 new since v0.7.0) |
| tests with `jobs.db` absent | ✅ 200 passed, `JOBSAPI_DB_PATH` pointed at a path that does not exist |
| home directory clean afterwards | ✅ `~/.local/share/jobsapi/app.db` predates the run by 11h, mtime unchanged |
| lint / format | ✅ `ruff check` clean, `ruff format --check` clean on 35 files |
| CI green | ✅ both jobs, `main` at `3468048` |
| release / tag | ✅ v0.8.0, annotated tag + GitHub release |

---

## Ship sequence — v0.8.1, run 2026-09-02

The first run of the sequence with a **version check** in it, added because
`v0.8.0` shipped an app reporting `0.7.0` and nothing in the old sequence would
have noticed. The check is not "the tests pass" — the version was internally
consistent and wrong.

| Step | Result |
|------|--------|
| tests | ✅ 214 passed (14 new) |
| lint / format | ✅ clean |
| CI green on the merge commit | ✅ both jobs, `c1fc7c4` |
| **version check — running server** | ✅ `/openapi.json` `info.version` = `0.8.1`, startup log = `0.8.1` |
| live behaviour, real dataset | ✅ `currency` `usd`/`USD`/`dollars` → 200/200/422; `limit` 100/101 → 200/422; `/runs?colour=red` → 422 |
| published schema | ✅ `currency` carries `^[A-Za-z]{3}$`; `limit` carries `minimum: 1`, `maximum: 100` |
| release / tag | ✅ v0.8.1, annotated, on the **merge commit** — the thing a `checkout` reproduces |

**Two rules this run fixed in place.**

*Tag the merge commit, after CI is green on `main`* — not the branch head. The
tag has to name what `git clone && git checkout v0.8.1` actually reproduces.

*Fix forward; never move a published tag.* `v0.8.0` permanently ships an app
reporting `0.7.0`. Moving the tag would make one published name mean two
different things depending on when a client fetched — and `git fetch` refuses to
clobber a tag a client already holds, so the two copies would disagree silently,
with no signal that anything happened. A wrong version string is visible and
explicable; a tag that means different things to different people is neither.
The [v0.8.0 release notes](https://github.com/professor3333/job-listings-api/releases/tag/v0.8.0)
now carry a known-issue notice instead — the release body is where a stranger
looks, and editing it leaves the tag object untouched.

---

## Re-derivation — `schemas.py`, run 2026-09-02

The first entry from the syllabus below, run in teach-me mode: `Pagination` and
`JobFilters` reasoned out from the contract before the file was opened. The
derivation was correct on every mechanism — `extra="forbid"` on the base,
`PydanticCustomError` for the cross-field code, `_upper` as transform-or-abstain
— and produced **four defects that a green suite could not see**, because each
is a disagreement *between* artefacts rather than a wrong answer from one.

| # | Finding | Fixed in |
|---|---------|----------|
| 1 | `model_config` restated on `JobFilters`, re-creating the drift its parent's docstring records as fixed | `schemas.py` |
| 2 | The `limit` cap was never tested at its boundary — any value 21–999 passed the whole suite | `tests/test_hardening.py` |
| 3 | `BeforeValidator` withdraws `pattern` from `/openapi.json`; `currency` was enforced but unpublished | `schemas.py`, `docs/api.md` |
| 4 | The version existed in two files; the app reported `0.7.0` for the whole of the `v0.8.0` tag | `main.py`, `pyproject.toml` |

Findings 3 and 4 have `DEBUGGING.md` entries and full learning-log write-ups.
Finding 3 is the substantive one: it is this build's own thesis — *the docs are
generated from the types* — holding everywhere except where a validator quietly
opts a constraint out.

Two method notes worth keeping:

- **A probe needs a case it must succeed at.** The experiment checking whether a
  `yield` dependency runs on a 422 first reported a clean `events=[]`, which was
  a true observation of the wrong experiment — an un-annotated `request`
  parameter had turned into a required query parameter. A control that was
  supposed to pass, and didn't, is what exposed it.
- **One test in the new boundary class hard-codes `100`** rather than importing
  `LIMIT_MAX`. A suite that imports the constant everywhere can only prove the
  code agrees with itself; it cannot notice the cap being changed to 250.

---

## Definition of done

- [x] `docs/design.md` and `docs/api.md` exist, with the reasoning for both
- [x] Every endpoint declares a `response_model`; nothing undeclared leaks
- [x] Every row of the hardening table has a test and passes
- [x] Every 4xx response uses the one documented error envelope
- [x] `pytest` green with the wifi off **and** with `jobs.db` deleted
- [x] The service never writes to `jobs.db` — enforced at the connection, and
      asserted by comparing the file's bytes across a write cycle
- [x] `/docs` accurate enough to use the API from it alone
- [x] GitHub Actions green on push
- [x] `docker build` works and the container serves real data from a mounted volume
- [x] README a stranger can follow
- [x] Every line explained in `learning_log/` — 31 register entries, all written up

All eleven met.

---

## Design decisions locked

**Phase 0**, in `docs/design.md`:

| § | Decision |
|---|----------|
| 1 | Open Build 2's `jobs.db` read-only via a configured path — not a snapshot copy, not a shared dependency. `mode=ro` URI + `PRAGMA query_only`. WAL **declined**, with the measurement: a WAL reader must create `-shm`, which a read-only bind mount forbids |
| 2 | RFC 9457 problem details, `application/problem+json`, and `422` throughout — the discrimination carried in the body (`VALIDATION_FAILED` vs `CROSS_FIELD_CONFLICT`) rather than the status line |

**The contract**, in `docs/api.md`:

| § | Decision |
|---|----------|
| 3 | NULL never satisfies a filter — governs ~70% of rows, so documented rather than inferred. The opposite call one field over: `remote=unknown` means `IS NULL`, because there NULL is the recorded fact |
| 4 | Unknown query parameters are **rejected**, not ignored — `?limt=5` silently returning unfiltered results is worse than an error |
| 5 | `sort` is a six-member enum allowlist. An identifier cannot be a bound parameter, so it is *chosen*, never interpolated |
| 6 | A list is an envelope (`items`/`total`/`limit`/`offset`), not a bare array — a bare array has nowhere to put `total` and cannot be extended without changing its type |
| 7 | Every sort ends `, id`. `LIMIT`/`OFFSET` over a non-total order silently repeats and skips rows |

**Phase 4**, in `docs/api.md`:

| § | Decision |
|---|----------|
| 8 | Writes go to a **separate database this service owns** — every setting inverted: read-write, WAL, `foreign_keys` ON, schema created rather than verified |
| 9 | `409` not `422` for a duplicate — the body was legal; the *state* refused it |
| 10 | The UNIQUE constraint detects the duplicate, never a prior `SELECT` — check-then-insert is a race both concurrent requests win |
| 11 | `PUT` replaces and `PATCH` merges, so they need **different request models**; `exclude_unset` is the mechanism |
| 12 | `PUT` to a missing id is `404`, not an upsert — ids are server-assigned |
| 13 | `DELETE` on something already gone is `404`, not a silent `204` |
| 14 | A cross-database job reference can dangle; it is reported (`job_missing: true`), never hidden, and still deletable |
| 15 | Missing key and wrong key are both `401` — `403` implies an identity to forbid, and there are none |

---

## Open threads

- **`v0.6.0` points at `7834b6d`**, before four documentation commits that
  landed after it. The code at the tag is identical apart from two corrected
  docstrings. Left alone on purpose — retagging for docs is not worth it.
  Overrule if you'd rather it moved. The same reasoning is why `v0.8.0` *was*
  cut: PR #14 added a response field, which a client can observe, so it needed
  a version to name. Docs move the tip; contract changes move the tag.
- **A whitespace-only text filter is legal and nearly unfiltered.** `?q=%20`
  is a one-character search for a space: `min_length=1` does not touch it, so it
  reaches the SQL as `LIKE '% %'` and matches almost every row. It is the same
  family as finding 4 by the **opposite mechanism** — `""` is falsy and was
  *dropped* before reaching SQL, `" "` is truthy and is *applied* as a filter
  that excludes almost nothing — and a client believes it filtered in both cases.
  Left as-is deliberately, and the line is stated in `docs/api.md` — the bound
  asks *"is there a term"*, not *"is the term useful"*. Fixing it needs a stripping
  `BeforeValidator`, which re-creates the `v0.8.1` `currency` failure (Pydantic
  withdraws `minLength` from `/openapi.json`) and would then need the
  `json_schema_extra` remedy on top. A test pins the case at `200` so the choice
  stays visible rather than becoming an accident.
- **The `source` enum is coupled to Build 2's data.** If the scraper adds a
  source, this service rejects it with a 422 until `SOURCE_VALUES` is updated.
  A loud, documented failure rather than a filter that silently matches
  nothing — but it is a coupling, recorded in `docs/api.md` under "Known
  coupling".
- **The `runs` table permanently holds two eras.** Build 2's zero-duration bug
  was fixed upstream on 2026-09-02 (`job-listing-scraper@1aead71`, issue #29
  closed), but not retroactively: 62 of 71 runs still carry `finished_at`
  exactly equal to `started_at`, and those measurements are unrecoverable.
  `/runs` now reports `duration_seconds`, using exact timestamp equality to
  tell the eras apart and returning `null` — never `0.0` — for the old ones.
  The ratio improves on its own as new runs accumulate; it never reaches zero.
- **The `/sources` LEFT JOIN is defensive, not load-bearing.** All eight
  sources appear in both tables today, so it is currently indistinguishable
  from an inner join. Worth keeping; worth knowing it is untested by real data.
- **SQLite's `LIKE` is case-insensitive for ASCII only**, so `company=ürsprung`
  does not match `Ürsprung AG`. A real fix needs ICU or a normalised column.
  Documented rather than papered over.
- **The application database has no migration path.** `CREATE TABLE IF NOT
  EXISTS` is idempotent but is not a migration system; adding a column later
  needs one, or a documented manual step. `user_version` is set to 1 so a future
  change has something to compare against.
- **`ApiKey` is not an IANA-registered scheme**, so the `WWW-Authenticate`
  header names something unregistered. Sent anyway, because RFC 9110 requires
  the header on a `401` and naming the scheme beats omitting it.
- **Dataset figures in `docs/` are snapshots.** 3,105 jobs at Phase 0, 3,498 at
  Phase 6 — ~13% growth in a day, while the proportions every decision rests on
  held (`salary_min` NULL 69% → 70.4%). Figures now carry the date they were
  measured.
- **The unaided-rebuild checkpoint, carried over from Build 1, did not happen
  here either.** Build 1's PROGRESS.md deferred it to "the next build, run it
  first, not last" — and Build 3 ran Claude-implements from Phase 0. Recorded as
  a fact rather than left looking pending; the syllabus below does not expire.
  **Corrected 2026-09-03:** two syllabus rows had been ticked ✅ for derivations
  *Claude* performed, in a column headed "re-derived unaided". The findings from
  those runs are real and stand; the ticks were not, because they recorded the
  wrong person doing the work — which would have made this very thread look
  half-closed while nothing about it had changed. The table now names who
  derived each row, and ⚙️ is not ✅.

## Queued work

- ~~`README.md` was empty~~ **Written, PR #5**, then extended for Phase 4 in
  PR #8. Every documented command executed against the running app before being
  written down — which found two defects in the process: dead configuration and
  a version mismatch.
- ~~`learning-log.md` was empty~~ **Written, three parts:** eight entries, the
  nine viva questions, and the register write-ups (PRs #7 and #8).
- ~~Ten register rows unwritten~~ **Closed, PR #7.** Checking each claim against
  the machine disproved two of the register's own one-liners.
- ~~`docker build` never run locally~~ **Done 2026-09-02, PR #9.** Table above.
- ~~Phase 4 skipped~~ **Done, PR #8, released as v0.7.0.**
- ~~`/runs` omitted `duration_seconds`, blocked on Build 2~~ **Unblocked and
  shipped 2026-09-02, PR #14.** The upstream fix had already landed an hour
  after the issue was filed and nobody had closed it; verified against the real
  dataset (8 post-fix runs, all with real elapsed times) before closing #29.
  The field is nullable because the fix could not be retroactive.
- ~~The README sent strangers to four 404s~~ **Fixed 2026-09-02, PR #13.**
  Three `README.md` links and one in `PROGRESS.md` pointed at the private
  `job-listing-scraper`. Shipped in v0.6.0 and missed by two ship sequences,
  because links were only ever followed from an account that can see the repo.
  See DEBUGGING.md.
- ~~Repo topics were unset~~ **Set 2026-09-02, PR #12:** `fastapi`, `python`,
  `sqlite`, `rest-api`, `pydantic`, `openapi`. A repository setting rather than
  a file, so it is not in the PR's diff — `gh repo edit --add-topic` writes it
  straight to GitHub.
- **The ship sequence now has a version check**, added 2026-09-02 after
  `v0.8.0` shipped an app reporting `0.7.0`: start the built artefact, read
  `info.version` from `/openapi.json` and the startup log, and compare it to the
  tag about to be cut. `/health` deliberately carries no version — its
  `Literal["ok"]` contract is narrow on purpose and was not widened to make the
  check convenient. The step lives in `CLAUDE.md`, which is untracked and
  therefore local-only, so it is recorded here as well: this file is the copy
  that travels with a clone.
- ~~`CLAUDE.md` cited a commit that no longer exists~~ **Fixed on disk
  2026-09-02**, both references now naming `cf6594b` — but *not* in PR #12's
  diff, because `CLAUDE.md` is excluded in `.git/info/exclude` and has never
  been tracked. That exclusion is local-only, so it does not travel with a
  clone; the file is simply absent from the repository for everyone else.
  The old id `9172d74` was not merely stale: the object still resolves in a
  clone predating the rewrite, so `git cat-file -t` reports a perfectly good
  commit and the reference looks sound from the machine that wrote it.
  `git merge-base --is-ancestor` is the check that matters, and it says
  unreachable from `main`.
- **`CLAUDE.md` stays untracked — decided 2026-09-03, and it is a decision,
  not an oversight.** It was tracked in PR #31 and untracked again in PR #32 at
  the owner's instruction, within the hour. The reasoning for tracking it was
  that a stranger cloning the repo gets no operating contract; the reasoning
  against, which wins, is that the file is the owner's working notes and its
  exclude entry has said `# Local working notes — never published` from the
  start. `PROGRESS.md` remains the copy that travels, which is why the
  version-check step is duplicated into it. **Do not re-track it without
  asking.** The blob was then **purged from history** with `git filter-repo`
  and a force-push (2026-09-03). Untracking removes a file from the tip, never
  from the past, so the purge was a separate operation from PR #32.
  **It is not fully gone from GitHub**, and that is a property of the host, not
  of the rewrite: a force-push never deletes unreachable objects, and
  `refs/pull/31/head` keeps the old commits alive regardless. The file is still
  fetchable at `af3bd18` and through PR #31's own diff. Only GitHub Support can
  drop those refs and run the collection that reclaims the objects — the
  request is filed under "remove sensitive data". No credentials were in the
  file, so this is tidiness rather than an incident.

---

## Ship sequence — v0.9.0, run 2026-09-03

The first release carrying a **breaking** change: `?q=` and `?company=` moved
from `200` to `422`. Also the first run where the version bump was cut as its
own commit *before* the tag rather than assumed — the direct lesson of `v0.8.0`.

| Step | Result |
|------|--------|
| tests | ✅ 237 passed (23 new since v0.8.1) |
| tests with `jobs.db` absent | ✅ 237 passed, `JOBSAPI_DB_PATH` pointed at a path that does not exist |
| home directory untouched by the suite | ✅ `~/.local/share/jobsapi/app.db` mtime and size identical either side of a full run |
| lint / format | ✅ `ruff check` clean, `ruff format --check` clean on 36 files |
| clean clone test | ✅ fresh clone → `uv sync` → 237 passed → demo DB → server; no `data/` in the clone |
| README verification — read path | ✅ all 10 documented `curl`s run against the live server |
| README verification — write path | ✅ 201+`Location`, 409, 201, the PATCH/PUT pair, 204 — `description` surviving a PATCH and cleared by a PUT, observed rather than assumed |
| `docker build` | ✅ `linux/arm64`. `docker image inspect --format '{{.Size}}'` = 58.7 MB — **not comparable to the 266 MB above**, see below |
| container checks | ✅ `id -u` 1001 · write to `/data/jobs.db` refused · healthcheck `healthy` · `docker stop` **exit 0**, inside the timeout · JSON logs on stdout |
| new behaviour, live | ✅ `?q=` and `?company=` → 422; `?q=%20` and `?q=engineer` → 200 — in the container as well as the local server |
| **version check — running server** | ✅ `/openapi.json` `info.version` = `0.9.0`, startup log = `0.9.0`, **and the same two inside the container** |
| CI green on the merge commit | ✅ both jobs |
| release / tag | ✅ v0.9.0, annotated, on the **merge commit** |

**On the image size: there was no 4.5× improvement, and nothing to investigate.**
`58.7 MB` and `266 MB` are two different quantities for the same image, not two
measurements of a changed one. Established without needing to recover the old
command:

- The build recipe is **unchanged since 2026-09-01** — `git log -- Dockerfile
  .dockerignore` last touches `7c0ec7d`/`c686b8b`, both before the 2026-09-02
  measurement — and `.dockerignore` already excluded `.venv` and `data/` then.
  So "a fat `COPY` layer got excluded afterwards" is ruled out by history.
- Docker on this machine now uses the **containerd image store**
  (`io.containerd.snapshotter.v1`), which reports compressed sizes. Proved
  locally rather than assumed: the same image reports `.Size` = 58,673,663 bytes
  while `du -sx /` inside a running container measures **196 MB** of actual
  files. A number that small cannot be a filesystem size for an image built
  `FROM python:3.13-slim`.

**The defect is in the record, not the image.** "266 MB" was written down
without the command that produced it, which makes it unreproducible and
un-comparable the moment the toolchain changes underneath it — and the toolchain
changed silently. `docker images` SIZE, `docker image inspect .Size`, `docker
system df`, `docker history`'s total and a registry's compressed figure are five
different quantities, and they differ by more than any change worth reporting.
Figures from here carry their command.

**On `docker stop`: the duration was never the assertion.** Whole-second shell
arithmetic cannot distinguish 0.64 s from 1.0 s, so there is no delta between
the two runs to explain. The property under test is that the container exited
**0** rather than **137** — `SIGTERM` forwarded to PID 1 and handled, not a
`SIGKILL` after the timeout expired. That is binary, and it passed.

**One defect found, and it was in the verification rather than the software.**
The first pass of the write-path `curl`s sent `{"notes": ...}` where the model
declares `description`, and got a `422`. The API was right — `extra="forbid"` on
a body model rejecting an unknown field is Phase 4 working exactly as designed —
and the README was right; the transcription was wrong. Recorded because "verify
every documented command" means running *the documented command*, and a
paraphrase of it tests something else. The corrected run used the README's bodies
verbatim.

---

## Ship sequence — v0.9.1, run 2026-09-03

A patch release for two behaviour changes that are invisible on the wire. The
reading that cut it is the same one that cut `v0.8.1` for re-derivation fixes:
docs move the tip, behaviour moves the tag — and "a database that booted under
`v0.9.0` is refused by `v0.9.1`" is something an operator needs a version to
name, even though no response shape changed.

| Step | Result |
|------|--------|
| tests | ✅ 252 passed (4 new since v0.9.0) |
| tests with `jobs.db` absent | ✅ 252 passed, `JOBSAPI_DB_PATH` pointed at a path that does not exist |
| home directory untouched by the suite | ✅ `~/.local/share/jobsapi/app.db` mtime and size identical either side of a full run |
| lint / format | ✅ `ruff check` clean, `ruff format --check` clean on 37 files |
| clean clone test | ✅ fresh clone → `uv sync` → 252 passed → demo DB → server; no `data/` in the clone |
| README verification | ⚠️ passed, and **found a defect** — see below |
| version check | ⚠️ **fired on the first attempt**, correctly — see below |
| startup gates against the real database | ✅ both, 6.1 ms, 4,224 rows |
| commit / push | ✅ PR #28 |
| CI green | ✅ both jobs |
| release / tag | ✅ v0.9.1, annotated tag + GitHub release |

**The version check fired, and the cause was the sequence rather than the app.**
The clean clone was taken before the version bump was committed, so the clone
carried `0.9.0` and reported it. That is the check doing exactly its job — it
cannot distinguish "the app reports the wrong version" from "you cloned the
wrong commit", and it should not: both mean *the artefact about to be tagged is
not the artefact that was tested*. Committing the bump first and re-cloning gave
`0.9.1` in both `/openapi.json` and the startup log.

Worth recording because the step was added after `v0.8.0` shipped an app
reporting `0.7.0`, and this is the first run where it caught something. The
lesson it taught is narrower than the one it was built for: **the bump must be
committed before the artefact is built, not merely before the tag.**

**README verification found the demo database had no positive case for
`duration_seconds`.** All three demo runs were zero-duration or unfinished, so
every one reported `null` — and a stranger following the README, plus CI's
container smoke test, sees only this database. The test fixture had been given a
post-fix run deliberately when the field shipped ("so `duration_seconds` has a
positive case to prove and not just nulls"); `scripts/make_demo_db.py` never got
the same treatment, because the two files were updated in different PRs and
nothing ties them together.

Run 2 now finishes 4.25s after it starts, so the demo shows all three shapes the
field distinguishes: a real measurement, the identical-timestamp era, and a run
with no end to measure from. This is the third defect the README-verification
step has found across five ship sequences — the other two were dead
configuration and the `v0.8.0` version mismatch.

---

## Re-derivation — `repository.py`, run 2026-09-03

The second syllabus entry, again in teach-me mode: the two-query envelope, the
WHERE builder and the `ORDER BY` allowlist reasoned out from `docs/api.md` and
`docs/design.md` before the file was opened. The derivation was correct on every
mechanism the file implements — accumulate-don't-enumerate, the conditional
`WHERE` keyword, the lockstep invariant between clause text and parameter order,
the parenthesised `q` clause, NULL semantics left to three-valued logic — and
produced **five findings**, four of them fixed here.

| # | Finding | Status |
|---|---------|--------|
| 1 | `total` and `items` read in separate transactions; a scraper commit between them makes them disagree, silently in the dangerous direction. Also `/runs`, `/jobs/{id}/changes`, and `/stats` with six reads | Fixed — `read_snapshot` |
| 2 | The skew *direction* depended on left-to-right keyword evaluation in one constructor call | Fixed — named locals, explicit order |
| 3 | Nothing asserted `_SORT_COLUMNS` was total; a future `SortField` member would be a `KeyError` → 500 | Fixed — completeness test |
| 4 | `?q=` and `?company=` validate, then are silently dropped by a truthiness test | Fixed — `min_length=1`, shipped separately as a contract change |
| 5 | `cache_size_kib` unbounded | Fixed — `ge=-1_048_576, le=-1` |

**Finding 1 is the substantive one**, and it is the first finding in this build
whose fix has a *cost* rather than being strictly better. Taking the transaction
means this service can delay Build 2's commit for the span of two queries. It
was taken anyway, on the asymmetry: the skew is silent and the contention is a
`503` that was already built, documented and tested. Reasoned in `docs/design.md`
as an addendum to Decision 1 — the second entry in the same locking ledger where
WAL was declined, and the entry that pays that decision's bill.

**The method note from this run.** The defect is *unreachable in the test
suite by construction* — `conftest.py` builds a database with no concurrent
writer, so no assertion on a response body could ever have found it. What is
testable is the mechanism rather than the symptom: that the second read sees
`conn.in_transaction`, that the transaction is released on both the normal and
the raising path, and that `BEGIN IMMEDIATE` really is refused on this
connection, which makes "deferred" documented as forced rather than preferred.

Two correct decisions with no recorded reasoning were also written down, in
`_build_order`'s docstring, on the grounds that unexplained correctness is what
gets "simplified": the tie-break's matching *direction* buys the keyset-pagination
option, and under `sort=salary_min` ~70% of rows tie on NULL, so the tie-break is
the ordering for most of the result set rather than a rare disambiguation.

---

## The application database's read snapshot — closed 2026-09-03

The thread left open by the `v0.9.0` work, and the cheapest of the two, because
it is the same fix with the trade removed. `read_snapshot` for `jobs.db` cost a
real contention argument: rollback-journal mode means a read transaction holds
`SHARED` and Build 2's commit waits behind it. The application database is WAL,
where a reader snapshots without blocking the writer, so here the guarantee is
free and only correctness was ever open.

| Endpoint | Before | Now |
|----------|--------|-----|
| `GET /watchlists` | count and page read separately | one snapshot, page before count |
| `GET /watchlists/{id}/jobs` | 404 gate, then page, then count — three independent reads | all three in one snapshot |

**`appdb.read_snapshot` is deliberately not `db.read_snapshot`.** The read-only
one ends its transaction unconditionally and suppresses failures, which is sound
only because that connection cannot write — a fact its docstring now states
precisely so it would not be copied. On a read-write connection those three
lines would turn a swallowed `COMMIT` failure into data loss reported as success.
So this one ends with `END` on the success path and lets errors surface, and
**rolls back** on the failure path, suppressing only that so a tidy-up failure
cannot replace the exception in flight. Two tests pin exactly that difference:
a write inside a failing block does not survive, and one inside a successful
block does.

**The 404 race is sharper here than for `jobs.db`.** Its competing writer is
*this service answering another request*, not an external scraper — so a
concurrent `DELETE /watchlists/{id}` between the existence check and the count is
an ordinary interleaving rather than a rare one. Pulling the gate inside the
snapshot is what keeps a 404 from becoming a 200 with a total of zero.

---

## Re-derivation — `routers/jobs.py`, run 2026-09-03

The third syllabus entry, and the first where the derivation produced **no
defects** — the route signatures, status codes and the declaration-order rule were
reasoned out correctly from `docs/api.md` and the repository derived the day
before. Three additions came out of it instead, all in the record rather than the
code.

| # | Addition | Where |
|---|----------|-------|
| 1 | `errors[].field` strips the location — `path.job_id` is flattened to `job_id` — which was undocumented and untested | `docs/api.md`, `tests/test_problems.py` |
| 2 | The same `description` snapshot figure was dated in `design.md` and undated in `api.md`, so a Phase 0 measurement read as a current fact | `docs/api.md` |
| 3 | The routes declare `response_model=` **and** a return annotation; FastAPI infers from the annotation when the argument is absent, so it is a redundancy — harmless, and `response_model` wins silently if they ever disagree | observation only |

**The two rules worth carrying forward.** The declaration-order rule is not
"literals before parameters": two routes collide only if they can match the same
concrete path *and* accept the same method, and with the default converter equal
segment count is the first-order filter. That is what makes `/jobs/{job_id}` (2
segments) and `/jobs/{job_id}/changes` (3) safe in either order, while a future
`/jobs/recent` would not be. And the failure signature is worth memorising: a
**422 naming a path parameter the client never sent**, on a path `/docs` plainly
lists — because both routes are registered, so a generated schema is correct
about existence and silent about behaviour.

Second: `response_model` saves the serialisation and the wire, and nothing else.
The disk read is avoided by `_SUMMARY_COLUMNS`, one layer down. The model is the
guarantee, the query is the saving, and treating either as a substitute for the
other is how a list endpoint ends up reading 21.7 MB it will discard.

---

## Re-derivation — `schemas.py` response models, run 2026-09-03

The fourth syllabus entry, and the one that closes the ◧ row: `Pagination` was
re-derived on 2026-09-02, the response models were not. Derived from
`docs/api.md` and Build 2's DDL before the file was opened — the envelope shape,
`JobSummary`'s omissions, `JobDetail` by inheritance, the truncation trio on
`JobChange`, and `duration_seconds` as a `@computed_field` with its three null
cases all came out matching. Two derived judgments matched the file for the
reasons the file gives: `url` is a plain `str` and not `HttpUrl`, and `seniority`
is `str` and not the filter enum, because a **response** model validates the
output — a strict type there turns a bad stored value into a 500 on a row that
exists.

That is also what produced the finding, by applying the same test to the one
field where the answer came out differently.

| # | Finding | Status |
|---|---------|--------|
| 1 | `posted_at: date` is the only response field narrower than its column. A timestamp in TEXT is a `500`, and because `items` validates as a list it fails the **whole page**, not the row | Fixed — `verify_posted_at_shape` |
| 2 | `SchemaContractError` said "missing a column"; it now covers a value-format contract too | Fixed — docstring |
| 3 | `/runs` silently omits `rules_version`, where `/jobs` documents `content_hash` and `hash_version` as never served | Fixed — `docs/api.md` |
| 4 | Five envelope classes duplicate `items`/`total`/`limit`/`offset`; a generic `Page[T]` would make their agreement structural | Observation only |

**Finding 1 is latent, not live** — all 4,224 rows carry a bare `YYYY-MM-DD`
today, so no request has ever failed this way. What made it worth code rather
than a note in "Known coupling" is the blast radius: the other couplings in this
build degrade locally (one filter matches nothing, one accent misses), while this
one turns a single upstream write into `500` on the main endpoint's first page,
since the default sort puts a new row there. `PRAGMA table_info` cannot see it —
the column is present and correctly named, and TEXT affinity is exactly the
promise that says nothing about values.

**The gate's limit is stated rather than implied.** It samples at startup, so a
row inserted afterwards still fails when served. That is the same incompleteness
`verify_schema` has always had and never admitted; both now say so. Cost is one
covering-index search on `idx_jobs_posted` — 6.1 ms for both gates against the
real database.

**Finding 4 was declined for the reason finding 1 was taken.** A generic
`Page[T]` would deduplicate four classes, but it renames the schemas in
`/openapi.json` (`Page_JobSummary_`), which every reader of the generated docs
can see, in exchange for no behaviour. Five copies that agree is a cost paid in
the file; renamed schemas is a cost paid by clients.

**The method note from this run.** The derivation found this by asking one
question of every field — *is this type wider or narrower than the column?* — and
the answer was uninteresting ten times and then not. A checklist applied
uniformly is what makes the eleventh case visible; reading the file top to bottom
had not surfaced it in three prior passes.

---

## Re-derivation — `repository.py` Phase 5, run 2026-09-03

The fifth syllabus entry, and the last unticked slice of a file whose other two
were re-derived on 2026-09-03: `/sources`, `/stats`, the `runs` projection and
its tie-break. Derived from `docs/api.md` before the file was opened. The
greatest-n-per-group shape, the correlated subquery, the `LEFT` for a source with
no runs, `SUM(CASE …)` for coverage in one scan rather than nine, and
`ORDER BY started_at DESC, id DESC` all matched.

The derivation asked three questions of the aggregates — *what is one row of this
join, what happens on an empty table, and do the numbers agree with each other* —
and the first was answered correctly by the code, the second by an unexercised
guard, the third not at all.

| # | Finding | Status |
|---|---------|--------|
| 1 | `list_sources`'s docstring claimed the LEFT JOIN protects a source with runs and no jobs. It cannot: `FROM jobs` is the driving table, so such a source is absent by construction | Fixed — docstring + a test that builds the state |
| 2 | Nothing asserted `/stats` agrees with itself. `remote` is reported twice by two different queries, and `present + missing == total_jobs` was never checked | Fixed — 3 invariant tests |
| 3 | The empty-database guards (`if total else 0.0`, `or 0`) were right by intention and exercised by nothing | Fixed — `empty_client` fixture, 4 tests |
| 4 | The `posted_at` gate shipped in v0.9.1 protects `/stats`'s date range too, which was undocumented | Fixed — `docs/api.md` |

**Finding 1 is the one worth keeping.** The claim was false and every test
agreed with it anyway, because all eight real sources and all four fixture
sources appear in both tables — so the wrong sentence and the right one predict
identical output everywhere the suite or the dataset can look. It is the second
time this exact query has been protected by data rather than by being correct;
the first is already in Open threads as "the `/sources` LEFT JOIN is defensive,
not load-bearing". Same query, same blind spot, one level down.

**Finding 2 is the sharper lesson about the v0.9.0 snapshot work.** That fix
guaranteed `/stats`'s six reads see one state of the database. It says nothing
about whether the two expressions that both count `remote` compute the same
thing — snapshot isolation is about *when* reads happen, agreement is about
*what they compute*. A response that is internally contradictory is exactly the
kind of wrong no client can detect, which is the reason the snapshot was taken;
the assertion half was missing.

**The method note.** Both findings came from asking a question the file cannot
answer about itself: *what state would make this claim false, and does anything
produce it?* Neither the real dataset nor the fixture produces a runs-only source
or an empty table, so both had to be constructed. Three of this build's last four
findings have been unreachable without building a state reality does not supply.

---

## Re-derivation syllabus

Every file in this build was written by Claude and explained inline, with the
concept behind each recorded in the implementation register in
`learning_log/gap-log.md`. All 31 entries there are now written up in
`learning_log/learning-log.md` — the register is closed.

This table is the other half: the list to rebuild unaided, which is a different
test from having read the explanation. ◧ means part of the file was re-derived
and the rest was not.

**Who derived it is part of the result, so the column now says.** Entries 1–3
were run in teach-me mode — the owner reasoning the file out, Claude confining
itself to confirming or correcting. Entries 4 and 5 (2026-09-03) were run in
Claude-implements mode at the owner's instruction: *Claude* derived those, which
is a real exercise and a useful one, but it is **not** the test this column was
built to record. Marking them ✅ alongside the others would have made the table
assert something false, and would have quietly contradicted the Open thread
above recording that the unaided-rebuild checkpoint never happened in this build.

- **✅** — re-derived by the owner, unaided.
- **⚙️** — re-derived by Claude in implements mode. The findings are real and are
  written up; the checkpoint is still open.

| File | Written | Re-derived | By |
|------|---------|------------|-----|
| `pyproject.toml` | 2026-09-01 | ⬜ | — |
| `.gitignore` | 2026-09-01 | ⬜ | — |
| `.github/workflows/ci.yml` | 2026-09-01 | ⬜ | — |
| `docs/design.md` | 2026-09-01 | ⬜ | — |
| `docs/api.md` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/config.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/db.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/errors.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/main.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/problems.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/schemas.py` | 2026-09-01 | ✅ 2026-09-02 (`Pagination`) · ⚙️ 2026-09-03 (response models) | owner · Claude |
| `src/jobsapi/schemas.py` (Phase 3) | 2026-09-01 | ✅ 2026-09-02 | owner |
| `src/jobsapi/repository.py` | 2026-09-01 | ✅ 2026-09-03 | owner |
| `src/jobsapi/repository.py` (Phase 3) | 2026-09-01 | ✅ 2026-09-03 | owner |
| `src/jobsapi/repository.py` (Phase 5) | 2026-09-01 | ⚙️ 2026-09-03 | Claude |
| `src/jobsapi/logging_config.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/routers/jobs.py` | 2026-09-01 | ✅ 2026-09-03 | owner |
| `src/jobsapi/routers/meta.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/routers/runs.py` | 2026-09-01 | ⬜ | — |
| `tests/conftest.py` | 2026-09-01 | ⬜ | — |
| `tests/test_health.py` | 2026-09-01 | ⬜ | — |
| `Dockerfile` | 2026-09-01 | ⬜ | — |
| `.dockerignore` | 2026-09-01 | ⬜ | — |
| `scripts/make_demo_db.py` | 2026-09-01 | ⬜ | — |
| `.github/workflows/ci.yml` (docker job) | 2026-09-01 | ⬜ | — |
| `README.md` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/appdb.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/watchlist_repository.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/routers/watchlists.py` | 2026-09-01 | ⬜ | — |
| `src/jobsapi/security.py` | 2026-09-01 | ⬜ | — |
| `tests/test_watchlists.py` | 2026-09-01 | ⬜ | — |

**The three worth re-deriving first**, because they carry the build's actual
lesson: `schemas.py` (the contract as types), `repository.py` (a WHERE clause
built from optional filters without concatenating anything, plus the `ORDER BY`
allowlist), and the route signatures in `routers/jobs.py` (path, method, status
code, and what a client that gets it wrong sees).
