"""Worker-side handlers for search tools.

Each function receives ``params: dict`` and returns ``dict``.
IDA modules are imported inside function bodies so the module
itself can be imported safely without IDA (e.g. during --list-plugins).

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

import re
from typing import Any

from ramune_ida.core import ToolError

_SEARCH_SOURCES = ("strings", "names", "types", "disasm")


def search(params: dict[str, Any]) -> dict[str, Any]:
    """Regex search across text sources."""
    pattern = params.get("pattern", "")
    if not pattern:
        raise ToolError(-4, "Missing required parameter: pattern")
    scope = params.get("type") or "all"
    count = int(params.get("count", 100) or 100)

    if scope == "all":
        sources = _SEARCH_SOURCES
    elif scope in _SEARCH_SOURCES:
        sources = (scope,)
    else:
        raise ToolError(
            -4, "Invalid type: %s (must be all, strings, names, types, disasm)" % scope
        )

    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ToolError(-4, "Invalid regex: %s" % exc)
    matches: list[dict[str, Any]] = []

    for src in sources:
        if len(matches) >= count:
            break
        remaining = count - len(matches)
        if src == "strings":
            matches.extend(_search_strings(rx, remaining))
        elif src == "names":
            matches.extend(_search_names(rx, remaining))
        elif src == "types":
            matches.extend(_search_types(rx, remaining))
        elif src == "disasm":
            matches.extend(_search_disasm(rx, remaining))

    return {"total": len(matches), "matches": matches[:count]}


def _search_strings(rx: re.Pattern, limit: int) -> list[dict[str, Any]]:
    import idautils

    results: list[dict[str, Any]] = []
    for s in idautils.Strings():
        value = str(s)
        if rx.search(value):
            results.append({"addr": hex(s.ea), "value": value, "source": "string"})
            if len(results) >= limit:
                break
    return results


def _search_names(rx: re.Pattern, limit: int) -> list[dict[str, Any]]:
    import idautils

    results: list[dict[str, Any]] = []
    for ea, name in idautils.Names():
        if rx.search(name):
            results.append({"addr": hex(ea), "value": name, "source": "name"})
            if len(results) >= limit:
                break
    return results


def _search_types(rx: re.Pattern, limit: int) -> list[dict[str, Any]]:
    import ida_typeinf

    til = ida_typeinf.get_idati()
    qty = ida_typeinf.get_ordinal_count(til)
    results: list[dict[str, Any]] = []
    for ordinal in range(1, qty + 1):
        name = ida_typeinf.get_numbered_type_name(til, ordinal)
        if name and rx.search(name):
            results.append({"value": name, "source": "type"})
            if len(results) >= limit:
                break
    return results


def _search_disasm(rx: re.Pattern, limit: int) -> list[dict[str, Any]]:
    import idc
    import idautils

    results: list[dict[str, Any]] = []
    for seg_ea in idautils.Segments():
        if idc.get_segm_attr(seg_ea, idc.SEGATTR_TYPE) != idc.SEG_CODE:
            continue
        seg_end = idc.get_segm_attr(seg_ea, idc.SEGATTR_END)
        ea = seg_ea
        while ea < seg_end and ea != idc.BADADDR:
            text = idc.GetDisasm(ea)
            if text and rx.search(text):
                results.append({"addr": hex(ea), "value": text, "source": "disasm"})
                if len(results) >= limit:
                    return results
            ea = idc.next_head(ea, seg_end)
    return results


def search_bytes(params: dict[str, Any]) -> dict[str, Any]:
    """Binary byte pattern search with hex and ?? wildcards."""
    import ida_bytes
    import ida_ida
    import idaapi

    pattern = params.get("pattern", "")
    if not pattern:
        raise ToolError(-4, "Missing required parameter: pattern")
    count = int(params.get("count", 100) or 100)

    start = ida_ida.inf_get_min_ea()
    end_ea = ida_ida.inf_get_max_ea()

    bv = ida_bytes.compiled_binpat_vec_t()
    err = ida_bytes.parse_binpat_str(bv, start, pattern, 16)
    if err:
        raise ToolError(-4, "Invalid byte pattern: %s" % err)

    matches: list[dict[str, str]] = []
    raw = ida_bytes.bin_search(start, end_ea, bv, ida_bytes.BIN_SEARCH_FORWARD)
    addr = raw[0] if isinstance(raw, tuple) else raw
    while addr != idaapi.BADADDR and len(matches) < count:
        matches.append({"addr": hex(addr)})
        raw = ida_bytes.bin_search(
            addr + 1, end_ea, bv, ida_bytes.BIN_SEARCH_FORWARD
        )
        addr = raw[0] if isinstance(raw, tuple) else raw

    return {"total": len(matches), "matches": matches}
