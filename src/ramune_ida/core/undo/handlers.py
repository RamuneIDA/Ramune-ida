"""Worker-side handlers for undo tool.

Each function receives ``params: dict`` and returns ``dict``.
IDA modules are imported inside function bodies so the module
itself can be imported safely without IDA (e.g. during --list-plugins).

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

from typing import Any


def undo(params: dict[str, Any]) -> dict[str, Any]:
    """Undo recent modifications."""
    import idaapi

    count = int(params.get("count", 1) or 1)
    undone: list[str] = []
    for _ in range(count):
        label = idaapi.get_undo_action_label()
        if not label:
            break
        if not idaapi.perform_undo():
            break
        undone.append(label)

    return {"undone": len(undone), "labels": undone}
