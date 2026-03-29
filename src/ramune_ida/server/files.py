"""HTTP file endpoints registered via ``@mcp.custom_route``.

All binary/large-text transfers bypass the MCP protocol to avoid
wasting token budget.  Every route is scoped to a project's work_dir::

    POST /files/{project_id}                upload to project work_dir
    GET  /files/{project_id}/{path:path}    download from project work_dir
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from ramune_ida.server.app import mcp, get_state


def _file_response(path: str) -> Response:
    return FileResponse(
        path,
        filename=os.path.basename(path),
        media_type="application/octet-stream",
    )


# ── Upload ────────────────────────────────────────────────────────


@mcp.custom_route("/files/{project_id}", methods=["POST"])
async def upload_to_project(request: Request) -> Response:
    """Upload a file into a project's work directory."""
    state = get_state()
    project_id = request.path_params["project_id"]
    project = state.projects.get(project_id)
    if project is None:
        return JSONResponse(
            {"error": f"Unknown project: {project_id}"}, status_code=404
        )

    form = await request.form()
    upload = form.get("file")
    if upload is None:
        return JSONResponse({"error": "Missing 'file' field"}, status_code=400)

    # TODO: stream to disk in chunks for large files instead of reading all into memory
    content = await upload.read()  # type: ignore[union-attr]
    filename = getattr(upload, "filename", None) or "upload"
    dest = os.path.join(project.work_dir, filename)
    with open(dest, "wb") as f:
        f.write(content)
    return JSONResponse({
        "project_id": project_id,
        "path": dest,
        "filename": filename,
        "size": len(content),
    })


# ── Download ──────────────────────────────────────────────────────


@mcp.custom_route("/files/{project_id}/{path:path}", methods=["GET"])
async def download_from_project(request: Request) -> Response:
    """Download any file from a project's work directory."""
    state = get_state()
    project_id = request.path_params["project_id"]
    rel_path = request.path_params["path"]

    project = state.projects.get(project_id)
    if project is None:
        return JSONResponse(
            {"error": f"Unknown project: {project_id}"}, status_code=404
        )

    full_path = os.path.realpath(os.path.join(project.work_dir, rel_path))
    work_dir_real = os.path.realpath(project.work_dir)

    if not full_path.startswith(work_dir_real + os.sep):
        return JSONResponse({"error": "Path traversal denied"}, status_code=403)
    if not os.path.isfile(full_path):
        return JSONResponse(
            {"error": f"File not found: {rel_path}"}, status_code=404
        )

    return _file_response(full_path)
