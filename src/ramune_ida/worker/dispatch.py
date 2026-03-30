"""Command dispatch: routes requests → handler functions.

Two dispatch tracks:

1. **Command track** — built-in lifecycle / legacy commands registered via
   ``@handler(Method.XXX)``.  The request is deserialised into a typed
   :class:`~ramune_ida.commands.Command` and passed to the handler.

2. **Plugin track** — plugin-style tools registered via
   ``register_plugins()``.  The IPC method uses a ``plugin:`` prefix
   (e.g. ``plugin:disasm``).  The handler receives raw ``params: dict``.

Both tracks share the same cancellation / error-handling wrapper
(``sys.setprofile`` + ``CancelledError``).
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ramune_ida.commands import Command, command_from_params
from ramune_ida.core import ToolError
from ramune_ida.protocol import ErrorCode, Method, Request, Response
from ramune_ida.worker import cancel

Handler = Callable[[Command], Any]
PluginHandler = Callable[[dict[str, Any]], Any]

_HANDLERS: dict[Method, Handler] = {}
_PLUGIN_HANDLERS: dict[str, PluginHandler] = {}

PLUGIN_PREFIX = "plugin:"


def handler(method: Method) -> Callable[[Handler], Handler]:
    """Register a function as the handler for *method*."""
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[method] = fn
        return fn
    return decorator


def register_plugins(handler_map: dict[str, Callable]) -> None:
    """Bulk-register plugin-style handlers (called once at startup)."""
    _PLUGIN_HANDLERS.update(handler_map)


def _cancel_profile(frame: Any, event: str, arg: Any) -> None:
    """setprofile callback — raise on function call/return if cancelled."""
    if cancel.is_requested():
        raise CancelledError


def dispatch(request: Request) -> Response:
    """Route *request* to the appropriate handler and return the response."""
    cancel.reset()

    if request.method.startswith(PLUGIN_PREFIX):
        tool_name = request.method[len(PLUGIN_PREFIX):]
        fn = _PLUGIN_HANDLERS.get(tool_name)
        if fn is None:
            return Response.fail(
                request.id, ErrorCode.METHOD_NOT_FOUND,
                f"No plugin handler: {tool_name}",
            )
        invoker: Callable[[], Any] = lambda: fn(request.params or {})
    else:
        try:
            cmd = command_from_params(request.method, request.params)
        except ValueError:
            return Response.fail(
                request.id, ErrorCode.METHOD_NOT_FOUND,
                f"Unknown method: {request.method}",
            )
        fn_cmd = _HANDLERS.get(cmd.method)
        if fn_cmd is None:
            return Response.fail(
                request.id, ErrorCode.METHOD_NOT_FOUND,
                f"No handler for method: {request.method}",
            )
        invoker = lambda: fn_cmd(cmd)  # noqa: E731

    try:
        sys.setprofile(_cancel_profile)
        result = invoker()
        return Response.ok(request.id, result)
    except CancelledError:
        return Response.fail(request.id, ErrorCode.CANCELLED, "Task cancelled")
    except (HandlerError, ToolError) as exc:
        return Response.fail(request.id, exc.code, str(exc))
    except Exception as exc:
        return Response.fail(
            request.id, ErrorCode.INTERNAL_ERROR,
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
