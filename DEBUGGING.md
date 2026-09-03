# Debugging record — Job Listings API

Significant failures only. Newest entry at the top.

```
## YYYY-MM-DD — one-line title
- **Problem:**
- **Root cause:**
- **Solution:**
- **Lesson:**
```

---

## 2026-09-03 — `total` and `items` were answers to two different questions

- **Problem:** *Found by derivation, never observed.* `GET /jobs` issued the page
  query and the count query as two independent statements. Under a concurrent
  scraper commit the response could report a `total` counted from a different
  state of the database than `items` was drawn from. `/runs` and
  `/jobs/{id}/changes` had the same pair; `/stats` had six independent reads.
  Nothing raises, no status code changes, and the dangerous direction is silent:
  a `total` that is too low makes a client stop paginating early and drop rows.
- **Root cause:** Python's `sqlite3` opens implicit transactions before DML only
  (`INSERT`/`UPDATE`/`DELETE`/`REPLACE`). A sequence of `SELECT`s therefore runs
  in autocommit, each statement taking and releasing its own `SHARED` lock. The
  assumption that "read-only means no transaction to think about" is exactly
  backwards — read-only is where isolation has to be asked for explicitly,
  because nothing else will ask for it.
- **Solution:** `read_snapshot` in `src/jobsapi/db.py` — a deferred `BEGIN` held
  across the statements that must agree, applied in `repository.jobs_page`,
  `runs_page`, `job_changes_page` and `stats`. Deferred is not a preference:
  `BEGIN IMMEDIATE` asks for a write lock, which `mode=ro` plus `PRAGMA
  query_only = 1` refuses. Reasoned in `docs/design.md` as an addendum to
  Decision 1, where the locking trade was first argued.
- **Lesson:** A transaction boundary is part of a query's meaning, not an
  implementation detail of writing. Whenever two reads are combined into one
  answer, ask what happens if the database changes between them — and note that
  a fixture database with no concurrent writer can never fail this test, which
  is why a green suite was not evidence.

## 2026-09-02 — A validator withdrew a constraint from the published schema

- **Problem:** `/jobs?currency=dollars` returned a correct `422`, but
  `/openapi.json` described `currency` as an unconstrained string. The rule was
  enforced and unpublished, so a client generated from the spec would send
  `dollars`, pass its own validation, and be refused by the server for a reason
  its copy of the contract did not contain. Nothing failed; the suite was green
  and the endpoint behaved correctly.
- **Root cause:** `Currency` is `Annotated[str, BeforeValidator(_upper),
  Field(pattern=r"^[A-Z]{3}$")]`. Pydantic drops `pattern` from the *validation*
  JSON schema when a `BeforeValidator` is present, because a transform runs
  ahead of the constraint and the declared pattern therefore no longer describes
  what is legal on the wire. Confirmed by building two otherwise identical
  models: with the validator the pattern is absent, without it the pattern is
  emitted. The withdrawal is deliberate on Pydantic's part and silent on ours.
- **Solution:** `json_schema_extra={"pattern": WIRE_CURRENCY_PATTERN}` in
  `schemas.py`, publishing `^[A-Za-z]{3}$` — the *wire* pattern. Republishing
  `^[A-Z]{3}$` would have replaced one wrong schema with another, telling
  clients `usd` is invalid when this API accepts it. Four tests in
  `TestTheGeneratedSchemaPublishesWhatIsEnforced` now check the published
  pattern against the service's actual answers in both directions.
- **Lesson:** "The docs are generated from the types" is a property, not a
  guarantee — it holds only while every constraint survives the trip into the
  schema, and a validator can remove one without removing the behaviour. The
  build's own thesis has an exception, and the exception is invisible from the
  endpoint: correct status codes prove nothing about what was published. The
  check that catches it is asserting the *schema*, not the response — which is
  why the new tests read `/openapi.json` rather than only calling `/jobs`.

## 2026-09-02 — The API reported version 0.7.0 for the whole of the v0.8.0 tag

- **Problem:** after tagging `v0.8.0`, the service still announced `0.7.0` in
  its startup log and in `/openapi.json`. A second occurrence: `PROGRESS.md`
  records a version mismatch already caught once during README verification.
- **Root cause:** the version existed twice — `pyproject.toml:3` and a
  hard-coded `version="0.7.0"` in `create_app`. Two copies of one fact, with
  nothing forcing agreement, so releasing meant remembering to edit both. The
  ship sequence has no step that compares the running app's version to the tag.
- **Solution:** `main.py` now reads `importlib.metadata.version("jobsapi")`,
  leaving `pyproject.toml` as the single source, bumped to `0.8.1`. The literal
  is gone rather than corrected, so the two cannot disagree again.
- **Lesson:** a value that must be updated in two places during a release will
  eventually be updated in one. The fix for a duplicated fact is deletion, not
  diligence — correcting the copy would have left the same bug armed for the
  next tag. Worth noting the tag itself is fine: `v0.8.0` permanently ships an
  app reporting `0.7.0`, and that is history now, fixed forward rather than by
  moving a published tag.

---

## 2026-09-02 — The shipped README sent every stranger to four 404s

- **Problem:** `README.md` linked the companion project `job-listing-scraper`
  three times — including the politeness-and-legal statement that documents how
  the data was acquired — and `PROGRESS.md` linked upstream issue #29. That
  repository is **private**, so all four URLs return **HTTP 404** to everyone
  except its owner. This shipped in v0.6.0 and survived the Phase 6 ship
  sequence, the Phase 4 ship sequence, and every review since. It was found
  while looking at repository visibility for an unrelated reason.
- **Root cause:** the ship sequence verified *commands*, not *references*. Its
  README-verification step is recorded as "every documented command and example
  request run against the live app" — and that was done honestly. But a `curl`
  in a code block and a Markdown link are different kinds of claim, and only the
  first was ever executed. The second failure was authentication: the links were
  certainly clicked at some point from an account that owns the private repo,
  where they resolve perfectly. Verification performed while logged in cannot
  see a permission error, so the check that mattered was the one nobody could
  fail.
- **Solution:** `README.md` and `PROGRESS.md` — the four links are gone. The
  provenance is still credited by name, and the politeness statement is now
  restated in the README as its own content rather than deferred to a page no
  reader can open. Verified by fetching every remaining `github.com` URL in both
  files unauthenticated: all six return 200.
- **Lesson:** a link is an assertion about what someone *else* can see, so it
  cannot be tested from inside your own session. Anything a public artefact
  points at needs checking the way a stranger meets it — unauthenticated, from
  the outside — and a public document should never depend on a private one for
  content it is responsible for. The defence is cheap: a loop over every URL in
  the docs asserting a 200, with no credentials loaded.

## 2026-09-01 — The write path created a database in the developer's home directory, and every test passed

- **Problem:** after `appdb.ensure_schema` was added to the lifespan, `uv run
  pytest` reported **153 passed** — and left a real 24 KB SQLite database at
  `~/.local/share/jobsapi/app.db`. No test failed, nothing was logged, and
  nothing in the output mentioned it. It was found by looking for it, not by a
  failure.
- **Root cause:** the autouse `_never_the_real_database` fixture points
  `JOBSAPI_DB_PATH` at a path that cannot exist, but it knew nothing about the
  new `JOBSAPI_APP_DB_PATH`, and the `settings` fixture overrode only `db_path`.
  So every `TestClient` ran the lifespan against the *default* application
  database path. The asymmetry is what hid it: the read path is designed to fail
  loudly when its file is missing — that is exactly what `check_database` is for
  — while the write path is *specified* to create what is missing. The identical
  mistake that turned Phase 1's suite red turned this one green.
- **Solution:** `tests/conftest.py` — `_never_the_real_database` now also points
  `JOBSAPI_APP_DB_PATH` into `tmp_path` and clears `JOBSAPI_API_KEY`; a new
  `app_db_path` fixture feeds the `settings` fixture, so every test gets its own
  file and the lifespan creates it there.
- **Lesson:** a guard against ambient resources is not written once. Every new
  ambient resource needs adding to it, and a resource the code *writes* is more
  dangerous than one it reads, because the failure mode is silent success. "The
  suite passes" says nothing about what the suite did to the machine — for a
  write path the question is not "did anything fail" but "what exists now that
  did not exist before". Verified by deleting the directory and re-running: it
  stays absent.

---

## 2026-09-01 — Phase 1 tests passed locally only because the real database existed

- **Problem:** `pytest` was green locally and failed on GitHub Actions with
  `SchemaContractError: Database file not found:
  /home/runner/code/job-listing-scraper/data/jobs.db`. Only the two Phase 1
  tests in `tests/test_health.py` failed; all 31 Phase 2 tests passed on both.
- **Root cause:** those tests called `create_app()` with no arguments, so the app
  fell back to `get_settings()` and the default `db_path`. That was harmless
  while nothing opened the database — but Phase 2 added a startup schema check to
  the lifespan, and `TestClient` as a context manager runs the lifespan. The
  tests then began depending on `~/code/job-listing-scraper/data/jobs.db`
  existing. It does on this machine; it does not on a CI runner. The tests had
  been silently coupled to the developer's filesystem from the moment the
  lifespan check landed.
- **Solution:** `tests/test_health.py` now takes the `client` fixture, which
  builds an app against a temporary fixture database. Added an autouse fixture
  `_never_the_real_database` in `tests/conftest.py` that points
  `JOBSAPI_DB_PATH` at a path which cannot exist and clears the `get_settings`
  cache, so any future test that forgets to inject `Settings` fails immediately
  and identically everywhere.
- **Lesson:** "the suite passes" and "the suite is self-contained" are different
  claims, and the first can hide the failure of the second for as long as the
  developer's machine happens to be configured correctly. The definition of done
  already said `pytest` must run green *with `jobs.db` deleted* — that line was
  untested, so it was untrue. A guard that makes the ambient resource
  unreachable is worth more than the discipline of remembering to inject it,
  because it converts a machine-dependent failure into a deterministic one.
  Verified with `JOBSAPI_DB_PATH=/nonexistent/jobs.db uv run pytest`.
