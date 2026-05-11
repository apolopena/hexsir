# scafcli — AI Scaffolding CLI

[← Back to Tools](README.md)

## Overview

`scafcli` has two main functions:

- **Repo scaffolding** — scaffold agentic AI infrastructure into new or existing repos
  - Module-based — assembles CLAUDE.md from per-module snippets, copies commands/agents/templates, validates output
  - Manifest-driven — all module definitions live in a JSON manifest with schema validation
  - Two output modes — archive (tarball) or repo (clone, scaffold, commit, push, open PR)
  - Optional modules — some modules can be excluded via `--no-*` flags (e.g., `--no-backend-lib`)

- **Tool generation** — create and extend CLI tools within the tool system
  - `tool new` — scaffolds a new tool with directory structure, bash wrapper, venv, tests
    - Optional flags:
      - `--include-repl` — REPL sessions
      - `--include-backend` — backend business logic *(unavailable if repo scaffolded with `--no-backend-lib`)*
  - `tool add command` — adds commands to existing tools with auto-wiring into `cli.py`

### ⚠️ `backend-lib` — optional business logic module

> If this repo was scaffolded with `--no-backend-lib`, the `--include-backend` flag is unavailable and `backend-lib` related content in this document does not apply.

## Prerequisites

```bash
cd tools/scafcli-src && uv venv && uv sync --group dev
```

## Modules

Scaffolding is module-based. Each module contributes files, templates, and CLAUDE.md snippets. Some modules can be excluded via flags.

| Module | Contents | Opt-out |
|--------|----------|---------|
| base | settings.json, .ai/scratch/ | always included |
| planning | PRP commands, templates, AGENTS.md | always included |
| priming | Context generation commands, primer agent | always included |
| github | ghcli agent, gh-dispatch workflow, git-ai.sh | `--no-github` |
| changelog | changelog-manager agent | always included |
| tooling | scafcli, display-lib, tree-lib, repl-lib, test-lib | always included |
| backend-lib | backend-lib shared library | `--no-backend-lib` |

### Module architecture

Modules are inclusion-based. Related items can be grouped into a single module (e.g., `tooling` bundles scafcli with generic shared libraries). To exclude something specifically, it needs its own module with a corresponding `--no-*` flag. This keeps the assembler simple — no conditional logic within modules, just module selection.

### backend-lib module

`backend-lib` provides HTTP client utilities, authentication helpers, and environment variable resolution for tools that communicate with backend services. It is optional — repos scaffolded with `--no-backend-lib` will not have this library, and the `--include-backend` flag on `scafcli tool new` will be unavailable.

If your repo was scaffolded without `backend-lib`, backend-related content in this document and related documentation does not apply.

## Commands

### `scafcli repo`

Scaffold AI infrastructure into a GitHub repo. Creates or clones the repo, scaffolds on a branch, commits, pushes, and creates a PR.

```bash
# Dry run
./tools/scafcli repo my-repo --dry-run

# Create new public repo with description
./tools/scafcli repo my-repo -r "My project" -P -y

# Scaffold into existing repo (detects conflicts)
./tools/scafcli repo my-repo -y

# Force overwrite conflicts in existing repo
./tools/scafcli repo my-repo --force -y
```

**Flags:**
- `--no-github` — exclude github module
- `--no-backend-lib` — exclude backend-lib shared library
- `-p, --private-repo` — private repo (default)
- `-P, --public-repo` — public repo
- `-y` — skip confirmation prompts
- `-r, --repo-description TEXT` — repo description (required for new repos)
- `--force` — overwrite conflicting files in existing repos
- `-n, --dry-run` — show plan without executing

**Exit codes:** 1=schema, 2=reference, 3=environment, 4=runtime, 5=conflict

### `scafcli archive repo`

Create a tarball of scaffolded AI infrastructure files.

```bash
# Dry run — show what would be created
./tools/scafcli archive repo --output /tmp --dry-run

# Create tarball (all modules)
./tools/scafcli archive repo --output /tmp

# Exclude github module
./tools/scafcli archive repo --output /tmp --no-github
```

**Flags:**
- `--output DIRECTORY` — output directory for tarball (required)
- `--no-github` — exclude github module (ghcli agent, workflow, git-ai.sh)
- `--no-backend-lib` — exclude backend-lib shared library
- `-n, --dry-run` — show plan without creating

### `scafcli tool new`

Scaffold a new CLI tool with an initial command. Generates the full directory structure, bash wrapper, venv, test foundations, and optional backend/REPL wiring. This is the primary entry point for creating new tools — typically invoked via `just tool-new`.

```bash
# Basic tool with one command
./tools/scafcli tool new demotoolcli mycommand

# With backend libraries and env var infrastructure
./tools/scafcli tool new demotoolcli mycommand --include-backend

# With REPL interactive session
./tools/scafcli tool new demotoolcli mycommand --include-repl

# With both — common for REPL-based tools that need backend libraries and environment variables
./tools/scafcli tool new demotoolcli mycommand --include-backend --include-repl

# Dry run — list files without creating
./tools/scafcli tool new demotoolcli mycommand --dry-run
```

**Arguments:**
- `TOOL_NAME` — binary name (lowercase letters only, must end in `cli`)
- `COMMAND_NAME` — initial command to scaffold (lowercase letters and hyphens, no leading/trailing hyphens)

**Flags:**
- `--include-backend` — adds `backend-lib` dependency, env var validation, backend connectivity boilerplate, env var defaults in `tests/conftest.py`
- `--include-repl` — adds `repl-lib` dependency, REPL dispatch function, `_CLICK_COMMANDS` dict, `repl` command in `cli.py`, `# [auto] scaffold:repl-commands` marker
- `-n, --dry-run` — list files that would be created without creating them

**What gets created:**

```
tools/<name>-src/
  cli.py              — Click group with --version, command registration
  commands/
    __init__.py       — module docstring
    <command>.py      — initial command stub with _cmd suffix
  pyproject.toml      — version 0.1.0, deps on display-lib (+ backend-lib, repl-lib if flagged)
  uv.lock             — generated by uv sync
  lib/
    __init__.py       — empty, add business logic here
    paths.py          — canonical get_root_dir() boilerplate
  data/
    __init__.py       — empty, add schemas/templates/seeds here
  tests/
    conftest.py       — env var defaults, integration marker
    unit/
      __init__.py
      test_cli.py     — smoke tests (--version, --help)
      test_<command>.py — command tests
  CHANGELOG.md        — initialized with 0.1.0 Unreleased
tools/<name>           — bash wrapper (executable)
```

After creation, `scafcli` runs `uv sync --group dev` to initialize the venv. The tool is immediately runnable via its bash wrapper.

**Validation:**
- Tool name must match `^[a-z]+cli$` — lowercase letters only, ending in `cli`
- Command name must match `^[a-z]+(-[a-z]+)*$` — lowercase letters and hyphens, no leading/trailing hyphens
- Fails if the tool directory or bash wrapper already exists

### `scafcli tool add command`

Add a command to an existing CLI tool. Generates the command file and test, and auto-wires into `cli.py` via scaffold markers.

```bash
./tools/scafcli tool add command demotoolcli billing
```

**What it does:**
- Creates `commands/<name>.py` with a Click command stub using the `_cmd` suffix convention
- Creates `tests/unit/test_<name>.py` with basic command tests
- If `cli.py` has scaffold markers (`[auto] scaffold:imports`, `[auto] scaffold:commands`), inserts the import and `cli.add_command()` registration automatically
- For REPL tools with `[auto] scaffold:repl-commands`, also wires into `_CLICK_COMMANDS`

If markers are not present, prints the lines to add manually.

**Arguments:**
- `TOOL_NAME` — target tool (must exist as `tools/<name>-src/`)
- `COMMAND_NAME` — command to add (lowercase letters and hyphens, no leading/trailing hyphens)

### `scafcli inspect templates`

List and view assembled template and snippet contents.

```bash
# Interactive — list entries, select by number
./tools/scafcli inspect templates

# Direct access by number
./tools/scafcli inspect templates 4

# Non-interactive — list and exit
./tools/scafcli inspect templates -N
```

**Flags:**
- `-N, --non-interactive` — list templates and exit

## Manifest

Module definitions live in `tools/scafcli-src/data/manifest.json`, validated against `tools/scafcli-src/data/schemas/manifest.schema.json` (JSON Schema draft 2020-12).

## CLAUDE.md Assembly

CLAUDE.md is assembled from per-module snippet files in `tools/scafcli-src/data/snippets/`. Each module can contribute a snippet (e.g., `base.claude.md`, `github.claude.md`). Snippets are concatenated in module order. Use `inspect templates` to preview the assembled output.

## Tests

```bash
just tool-test scafcli
```
