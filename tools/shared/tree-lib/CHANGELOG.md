# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.3] - 2026-04-22

**MAINT:** *return type on run_task*

- Added `Any` return type annotation to `run_task()` in dynamic.py

---

## [3.0.2] - 2026-04-21

**MAINT:** *pytest pin tightened*

- Tightened pytest to `>=8.2,<9`

---

## [3.0.1] - 2026-04-16

**MAINT:** Coverage omit tests/*.

---

## [3.0.0] - 2026-04-07

**BREAKING:** *render_tree API, TreeNode, tree_warn*

- Renamed `static_tree` to `render_tree_from_paths` (path-based convenience)
- Added `render_tree(root)` — explicit TreeNode hierarchy rendering (core API)
- Added `TreeNode` dataclass with `text`, `children`, `label`, `color`
- Added `tree_warn` primitive (yellow ⚠)
- Added `dim_connectors` parameter to both render functions
- Replaced `static.py` with `render.py` — core renderer (`_render_nodes`) is dumb, preserves insertion order, no sorting or `/` suffix
- Path-specific behavior (sorting, `/` suffix) handled during TreeNode construction in `render_tree_from_paths`, not in the renderer

---

## [2.0.0] - 2026-04-07

**BREAKING:** *remove print_tree*

- Removed `print_tree` — callers use `static_tree` with their own directory walk instead
- Tree-lib is now pure data rendering (no filesystem access)

---

## [1.0.0] - 2026-04-06

**FEAT:** *initial-release*

- `static_tree(entries, root_connectors)` — hierarchical tree from slash-delimited paths with labels and validation
- `run_task(entry)` — task execution with pass/fail tree rendering, spinner, async guard
- Primitives moved from display-lib: `tree_group`, `tree_ok`, `tree_fail`, `tree_item`, `print_tree`
- Constants: `TREE_INDENT_PIPE`, `TREE_INDENT_SPACE`
- Types: `StaticEntry`, `StaticTreeResult`, `TaskEntry`
- Depends on `display-lib>=2.1.0` for formatters and colors
