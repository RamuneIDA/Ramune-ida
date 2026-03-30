"""Handler for execute_python — run arbitrary IDAPython code."""

from __future__ import annotations

import io
import sys
import traceback
from typing import Any

from ramune_ida.commands import ExecPython
from ramune_ida.protocol import ErrorCode, Method
from ramune_ida.worker.dispatch import handler, HandlerError

_IDA_MODULES = ("idaapi", "idc", "idautils")


def _build_namespace() -> dict[str, Any]:
    """Pre-inject common IDA modules into the exec namespace."""
    ns: dict[str, Any] = {"__builtins__": __builtins__}
    for name in _IDA_MODULES:
        try:
            ns[name] = __import__(name)
        except ImportError:
            pass
    return ns


@handler(Method.EXEC_PYTHON)
def handle_exec_python(cmd: ExecPython) -> dict[str, Any]:
    if not cmd.code:
        raise HandlerError(ErrorCode.INVALID_PARAMS, "Missing required parameter: code")

    namespace = _build_namespace()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    error_msg = ""
    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        exec(cmd.code, namespace)
    except Exception:
        error_msg = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "output": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "result": namespace.get("_result"),
        "error": error_msg,
    }
