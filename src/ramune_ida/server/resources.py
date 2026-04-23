"""MCP Resources — read-only metadata exposed to AI clients.

Resources let the AI discover what files and outputs exist, along with
their HTTP download URLs, without spending a tool-call turn.

Principle: **Resources are for discovery, HTTP routes are for transfer.**
"""

from __future__ import annotations

import json
import os
import time

from ramune_ida.server.app import mcp, get_state


# ── Projects overview ─────────────────────────────────────────────


@mcp.resource(
    "projects://overview",
    description=(
        "All open projects at a glance: IDs, worker state, active task "
        "counts, and instance limits."
    ),
)
def projects_overview() -> str:
    state = get_state()
    projects = []
    for pid, project in state.projects.items():
        projects.append({
            "project_id": pid,
            "has_worker": project._handle is not None,
            "has_database": project.has_database,
            "active_tasks": len(project._tasks),
        })

    limiter = state.limiter
    return json.dumps({
        "projects": projects,
        "instance_count": limiter.instance_count,
        "soft_limit": limiter._soft_limit,
        "hard_limit": limiter._hard_limit,
        "over_soft_limit": limiter.over_soft_limit,
    })


# ── Project metadata ──────────────────────────────────────────────


@mcp.resource(
    "project://{project_id}/status",
    description="Detailed project status: paths, worker state, active tasks.",
)
def project_status(project_id: str) -> str:
    state = get_state()
    project = state.projects.get(project_id)
    if project is None:
        return json.dumps({"error": f"Unknown project: {project_id}"})

    tasks = [t.to_dict() for t in project._tasks.values()]

    idle = round(time.monotonic() - project.last_accessed, 1) if project.last_accessed > 0 else None

    return json.dumps({
        "project_id": project_id,
        "exe_path": project.exe_path,
        "idb_path": project.idb_path,
        "work_dir": project.work_dir,
        "has_worker": project._handle is not None,
        "idle_seconds": idle,
        "tasks": tasks,
        "output_count": len(state.output_store.list_outputs(project_id)),
    })


# ── Project files ─────────────────────────────────────────────────


@mcp.resource(
    "project://{project_id}/files",
    description=(
        "File listing for a project work_dir with sizes and download URLs."
    ),
)
def project_files(project_id: str) -> str:
    state = get_state()
    if state.config.local_mode:
        return json.dumps({"error": "File listing is not available."})
    project = state.projects.get(project_id)
    if project is None:
        return json.dumps({"error": f"Unknown project: {project_id}"})

    files: list[dict] = []
    work_dir = project.work_dir
    if os.path.isdir(work_dir):
        for root, dirs, filenames in os.walk(work_dir):
            for name in filenames:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, work_dir)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = None
                files.append({
                    "name": rel,
                    "size": size,
                    "download_url": f"/files/{project_id}/{rel}",
                })

    return json.dumps({
        "project_id": project_id,
        "work_dir": work_dir,
        "files": files,
    })


# ── Truncated outputs ─────────────────────────────────────────────


@mcp.resource(
    "outputs://{project_id}",
    description="Truncated output listing with download URLs.",
)
def project_outputs(project_id: str) -> str:
    state = get_state()
    if project_id not in state.projects:
        return json.dumps({"error": f"Unknown project: {project_id}"})

    local_mode = state.config.local_mode
    raw = state.output_store.list_outputs(project_id)
    outputs = []
    for oid, path in raw.items():
        size = None
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        if local_mode:
            url = path
        else:
            ext = os.path.splitext(path)[1] or ".txt"
            url = f"/files/{project_id}/outputs/{oid}{ext}"
        outputs.append({
            "output_id": oid,
            "size": size,
            "download_url": url,
        })

    return json.dumps({
        "project_id": project_id,
        "count": len(outputs),
        "outputs": outputs,
    })
