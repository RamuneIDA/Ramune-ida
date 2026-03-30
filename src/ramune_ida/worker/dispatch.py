"""Command dispatch: routes Method → handler function.

Installs ``sys.setprofile`` around every handler call so that
a cancellation flag (set via SIGUSR1) is checked at Python
function-call boundaries.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ramune_ida.commands import Command, command_from_params
from ramune_ida.protocol import ErrorCode, Method, Request, Response
from ramune_ida.worker import cancel

Handler = Callable[[Command], Any]

_HANDLERS: dict[Method, Handler] = {}


def handler(method: Method) -> Callable[[Handler], Handler]:
    """Register a function as the handler for *method*."""
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[method] = fn
        return fn
    return decorator


def _cancel_profile(frame: Any, event: str, arg: Any) -> None:
    """setprofile callback — raise on function call/return if cancelled."""
    if cancel.is_requested():
        raise CancelledError


def dispatch(request: Request) -> Response:
    """Look up the handler for *request.method* and call it."""
    cancel.reset()
    try:
        cmd = command_from_params(request.method, request.params)
    except ValueError:
        return Response.fail(
            request.id,
            ErrorCode.METHOD_NOT_FOUND,
            f"Unknown method: {request.method}",
        )

    fn = _HANDLERS.get(cmd.method)
    if fn is None:
        return Response.fail(
            request.id,
            ErrorCode.METHOD_NOT_FOUND,
            f"No handler for method: {request.method}",
        )
    try:
        sys.setprofile(_cancel_profile)
        result = fn(cmd)
        return Response.ok(request.id, result)
    except CancelledError:
        return Response.fail(request.id, ErrorCode.CANCELLED, "Task cancelled")
    except HandlerError as exc:
        return Response.fail(request.id, exc.code, str(exc))
    except Exception as exc:
        return Response.fail(
            request.id,
            ErrorCode.INTERNAL_ERROR,
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        sys.setprofile(None)
        cancel.reset()


class CancelledError(BaseException):
    """Raised by the setprofile hook when cancellation is requested.

    Inherits from BaseException so that ``except Exception`` in
    handlers (especially execute_python) does not swallow it.
    """


class HandlerError(Exception):
    """Raised by handlers to return a structured error."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
