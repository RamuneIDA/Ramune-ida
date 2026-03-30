"""Direct Worker process tests with real IDA.

Spawns a real Worker subprocess, talks to it over socketpair,
and tests every handler without MCP framework overhead.

Run with: pytest tests/test_worker_real.py --run-ida
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys

import orjson
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytestmark = pytest.mark.ida

IDA_DIR = os.environ.get("IDADIR", "/home/explorer/ida-pro-9.3")
IDA_PYTHON_PATH = os.path.join(IDA_DIR, "idalib", "python")
PYTHON = sys.executable
BINARY_DIR = os.path.join(os.path.dirname(__file__), "binary")

from ramune_ida.worker.socket_io import ENV_SOCK_FD


# ── Worker subprocess helper ──────────────────────────────────────


class WorkerProc:
    """Manage a real Worker subprocess with socketpair IPC."""

    def __init__(self, cwd: str | None = None):
        parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        child_fd = child_sock.fileno()

        env = os.environ.copy()
        env[ENV_SOCK_FD] = str(child_fd)
        env["IDADIR"] = IDA_DIR
        env["PYTHONPATH"] = IDA_PYTHON_PATH + os.pathsep + env.get("PYTHONPATH", "")

        self.proc = subprocess.Popen(
            [PYTHON, "-m", "ramune_ida.worker.main"],
            env=env,
            cwd=cwd,
            pass_fds=(child_fd,),
        )
        child_sock.close()

        self._sock = parent_sock
        self._reader = parent_sock.makefile("rb")
        self._writer = parent_sock.makefile("wb")

    def send(self, msg: dict) -> dict:
        self._writer.write(orjson.dumps(msg) + b"\n")
        self._writer.flush()
        return self.recv()

    def recv(self) -> dict:
        line = self._reader.readline()
        if not line:
            raise RuntimeError("Worker closed (EOF)")
        return orjson.loads(line)

    def close(self):
        self._reader.close()
        self._writer.close()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()
        self.proc.wait(timeout=10)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def work_dir(tmp_path):
    d = str(tmp_path / "work")
    os.makedirs(d)
    return d


@pytest.fixture
def binary(work_dir):
    """Copy ch01 test binary to work_dir."""
    src = os.path.join(BINARY_DIR, "ch01")
    if not os.path.isfile(src):
        pytest.skip("Test binary ch01 not found")
    dest = os.path.join(work_dir, "ch01")
    shutil.copy2(src, dest)
    return dest


@pytest.fixture
def worker(work_dir):
    w = WorkerProc(cwd=work_dir)
    init = w.recv()
    assert init["result"]["status"] == "ready"
    yield w
    try:
        w.send({"id": "shutdown", "method": "shutdown", "params": {}})
    except Exception:
        pass
    w.close()


# ── Lifecycle ─────────────────────────────────────────────────────


def test_ping(worker):
    r = worker.send({"id": "1", "method": "ping", "params": {}})
    assert r["result"]["status"] == "pong"


def test_unknown_method(worker):
    r = worker.send({"id": "1", "method": "no_such_method", "params": {}})
    assert "error" in r


def test_open_close_database(worker, binary):
    r = worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})
    assert "error" not in r
    assert r["result"]["path"] == binary

    r = worker.send({"id": "2", "method": "close_database", "params": {}})
    assert "error" not in r


def test_open_database_missing_path(worker):
    r = worker.send({"id": "1", "method": "open_database", "params": {"path": ""}})
    assert "error" in r


def test_open_database_nonexistent_file(worker):
    r = worker.send({"id": "1", "method": "open_database", "params": {"path": "/nonexistent/file.bin"}})
    assert "error" in r


def test_save_database(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})
    r = worker.send({"id": "2", "method": "save_database", "params": {}})
    assert "error" not in r
    worker.send({"id": "3", "method": "close_database", "params": {}})


# ── Decompile (plugin:decompile) ──────────────────────────────────


def test_decompile_by_name(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:decompile", "params": {"func": "main"}})
    assert "error" not in r
    assert "code" in r["result"]
    assert "addr" in r["result"]
    assert len(r["result"]["code"]) > 0

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_decompile_by_address(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:decompile", "params": {"func": "main"}})
    addr = r["result"]["addr"]

    r = worker.send({"id": "3", "method": "plugin:decompile", "params": {"func": addr}})
    assert "error" not in r
    assert r["result"]["addr"] == addr

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_decompile_missing_func(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:decompile", "params": {"func": ""}})
    assert "error" in r

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_decompile_unknown_func(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:decompile", "params": {"func": "nonexistent_func_xyz"}})
    assert "error" in r

    worker.send({"id": "99", "method": "close_database", "params": {}})


# ── Disasm (plugin:disasm) ────────────────────────────────────────


def test_disasm_by_name(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:disasm", "params": {"addr": "main", "count": 5}})
    assert "error" not in r
    lines = r["result"]["lines"]
    assert len(lines) > 0
    assert len(lines) <= 5
    assert "addr" in lines[0]
    assert "disasm" in lines[0]
    assert "size" in lines[0]

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_disasm_by_address(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:disasm", "params": {"addr": "main"}})
    addr = r["result"]["start_addr"]

    r = worker.send({"id": "3", "method": "plugin:disasm", "params": {"addr": addr, "count": 3}})
    assert "error" not in r
    assert len(r["result"]["lines"]) <= 3

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_disasm_missing_addr(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:disasm", "params": {"addr": ""}})
    assert "error" in r

    worker.send({"id": "99", "method": "close_database", "params": {}})


def test_disasm_unknown_addr(worker, binary):
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:disasm", "params": {"addr": "nonexistent_xyz"}})
    assert "error" in r

    worker.send({"id": "99", "method": "close_database", "params": {}})


# ── Multiple commands in sequence ─────────────────────────────────


def test_sequential_commands(worker, binary):
    """Verify the worker handles a realistic sequence correctly."""
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})

    r = worker.send({"id": "2", "method": "plugin:decompile", "params": {"func": "main"}})
    assert "code" in r["result"]

    r = worker.send({"id": "3", "method": "plugin:disasm", "params": {"addr": "main", "count": 10}})
    assert len(r["result"]["lines"]) > 0

    r = worker.send({"id": "4", "method": "save_database", "params": {}})
    assert "error" not in r

    r = worker.send({"id": "5", "method": "close_database", "params": {}})
    assert "error" not in r


def test_reopen_after_close(worker, binary):
    """Close and reopen the same database in one worker session."""
    worker.send({"id": "1", "method": "open_database", "params": {"path": binary}})
    worker.send({"id": "2", "method": "close_database", "params": {}})

    worker.send({"id": "3", "method": "open_database", "params": {"path": binary}})
    r = worker.send({"id": "4", "method": "plugin:decompile", "params": {"func": "main"}})
    assert "code" in r["result"]

    worker.send({"id": "99", "method": "close_database", "params": {}})
