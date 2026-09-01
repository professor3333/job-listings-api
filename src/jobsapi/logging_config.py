"""Structured logging: one JSON object per line, correlated by request id.

Plain-text logs are readable by a person and useless to a machine. JSON lines
can be grepped *and* queried, which is what matters the moment there is more
than one request in flight and their log lines interleave.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# A ContextVar rather than a parameter threaded through every function.
# Each request runs in its own context — including across `await` points and the
# threadpool FastAPI uses for `def` endpoints — so a value set at the edge is
# visible to any log call made while handling that request, without repository
# or db code having to know a request exists.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes the stdlib puts on every LogRecord. Anything *not* in here was
# passed by us via `extra=` and is worth emitting.
_STANDARD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            # The traceback belongs here and nowhere else. The HTTP body for a
            # 500 says nothing; this is the other half of that bargain, and
            # `request_id` is what joins the two.
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger.

    Writes to stdout because that is what a container expects: the runtime
    collects stdout, and an application that manages its own log files inside a
    container is fighting its environment.

    Replaces existing handlers rather than adding to them, so calling this twice
    — as tests do when they build several apps — does not duplicate every line.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own access log in a different format. Ours carries the
    # request id and the duration, so theirs is redundant noise.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
