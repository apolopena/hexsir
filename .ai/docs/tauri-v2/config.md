# Tauri v2 — Configuration Reference

> **Source:** https://v2.tauri.app/reference/config/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify whether Tauri v2 supports config extensions / overlays / `TAURI_CONFIG` env var.

## Platform-Specific Configuration Files

Tauri v2 auto-merges platform-specific files onto the base config:

> "Tauri can read a platform-specific configuration from `tauri.linux.conf.json`, `tauri.windows.conf.json`, `tauri.macos.conf.json`, `tauri.android.conf.json` and `tauri.ios.conf.json` (or `Tauri.linux.toml`, `Tauri.windows.toml`, `Tauri.macos.toml`, `tauri.android.toml` and `tauri.ios.toml` if the `Tauri.toml` format is used), which gets merged with the main configuration object."

**Critical for PRP-7:** the flavor names are **fixed to platform identifiers**, not user-defined. A custom name like `tauri.superpowers.conf.json` will **not** be auto-merged. To merge a user-defined overlay, use the `-c`/`--config` CLI flag (see `cli.md`).

## Format Support

- **JSON** (default): `tauri.conf.json`
- **JSON5**: `tauri.conf.json5` (via `config-json5` Cargo feature)
- **TOML**: `Tauri.toml` (via `config-toml` Cargo feature)

## `TAURI_CONFIG` Environment Variable

> "The documentation does not mention a `TAURI_CONFIG` environment variable for selecting alternate configuration files."

**Verified absent.** The platform detection is automatic based on the build target, not user-selectable via env var. PRP-7's earlier reliance on `TAURI_CONFIG=tauri.superpowers.conf.json` is incorrect; replace with `-c` CLI flag.

## Notes for PRP-7

- The compile-time mode-gating mechanism described in PRP-7 must be redesigned:
  - **Original (incorrect):** `TAURI_CONFIG=tauri.superpowers.conf.json` env var → auto-merges overlay.
  - **Correct:** `tauri build -c src-tauri/tauri.overlay.superpowers.json` (CLI flag).
- See `cli.md` for the verified flag forms.
