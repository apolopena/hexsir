"""TCP/JSON RPC client for rs-shim.

One connection per call (open, send line-delimited JSON, read response,
close). Bytes-in-payloads are hex-encoded both directions; addresses are
JSON ints. Raw socket / JSON / RPC errors are translated into the typed
hierarchy in lib.errors so command code can branch on category.
"""

import json
import re
import socket

from . import config, errors


def call(
    method: str,
    params: dict | None = None,
    host: str | None = None,
    port: int | None = None,
    connect_timeout: float = 3.0,
    read_timeout: float = 30.0,
) -> dict:
    """Send a single RPC and return the parsed `result` field.

    Raises:
        errors.ShimUnreachable      - shim not listening (connection refused)
        errors.ShimTimeout          - connect or read timed out
        errors.ShimDisconnected     - peer closed mid-request
        errors.ShimProtocolError    - malformed or empty response
        errors.ShimRPCError         - shim returned `{"error": "..."}` (kind set
                                      from leading exception name when present)
        errors.HostUnresolvable     - host auto-detect failed (only when host
                                      is left to default)
    """
    resolved_host = config.shim_host(host)
    resolved_port = config.shim_port(port)

    request = {"id": 1, "method": method}
    if params:
        request["params"] = params
    payload = (json.dumps(request) + "\n").encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        try:
            sock.connect((resolved_host, resolved_port))
        except ConnectionRefusedError as e:
            raise errors.ShimUnreachable(
                f"shim not reachable at {resolved_host}:{resolved_port} "
                f"(refused) — is rs_shim.py running on Windows?"
            ) from e
        except (socket.timeout, TimeoutError) as e:
            raise errors.ShimTimeout(
                f"connect to {resolved_host}:{resolved_port} timed out"
            ) from e
        except OSError as e:
            raise errors.ShimUnreachable(
                f"cannot reach {resolved_host}:{resolved_port}: {e}"
            ) from e

        sock.settimeout(read_timeout)
        try:
            sock.sendall(payload)
        except (BrokenPipeError, ConnectionResetError) as e:
            raise errors.ShimDisconnected(
                "shim closed the connection while sending"
            ) from e

        try:
            line = _read_line(sock)
        except (socket.timeout, TimeoutError) as e:
            raise errors.ShimTimeout("shim response timed out") from e
        except ConnectionResetError as e:
            raise errors.ShimDisconnected(
                "shim closed the connection while reading"
            ) from e
    finally:
        try:
            sock.close()
        except OSError:
            pass

    if not line:
        raise errors.ShimProtocolError(
            "shim closed the connection without responding"
        )
    try:
        resp = json.loads(line)
    except json.JSONDecodeError as e:
        raise errors.ShimProtocolError(
            f"shim returned malformed JSON: {e.msg}"
        ) from e

    if "error" in resp:
        raw = resp["error"]
        kind = None
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", raw)
        if m:
            kind = m.group(1)
            message = m.group(2)
        else:
            message = raw
        raise errors.ShimRPCError(message, kind=kind)

    if "result" not in resp:
        raise errors.ShimProtocolError(
            f"shim response missing both 'result' and 'error': {resp!r}"
        )
    return resp["result"]


def _read_line(sock: socket.socket, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    """Read one newline-terminated line from sock, up to max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    data = b"".join(chunks)
    nl = data.find(b"\n")
    if nl == -1:
        return data.strip()
    return data[:nl].strip()
