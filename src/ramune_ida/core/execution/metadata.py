"""Metadata for built-in execution tools (execute_python, …)."""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "execute_python",
        "description": "Execute IDAPython code in the IDA environment.",
        "tags": ["execution"],
        "params": {
            "code": {
                "type": "string",
                "required": True,
                "description": "IDAPython code. Assign _result for structured return",
            },
        },
        "timeout": 60,
    },
]
