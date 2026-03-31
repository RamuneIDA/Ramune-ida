"""Worker-side handler for execute_python.

Runs arbitrary Python code in the IDA environment with
stdout/stderr capture and ``_result`` convention.

The ``timeout`` parameter is a **hard limit** enforced via
``signal.alarm`` (SIGALRM) on the main thread.  This keeps IDA API
calls working (they require the main thread) while still being able
to interrupt long-running code.  ``timeout=0`` means no limit — run
until completion or external cancel.

``ExecutionTimeout`` inherits from ``BaseException`` so a bare
``except Exception:`` in user code won't swallow it.

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

import io
import signal
import sys
import traceback
from typing import Any

from ramune_ida.core import ToolError

_IDA_MODULES = ("idaapi", "idc", "idautils")
_DEFAULT_TIMEOUT = 30


class ExecutionTimeout(BaseException):
    """Raised by SIGALRM when execution exceeds the hard timeout."""


def _on_alarm(_signum: int, _frame: object) -> None:
    raise ExecutionTimeout()


def _build_namespace() -> dict[str, Any]:
    """Pre-inject common IDA modules into the exec namespace."""
    ns: dict[str, Any] = {"__builtins__": __builtins__}
    for name in _IDA_MODULES:
        try:
            ns[name] = __import__(name)
        except ImportError:
            pass
    return ns


def execute_python(params: dict[str, Any]) -> dict[str, Any]:
    """Execute arbitrary IDAPython code."""
    code = params.get("code", "")
    if not code:
        raise ToolError(-4, "Missing required parameter: code")

    timeout = params.get("timeout", _DEFAULT_TIMEOUT)
    if timeout is not None:
        timeout = int(timeout) or 0  # normalise

    namespace = _build_namespace()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    error_msg = ""
    timed_out = False

    old_handler = signal.signal(signal.SIGALRM, _on_alarm)
    if timeout:
        signal.alarm(timeout)
    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        exec(code, namespace)
    except ExecutionTimeout:
        timed_out = True
    except Exception:
        error_msg = traceback.format_exc()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    if timed_out:
        error_msg = f"Execution timed out after {timeout}s"

    return {
        "output": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "result": namespace.get("_result") if not timed_out else None,
        "error": error_msg,
    }
