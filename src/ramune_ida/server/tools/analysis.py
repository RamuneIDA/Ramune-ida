"""Analysis tools — decompile, disasm, xrefs, survey, etc."""

from __future__ import annotations

from mcp.server.fastmcp import Context

from ramune_ida.commands import Decompile
from ramune_ida.server.app import get_state


async def decompile(
    project_id: str,
    func: str,
    ctx: Context,
) -> dict:
    state = get_state()
    project = state.resolve_project(project_id)
    task = await project.execute(Decompile(func=func))
    result: dict = {"project_id": project_id, "status": task.status.value}
    if task.result is not None:
        result.update(task.result)
    if task.error is not None:
        result["error"] = task.error.message
    return result
