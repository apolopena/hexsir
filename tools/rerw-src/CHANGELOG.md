# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.1.0] - 2026-04-25

**FEAT:** *initial-release*

Initial scaffolded tool.

**FEAT:** *swap-savefile*

- `swap savefile --source PATH [--dest PATH]` — install a save as `Profile_1.ob` in `$RERW_SAVEGAME_DIR` (default: WSL path to Ravenswatch's `_Save`).

**FEAT:** *interactive-repl*

- `interactive` launches a `repl-lib` REPL.
- Built-in `swap-savefile` enters `rerw:swap-savefile>` sub-mode (flag-only input) or runs inline when flags are supplied.
- `exit` is context-aware: leaves the sub-mode first, then quits the REPL.

**CHORE:** *polish*

- Description set to "Ravenswatch reverse engineering tool".
- 35 unit tests, 83% coverage (commands and lib at 100%).
