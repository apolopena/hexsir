# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.2] - 2026-04-21

**MAINT:** *pytest-asyncio 1.x bump*

- Bumped pytest-asyncio to `>=1.3,<2`, pytest to `>=8.2,<9`

---

## [1.1.1] - 2026-04-16

**MAINT:** Coverage omit tests/*.

---

## [1.1.0] - 2026-04-10

**FEATURE:** Optional `validator` callback on `Repl.builtin()`. Sync or async; returns `True` to accept or an error message string to reject. State is not updated on rejection. Builtin handlers are now async internally — backward compatible with existing sync usage via the dispatch loop.

---

## [1.0.1] - 2026-04-06

**REFACTOR:** *REPL help and per-command help*

- Help output restructured: Built-ins section (custom + defaults) above, Commands section below
- Commands section auto-generated from Click command metadata via `get_short_help_str()`
- Removed `output_help()` — no longer needed for help registration
- Added `commands` constructor parameter (dict of Click command objects)
- Built-in `--help`/`-h` support for all builtins at the loop level
- Changed help builtin description from "Show this help" to "List commands and built-ins"

---

## [1.0.0] - 2026-04-03

**FEAT:** *initial-release*

- `Repl` class — generic async REPL engine with dispatch table pattern
- Built-in `exit`, `reset`, `help` handlers
- State dict with initial state and reset support
- Configurable prompt with optional labeled state display
- Builtin registration with help text auto-generation
- `SystemExit` protection for sync command dispatch
- `prompt-toolkit` integration with persistent command history
- Colorized output via `cli-lib` (error messages, help text, info confirmations)
- Declarative state-setting builtins with type validation and error reporting
