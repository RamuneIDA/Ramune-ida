"""Metadata for built-in analysis tools (decompile, disasm, …)."""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "decompile",
        "description": "Decompile a function.",
        "tags": ["analysis"],
        "params": {
            "func": {
                "type": "string",
                "required": True,
                "description": "Function name or hex address",
            },
        },
        "timeout": 30,
    },
    {
        "name": "disasm",
        "description": "Disassemble instructions starting at an address.",
        "tags": ["analysis"],
        "params": {
            "addr": {
                "type": "string",
                "required": True,
                "description": "Address or function name",
            },
            "count": {
                "type": "integer",
                "required": False,
                "default": 20,
                "description": "Number of instructions",
            },
        },
        "timeout": 30,
    },
]
