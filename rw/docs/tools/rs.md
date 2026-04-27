[← Back to tools](README.md)

# rs / rs-shim

Live trainer for Ravenswatch. Two-piece architecture: a tiny shim on Windows
that owns the pymem attach, and a Click CLI on the WSL side that holds all
the smart code.

```
   Windows                        WSL (repo)
┌─────────────────┐         ┌────────────────────────┐
│  rs-shim.py     │  TCP    │  rs CLI (Click)        │
│  ~250 LOC       │ ◄─────► │  rs.core (lib)         │
│  pymem only     │  JSON   │  scan / pin / output   │
└────────┬────────┘         └────────────────────────┘
         │
         ▼
   Ravenswatch.exe
```

The shim is `rw/scripts/windows/rs_shim.py`. The `rs` CLI lives at
`tools/rs-src/` (when scaffolded).

## Dependencies

### Windows (rs-shim)

- Python 3.10+ (3.12 recommended)
- `pymem` (PyPI): `py -m pip install pymem`
- Run as administrator (OpenProcess on a foreign process needs debug
  privileges)

### WSL (rs CLI + smoke tests)

- Python 3.12+ (already installed in most setups)
- `openbsd-netcat` (only for the manual smoke-test — not required for `rs`
  itself; `rs` uses Python sockets directly)

#### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y netcat-openbsd
```

Note: on Debian/Ubuntu the package is `netcat-openbsd`. The binary it
provides is `nc`.

#### Void Linux

```bash
sudo xbps-install -S openbsd-netcat
```

Note: on Void the package name is **`openbsd-netcat`** (different word order
from Debian).

#### Why openbsd-netcat specifically

The OpenBSD variant is actively maintained, supports IPv6, supports the `-q1`
flag we use in smoke-test recipes, and is the de-facto default on most modern
distros. Avoid GNU netcat (essentially abandoned) and `nmap-ncat` (heavier,
extra features we don't need).

## Smoke-test recipe

After copying the shim to Windows and starting it, verify the wire
end-to-end. Steps assume the shim is running on its default port.

1. **Start the shim** (Windows admin PowerShell):

   ```powershell
   Copy-Item \\wsl.localhost\Void\home\ks73\repos\work\ravensmith\rw\scripts\windows\rs_shim.py C:\ravensmith\scripts\rs_shim.py -Force
   py C:\ravensmith\scripts\rs_shim.py
   ```

   Expected output:
   ```
   rs-shim: idle (no process attached); listening on 0.0.0.0:8765
   ```

2. **Discover the Windows host IP** (WSL):

   ```bash
   WIN_IP=$(ip route show default | awk '{print $3}')
   echo "Windows host: $WIN_IP"
   ```

   If `ip route` returns no default route, fall back:
   ```bash
   WIN_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
   ```

3. **Ping the shim** (game does not need to be running):

   ```bash
   echo '{"id":1,"method":"ping"}' | nc -q1 $WIN_IP 8765
   ```

   Expected: `{"id":1,"result":{"ok":true,"attached":false,"pid":null,"process_base":null}}`

4. **Start Ravenswatch, then attach**:

   ```bash
   echo '{"id":2,"method":"attach"}' | nc -q1 $WIN_IP 8765
   ```

   Expected: `{"id":2,"result":{"ok":true,"pid":...,"process_base":...,"process":"Ravenswatch.exe"}}`

5. **Confirm attached state**:

   ```bash
   echo '{"id":3,"method":"ping"}' | nc -q1 $WIN_IP 8765
   ```

   Expected: `attached: true` plus process info.

6. **Sanity test a real call** (`modules` lists every loaded module):

   ```bash
   echo '{"id":4,"method":"modules"}' | nc -q1 $WIN_IP 8765
   ```

   Expected: long JSON list with `Ravenswatch.exe` near the start.

If all six round-trip cleanly the shim is good and the wire is good. The
Click CLI on the WSL side then drives this same protocol with no further
shim changes.

## Method reference

See the docstring at the top of `rw/scripts/windows/rs_shim.py` for the full
RPC method list. As of this writing:

| Method | Requires attach? | Returns |
|--------|------------------|---------|
| `ping` | no | `{ok, attached, pid?, process_base?}` |
| `attach(process="Ravenswatch.exe")` | no | `{ok, pid, process_base, process}` |
| `detach()` | no | `{ok}` |
| `modules()` | yes | list of `{base, size, name}` |
| `regions()` | yes | list of `{base, size}` (committed writable only) |
| `read(addr, length)` | yes | hex string |
| `write(addr, data_hex)` | yes | `{written: int}` |
| `find(needle_hex, alignment=1)` | yes | list of `addr` |

## Shim stdout logging

Per-RPC logging is **on by default**. Each successfully-handled request
produces one stdout line on the shim's PowerShell window:

```
    -> read(addr=0x27cdcfe8668, length=4) -> 8 chars
    -> attach(process=Ravenswatch.exe) -> {ok=True, pid=22768, ...}
    -> write(addr=0x27cdcfe8668, data_hex=06000000) -> {written=4}
    -> read(addr=0x100, length=4) ✗ NotAttached: not attached; call attach first
```

Long hex payloads (`data_hex`, `needle_hex`) are truncated; addresses are
rendered as hex; lists and strings show their size. The connect / disconnect
lines (`client 1.2.3.4:54321` / `disconnected`) print regardless.

Pass ``--quiet`` to suppress the per-RPC lines:

```powershell
py C:\ravensmith\scripts\rs_shim.py --quiet
```

Connect / disconnect lines still print so you can see traffic activity.

## Persistent connections (rs watch)

The Click CLI's ``rs watch`` command opens **one TCP connection** for the
duration of its polling window and multiplexes all reads over it. This
avoids paying the connection-handshake cost on every poll. The shim
already supports this — its ``serve_client`` loops on the connection until
the client disconnects — so no shim change is required.

One-shot commands (``rs read``, ``rs write``, ``rs find``, ``rs status``,
``rs attach``, ``rs detach``) still use the simpler one-connection-per-call
path via ``shim_client.call()``. Use ``shim_client.Session`` from Python
when you need persistent connections in your own scripts.
