# telemetry-warden

Block Ravenswatch's outbound telemetry calls and report each one to stdout. Standalone, stdlib-only Python. Two pieces:

- `warden.py` — local TCP listener. Binds `127.0.0.1` ports 80, 443, 8888. Accepts incoming connections, peeks the TLS SNI or HTTP `Host` header, prints a `BLOCKED` line to stdout, drops the connection. No bytes leave the machine. Nothing is written to disk.
- One-time **hosts file edit** that points the telemetry hostnames at `127.0.0.1` so the game's connections land on the listener.

## Hosts file

Add these lines once to `C:\Windows\System32\drivers\etc\hosts` (open Notepad **as administrator**):

```
# === BEGIN ravensmith telemetry-warden ===
127.0.0.1  dt-live.passtechgames.com
127.0.0.1  dt-live-2.passtechgames.com
127.0.0.1  dt-live-3.passtechgames.com
127.0.0.1  dt-dev.passtechgames.com
127.0.0.1  nacon-os.com
127.0.0.1  nacon-os-rec-54f75zaw5q-ew.a.run.app
127.0.0.1  nacon-os-rec-v2-54f75zaw5q-ew.a.run.app
127.0.0.1  submit.backtrace.io
# === END ravensmith telemetry-warden ===
```

Reverse: delete those eleven lines.

## Run

From a Windows administrator terminal (PowerShell or cmd; admin needed for ports < 1024):

```
python warden.py
```

Launch Ravenswatch. Every telemetry call gets intercepted, reported to the terminal, and dropped. Output looks like:

```
telemetry-warden — listening on 127.0.0.1:80,443,8888
stop with Ctrl+C

2026-05-07 14:32:01  BLOCKED  dt-live.passtechgames.com:443  (TLS)
2026-05-07 14:32:14  BLOCKED  nacon-os.com:443               (TLS)
2026-05-07 14:33:02  BLOCKED  dt-live-2.passtechgames.com:443  (TLS)
```

Stop with Ctrl+C. End-of-session summary prints a per-host count.

## Notes

- **Game-side behavior:** the game's WinHTTP request fails because the TCP connection closes before TLS completes. The game treats it as a network error. It may retry the same event a few times within a session — those retries also get reported and dropped, never leaving the machine.
- **What's reported:** timestamp, hostname (from SNI or `Host` header), port, kind (`TLS` or `HTTP`). No request bodies — we close before reading the encrypted payload. Nothing is persisted; if you want a record, redirect stdout to a file yourself (`python warden.py > my-session.log`).
- **Persistence:** stop the warden any time. Hosts entries stay in place — the game's calls then hit a dead socket and fail. To temporarily restore real DNS, comment out the lines (`#` prefix) or delete them.
- **WSL note:** this runs on **Windows**, not in WSL. The Windows hosts file resolves names against the Windows network stack; only a Windows-side process binding `127.0.0.1` will receive the game's traffic. Run `python warden.py` from a Windows terminal.
