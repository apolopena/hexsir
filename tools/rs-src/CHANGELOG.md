# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
