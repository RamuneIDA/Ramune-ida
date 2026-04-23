"""FastMCP application instance and lifespan management.

All tool / resource / custom-route modules import ``register_tool`` and
``mcp`` from here.  ``register_tool`` is a drop-in replacement for
``@mcp.tool`` that automatically passes every return value through
:meth:`OutputStore.process` when the result contains a ``project_id``.
Results without a ``project_id`` are returned as-is (no truncation).

``get_state()`` is the canonical way to obtain the shared
:class:`AppState` from within any handler.
"""

from __future__ import annotations

import contextvars
import inspect
import os
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, AsyncIterator, Callable

from mcp.server.fastmcp import FastMCP

from ramune_ida.config import ServerConfig
from ramune_ida.server.state import AppState

# Module-level singletons ---------------------------------------------------

_config: ServerConfig | None = None
_state: AppState | None = None
_submodules_imported = False

request_base_url: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_base_url", default=""
)


def configure(config: ServerConfig) -> None:
    """Set the configuration before ``mcp.run()``.

    Also triggers (once) the import of tool / resource / custom-route
    submodules so they can see the resolved config and register
    description text accordingly.
    """
    global _config, _submodules_imported
    _config = config
    mcp._mcp_server.instructions = build_instructions(config)
    if not _submodules_imported:
        _submodules_imported = True
        import ramune_ida.server.tools  # noqa: F401
        import ramune_ida.server.files  # noqa: F401
        import ramune_ida.server.resources  # noqa: F401


def get_state() -> AppState:
    """Return the active AppState.  Raises if the server is not started."""
    if _state is None:
        raise RuntimeError("Server not initialised — AppState is None")
    return _state


def get_config() -> ServerConfig:
    """Return the active ServerConfig.  Raises if ``configure()`` was not called."""
    if _config is None:
        raise RuntimeError("Server not configured — call configure() first")
    return _config


# Lifespan -------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[dict]:
    global _state

    if _state is not None:
        # Already initialised (e.g. by the web module's startup).
        yield {}
        return

    assert _config is not None, "Call configure() before starting the server"

    if _config.plugins_enabled:
        from ramune_ida.server.plugins import discover_tools, register_plugin_tools

        tools_meta = await discover_tools(
            _config.worker_python,
            plugin_dir=_config.resolved_plugin_dir,
        )
        register_plugin_tools(tools_meta, exclude_tags=list(_config.exclude_tags))

    state = AppState(_config)
    await state.start()
    _state = state
    try:
        yield {}
    finally:
        await state.shutdown()
        _state = None


async def ensure_state() -> AppState:
    """Initialise AppState if not already done.  Called by the web module."""
    global _state
    if _state is not None:
        return _state
    assert _config is not None, "Call configure() before ensure_state()"

    if _config.plugins_enabled:
        from ramune_ida.server.plugins import discover_tools, register_plugin_tools

        tools_meta = await discover_tools(
            _config.worker_python,
            plugin_dir=_config.resolved_plugin_dir,
        )
        register_plugin_tools(tools_meta, exclude_tags=list(_config.exclude_tags))

    state = AppState(_config)
    await state.start()
    _state = state
    return state


# FastMCP instance -----------------------------------------------------------

_INSTRUCTIONS_HTTP = """\
Ramune-ida — headless IDA Pro for AI reverse engineering.

Concepts:
- project: a workspace with its own directory. Created by open_project().
- database: an IDA database opened inside a project via open_database().
- project_id: returned by open_project(), required by all other tools.

File transfer: open_project returns upload/download endpoint URLs.
  Upload:   POST {upload_url} (multipart form, field "file")
  Download: GET  {download_url}
open_database path is relative to work_dir — just use the filename you uploaded.

Workflow: open_project → upload binary → open_database → analyze → close_project.
The IDA worker is started lazily: if it has exited or crashed, the next tool call
automatically restarts it and reopens the database. You do NOT need to call
open_database again after a restart or between analysis commands.

Concurrency: you can call multiple tools concurrently. Each project executes
requests sequentially through a queue — concurrent calls are queued automatically,
so you do not need to wait for one to finish before sending the next.
Multiple projects run isolated IDA processes and never interfere with each other.

If a request takes too long, it continues in the background and returns a task_id.
Poll with get_task_result.
If a tool cannot handle your request, use execute_python to run arbitrary IDAPython.
"""


_INSTRUCTIONS_LOCAL = """\
Ramune-ida — headless IDA Pro for AI reverse engineering.

Concepts:
- project: a workspace. Created by open_project().
- database: an IDA database opened inside a project via open_database().
- project_id: returned by open_project(), required by all other tools.

Workflow: open_project → open_database(path) → analyze → close_project.
Pass an absolute path (or a path relative to your own working directory) to
open_database. The IDA worker is started lazily: if it has exited or crashed,
the next tool call automatically restarts it and reopens the database. You do
NOT need to call open_database again after a restart or between analysis
commands.

Concurrency: you can call multiple tools concurrently. Each project executes
requests sequentially through a queue — concurrent calls are queued automatically,
so you do not need to wait for one to finish before sending the next.
Multiple projects run isolated IDA processes and never interfere with each other.

If a request takes too long, it continues in the background and returns a task_id.
Poll with get_task_result.
If a tool cannot handle your request, use execute_python to run arbitrary IDAPython.
"""


def build_instructions(config: ServerConfig) -> str:
    """Return the MCP server instructions appropriate for *config*."""
    return _INSTRUCTIONS_LOCAL if config.local_mode else _INSTRUCTIONS_HTTP


mcp = FastMCP("ramune-ida", instructions=_INSTRUCTIONS_HTTP, lifespan=_lifespan)


# Auto-truncating tool decorator --------------------------------------------

def _resolve_project_context(
    state: AppState, result: Any
) -> tuple[str | None, str | None]:
    """Extract project_id from a tool result and return *(pid, output_dir)*.

    Returns ``(None, None)`` when truncation should be skipped.
    """
    if not isinstance(result, dict):
        return None, None
    pid = result.get("project_id")
    if pid is None:
        return None, None
    project = state.projects.get(pid)
    if project is None:
        return None, None
    return pid, project.outputs_dir


def register_tool(*deco_args: Any, **deco_kwargs: Any) -> Any:
    """Register an MCP tool with automatic output truncation.

    Drop-in replacement for ``@mcp.tool``.  Preserves the original
    function signature so FastMCP / Pydantic can generate the correct
    JSON schema.  After the tool function returns, the result is passed
    through ``OutputStore.process()`` **only if** the result contains a
    valid ``project_id``.  Otherwise the result is returned as-is.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            try:
                state = get_state()
                pid, output_dir = _resolve_project_context(state, result)
                if pid is not None and output_dir is not None:
                    return state.output_store.process(result, pid, output_dir)
            except RuntimeError:
                pass
            return result

        wrapper.__signature__ = inspect.signature(fn)
        return mcp.tool(*deco_args, **deco_kwargs)(wrapper)

    if deco_args and callable(deco_args[0]) and not deco_kwargs:
        return decorator(deco_args[0])
    return decorator


# NOTE: tool / resource / custom-route submodule imports are deferred to
# ``configure()`` so they can inspect the resolved ServerConfig (e.g. to pick
# local-mode descriptions).  Callers MUST invoke ``configure()`` before the
# server starts handling requests — both CLI and tests do this.
