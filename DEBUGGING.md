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
