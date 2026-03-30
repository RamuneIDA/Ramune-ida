"""Core built-in tools — plugin-style metadata + handlers.

Each sub-package (analysis, execution, ...) provides:
  - ``metadata.py`` with a ``TOOLS`` list (tool name, description, params)
  - ``handlers.py`` with handler functions (name matches tool name)

Discovery is handled by :mod:`ramune_ida.worker.plugins`.

.. note:: Must stay compatible with Python 3.10 (runs in Worker).
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations


class ToolError(Exception):
    """Raised by tool handlers for structured error responses.

    *code* should be a negative integer matching
    :class:`~ramune_ida.protocol.ErrorCode` values.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
