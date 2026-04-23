# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.2] - 2026-04-21

**MAINT:** *pytest-asyncio 1.x bump*

- Bumped pytest-asyncio to `>=1.3,<2`, pytest to `>=8.2,<9`

---

## [3.0.1] - 2026-04-16

**MAINT:** *type hints + test config*

- Remaining type hints across public API
- Scaffold artifact exclusions
- Coverage omit tests/*

---

## [3.0.0] - 2026-04-07

**BREAKING:** *public API cleanup + AsyncSpinner*

- Removed `TREE_EXCLUDE` from public API (callers own their exclusion sets)
- Removed `SPINNER_FRAMES` from public API (implementation detail)
- Added `AsyncSpinner` — start/stop lifecycle spinner for async processes (WebSocket streams, monitors)
- Extracted shared `_render_frame()` helper — all three spinners (`spin`, `Spinner`, `AsyncSpinner`) use the same rendering
- Added `_clear_spinner()` internal helper

---

## [2.1.0] - 2026-04-06

**FEAT:** *formatter-layer*

- Added `format_ok(msg)` — returns styled success string without printing
- Added `format_fail(msg)` — returns styled failure string without printing
- Refactored `success()` and `error()` to use formatters (no behavior change)
- Removed tree functions to tree-lib: `tree_group`, `tree_ok`, `tree_fail`, `tree_item`, `print_tree`, `TREE_INDENT_PIPE`, `TREE_INDENT_SPACE`
- `TREE_EXCLUDE` remains (used by consumers and tree-lib)

---

## [2.0.0] - 2026-04-04

**REFACTOR:** *rename to display-lib*

- Renamed from `cli-lib` to `display-lib` (package import: `display_lib`)
- Moved to `tools/shared/display-lib/`
- Removed `paths.py` (`find_repo_root` moved to scafcli)
- Moved `agent_display.py` to adcli `lib/` (tool-specific, not shared)
- Updated `dim()` docstring documenting inline formatter pattern

---

## [1.1.0] - 2026-04-02

**FEAT:** *shared-logical-tree-helpers*

- `tree_group()`, `tree_ok()`, `tree_fail()`, `tree_item()` — shared helpers for logical tree output (validation results, process steps)
- `TREE_INDENT_PIPE`, `TREE_INDENT_SPACE` — constants for nested indentation
- 11 new tests in `test_output.py`

---

## [1.0.0] - 2026-04-01

**FEAT:** *initial-release*

Initial release — extracted from monolithic agentic-devtool-cli as part of POST-IMPL-68 decoupling refactor.

- `output.py` — `success()`, `error()`, `info()`, `warn()`, `header()`, `dim()`, `spin()`, `Spinner`
- `paths.py` — `find_repo_root()`, `print_tree()`
- `agent_display.py` — Agent activity display formatting
- `stream_event_display.py` — WebSocket event display formatting
- Zero external dependencies
