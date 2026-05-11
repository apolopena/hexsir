#!/usr/bin/env python3
"""
telemetry-warden — block Ravenswatch telemetry calls and report each one to stdout.

Run from a Windows admin terminal (binds privileged ports 80/443):

    python warden.py

Stop with Ctrl+C. Stdlib only — no external deps. Nothing is written to disk.
"""

import datetime
import socket
import struct
import sys
import threading

PORTS = [80, 443, 8888]

_state_lock = threading.Lock()
_total = 0
_by_host: dict[str, int] = {}


def parse_sni(data: bytes) -> str | None:
    """Extract SNI hostname from a TLS ClientHello. None if unparseable."""
    try:
        if len(data) < 5 or data[0] != 0x16:
            return None
        i = 5 + 1 + 3 + 2 + 32  # record hdr + handshake hdr + version + random
        sid_len = data[i]
        i += 1 + sid_len
        cs_len = struct.unpack(">H", data[i:i + 2])[0]
        i += 2 + cs_len
        cm_len = data[i]
        i += 1 + cm_len
        ext_total = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        end = min(i + ext_total, len(data))
        while i + 4 <= end:
            ext_type, ext_len = struct.unpack(">HH", data[i:i + 4])
            i += 4
            if ext_type == 0:  # server_name
                name_len = struct.unpack(">H", data[i + 3:i + 5])[0]
                return data[i + 5:i + 5 + name_len].decode("ascii", errors="replace")
            i += ext_len
    except Exception:
        return None
    return None


def parse_http_host(data: bytes) -> str | None:
    """Extract the Host header from an HTTP request. None if unparseable."""
    try:
        head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1", errors="replace")
        for line in head.split("\r\n"):
            if line.lower().startswith("host:"):
                return line.split(":", 1)[1].strip().split(":")[0]
    except Exception:
        return None
    return None


def report_block(host: str, port: int, kind: str) -> None:
    global _total
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _state_lock:
        _total += 1
        _by_host[host] = _by_host.get(host, 0) + 1
        sys.stdout.write(f"{ts}  BLOCKED  {host}:{port}  ({kind})\n")
        sys.stdout.flush()


def handle(client: socket.socket, port: int) -> None:
    try:
        client.settimeout(2.0)
        try:
            data = client.recv(2048)
        except socket.timeout:
            data = b""
        host = None
        kind = "no-data"
        if data:
            if data[:1] == b"\x16":
                host = parse_sni(data)
                kind = "TLS"
            else:
                host = parse_http_host(data)
                kind = "HTTP"
        report_block(host or "<unknown>", port, kind)
    finally:
        try:
            client.close()
        except Exception:
            pass


def listener(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    except OSError as e:
        sys.stderr.write(f"[warden] cannot bind 127.0.0.1:{port}: {e}\n")
        sys.stderr.write("         (run elevated, or check that no other process owns this port)\n")
        return
    s.listen(64)
    while True:
        client, _ = s.accept()
        threading.Thread(target=handle, args=(client, port), daemon=True).start()


def main() -> None:
    print(f"telemetry-warden — listening on 127.0.0.1:{','.join(map(str, PORTS))}")
    print("stop with Ctrl+C\n")
    for p in PORTS:
        threading.Thread(target=listener, args=(p,), daemon=True).start()
    try:
        while True:
            threading.Event().wait(60)
    except KeyboardInterrupt:
        with _state_lock:
            print(f"\n\nsession blocked {_total} telemetry calls across {len(_by_host)} hosts:")
            for host, count in sorted(_by_host.items(), key=lambda x: -x[1]):
                print(f"  {count:>4d}  {host}")


if __name__ == "__main__":
    main()
