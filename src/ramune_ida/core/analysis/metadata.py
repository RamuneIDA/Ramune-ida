"""Metadata for built-in analysis tools (decompile, disasm, …)."""

from __future__ import annotations

from ramune_ida.worker.tags import TAG_KIND_READ

TOOLS: list[dict] = [
    {
        "name": "decompile",
        "description": "Decompile a function.",
        "tags": ["analysis", TAG_KIND_READ],
        "params": {
            "func": {
                "type": "string",
                "required": True,
                "description": "Name or hex address",
            },
        },
    },
    {
        "name": "disasm",
        "description": "Disassemble from an address.",
        "tags": ["analysis", TAG_KIND_READ],
        "params": {
            "addr": {
                "type": "string",
                "required": True,
                "description": "Address or name",
            },
            "count": {
                "type": "integer",
                "required": False,
                "default": 20,
                "description": "Number of instructions",
            },
        },
    },
    {
        "name": "xrefs",
        "description": "List cross-references to a target.",
        "tags": ["analysis", TAG_KIND_READ],
        "params": {
            "addr": {
                "type": "string",
                "required": True,
                "description": "Address or name",
            },
        },
    },
    {
        "name": "survey",
        "description": "Binary overview: file identity, segments, entry/exports, function stats, import modules.",
        "tags": ["analysis", TAG_KIND_READ],
        "params": {},
    },
]
