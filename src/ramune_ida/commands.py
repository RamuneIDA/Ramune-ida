"""Typed command definitions for IPC between Server and Worker.

Each ``Command`` subclass is self-contained: it declares the IPC
method, the parameters (as dataclass fields), and a nested ``Result``
class that describes the expected response.

Use ``COMMAND_TYPES`` or ``command_from_params()`` to reconstruct a
typed Command from wire-format data.

.. note:: Imported by the worker — must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from ramune_ida.protocol import Method, Request


# ---------------------------------------------------------------------------
# Command base
# ---------------------------------------------------------------------------

class Command(BaseModel):
    """Base class for all IPC commands.

    Subclasses declare ``method: ClassVar[Method]`` and typed fields
    for parameters.  Each subclass also contains a nested ``Result``
    class that mirrors the expected response payload.
    """

    method: ClassVar[Method]

    def to_params(self) -> dict[str, Any]:
        return self.model_dump() if type(self).model_fields else {}

    def to_request(self, req_id: str) -> Request:
        return Request(id=req_id, method=self.method.value, params=self.to_params())


# ---------------------------------------------------------------------------
# Lifecycle commands
# ---------------------------------------------------------------------------

class Ping(Command):
    method: ClassVar[Method] = Method.PING

    class Result(BaseModel):
        status: str = "pong"

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


class Shutdown(Command):
    method: ClassVar[Method] = Method.SHUTDOWN

    class Result(BaseModel):
        status: str = "shutdown"

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


# ---------------------------------------------------------------------------
# Database commands
# ---------------------------------------------------------------------------

class OpenDatabase(Command):
    method: ClassVar[Method] = Method.OPEN_DATABASE
    path: str = ""
    auto_analysis: bool = True

    class Result(BaseModel):
        path: str = ""

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


class CloseDatabase(Command):
    method: ClassVar[Method] = Method.CLOSE_DATABASE
    save: bool = True

    class Result(BaseModel):
        def to_dict(self) -> dict[str, Any]:
            return {}


class SaveDatabase(Command):
    method: ClassVar[Method] = Method.SAVE_DATABASE

    class Result(BaseModel):
        def to_dict(self) -> dict[str, Any]:
            return {}


# ---------------------------------------------------------------------------
# Plugin invocation (no Method enum, no Pydantic model)
# ---------------------------------------------------------------------------

class PluginInvocation:
    """Lightweight stand-in for Command in plugin tool calls.

    Implements the interface that :class:`~ramune_ida.project.Task` and
    :meth:`Project._exec_one` require (``method.value``, ``to_request``,
    ``to_params``) without needing a :class:`Method` enum member or a
    Pydantic model class.
    """

    class _MethodProxy:
        """Quacks like a :class:`Method` enum member."""
        __slots__ = ("value",)

        def __init__(self, v: str) -> None:
            self.value = v

    __slots__ = ("method", "_params")

    def __init__(self, tool_name: str, params: dict[str, Any]) -> None:
        self.method = self._MethodProxy(f"plugin:{tool_name}")
        self._params = params

    def to_params(self) -> dict[str, Any]:
        return self._params

    def to_request(self, req_id: str) -> Request:
        return Request(id=req_id, method=self.method.value, params=self._params)


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

COMMAND_TYPES: dict[str, type[Command]] = {
    cls.method.value: cls  # type: ignore[attr-defined]
    for cls in (
        Ping, Shutdown,
        OpenDatabase, CloseDatabase, SaveDatabase,
    )
}


def command_from_params(method: str, params: dict[str, Any]) -> Command:
    """Reconstruct a typed Command from a method name and params dict."""
    cls = COMMAND_TYPES.get(method)
    if cls is None:
        raise ValueError(f"Unknown method: {method}")
    return cls(**params) if params else cls()
