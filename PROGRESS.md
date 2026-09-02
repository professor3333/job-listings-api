# Progress

Running status of the build. Updated by Claude as work lands.

**Last updated:** 2026-09-02
**Repo:** https://github.com/professor3333/job-listings-api (public)
**Local path:** `~/code/job-listings-api`
**Branch:** `main` — **Phases 1, 2, 3, 5, 6 shipped as v0.6.0**; **Phase 4 as v0.7.0**
**CI:** 🟢 green — 197 tests passing, lint and format clean, Docker image built
and smoke-tested on every push.
**Releases:** [v0.6.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.6.0)
· [v0.7.0](https://github.com/professor3333/job-listings-api/releases/tag/v0.7.0)

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
| image | ✅ `linux/arm64`, 266 MB |
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
  Overrule if you'd rather it moved.
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

---

## Re-derivation syllabus

Every file in this build was written by Claude and explained inline, with the
concept behind each recorded in the implementation register in
`learning_log/gap-log.md`. All 31 entries there are now written up in
`learning_log/learning-log.md` — the register is closed.

This table is the other half: the list to rebuild unaided, which is a different
test from having read the explanation. Nothing is ticked yet.

| File | Written | Re-derived unaided |
|------|---------|--------------------|
| `pyproject.toml` | 2026-09-01 | ⬜ |
| `.gitignore` | 2026-09-01 | ⬜ |
| `.github/workflows/ci.yml` | 2026-09-01 | ⬜ |
| `docs/design.md` | 2026-09-01 | ⬜ |
| `docs/api.md` | 2026-09-01 | ⬜ |
| `src/jobsapi/config.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/db.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/errors.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/main.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/problems.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/schemas.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/schemas.py` (Phase 3) | 2026-09-01 | ⬜ |
| `src/jobsapi/repository.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/repository.py` (Phase 3) | 2026-09-01 | ⬜ |
| `src/jobsapi/repository.py` (Phase 5) | 2026-09-01 | ⬜ |
| `src/jobsapi/logging_config.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/routers/jobs.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/routers/meta.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/routers/runs.py` | 2026-09-01 | ⬜ |
| `tests/conftest.py` | 2026-09-01 | ⬜ |
| `tests/test_health.py` | 2026-09-01 | ⬜ |
| `Dockerfile` | 2026-09-01 | ⬜ |
| `.dockerignore` | 2026-09-01 | ⬜ |
| `scripts/make_demo_db.py` | 2026-09-01 | ⬜ |
| `.github/workflows/ci.yml` (docker job) | 2026-09-01 | ⬜ |
| `README.md` | 2026-09-01 | ⬜ |
| `src/jobsapi/appdb.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/watchlist_repository.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/routers/watchlists.py` | 2026-09-01 | ⬜ |
| `src/jobsapi/security.py` | 2026-09-01 | ⬜ |
| `tests/test_watchlists.py` | 2026-09-01 | ⬜ |

**The three worth re-deriving first**, because they carry the build's actual
lesson: `schemas.py` (the contract as types), `repository.py` (a WHERE clause
built from optional filters without concatenating anything, plus the `ORDER BY`
allowlist), and the route signatures in `routers/jobs.py` (path, method, status
code, and what a client that gets it wrong sees).
