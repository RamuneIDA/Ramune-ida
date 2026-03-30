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

from pydantic import BaseModel, Field

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
# Analysis commands
# ---------------------------------------------------------------------------

class Decompile(Command):
    method: ClassVar[Method] = Method.DECOMPILE
    func: str = ""

    class Result(BaseModel):
        addr: str = ""
        code: str = ""

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


class Disasm(Command):
    method: ClassVar[Method] = Method.DISASM
    addr: str = ""
    count: int = 20

    class Result(BaseModel):
        start_addr: str = ""
        lines: list[dict[str, Any]] = Field(default_factory=list)

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


# ---------------------------------------------------------------------------
# Execution commands
# ---------------------------------------------------------------------------

class ExecPython(Command):
    method: ClassVar[Method] = Method.EXEC_PYTHON
    code: str = ""

    class Result(BaseModel):
        output: str = ""
        result: Any = None
        error: str = ""

        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

COMMAND_TYPES: dict[str, type[Command]] = {
    cls.method.value: cls  # type: ignore[attr-defined]
    for cls in (
        Ping, Shutdown,
        OpenDatabase, CloseDatabase, SaveDatabase,
        Decompile, Disasm,
        ExecPython,
    )
}


def command_from_params(method: str, params: dict[str, Any]) -> Command:
    """Reconstruct a typed Command from a method name and params dict."""
    cls = COMMAND_TYPES.get(method)
    if cls is None:
        raise ValueError(f"Unknown method: {method}")
    return cls(**params) if params else cls()
