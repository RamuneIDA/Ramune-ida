"""Tests for worker crash detection and automatic recovery.

These tests mock WorkerHandle to simulate crash scenarios without IDA.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ramune_ida.commands import Ping, PluginInvocation
from ramune_ida.limiter import Limiter
from ramune_ida.project import Project, Task
from ramune_ida.protocol import ErrorCode, Response, TaskStatus
from ramune_ida.worker_handle import WorkerDead, WorkerHandle


# ── Helpers ───────────────────────────────────────────────────────


def _make_project(tmp_path, pid: str = "test") -> Project:
    work_dir = str(tmp_path / pid)
    os.makedirs(work_dir, exist_ok=True)
    p = Project(
        project_id=pid,
        work_dir=work_dir,
        limiter=Limiter(soft_limit=0, hard_limit=0),
    )
    p.set_database("/fake/binary.elf")
    (tmp_path / "binary.i64").write_bytes(b"\x00")
    p.idb_path = str(tmp_path / "binary.i64")
    return p


def _make_mock_handle(*, alive: bool = True, exec_response: Response | None = None):
    """Create a mock WorkerHandle that passes _ensure_worker checks."""
    handle = MagicMock(spec=WorkerHandle)
    handle.instance_id = "w-mock"
    handle.is_alive.return_value = alive

    if exec_response:
        handle.execute = AsyncMock(return_value=exec_response)
    else:
        handle.execute = AsyncMock(return_value=Response.ok("__open__", {"path": "/fake"}))

    handle.spawn = AsyncMock()
    handle.kill = MagicMock()
    handle.send_signal = MagicMock()
    return handle


# ── Test: crash during execution ─────────────────────────────────


@pytest.mark.asyncio
async def test_crash_during_execution_fails_task(tmp_path):
    """Worker crash mid-execution → task fails with INTERNAL_ERROR."""
    p = _make_project(tmp_path)

    handle = _make_mock_handle()
    handle.execute = AsyncMock(side_effect=WorkerDead("socket EOF — worker process died"))
    p._handle = handle
    p._limiter.on_spawned(p.project_id)

    task = await p.execute(Ping())

    assert task.status == TaskStatus.FAILED
    assert task.error is not None
    assert "crashed" in task.error.message.lower()
    assert p._handle is None


@pytest.mark.asyncio
async def test_crash_decrements_limiter(tmp_path):
    """Limiter count decreases when worker crashes."""
    p = _make_project(tmp_path)

    handle = _make_mock_handle()
    handle.execute = AsyncMock(side_effect=WorkerDead("gone"))
    p._handle = handle
    p._limiter.on_spawned(p.project_id)

    assert p._limiter.instance_count == 1
    task = await p.execute(Ping())
    assert task.status == TaskStatus.FAILED
    assert p._limiter.instance_count == 0


# ── Test: recovery after crash ───────────────────────────────────


@pytest.mark.asyncio
async def test_next_task_recovers_after_crash(tmp_path):
    """After a crash, the next task spawns a new worker and succeeds."""
    p = _make_project(tmp_path)

    crash_handle = _make_mock_handle()
    crash_handle.execute = AsyncMock(side_effect=WorkerDead("gone"))
    p._handle = crash_handle
    p._limiter.on_spawned(p.project_id)

    task1 = await p.execute(Ping())
    assert task1.status == TaskStatus.FAILED
    assert p._handle is None

    recovery_handle = _make_mock_handle()
    call_count = 0

    async def mock_execute_recovery(req):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return Response.ok(req.id, {"path": "/fake"})
        return Response.ok(req.id, {"status": "pong"})

    recovery_handle.execute = AsyncMock(side_effect=mock_execute_recovery)

    with patch("ramune_ida.project.WorkerHandle", return_value=recovery_handle):
        task2 = await p.execute(Ping())

    assert task2.status == TaskStatus.COMPLETED
    assert task2.result == {"status": "pong"}
    assert p._limiter.instance_count == 1


# ── Test: _ensure_worker detects dead process ────────────────────


@pytest.mark.asyncio
async def test_ensure_worker_detects_dead_process(tmp_path):
    """If worker process exited between tasks, _ensure_worker respawns."""
    p = _make_project(tmp_path)

    dead_handle = _make_mock_handle(alive=False)
    p._handle = dead_handle
    p._limiter.on_spawned(p.project_id)

    new_handle = _make_mock_handle()
    call_count = 0

    async def mock_execute(req):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return Response.ok(req.id, {"path": "/fake"})
        return Response.ok(req.id, {"status": "pong"})

    new_handle.execute = AsyncMock(side_effect=mock_execute)

    with patch("ramune_ida.project.WorkerHandle", return_value=new_handle):
        task = await p.execute(Ping())

    assert task.status == TaskStatus.COMPLETED
    dead_handle.kill.assert_called_once()


# ── Test: crash after cancel request ─────────────────────────────


@pytest.mark.asyncio
async def test_crash_after_cancel_marks_cancelled(tmp_path):
    """Worker killed by cancel watchdog → task is CANCELLED, not FAILED."""
    p = _make_project(tmp_path)

    handle = _make_mock_handle()
    started = asyncio.Event()

    async def slow_then_die(req):
        if req.method == "open_database":
            return Response.ok(req.id, {"path": "/fake"})
        started.set()
        await asyncio.sleep(10)
        raise WorkerDead("killed")

    handle.execute = AsyncMock(side_effect=slow_then_die)
    p._handle = handle
    p._limiter.on_spawned(p.project_id)

    cmd = Ping()
    task = p._submit(cmd)

    await started.wait()

    task._cancel_requested = True
    handle.execute.side_effect = WorkerDead("killed by watchdog")
    if task._coro and not task._coro.done():
        task._coro.cancel()

    await asyncio.sleep(0.1)
    assert task.status == TaskStatus.CANCELLED


# ── Test: no database → error ────────────────────────────────────


@pytest.mark.asyncio
async def test_no_database_prevents_spawn(tmp_path):
    """Without set_database(), execute raises RuntimeError."""
    work_dir = str(tmp_path / "no-db")
    os.makedirs(work_dir, exist_ok=True)
    p = Project(
        project_id="no-db",
        work_dir=work_dir,
        limiter=Limiter(soft_limit=0, hard_limit=0),
    )

    task = await p.execute(Ping())
    assert task.status == TaskStatus.FAILED
    assert "No database opened" in task.error.message


# ── Test: open_database failure during recovery ──────────────────


@pytest.mark.asyncio
async def test_open_database_failure_during_recovery(tmp_path):
    """If open_database fails on the fresh worker, task fails cleanly."""
    p = _make_project(tmp_path)

    handle = _make_mock_handle()
    handle.execute = AsyncMock(
        return_value=Response.fail("__open__", ErrorCode.DATABASE_OPEN_FAILED, "corrupt idb")
    )

    with patch("ramune_ida.project.WorkerHandle", return_value=handle):
        task = await p.execute(Ping())

    assert task.status == TaskStatus.FAILED
    assert "open_database failed" in task.error.message
    handle.kill.assert_called_once()
    assert p._limiter.instance_count == 0


# ── Test: force_close kills worker ───────────────────────────────


@pytest.mark.asyncio
async def test_force_close_kills_and_cancels(tmp_path):
    """force_close kills the worker and cancels pending tasks."""
    p = _make_project(tmp_path)

    handle = _make_mock_handle()
    p._handle = handle
    p._limiter.on_spawned(p.project_id)

    p.force_close()

    handle.kill.assert_called_once()
    assert p._handle is None
    assert p._limiter.instance_count == 0


# ── Test: rapid crash loop (no circuit breaker) ──────────────────


@pytest.mark.asyncio
async def test_rapid_crashes_all_fail(tmp_path):
    """Multiple sequential crashes: each task fails, no circuit breaker."""
    p = _make_project(tmp_path)
    crash_count = 0

    def make_crashing_handle():
        h = _make_mock_handle()
        call_count = 0

        async def crash_on_second(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response.ok(req.id, {"path": "/fake"})
            nonlocal crash_count
            crash_count += 1
            raise WorkerDead("crash")

        h.execute = AsyncMock(side_effect=crash_on_second)
        return h

    handles = [make_crashing_handle() for _ in range(5)]
    handle_idx = 0

    def make_handle(*a, **kw):
        nonlocal handle_idx
        h = handles[handle_idx]
        handle_idx += 1
        return h

    with patch("ramune_ida.project.WorkerHandle", side_effect=make_handle):
        for i in range(5):
            task = await p.execute(Ping())
            assert task.status == TaskStatus.FAILED

    assert crash_count == 5
    assert p._limiter.instance_count == 0


# ── Test: concurrent tasks during crash ──────────────────────────


@pytest.mark.asyncio
async def test_pending_task_survives_crash(tmp_path):
    """A task waiting on exec_lock while current task crashes:
    the pending task should attempt recovery on its own."""
    p = _make_project(tmp_path)

    iteration = 0

    def make_handle(*a, **kw):
        nonlocal iteration
        iteration += 1
        h = _make_mock_handle()
        current_iter = iteration
        call_count = 0

        async def execute(req):
            nonlocal call_count
            call_count += 1
            if req.method == "open_database":
                return Response.ok(req.id, {"path": "/fake"})
            if current_iter == 1:
                await asyncio.sleep(0.05)
                raise WorkerDead("crash")
            return Response.ok(req.id, {"status": "pong"})

        h.execute = AsyncMock(side_effect=execute)
        return h

    p._handle = None
    with patch("ramune_ida.project.WorkerHandle", side_effect=make_handle):
        task1_coro = p.execute(Ping())
        task2_coro = p.execute(Ping())

        task1, task2 = await asyncio.gather(task1_coro, task2_coro)

    assert task1.status == TaskStatus.FAILED
    assert task2.status == TaskStatus.COMPLETED
