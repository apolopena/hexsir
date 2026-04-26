# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.1.0] - 2026-04-26

**FEAT:** *initial-release*

Initial scaffolded tool — Ravensmith trainer CLI for live read/write of
Ravenswatch runtime stats. Talks to a Windows-side `rs_shim.py` over TCP/JSON
RPC; the shim owns the `pymem` attach.

**FEAT:** *attach / detach / status*

- `attach [--process NAME] [--verbose]` — attach the shim to a running game
  process. Quiet mode prints a single success line; verbose mode renders a
  four-step tree via `tree-lib` (resolve host → ping shim → attach RPC →
  verify state).
- `detach` — release the shim's attachment.
- `status` — report shim health and current attach state.

**FEAT:** *dev sync-shim*

- `dev sync-shim` — copy `rw/scripts/windows/rs_shim.py` from the repo to
  `$RS_SHIM_LOC` (default `/mnt/c/ravensmith/scripts/rs_shim.py`). Pure
  local file copy; prints a Windows-style restart hint using the
  WSL→Windows path conversion in `lib/paths.to_display_path`.

**FEAT:** *interactive REPL*

- `interactive` launches a `repl-lib` REPL with a state-aware prompt:
  `rs>` when idle, `rs:Ravenswatch.exe>` after attach. The `exit` built-in
  is overridden to auto-detach if currently attached.

**FEAT:** *config and error model*

- `lib/config.py` — env-var override chain (CLI flag > env var > default)
  for `RS_SHIM_HOST` (auto-detects WSL2 default gateway, then
  `/etc/resolv.conf` nameserver), `RS_SHIM_PORT` (8765), `RS_SHIM_LOC`.
- `lib/errors.py` — typed `ShimError` hierarchy (`ShimUnreachable`,
  `ShimTimeout`, `ShimDisconnected`, `ShimProtocolError`, `ShimRPCError`,
  `HostUnresolvable`).
- `lib/shim_client.py` — TCP/JSON RPC client; one connection per call;
  translates raw socket / JSON / RPC failures into typed exceptions.

**CHORE:** *bash wrapper*

- Documents the env vars and passes them through to the Python entry
  point. Defaults stay in `lib/config.py` to keep one source of truth.
