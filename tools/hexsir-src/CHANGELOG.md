# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

**BREAKING:** Rename tool from `hexsircli` to `hexsir`

The `cli` suffix is no longer required for tools in this repo. Source directory renamed `hexsircli-src` → `hexsir-src`, wrapper renamed `tools/hexsircli` → `tools/hexsir`.

---

## [1.0.0] - 2026-04-23

**BREAKING:** Reorganize CLI structure with command groups

Existing commands moved under `checksum` group:
- `hexsir basic` → `hexsir checksum basic`
- `hexsir header` → `hexsir checksum header`
- `hexsir scan` → `hexsir checksum scan`
- `hexsir verify` → `hexsir checksum verify`

**FEATURE:** Add command groups and new commands

- Reorganize commands into `checksum` and `probe` groups
- Add `probe key` command for searching text patterns in binary files
- Add `probe delimiter` command for finding delimiters at offsets
- Add `mint` command for creating mutated files with known checksums
- Add `HEXSIR_FILE` and `HEXSIR_CKSPEC` environment variable support
- Extract shared display helpers to `lib/display.py`
- Extract encoding helpers to `lib/encoding.py`
- Extract env var handling to `lib/env.py`

---

## [0.1.0] - 2026-04-23

**FEAT:** *initial-release*

Initial scaffolded tool.
