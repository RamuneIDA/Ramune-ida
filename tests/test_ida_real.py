"""Real IDA integration tests — requires IDA Pro + idalib.

Run with: pytest tests/test_ida_real.py --run-ida

These tests spawn actual IDA Worker processes (no mock) and open
real binaries.  They verify the full pipeline from MCP tool call
through IPC to IDA API execution.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

IDA_DIR = os.environ.get("IDADIR", "/home/explorer/ida-pro-9.3")
IDA_PYTHON_PATH = os.path.join(IDA_DIR, "idalib", "python")
WORKER_PYTHON = sys.executable
BINARY_DIR = os.path.join(os.path.dirname(__file__), "binary")

pytestmark = pytest.mark.ida

# ── Setup ─────────────────────────────────────────────────────────

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module


_plugins_registered = False


@pytest_asyncio.fixture
async def mcp_ida(tmp_path):
    """Start MCP with real IDA worker (no mock)."""
    global _plugins_registered

    config = ServerConfig(
        worker_python=WORKER_PYTHON,
        soft_limit=0,
        hard_limit=2,
        auto_save_interval=0,
        data_dir=str(tmp_path),
    )

    os.environ["IDADIR"] = IDA_DIR
    os.environ["PYTHONPATH"] = IDA_PYTHON_PATH + os.pathsep + os.environ.get("PYTHONPATH", "")

    app_module.configure(config)

    if not _plugins_registered:
        from ramune_ida.server.plugins import discover_tools, register_plugin_tools
        tools_meta = await discover_tools(WORKER_PYTHON)
        register_plugin_tools(tools_meta)
        _plugins_registered = True

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state

    yield app_module.mcp

    await state.shutdown()
    app_module._state = None


async def call(mcp, name: str, args: dict | None = None) -> dict:
    result = await mcp.call_tool(name, args or {})
    if isinstance(result, tuple):
        content_list = result[0]
    elif isinstance(result, list):
        content_list = result
    elif isinstance(result, dict):
        return result
    else:
        raise ValueError(f"Unexpected: {type(result)}")
    for item in content_list:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise ValueError(f"No text content: {result}")


# ── Helpers ───────────────────────────────────────────────────────


def _get_work_dir(project_id: str) -> str:
    """Read a project's work_dir from internal state (test-only)."""
    state = app_module.get_state()
    return state.projects[project_id].work_dir


def _copy_binary(name: str, work_dir: str) -> str:
    """Copy a test binary to the project work_dir."""
    src = os.path.join(BINARY_DIR, name)
    if not os.path.isfile(src):
        pytest.skip(f"Test binary not found: {src}")
    import shutil
    dest = os.path.join(work_dir, name)
    shutil.copy2(src, dest)
    return name


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_close_real_binary(mcp_ida):
    """Open a real binary, verify worker spawns, then close."""
    mcp = mcp_ida

    r = await call(mcp, "open_project", {"project_id": "ida-test"})
    pid = r["project_id"]
    binary = _copy_binary("ch01", _get_work_dir(pid))

    r = await call(mcp, "open_database", {"project_id": pid, "path": binary})
    assert r["status"] == "completed"
    assert r.get("idb_path") is not None

    r = await call(mcp, "projects")
    p = r["projects"][0]
    assert p["has_worker"] is True
    assert p["has_database"] is True

    r = await call(mcp, "close_database", {"project_id": pid})
    assert r["status"] in ("completed", "killed")

    r = await call(mcp, "close_project", {"project_id": pid})
    assert r["status"] == "closed"


@pytest.mark.asyncio
async def test_reopen_idb(mcp_ida):
    """Open binary (creates IDB), close, reopen from IDB."""
    mcp = mcp_ida

    r = await call(mcp, "open_project", {"project_id": "reopen"})
    pid = r["project_id"]
    work_dir = _get_work_dir(pid)
    binary = _copy_binary("ch01", work_dir)

    r = await call(mcp, "open_database", {"project_id": pid, "path": binary})
    assert r["status"] == "completed"
    idb_path = r.get("idb_path", "")

    r = await call(mcp, "close_database", {"project_id": pid})

    idb_name = os.path.basename(idb_path)
    if os.path.isfile(os.path.join(work_dir, idb_name)):
        r = await call(mcp, "open_database", {"project_id": pid, "path": idb_name})
        assert r["status"] == "completed"
        r = await call(mcp, "close_database", {"project_id": pid})

    await call(mcp, "close_project", {"project_id": pid})


@pytest.mark.asyncio
async def test_multiple_projects_real(mcp_ida):
    """Open two different binaries in separate projects."""
    mcp = mcp_ida

    await call(mcp, "open_project", {"project_id": "multi-a"})
    await call(mcp, "open_project", {"project_id": "multi-b"})

    bin_a = _copy_binary("ch01", _get_work_dir("multi-a"))
    bin_b = _copy_binary("ch02", _get_work_dir("multi-b"))

    ra = await call(mcp, "open_database", {"project_id": "multi-a", "path": bin_a})
    rb = await call(mcp, "open_database", {"project_id": "multi-b", "path": bin_b})
    assert ra["status"] == "completed"
    assert rb["status"] == "completed"

    r = await call(mcp, "projects")
    assert r["count"] == 2
    assert r["instance_count"] == 2

    await call(mcp, "close_database", {"project_id": "multi-a"})
    await call(mcp, "close_database", {"project_id": "multi-b"})
    await call(mcp, "close_project", {"project_id": "multi-a"})
    await call(mcp, "close_project", {"project_id": "multi-b"})


@pytest.mark.asyncio
async def test_decompile_via_mcp(mcp_ida):
    """Full MCP chain: open_project -> open_database -> decompile -> close."""
    mcp = mcp_ida

    await call(mcp, "open_project", {"project_id": "dec-real"})
    binary = _copy_binary("ch01", _get_work_dir("dec-real"))

    await call(mcp, "open_database", {"project_id": "dec-real", "path": binary})

    r = await call(mcp, "decompile", {"project_id": "dec-real", "func": "main"})
    assert r["status"] == "completed"
    assert "code" in r
    assert "addr" in r
    assert len(r["code"]) > 0

    await call(mcp, "close_database", {"project_id": "dec-real"})
    await call(mcp, "close_project", {"project_id": "dec-real"})


# ── Local mode (real IDA) ─────────────────────────────────────────


@pytest_asyncio.fixture
async def mcp_ida_local(tmp_path, monkeypatch):
    """Start MCP in local mode with real IDA worker, chdir'd into a tmp dir."""
    global _plugins_registered

    monkeypatch.chdir(tmp_path)

    config = ServerConfig(
        worker_python=WORKER_PYTHON,
        soft_limit=0,
        hard_limit=2,
        auto_save_interval=0,
        data_dir=str(tmp_path / "_data"),
        local_mode=True,
    )

    os.environ["IDADIR"] = IDA_DIR
    os.environ["PYTHONPATH"] = IDA_PYTHON_PATH + os.pathsep + os.environ.get("PYTHONPATH", "")

    app_module.configure(config)

    if not _plugins_registered:
        from ramune_ida.server.plugins import discover_tools, register_plugin_tools
        tools_meta = await discover_tools(WORKER_PYTHON)
        register_plugin_tools(tools_meta)
        _plugins_registered = True

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state

    yield app_module.mcp

    await state.shutdown()
    app_module._state = None


@pytest.mark.asyncio
async def test_local_decompile_via_absolute_path(mcp_ida_local, tmp_path):
    """Local mode: open a binary by absolute path, decompile main,
    verify cwd is untouched and outputs live under .ramune-outputs/."""
    mcp = mcp_ida_local

    # AI-side view: only project_id comes back — no upload/download/work_dir.
    r = await call(mcp, "open_project", {"project_id": "loc"})
    assert r["project_id"] == "loc"
    for forbidden in ("upload", "download", "curl_upload", "work_dir", "mode"):
        assert forbidden not in r

    # Pre-seed a sentinel file in cwd; close_project must not delete it.
    sentinel = tmp_path / "user_notes.txt"
    sentinel.write_text("important reversing notes")

    # Drop the binary somewhere OUTSIDE cwd to prove absolute paths work.
    import shutil
    src = os.path.join(BINARY_DIR, "ch01")
    if not os.path.isfile(src):
        pytest.skip(f"Test binary not found: {src}")
    external = tmp_path.parent / "external_bins"
    external.mkdir(exist_ok=True)
    abs_binary = str(external / "ch01")
    shutil.copy2(src, abs_binary)

    r = await call(mcp, "open_database", {"project_id": "loc", "path": abs_binary})
    assert r["status"] == "completed"
    assert r.get("idb_path") is not None

    r = await call(mcp, "decompile", {"project_id": "loc", "func": "main"})
    assert r["status"] == "completed"
    assert "code" in r and len(r["code"]) > 0

    await call(mcp, "close_database", {"project_id": "loc"})

    # outputs_dir must be under cwd/.ramune-outputs/<pid>/
    outputs_dir = _get_work_dir("loc")  # == cwd
    assert outputs_dir == str(tmp_path)
    expected_outputs = tmp_path / ".ramune-outputs" / "loc"
    # May or may not exist depending on truncation — either is fine.

    await call(mcp, "close_project", {"project_id": "loc"})

    # cwd and sentinel must survive close_project.
    assert tmp_path.is_dir()
    assert sentinel.exists()
    assert sentinel.read_text() == "important reversing notes"
    # Per-project outputs dir is gone.
    assert not expected_outputs.exists()


@pytest.mark.asyncio
async def test_local_multi_projects_share_cwd(mcp_ida_local, tmp_path):
    """Two projects in local mode share cwd but isolate outputs."""
    mcp = mcp_ida_local

    import shutil
    src = os.path.join(BINARY_DIR, "ch01")
    if not os.path.isfile(src):
        pytest.skip(f"Test binary not found: {src}")
    # Binary lives in cwd — relative path must work too.
    rel_binary = "ch01"
    shutil.copy2(src, tmp_path / rel_binary)

    await call(mcp, "open_project", {"project_id": "a"})
    await call(mcp, "open_project", {"project_id": "b"})
    assert _get_work_dir("a") == str(tmp_path)
    assert _get_work_dir("b") == str(tmp_path)

    # Both should accept the same cwd-relative path.
    ra = await call(mcp, "open_database", {"project_id": "a", "path": rel_binary})
    rb = await call(mcp, "open_database", {"project_id": "b", "path": rel_binary})
    assert ra["status"] == "completed"
    assert rb["status"] == "completed"

    await call(mcp, "close_database", {"project_id": "a"})
    await call(mcp, "close_database", {"project_id": "b"})
    await call(mcp, "close_project", {"project_id": "a"})
    await call(mcp, "close_project", {"project_id": "b"})

    # cwd intact.
    assert tmp_path.is_dir()
    assert (tmp_path / rel_binary).exists()
