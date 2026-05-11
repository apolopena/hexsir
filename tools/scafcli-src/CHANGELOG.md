# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.2.1] - 2026-04-22

**FIX:** *`--include-backend` flag isolation*

- Changed `--include-backend` from hidden to conditionally registered (only when backend-lib exists)
- Justfile template guards "Include backend?" prompt on `tools/shared/backend-lib/` existence
- Prevents Click error suggestions exposing unavailable flag

---

## [4.2.0] - 2026-04-22

**FEATURE:** *`--no-backend-lib` module exclusion*

- Added `backend-lib` as standalone module with `--no-backend-lib` flag for repo/archive commands
- `--include-backend` flag on `tool new` hidden and guarded when `backend-lib` not scaffolded
- Removed stale `coding-standards.md` template (now copied directly from source)
- scafcli.md refactored: Overview bulleted, Modules moved before Commands, commands reordered (repo/archive before tool)
- Added `### backend-lib module` subsection to Modules documentation
- Added `⚠️ backend-lib — optional business logic module` preface to scafcli.md, coding-standards.md, creating-a-new-tool.md

---

## [4.1.2] - 2026-04-21

**FIX:** *scaffolded repos missing scafcli data directory*

- Changed `.gitignore` template `data/` to `/data/` so it only ignores root-level data directory, not `tools/scafcli-src/data/`

---

## [4.1.1] - 2026-04-21

**MAINT:** *pytest-asyncio 1.x + test-lib scaffold propagation*

- Bumped pytest-asyncio to `>=1.3,<2`, pytest to `>=8.2,<9`
- Migrated success-path CLI assertions to `assert_cli_ok`
- Updated scaffold templates and golden fixtures for test-lib
- Added test-lib to manifest for downstream repo scaffolding
- Lengthened scaffolded test JWT secret to 32 bytes (suppresses HMAC-SHA256 warning)

---

## [4.1.0] - 2026-04-18

**FEATURE:** *scaffold Justfile recipe parity + shared-lib completeness*

- Scaffolded Justfile template: `scafcli scaffold tool` syntax replaced with `scafcli tool new`; added `tool-list`, `tool-versions`, `tool-build`, `tool-build-all`, `tool-install`, `tool-install-all`, `tool-uninstall`, `tool-uninstall-all`, `tool-rebuild`, `tool-smoke-test`
- Manifest: `tools/shared/backend-lib` and `tools/shared/repl-lib` wired as scaffolded trees so `--include-backend` / `--include-repl` flags produce working tools in scaffolded repos
- Manifest: `scripts/tool-smoke-test.sh` and `scripts/tool-info.sh` wired as scaffolding so the new Justfile recipes have supporting scripts
- Orphan `data/templates/docs/tools/coding-standards.md` wired as a template and rewritten from the real doc, trimmed to what ships in scafcli-only repos (removed adcli/evalcli/syscli/deploycli/backend-lib/repl-lib-specific sections, REPL dispatch, scaffold flags)
- Scaffolded-repo README templates: `scafcli scaffold tool` → `scafcli tool new`
- `inspect templates` no longer prints a file tree for scaffolded directories; lists inspectable template entries only
- Guard test: `test_every_shared_lib_is_in_manifest` asserts every `tools/shared/<lib>` on disk is scaffolded by the manifest
- Terminology cleanup across `lib/assembler.py`, `lib/display.py`, `lib/manifest.py`, `commands/inspect.py`, `commands/repo.py` and a test: comments/labels now distinguish scaffolding (verbatim copies) from templates (trimmed)

---

## [4.0.0] - 2026-04-18

**BREAKING:** *remove `inspect drift` subcommand and `.drift-expect`*

- Deleted `commands/drift.py` and `tests/test_drift.py`
- Removed `.drift-expect` whitelist from `data/templates/`
- Removed vestigial empty `data/templates/tools/` directory
- Docs stripped of drift references: `docs/tools/scafcli.md`, `scaffold-upkeep.md`, `coding-standards.md`, `data/templates/docs/README.md`, `data/templates/docs/tools/README.md`
- Rationale: a template exists only because it differs from the real file, so every template required a `.drift-expect` entry — the "unexpected drift" guardrail never legitimately fired

---

## [3.1.0] - 2026-04-16

**FEATURE:** *pathing-by-default*

- `tool new` now generates `lib/paths.py` with canonical `get_root_dir()` boilerplate in every scaffolded tool
- Wrapper template exports `CLI_ROOT_DIR` in the default block (no longer requires `--include-backend`)
- Own `lib/paths.py` reorganized: canonical `get_root_dir()` first, then tool-specific helpers (`get_scaf_data_dir`, `require_source_repo`) below
- Golden fixtures include `lib/paths.py`

---

## [3.0.0] - 2026-04-16

**BREAKING:** *retire `tool add pathing` subcommand*

- `scafcli tool add pathing` removed; deleted `commands/pathing.py` and `tests/test_pathing_scaffold.py`
- `lib/paths.py`: tightened `get_scaf_data_dir` and `require_source_repo` docstrings
- Package-data path exception documented in `docs/tools/coding-standards.md#package-data-paths`
- CLI hierarchy: `tool new`, `tool add command`, `archive repo`, `inspect templates/drift`
- Added `get_scaf_data_dir()` for bundled package data; `require_source_repo()` for scaffold-manifest validation
- `CLI_ROOT_DIR` overridable via `${CLI_ROOT_DIR:-default}` wrapper pattern
- Flattened `lib/shared/` to `lib/`; `inspect templates` works standalone
- Test infrastructure: standardized test_cli.py, scaffold artifact exclusions, coverage omit tests/*

---

## [2.0.0] - 2026-04-14

**BREAKING:** `SCAFCLI_ROOT_DIR` replaced by unified `CLI_ROOT_DIR`. Path resolution in `lib/shared/paths.py` updated with proper error handling (`error()` + `sys.exit(1)`, `is_dir()` validation).

**FEATURE:** `scafcli add pathing` command — scaffolds `lib/paths.py` with canonical `get_root_dir()` and adds `CLI_ROOT_DIR` export to the bash wrapper.

---

## [1.2.4] - 2026-04-06

**FEAT:** *drift detection + template cleanup*

- `scaffold inspect drift` command — detects template drift against real repo files
- `.drift-expect` for intentional template differences, stale entry detection with `--fix`
- Replaced `example` module with `tooling` module (scafcli + display-lib + tree-lib)
- Removed orphaned templates (dev-setup, testing docs, .run artifacts)
- Converted 2 near-identical doc templates to direct file refs
- Tests use manifest-driven assertions instead of hardcoded values

---

## [1.2.3] - 2026-04-06

**REFACTOR:** *tree-lib + bug fix*

- Refactored `print_file_tree` to use `static_tree` from tree-lib
- Replaced `_tree_run`/`_tree_run_spin` with `run_task` from tree-lib
- Updated `print_tree` import to tree-lib in inspect and assembler
- Added tree-lib dependency
- Fixed missing `error()` import in REPL scaffold template

---

## [1.2.2] - 2026-04-06

**REFACTOR:** *REPL scaffold template update*

- Template passes `commands=_CLICK_COMMANDS` to Repl constructor
- Removed `output_help()` and `scaffold:repl-help` marker from template
- Removed `MARKER_REPL_HELP` wiring logic from `scafcli add command`

---

## [1.2.1] - 2026-04-05

**MAINT:** Add scaffold markers for `scafcli add command` auto-wiring.

---

## [1.2.0] - 2026-04-04

**REFACTOR:** *CLI tooling refactor*

- Renamed display-lib dependency (was cli-lib), updated import paths
- Moved commands to commands/ directory with _cmd suffix
- Uniform cli.py boilerplate with add_command registration
- Moved shared libs to tools/shared/

---

## [1.1.1] - 2026-04-02

**REFACTOR:** *shared-tree-helpers*

- Replaced local `_tree_group`, `_tree_ok`, `_tree_fail` in `commands/repo.py` with shared `cli_lib.output` tree helpers
- Removed unused color constant imports (`BRIGHT_GREEN`, `CYAN`, `GREEN`, `NC`, `RED`)

---

## [1.1.0] - 2026-04-02

**FEAT:** *scaffold-tool-command*

- New `scaffold tool` command: `scafcli scaffold tool --name <name> [--backend-connected] [--dry-run]`
- Generates 8 files + bash wrapper + venv for a ready-to-use CLI tool
- Name validation, existing directory guard, dry-run support
- 11 tests in `test_tool_scaffold.py`
- Renamed source directory from `scaf-cli` to `scafcli-src` (POST-IMPL-69 naming convention)

---

## [1.0.0] - 2026-04-01

**FEAT:** *initial-release*

Initial release — extracted from monolithic agentic-devtool-cli as part of POST-IMPL-68 decoupling refactor.

- Standalone package with own venv and `pyproject.toml`
- Click CLI entry point with `--version`
- Commands: `scaffold repo`, `scaffold archive`, `scaffold inspect`
- `lib/` modules: assembler, errors, manifest, validator, shared/display, shared/paths
- `data/` assets: manifest.json, schemas, snippets, templates
- Depends on `cli-lib` shared package
- Bash wrapper with `TOOL_EXEC_MODE`, `PATH` export
