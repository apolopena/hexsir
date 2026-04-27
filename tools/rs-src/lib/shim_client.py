"""TCP/JSON RPC client for rs-shim.

Two paths:

- :func:`call` — one connection per RPC. Open, send, recv, close. Right for
  one-shot CLI commands where setup overhead is negligible.
- :class:`Session` — context manager holding one socket open across many
  RPCs. Right for polling commands like ``rs watch``, where connection-per-
  call would multiply TCP handshake cost across hundreds of reads.

Bytes-in-payloads are hex-encoded both directions; addresses are JSON ints.
Raw socket / JSON / RPC errors are translated into the typed hierarchy in
:mod:`lib.errors` so command code can branch on category.
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

    payload = _build_request(method, params, request_id=1)

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

    return _parse_response(line)


class Session:
    """Persistent-connection client for high-frequency RPC sequences.

    Use as a context manager. One TCP connection is opened on ``__enter__``
    and closed on ``__exit__``; all calls in between share that socket.

    Example::

        with Session() as s:
            for _ in range(100):
                value = s.call("read", {"addr": addr, "length": 4})

    Raises the same typed exceptions as :func:`call`. If a transport-level
    error occurs mid-session the socket is closed; further calls will raise
    :class:`errors.ShimDisconnected` until the session is exited.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        connect_timeout: float = 3.0,
        read_timeout: float = 30.0,
    ) -> None:
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._sock: socket.socket | None = None
        self._next_id = 1

    def __enter__(self) -> "Session":
        resolved_host = config.shim_host(self._host)
        resolved_port = config.shim_port(self._port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout)
        try:
            sock.connect((resolved_host, resolved_port))
        except ConnectionRefusedError as e:
            sock.close()
            raise errors.ShimUnreachable(
                f"shim not reachable at {resolved_host}:{resolved_port} "
                f"(refused) — is rs_shim.py running on Windows?"
            ) from e
        except (socket.timeout, TimeoutError) as e:
            sock.close()
            raise errors.ShimTimeout(
                f"connect to {resolved_host}:{resolved_port} timed out"
            ) from e
        except OSError as e:
            sock.close()
            raise errors.ShimUnreachable(
                f"cannot reach {resolved_host}:{resolved_port}: {e}"
            ) from e
        sock.settimeout(self._read_timeout)
        self._sock = sock
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send an RPC over the open session socket and return the result."""
        if self._sock is None:
            raise errors.ShimError("Session not open (use as context manager)")
        payload = _build_request(method, params, request_id=self._next_id)
        self._next_id += 1
        try:
            self._sock.sendall(payload)
        except (BrokenPipeError, ConnectionResetError) as e:
            raise errors.ShimDisconnected(
                "shim closed the connection while sending"
            ) from e
        try:
            line = _read_line(self._sock)
        except (socket.timeout, TimeoutError) as e:
            raise errors.ShimTimeout("shim response timed out") from e
        except ConnectionResetError as e:
            raise errors.ShimDisconnected(
                "shim closed the connection while reading"
            ) from e
        return _parse_response(line)


def _build_request(method: str, params: dict | None, request_id: int) -> bytes:
    request: dict = {"id": request_id, "method": method}
    if params:
        request["params"] = params
    return (json.dumps(request) + "\n").encode()


def _parse_response(line: bytes) -> dict:
    if not line:
        raise errors.ShimProtocolError("shim closed the connection without responding")
    try:
        resp = json.loads(line)
    except json.JSONDecodeError as e:
        raise errors.ShimProtocolError(f"shim returned malformed JSON: {e.msg}") from e

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
