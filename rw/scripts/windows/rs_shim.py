"""rs-shim — minimal pymem RPC for the Ravensmith trainer.

Stays on the Windows side. Handles only the operations that *must* run on
Windows (pymem attach, ReadProcessMemory / WriteProcessMemory, region
enumeration). All higher-level logic lives in the WSL-side `rs` package.

Why a shim: keeping a multi-file Python package in sync between the WSL repo
and the Windows side is friction. The shim is small (~220 LOC) and stable, so
it gets copied once and rarely needs to change again. Day-to-day development
of `rs` (Click CLI, stat catalog, scan algorithms, output formatting) happens
in the repo, no Copy-Item churn.

Requires:
    pip install pymem
    Windows. Run as administrator (OpenProcess needs debug privileges).

Usage:
    py rs_shim.py [--host 0.0.0.0] [--port 8765]

The shim boots in an idle state — it listens immediately and does NOT attach
to a process until `rs` explicitly calls the `attach` method. This lets the
shim be started before the game and lets `rs` re-attach if the game restarts.

Protocol: line-delimited JSON over TCP. One request per line, one response
per line. Bytes are hex-encoded.

    request:  {"id": int, "method": str, "params": object}
    response: {"id": int, "result": ...}  OR  {"id": int, "error": str}

Methods:
    ping()                          -> {ok, attached, pid?, process_base?}
    attach(process="Ravenswatch.exe")
                                    -> {ok, pid, process_base}
    detach()                        -> {ok}

    (require prior attach:)
    modules()                       -> [{base, size, name}, ...]
    regions()                       -> [{base, size}, ...]   (committed writable only)
    read(addr, length)              -> hex string
    write(addr, data_hex)           -> {"written": int}
    find(needle_hex, alignment=1)   -> [addr, ...]   (server-side scan over regions)

Errors are returned as strings ("error" field). Server keeps running.

Single-threaded — handles one client at a time. The trainer use case has one
client; multi-client would queue serially.
"""

import argparse
import ctypes
import json
import socket
import sys
from ctypes import wintypes

import pymem

MEM_COMMIT = 0x1000
WRITABLE_MASK = 0x04 | 0x08 | 0x40 | 0x80  # RW, WC, ERW, EWC


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def enum_regions(handle):
    """Yield (base, size) for committed writable regions."""
    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    while address < 0x7FFFFFFFFFFF:
        rc = ctypes.windll.kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(address),
            ctypes.byref(mbi), ctypes.sizeof(mbi),
        )
        if rc == 0:
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if mbi.State == MEM_COMMIT and (mbi.Protect & WRITABLE_MASK):
            yield base, size
        address = base + size


class State:
    """Holds the (single) attached pymem instance, or None if idle."""
    pm = None


def require_attached(state):
    if state.pm is None:
        raise RuntimeError("not attached; call attach first")
    return state.pm


def m_ping(state, params):
    pm = state.pm
    return {
        "ok": True,
        "attached": pm is not None,
        "pid": pm.process_id if pm else None,
        "process_base": int(pm.process_base.lpBaseOfDll or 0) if pm else None,
    }


def m_attach(state, params):
    process = params.get("process", "Ravenswatch.exe")
    state.pm = pymem.Pymem(process)
    return {
        "ok": True,
        "pid": state.pm.process_id,
        "process_base": int(state.pm.process_base.lpBaseOfDll or 0),
        "process": process,
    }


def m_detach(state, params):
    state.pm = None
    return {"ok": True}


def m_modules(state, params):
    pm = require_attached(state)
    return [
        {
            "base": int(m.lpBaseOfDll or 0),
            "size": int(m.SizeOfImage),
            "name": m.name,
        }
        for m in pm.list_modules()
    ]


def m_regions(state, params):
    pm = require_attached(state)
    return [
        {"base": b, "size": s}
        for b, s in enum_regions(pm.process_handle)
    ]


def m_read(state, params):
    pm = require_attached(state)
    addr = int(params["addr"])
    length = int(params["length"])
    return pm.read_bytes(addr, length).hex()


def m_write(state, params):
    pm = require_attached(state)
    addr = int(params["addr"])
    data = bytes.fromhex(params["data_hex"])
    pm.write_bytes(addr, data, len(data))
    return {"written": len(data)}


def m_find(state, params):
    pm = require_attached(state)
    needle = bytes.fromhex(params["needle_hex"])
    alignment = int(params.get("alignment", 1))
    matches = []
    for base, size in enum_regions(pm.process_handle):
        try:
            data = pm.read_bytes(base, size)
        except Exception:
            continue
        i = 0
        while True:
            idx = data.find(needle, i)
            if idx == -1:
                break
            addr = base + idx
            if alignment <= 1 or (addr % alignment) == 0:
                matches.append(addr)
            i = idx + 1
    return matches


METHODS = {
    "ping": m_ping,
    "attach": m_attach,
    "detach": m_detach,
    "modules": m_modules,
    "regions": m_regions,
    "read": m_read,
    "write": m_write,
    "find": m_find,
}


def serve_client(conn, state):
    """Handle line-delimited JSON requests until the client disconnects."""
    f = conn.makefile("rwb")
    try:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            req = None
            try:
                req = json.loads(line)
                method = req["method"]
                fn = METHODS.get(method)
                if fn is None:
                    raise ValueError(f"unknown method: {method}")
                params = req.get("params") or {}
                resp = {"id": req.get("id"), "result": fn(state, params)}
            except Exception as e:
                rid = req.get("id") if isinstance(req, dict) else None
                resp = {"id": rid, "error": f"{type(e).__name__}: {e}"}
            f.write((json.dumps(resp) + "\n").encode())
            f.flush()
    finally:
        f.close()
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="0.0.0.0",
                   help="Bind address. Default 0.0.0.0 lets WSL connect via "
                        "the Windows host IP.")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    state = State()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(4)
    print(f"rs-shim: idle (no process attached); "
          f"listening on {args.host}:{args.port}", flush=True)

    try:
        while True:
            conn, peer = sock.accept()
            print(f"  client {peer[0]}:{peer[1]}", flush=True)
            try:
                serve_client(conn, state)
            except Exception as e:
                print(f"  client {peer[0]}:{peer[1]} error: {e}", flush=True)
            print(f"  client {peer[0]}:{peer[1]} disconnected", flush=True)
    except KeyboardInterrupt:
        print("\nrs-shim: shutting down")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
