"""Worker-side cancellation flag.

The Worker is single-threaded, so a plain boolean is sufficient.
SIGUSR1 handler calls ``request()``, and ``sys.setprofile`` hook
in ``dispatch`` checks ``is_requested()`` to raise at Python
bytecode boundaries.
"""

from __future__ import annotations

_cancel_requested = False


def request() -> None:
    """Mark the current command as cancel-requested (called from SIGUSR1 handler)."""
    global _cancel_requested
    _cancel_requested = True


def is_requested() -> bool:
    return _cancel_requested


def reset() -> None:
    """Clear the flag — called at dispatch entry and exit."""
    global _cancel_requested
    _cancel_requested = False
