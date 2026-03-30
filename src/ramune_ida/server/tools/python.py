"""Python execution tool — execute_python."""

from __future__ import annotations

from mcp.server.fastmcp import Context

from ramune_ida.commands import ExecPython
from ramune_ida.server.app import get_state


async def execute_python(
    project_id: str,
    code: str,
    ctx: Context,
    timeout: int = 60,
) -> dict:
    state = get_state()
    project = state.resolve_project(project_id)
    task = await project.execute(ExecPython(code=code), timeout=float(timeout))
    result: dict = {"project_id": project_id, "status": task.status.value}
    if task.result is not None:
        result.update(task.result)
    if task.error is not None:
        result["error"] = task.error.message
    if not task.is_done:
        result["task_id"] = task.task_id
    return result
