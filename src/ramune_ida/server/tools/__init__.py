"""Tool Registry — the single place that declares every MCP tool.

Open this file to see all available tools at a glance: name,
description, and which module implements it.

Implementation functions live in sibling modules (session.py,
analysis.py, ...).  This file only handles **registration**.

Adding a new tool
-----------------
1. ``commands.py``  — define the Command + Result dataclass
2. ``worker/handlers/*.py``  — implement the IDA-side handler
3. ``server/tools/<module>.py``  — write the MCP-side async function
4. **Here** — add a ``register_tool(description=...)(impl)`` entry
"""

from ramune_ida.server.app import register_tool
from ramune_ida.server.tools import analysis, python, session

# ── Project lifecycle ─────────────────────────────────────────────

register_tool(
    description="Create a new project workspace. Returns project_id and work_dir.",
)(session.open_project)

register_tool(
    description="Destroy a project and clean up its work directory.",
)(session.close_project)

register_tool(
    description="List all open projects and their status.",
)(session.projects)

# ── Database lifecycle ────────────────────────────────────────────

register_tool(
    description="Open a binary or IDB in the project. Path is relative to work_dir.",
)(session.open_database)

register_tool(
    description=(
        "Close the database and terminate the IDA process. "
        "The project stays alive. Set force=true to kill without saving."
    ),
)(session.close_database)

# ── Analysis ──────────────────────────────────────────────────────

register_tool(
    description="Decompile a function by name or hex address.",
)(analysis.decompile)

# ── Execution ─────────────────────────────────────────────────────

register_tool(
    description=(
        "Execute arbitrary IDAPython code. "
        "Assign _result to return structured data; stdout/stderr are captured separately."
    ),
)(python.execute_python)

# ── Async tasks ───────────────────────────────────────────────────

register_tool(
    description="Poll the result of a long-running task.",
)(session.get_task_result)

register_tool(
    description="Cancel a running or queued task.",
)(session.cancel_task)
