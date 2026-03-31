"""Worker-side handlers for listing tools.

Each function receives ``params: dict`` and returns ``dict``.
IDA modules are imported inside function bodies so the module
itself can be imported safely without IDA (e.g. during --list-plugins).

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

from typing import Any


def _paginate(
    items: list[dict[str, Any]],
    filter_str: str,
    match_key: str,
    offset: int,
    count: int,
) -> dict[str, Any]:
    """Apply substring filter + pagination, return wrapped result."""
    if filter_str:
        fl = filter_str.lower()
        items = [i for i in items if fl in str(i.get(match_key, "")).lower()]
    total = len(items)
    return {
        "total": total,
        "offset": offset,
        "count": count,
        "items": items[offset : offset + count],
    }


def _extract_pagination(params: dict[str, Any]) -> tuple[str, int, int]:
    """Extract common filter/offset/count from params."""
    filter_str = params.get("filter") or ""
    offset = params.get("offset", 0) or 0
    count = params.get("count", 100) or 100
    return filter_str, int(offset), int(count)


def list_funcs(params: dict[str, Any]) -> dict[str, Any]:
    """List functions with addr, name, size."""
    import idaapi
    import idautils
    import idc

    filter_str, offset, count = _extract_pagination(params)

    items: list[dict[str, Any]] = []
    for ea in idautils.Functions():
        name = idc.get_name(ea, 0) or ""
        func = idaapi.get_func(ea)
        size = (func.end_ea - func.start_ea) if func else 0
        items.append({"addr": hex(ea), "name": name, "size": size})

    return _paginate(items, filter_str, "name", offset, count)


def list_strings(params: dict[str, Any]) -> dict[str, Any]:
    """List strings found in the binary."""
    import idautils

    filter_str, offset, count = _extract_pagination(params)

    items: list[dict[str, Any]] = []
    for s in idautils.Strings():
        value = str(s)
        items.append({"addr": hex(s.ea), "value": value, "length": s.length})

    return _paginate(items, filter_str, "value", offset, count)


def list_imports(params: dict[str, Any]) -> dict[str, Any]:
    """List imported functions (flat, with module field)."""
    import ida_nalt

    filter_str, offset, count = _extract_pagination(params)

    items: list[dict[str, Any]] = []
    for i in range(ida_nalt.get_import_module_qty()):
        mod_name = ida_nalt.get_import_module_name(i) or ""
        collected: list[dict[str, Any]] = []

        def _cb(
            ea: int,
            name: str | None,
            ordinal: int,
            _out: list = collected,
            _mod: str = mod_name,
        ) -> bool:
            _out.append({
                "module": _mod,
                "name": name or ("ord#%d" % ordinal),
                "addr": hex(ea),
            })
            return True

        ida_nalt.enum_import_names(i, _cb)
        items.extend(collected)

    return _paginate(items, filter_str, "name", offset, count)


def list_names(params: dict[str, Any]) -> dict[str, Any]:
    """List all named addresses."""
    import idautils

    filter_str, offset, count = _extract_pagination(params)

    items: list[dict[str, Any]] = []
    for ea, name in idautils.Names():
        items.append({"addr": hex(ea), "name": name})

    return _paginate(items, filter_str, "name", offset, count)
