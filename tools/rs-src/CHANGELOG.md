# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.2.0] - 2026-04-26

**FEAT:** *read / write / find / watch primitives*

- `read <addr> [--length N] [--as TYPE]` — read a typed value. Types: `hex` (default), `int32`, `uint32`, `int64`, `uint64`, `float32`, `float64`, `bool`. Length defaults to the type's natural size (4 for hex). `ADDR` accepts `0x...` hex or decimal.
- `write <addr> <value> [--as TYPE]` — write a typed value. No confirmation prompt; verify with `read` first. Same type set as `read`.
- `find <hex> [--alignment N] [--limit N] [--all] [--out FILE]` — pass-through to the shim's heap scan. Default summary prints count + first 20 matches inline; `--all` prints everything; `--out FILE` dumps the full address list to a file.
- `watch <addr> [--length N] [--as TYPE] [--interval S] [--duration S] [--all]` — poll a memory address over a single persistent TCP connection. Default prints baseline + on-change rows only; `--all` prints every tick.

All four commands follow the existing rs convention: default single-line output, `--verbose`/`-v` for the `tree-lib` step-by-step tree.

**FEAT:** *persistent shim connections*

- `lib/shim_client.Session` — context manager that holds one TCP socket open across many RPCs. Used by `rs watch`; available for any caller that needs polling without paying the connection-handshake cost per call. `lib/shim_client.call` (one-shot, connection-per-call) is unchanged for one-shot CLI commands.

**FEAT:** *typed value codec*

- `lib/value_codec` — single source of truth for the `read`/`write`/`watch` type table (sizes, struct formats, encode/decode, address parsing). Little-endian throughout (matches x86_64 and OEngine on-disk format).

**FEAT:** *shim per-RPC stdout logging*

- `rw/scripts/windows/rs_shim.py` now prints one stdout line per request — method, param summary (long hex truncated, addresses rendered as hex), and result summary. On by default; pass `--quiet` to suppress.

---

## [0.1.0] - 2026-04-26

**FEAT:** *initial-release*

Ravensmith trainer CLI. Talks to a Windows-side `rs_shim.py` over TCP/JSON RPC; the shim owns the `pymem` attach.

**FEAT:** *attach / detach / status*

- `attach [--process NAME] [--verbose]` — attach the shim to a running game process. Verbose mode renders a four-step `tree-lib` tree (resolve host → ping → attach → verify).
- `detach` — release the shim's attachment.
- `status` — report shim health and current attach state.

**FEAT:** *dev sync-shim*

- `dev sync-shim` — copy `rw/scripts/windows/rs_shim.py` to `$RS_SHIM_LOC` (default `/mnt/c/ravensmith/scripts/rs_shim.py`). Prints a Windows-style restart hint via `lib/paths.to_display_path`.

**FEAT:** *interactive REPL*

- `interactive` launches a `repl-lib` REPL. Prompt is state-aware: `rs>` idle, `rs:<process>>` attached. `exit` auto-detaches first.

**CHORE:** *config and errors*

- Env vars `RS_SHIM_HOST` / `RS_SHIM_PORT` / `RS_SHIM_LOC` with override chain (CLI flag > env > default); host auto-detects via the WSL2 gateway, falling back to `/etc/resolv.conf`.
- Typed `ShimError` hierarchy in `lib/errors`; `lib/shim_client` translates raw socket / JSON / RPC failures into it.
