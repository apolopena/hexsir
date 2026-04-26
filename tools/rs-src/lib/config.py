"""Configuration resolution for rs.

Single source of truth for env vars and defaults consumed by every command.
Override chain (per setting): explicit CLI flag > env var > default.

Env vars (also documented in tools/rs):
    RS_SHIM_HOST  Windows host IP. If unset/empty, auto-detect via the
                  WSL2 default gateway, falling back to the
                  /etc/resolv.conf nameserver.
    RS_SHIM_PORT  Shim TCP port. Default: 8765.
    RS_SHIM_LOC   Path to deployed shim file (used by `rs dev sync-shim`).
                  Default: /mnt/c/ravensmith/scripts/rs_shim.py
"""

import os
import re
import subprocess

from .errors import HostUnresolvable

DEFAULT_PORT = 8765
DEFAULT_SHIM_LOC = "/mnt/c/ravensmith/scripts/rs_shim.py"


def shim_host(explicit: str | None = None) -> str:
    """Resolve the shim host. Override chain: explicit > env > auto-detect."""
    if explicit:
        return explicit
    env = os.environ.get("RS_SHIM_HOST", "").strip()
    if env:
        return env
    detected = _detect_gateway()
    if detected:
        return detected
    raise HostUnresolvable(
        "could not auto-detect Windows host IP — set RS_SHIM_HOST"
    )


def shim_port(explicit: int | None = None) -> int:
    """Resolve the shim port. Override chain: explicit > env > default."""
    if explicit is not None:
        return int(explicit)
    raw = os.environ.get("RS_SHIM_PORT", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_PORT


def shim_loc() -> str:
    """Resolve the deployed shim path. Env var > default."""
    raw = os.environ.get("RS_SHIM_LOC", "").strip()
    return raw or DEFAULT_SHIM_LOC


def _detect_gateway() -> str | None:
    """Best-effort detect of the Windows host IP from inside WSL.

    Tries `ip route show default` first (default gateway = Windows host on
    WSL2 NAT mode), then falls back to the first nameserver in
    /etc/resolv.conf. Returns None if neither yields a usable IP.
    """
    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"],
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        )
        m = re.search(r"via\s+(\S+)", out)
        if m:
            return m.group(1)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                m = re.match(r"^\s*nameserver\s+(\S+)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None
