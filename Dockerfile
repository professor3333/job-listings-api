# syntax=docker/dockerfile:1

# Multi-stage. The builder needs uv, a lockfile and the project source; the
# runtime needs none of those — only a virtualenv and the interpreter. Keeping
# them in separate stages means the build toolchain never ships, which is both
# a size and an attack-surface argument: a compiler that is not in the image
# cannot be used by anything that gets into the image.

# --------------------------------------------------------------------------
# Stage 1 — builder
# --------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# uv comes from its own published image rather than `pip install uv`, pinned to
# the same version the lockfile was written with. An unpinned `:latest` would
# make the image non-reproducible for exactly the reason `uv sync --locked`
# exists to prevent.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies in their own layer, installed *before* the source is copied.
# Dependencies change rarely and source changes constantly, so this ordering is
# what makes a code-only rebuild reuse the cached dependency layer instead of
# re-resolving and re-downloading every time.
#
# `--no-install-project` installs the dependencies but not `jobsapi` itself,
# which is the whole point: the project is not here yet.
# `--locked` fails rather than re-resolving if uv.lock and pyproject.toml
# disagree — the image must contain the dependency set that was tested.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

# README.md is copied because pyproject.toml declares `readme = "README.md"`,
# so the build backend reads it while building the project's wheel.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# `--no-editable` installs jobsapi as a real wheel in site-packages rather than
# as a link back to /app/src. That is what lets the runtime stage copy only the
# virtualenv and leave the source tree behind.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --------------------------------------------------------------------------
# Stage 2 — runtime
# --------------------------------------------------------------------------
FROM python:3.13-slim

# A non-root user, created with a fixed uid so the ownership of a bind-mounted
# file is predictable from the host side. It writes in exactly one place — the
# application database below — and nowhere else: `jobs.db` is mounted read-only
# and the logs go to stdout.
RUN groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --no-create-home app

# PYTHONUNBUFFERED because Python block-buffers stdout when it is not a tty,
# which is exactly the case inside a container. Without it, the structured log
# lines this service is careful to emit would sit in a buffer instead of
# reaching the runtime's log collector.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# The read database lives on a mounted volume, never in a layer. Baking a 64 MB
# snapshot into the image would make it stale the moment the scraper next runs,
# and would put someone else's data in an artefact that gets pushed to a
# registry. `docs/design.md` Decision 1 is "a path, not a policy" — this is that
# decision expressed as a default, overridable with `-e JOBSAPI_DB_PATH=...`.
ENV JOBSAPI_DB_PATH=/data/jobs.db

# The write database (Phase 4) needs somewhere writable, and /data is mounted
# read-only, so it cannot live beside the database it references. The directory
# is created and handed to the app user at build time because the running
# container cannot create it: /app and / are root-owned and the process is not.
#
# Nothing is mounted here by default, which means watchlists live in the
# container's writable layer and die with it. That is the right default for a
# service whose primary job is reading, and the README documents the volume to
# mount when they should outlive the container.
ENV JOBSAPI_APP_DB_PATH=/var/lib/jobsapi/app.db
RUN mkdir -p /var/lib/jobsapi && chown app:app /var/lib/jobsapi

WORKDIR /app

# Only the virtualenv crosses the stage boundary. No uv, no lockfile, no
# compiler, no source tree.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app

EXPOSE 8000

# /health is the right target: it touches no database and no filesystem, so it
# answers "is this process serving?" rather than "is Build 2's scraper healthy?".
# urllib rather than curl because the slim image has no curl, and adding one to
# support a healthcheck would be a package installed for the benefit of the
# healthcheck alone.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Exec form, so uvicorn is PID 1 and receives SIGTERM directly — a shell-form
# CMD would put /bin/sh at PID 1, which does not forward signals, and the
# container would be killed rather than shut down gracefully.
#
# One worker on purpose. Concurrency here comes from the event loop plus the
# threadpool that runs the blocking sqlite3 endpoints; multiple workers would
# multiply connections to a single read-only file for no throughput this
# service needs. Scale with replicas if it ever matters.
CMD ["uvicorn", "jobsapi.main:app", "--host", "0.0.0.0", "--port", "8000"]
