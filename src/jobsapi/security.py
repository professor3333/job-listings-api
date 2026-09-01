"""The single optional API key guarding the write endpoints.

This is the whole of the build's authentication, on purpose: no users, no
sessions, no JWT, no roles. One shared secret, checked in one dependency, and
disabled entirely unless it is configured.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, Request

from jobsapi.config import Settings
from jobsapi.errors import ApiKeyRequired

API_KEY_HEADER = "X-API-Key"


def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> None:
    """Reject a mutating request when a key is configured and not presented.

    Declaring the header as a parameter rather than reading `request.headers`
    puts it in the OpenAPI schema, so `/docs` shows callers that the endpoint
    takes it.

    `secrets.compare_digest` rather than `==` because a plain string comparison
    returns as soon as two bytes differ, and that timing difference is
    measurable across enough requests. It matters little for a localhost service
    and costs nothing, which is the right trade for a comparison against a
    secret.

    Both "no key" and "wrong key" are the same failure. A wrong key is not
    *authenticated-but-forbidden* — there is no identity here to forbid — so 403
    would be a misuse of the status; both produce 401.
    """
    settings: Settings = request.app.state.settings
    if settings.api_key is None:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise ApiKeyRequired("A valid X-API-Key header is required.")


# Applied to whole routers with `dependencies=[...]`, where the dependency runs
# for every route but its return value is discarded. That is the shape to reach
# for when a dependency exists purely for its side effect of raising.
RequireApiKey = Depends(require_api_key)
