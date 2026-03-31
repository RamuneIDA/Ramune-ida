"""Explore: safe eamap iteration + line→EA map."""
from __future__ import annotations
import os, shutil, socket, subprocess, sys, tempfile
import orjson

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
IDA_DIR = os.environ.get("IDADIR", "/home/explorer/ida-pro-9.3")
IDA_PYTHON_PATH = os.path.join(IDA_DIR, "idalib", "python")
BINARY_SRC = os.path.join(os.path.dirname(__file__), "binary", "ch01")
from ramune_ida.worker.socket_io import ENV_SOCK_FD

tmpdir = tempfile.mkdtemp()
binary = shutil.copy2(BINARY_SRC, os.path.join(tmpdir, "ch01"))

def make_worker():
    p, c = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    env = os.environ.copy()
    env[ENV_SOCK_FD] = str(c.fileno())
    env["IDADIR"] = IDA_DIR
    env["PYTHONPATH"] = IDA_PYTHON_PATH + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "ramune_ida.worker.main"],
                            env=env, pass_fds=(c.fileno(),))
    c.close()
    r, w = p.makefile("rb"), p.makefile("wb")
    orjson.loads(r.readline())
    return proc, r, w

def send(r, w, msg):
    w.write(orjson.dumps(msg) + b"\n"); w.flush()
    return orjson.loads(r.readline())

proc, r, w = make_worker()
send(r, w, {"id": "1", "method": "open_database", "params": {"path": binary}})

# ── 1. Safe eamap iteration + line map ─────────────────────────────
print("=== Safe line→EA map ===")
resp = send(r, w, {"id": "10", "method": "plugin:execute_python", "params": {"code": """
import ida_hexrays
import ida_lines
import idc

BADADDR = 0xFFFFFFFFFFFFFFFF
main_ea = idc.get_name_ea_simple("main")

cfunc = ida_hexrays.decompile(main_ea)
cfunc.user_cmts = ida_hexrays.user_cmts_new()
cfunc.save_user_cmts()

cfunc = ida_hexrays.decompile(main_ea)
eamap = cfunc.get_eamap()
pseudocode = cfunc.get_pseudocode()
treeitems = cfunc.treeitems

# Build item_ea → line safely
item_ea_to_line = {}
for idx in range(treeitems.size()):
    item = treeitems[idx]
    try:
        ea = item.ea
        if ea == BADADDR:
            continue
        coords = cfunc.find_item_coords(item)
        if coords:
            if ea not in item_ea_to_line:
                item_ea_to_line[ea] = coords[0]
    except (ValueError, RuntimeError):
        continue

# Safely iterate eamap
asm_ea_to_nearest = {}
for asm_ea in eamap:
    try:
        items = eamap[asm_ea]
        if items.size() == 0:
            continue
        nearest_ea = items[0].ea
        asm_ea_to_nearest[asm_ea] = nearest_ea
    except (ValueError, RuntimeError):
        continue

print(f"eamap entries processed: {len(asm_ea_to_nearest)}")
print(f"item_ea_to_line entries: {len(item_ea_to_line)}")

# Build line → nearest EA
line_to_nearest = {}
line_to_asm_ea = {}
for asm_ea, nearest_ea in asm_ea_to_nearest.items():
    ln = item_ea_to_line.get(nearest_ea) or item_ea_to_line.get(asm_ea)
    if ln is not None and ln not in line_to_nearest:
        line_to_nearest[ln] = nearest_ea
        line_to_asm_ea[ln] = asm_ea

print(f"Lines with mapping: {len(line_to_nearest)} / {pseudocode.size()}")
print()

# Show lines 46-130
for i in range(46, min(135, pseudocode.size())):
    clean = ida_lines.tag_remove(pseudocode[i].line)
    if i in line_to_nearest:
        near = hex(line_to_nearest[i])
    else:
        near = "---"
    print(f"  {i:3d} [{near:>10s}]: {clean[:65]}")
"""}})
print(resp.get("result", resp.get("error")))

# ── 2. Verify positions ──────────────────────────────────────────
print("\n=== Verify: set comment by line → check position ===")
resp = send(r, w, {"id": "20", "method": "plugin:execute_python", "params": {"code": """
import ida_hexrays
import ida_lines
import idc

BADADDR = 0xFFFFFFFFFFFFFFFF
main_ea = idc.get_name_ea_simple("main")

def build_line_map(cfunc):
    eamap = cfunc.get_eamap()
    treeitems = cfunc.treeitems
    
    item_ea_to_line = {}
    for idx in range(treeitems.size()):
        item = treeitems[idx]
        try:
            ea = item.ea
            if ea == BADADDR:
                continue
            coords = cfunc.find_item_coords(item)
            if coords and ea not in item_ea_to_line:
                item_ea_to_line[ea] = coords[0]
        except (ValueError, RuntimeError):
            continue
    
    asm_to_nearest = {}
    for asm_ea in eamap:
        try:
            items = eamap[asm_ea]
            if items.size() > 0:
                asm_to_nearest[asm_ea] = items[0].ea
        except (ValueError, RuntimeError):
            continue
    
    line_to_nearest = {}
    for asm_ea, nearest_ea in asm_to_nearest.items():
        ln = item_ea_to_line.get(nearest_ea) or item_ea_to_line.get(asm_ea)
        if ln is not None and ln not in line_to_nearest:
            line_to_nearest[ln] = nearest_ea
    
    return line_to_nearest

# Set comments at target lines
test_lines = [47, 55, 68, 80, 95, 100, 107, 110, 120, 130, 135]

for target_ln in test_lines:
    cfunc = ida_hexrays.decompile(main_ea)
    cfunc.user_cmts = ida_hexrays.user_cmts_new()
    cfunc.save_user_cmts()
    
    cfunc = ida_hexrays.decompile(main_ea)
    lm = build_line_map(cfunc)
    
    if target_ln not in lm:
        print(f"  Line {target_ln}: NO MAPPING")
        continue
    
    nearest = lm[target_ln]
    tl = ida_hexrays.treeloc_t()
    tl.ea = nearest
    tl.itp = ida_hexrays.ITP_SEMI
    cfunc.set_user_cmt(tl, f"TGT_{target_ln}")
    cfunc.save_user_cmts()
    
    cfunc2 = ida_hexrays.decompile(main_ea)
    text = str(cfunc2)
    found_line = None
    for i, line in enumerate(text.split("\\n")):
        if f"TGT_{target_ln}" in line:
            found_line = i
            break
    
    if found_line is not None:
        drift = found_line - target_ln
        status = "OK" if drift == 0 else f"DRIFT={drift:+d}"
    else:
        status = "ORPHAN"
    print(f"  Line {target_ln} -> {hex(nearest)}: found@{found_line} {status}")

# Final cleanup
cfunc = ida_hexrays.decompile(main_ea)
cfunc.user_cmts = ida_hexrays.user_cmts_new()
cfunc.save_user_cmts()
"""}})
print(resp.get("result", resp.get("error")))

# ── 3. Full get+set lifecycle with line numbers ──────────────────
print("\n=== Full lifecycle: set/get/delete by line ===")
resp = send(r, w, {"id": "30", "method": "plugin:execute_python", "params": {"code": """
import ida_hexrays
import ida_lines
import idc

BADADDR = 0xFFFFFFFFFFFFFFFF
main_ea = idc.get_name_ea_simple("main")

def build_line_map(cfunc):
    eamap = cfunc.get_eamap()
    treeitems = cfunc.treeitems
    item_ea_to_line = {}
    for idx in range(treeitems.size()):
        item = treeitems[idx]
        try:
            ea = item.ea
            if ea == BADADDR:
                continue
            coords = cfunc.find_item_coords(item)
            if coords and ea not in item_ea_to_line:
                item_ea_to_line[ea] = coords[0]
        except (ValueError, RuntimeError):
            continue
    
    asm_to_nearest = {}
    for asm_ea in eamap:
        try:
            items = eamap[asm_ea]
            if items.size() > 0:
                asm_to_nearest[asm_ea] = items[0].ea
        except (ValueError, RuntimeError):
            continue
    
    line_to_nearest = {}
    for asm_ea, nearest_ea in asm_to_nearest.items():
        ln = item_ea_to_line.get(nearest_ea) or item_ea_to_line.get(asm_ea)
        if ln is not None and ln not in line_to_nearest:
            line_to_nearest[ln] = nearest_ea
    return line_to_nearest

# Clean
cfunc = ida_hexrays.decompile(main_ea)
cfunc.user_cmts = ida_hexrays.user_cmts_new()
cfunc.save_user_cmts()

# SET at line 100
cfunc = ida_hexrays.decompile(main_ea)
lm = build_line_map(cfunc)
nearest = lm.get(100)
print(f"Line 100 nearest EA: {hex(nearest) if nearest else 'None'}")

if nearest:
    tl = ida_hexrays.treeloc_t()
    tl.ea = nearest
    tl.itp = ida_hexrays.ITP_SEMI
    cfunc.set_user_cmt(tl, "Hello from line 100!")
    cfunc.save_user_cmts()
    
    # GET: read back
    cfunc2 = ida_hexrays.decompile(main_ea)
    lm2 = build_line_map(cfunc2)
    nearest2 = lm2.get(100)
    tl2 = ida_hexrays.treeloc_t()
    tl2.ea = nearest2
    tl2.itp = ida_hexrays.ITP_SEMI
    cmt = cfunc2.get_user_cmt(tl2, ida_hexrays.RETRIEVE_ALWAYS)
    print(f"GET line 100: {cmt!r}")
    
    # Verify in decompile output
    text = str(cfunc2)
    for i, line in enumerate(text.split("\\n")):
        if "Hello from line 100" in line:
            print(f"Visible at str() line {i}: {line.strip()[:80]}")
            break
    
    # DELETE
    cfunc3 = ida_hexrays.decompile(main_ea)
    tl3 = ida_hexrays.treeloc_t()
    tl3.ea = nearest
    tl3.itp = ida_hexrays.ITP_SEMI
    cfunc3.set_user_cmt(tl3, "")
    cfunc3.save_user_cmts()
    
    cfunc4 = ida_hexrays.decompile(main_ea)
    cmt2 = cfunc4.get_user_cmt(tl3, ida_hexrays.RETRIEVE_ALWAYS)
    print(f"After DELETE: {cmt2!r}")
"""}})
print(resp.get("result", resp.get("error")))

send(r, w, {"id": "99", "method": "close_database", "params": {}})
proc.terminate()
shutil.rmtree(tmpdir, ignore_errors=True)
print("\nDone.")
