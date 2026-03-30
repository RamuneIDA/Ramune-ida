"""Fake Worker that responds to commands without IDA.

Used for unit tests.  Supports the same IPC protocol as the real
Worker (UNIX socketpair, JSON line) but returns canned responses
for lifecycle commands and echoes everything else.

exec_python is handled with real ``exec()`` (no IDA modules) to
support stdout capture, ``_result``, and traceback tests.
SIGUSR1 is handled to support graceful cancellation tests.

Run with:
    RAMUNE_SOCK_FD=... python tests/mock_worker.py
"""

from __future__ import annotations

import io
import os
import signal
import socket
import sys
import time
import traceback

import orjson

ENV_SOCK_FD = "RAMUNE_SOCK_FD"

_cancel_requested = False


def _on_sigusr1(_sig: int, _frame: object) -> None:
    global _cancel_requested
    _cancel_requested = True


def _cancel_profile(_frame: object, _event: str, _arg: object) -> None:
    if _cancel_requested:
        raise _CancelledError


class _CancelledError(BaseException):
    pass


def _exec_python(code: str) -> dict:
    """Execute code with stdout capture, _result, and traceback."""
    global _cancel_requested
    _cancel_requested = False

    namespace: dict = {"__builtins__": __builtins__}
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    error_msg = ""
    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        sys.setprofile(_cancel_profile)
        exec(code, namespace)
    except _CancelledError:
        error_msg = "Task cancelled"
    except Exception:
        error_msg = traceback.format_exc()
    finally:
        sys.setprofile(None)
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "output": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "result": namespace.get("_result"),
        "error": error_msg,
    }


def main() -> None:
    signal.signal(signal.SIGUSR1, _on_sigusr1)

    sock_fd = int(os.environ[ENV_SOCK_FD])
    sock = socket.socket(fileno=sock_fd)
    sock.setblocking(True)
    reader = sock.makefile("rb")
    writer = sock.makefile("wb")

    current_db: str | None = None

    def send(msg: dict) -> None:
        writer.write(orjson.dumps(msg) + b"\n")
        writer.flush()

    send({"id": "__init__", "result": {"status": "ready"}})

    while True:
        line = reader.readline()
        if not line:
            break

        req = orjson.loads(line)
        rid = req["id"]
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "shutdown":
            send({"id": rid, "result": {"status": "shutdown"}})
            break

        elif method == "ping":
            send({"id": rid, "result": {"status": "pong"}})

        elif method == "open_database":
            path = params.get("path", "")
            current_db = path
            send({"id": rid, "result": {"path": path}})

        elif method == "close_database":
            current_db = None
            send({"id": rid, "result": {"status": "closed"}})

        elif method == "save_database":
            send({"id": rid, "result": {"status": "saved"}})

        elif method in ("exec_python", "plugin:execute_python"):
            code = params.get("code", "")
            if not code:
                send({"id": rid, "error": {"code": -4, "message": "Missing required parameter: code"}})
            else:
                result = _exec_python(code)
                if result["error"] == "Task cancelled":
                    send({"id": rid, "error": {"code": -16, "message": "Task cancelled"}})
                else:
                    send({"id": rid, "result": result})

        elif method == "slow_command":
            delay = params.get("delay", 5)
            time.sleep(delay)
            send({"id": rid, "result": {"delayed": delay}})

        else:
            send({"id": rid, "result": {"echo": method, "params": params}})

    reader.close()
    writer.close()
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


if __name__ == "__main__":
    main()
