"""Worker process — runs inside IDA's bundled Python.

Compatibility: Python >= 3.10
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The worker process is spawned with whatever Python ships with IDA Pro
(``--worker-python``).  To keep the lower bound at 3.10:

* Every file MUST start with ``from __future__ import annotations``.
* No ``match``/``case`` statements.
* No ``except*`` / ``ExceptionGroup`` (3.11+).
* No ``type`` alias statements (3.12+).
* All third-party deps must support 3.10+.

These constraints also apply to shared modules imported by the worker:
``protocol.py`` and ``commands.py``.
"""
