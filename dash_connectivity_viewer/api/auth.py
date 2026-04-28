import os
from functools import wraps

import flask


_DEV_BYPASS = os.environ.get("DCV_DEV_AUTH_BYPASS", "").lower() in {"1", "true", "yes", "on"}


def _bypass_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


if _DEV_BYPASS:
    auth_required = _bypass_decorator
    auth_requires_permission = lambda *_, **__: _bypass_decorator  # noqa: E731
else:
    from middle_auth_client import (
        auth_required as auth_required,
        auth_requires_permission as auth_requires_permission,
    )


def current_token() -> str | None:
    token = flask.g.get("auth_token")
    if token:
        return token
    header = flask.request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(None, 1)[1].strip() or None
    return None


def is_dev_bypass() -> bool:
    return _DEV_BYPASS
