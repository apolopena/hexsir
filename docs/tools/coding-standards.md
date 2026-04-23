# CLI Tooling Coding Standards

[← Back to Tools](README.md)

## Overview

Standards for building and maintaining CLI tools and the bash scripts that support them in this repository. The tool ecosystem has three layers that work together:

- **Justfile** — task runner that wraps common workflows (`just tool-new`, `just tool-test`, `just tool-sync`). Entry point for most operations.
- **scafcli** — scaffold tool that generates new tools and commands conforming to these standards. Keeps directory layout, Click wiring, shared library dependencies, test foundations, and bash wrappers uniform across all tools.
- **Shared libraries** — `display-lib`, `tree-lib`, `backend-lib`, `repl-lib`, `test-lib`. Common functionality that tools consume instead of reimplementing. Output functions, tree rendering, HTTP clients, REPL infrastructure, test assertion helpers.

Adhering to these standards matters because the scaffold, test runner, and Justfile recipes all assume the conventions described here. New tools that follow them work with the entire system immediately. Existing tools that deviate break the automation.

The workflow is iterative: build new tools and patterns to these standards, then fold proven patterns back into scafcli and shared libraries so future tools inherit them automatically. This keeps the ecosystem uniform, reduces boilerplate, and ensures quality improves across all tools as the system matures.

### Creating and Modifying Tools

- **New tool:** See [creating a new tool](creating-a-new-tool.md) for the scaffold-driven development guide.
- **Existing tool:** This document is the reference for conventions, shared libraries, and patterns that all tools follow.
- **Scaffold CLI:** See [scafcli](scafcli.md) for the full command reference.

### ⚠️ `backend-lib` — optional business logic module

> If this repo was scaffolded with `--no-backend-lib`, the `--include-backend` flag is unavailable and `backend-lib` related content in this document does not apply.

---

## Part 1: Conventions

These apply to all Python code in tools and shared libraries.

### Naming

**Tools:**
- Lowercase letters only, ending in `cli`. No digits, hyphens, or underscores.

**Commands** (have logic, live in `commands/<name>.py`):
- CLI name: kebab-case (`check-status`)
- Function: snake_case with `_cmd` suffix (`check_status_cmd`)
- File: snake_case matching CLI name (`commands/check_status.py`)

**Groups** (no logic, defined inline in `cli.py`):
- CLI name: kebab-case (`inspect`)
- Top-level groups: trailing underscore to avoid import collisions (`def inspect_():`)
- Nested groups: parent prefix (`tool_add` for `tool add`)
- No file — groups are defined inline in `cli.py`

**Single source of truth:** `cli.py` defines all groups inline and registers all commands. Names are set at registration (`add_command(..., name="...")`), never in decorators.

### Type hints

All public functions in shared libraries must have type hints on all parameters and return types. This is required, not optional. Type hints serve as the contract between shared libraries and their consumers. Without them, callers can't know the expected input shape without reading the implementation.

When parameters are simple, put them directly on the signature:

```python
def tree_ok(message: str, is_last: bool = False, indent: str = "") -> None:
```

When parameters grow complex, extract a dataclass. The dataclass becomes the documentation — callers read it to understand the contract:

```python
@dataclass
class TaskEntry:
    label: str
    action: Callable
    spin: bool = False
    done_label: str | None = None
    on_fail: Callable | None = None
    exit_code: int = 1
    is_last: bool = False
    indent: str = ""
```

The function signature stays clean — one typed argument instead of eight parameters:

```python
def run_task(entry: TaskEntry) -> Any:
    """Execute a task and render pass/fail as a tree line."""
```

Both examples are from `tree-lib`.

### Docstrings

All public functions in shared libraries must have docstrings. Single-line docstrings are sufficient for simple functions:

```python
def success(msg: str) -> None:
    """Print success message with bright green checkmark."""
    print(format_ok(msg))
```

For complex functions with multiple parameters, non-obvious behavior, or exceptions, use Google-style docstrings with Args/Returns/Raises sections:

```python
def run_db_query(
    script: str,
    container: str = "backend",
    timeout: int = 30,
) -> QueryResult:
    """Run a Python script in a container to query the database.

    Args:
        script: Python script to execute. Should print JSON to stdout.
        container: Docker container name (default: "backend")
        timeout: Query timeout in seconds

    Returns:
        QueryResult with success status and data or error message.
    """
```

The goal is doc-generator compatibility. Both styles work with pdoc, mkdocs, and Sphinx.

### Output, colors, and tree rendering

Before writing output or rendering code, check the shared libraries. Most patterns are already handled:

**`display-lib`** — standard output functions used by every tool:

| Function | Color | Symbol | Stream | Use for |
|----------|-------|--------|--------|---------|
| `success(msg)` | Green | `✓` | stdout | Completed operations |
| `error(msg)` | Red | `✗` | **stderr** | Failures, validation errors |
| `info(msg)` | Blue | — | stdout | Progress updates, neutral information |
| `warn(msg)` | Yellow | — | stdout | Non-fatal warnings |
| `header(msg)` | Magenta bold | `===` | stdout | Section headers |
| `dim(msg)` | Dim | — | (returns string) | Timestamps, secondary text |

`error()` always goes to stderr. This enables error propagation between tools (e.g., evalcli captures adcli errors). Only two symbols: `✓` for success, `✗` for error.

**`tree-lib`** — tree rendering and task execution, including spinner support:

| Function | Use for |
|----------|---------|
| `render_tree(root)` | Render explicit TreeNode hierarchy |
| `render_tree_from_paths(entries)` | Render hierarchies from slash-delimited paths |
| `run_task(entry)` | Execute an operation with pass/fail tree output and optional spinner |
| `tree_ok`, `tree_fail`, `tree_group`, `tree_item` | Individual tree line output |

`run_task` handles the common pattern of running a function, showing a spinner during execution, and printing `✓` or `✗` based on the result. If your use case involves showing progress on a sequence of operations, use `run_task` — don't build spinner + tree output manually.

For cases not covered by tree-lib (e.g., a standalone async spinner without tree context), `display-lib` provides `spin()` (async) and `Spinner` (sync context manager) directly.

### Error handling

- **Always check HTTP status codes.** Never assume success — `AgentClient` returns `(data, status)`, not exceptions.
- **Custom exceptions** for domain errors: `SeedError`, `DatabaseQueryError`. Keep them in the module that raises them.
- **Preflight health checks** before long operations: check backend connectivity, validate input, check secrets.
- **Never hardcode secret fallbacks.** Use `get_internal_secret()` from `backend_lib.auth`. If it returns `None`, error and exit.
- **Exit codes:** `sys.exit(1)` for fatal errors. In REPL mode, `return` instead of exit.

### File conventions

| Purpose | Location |
|---------|----------|
| Non-code assets (schemas, templates) | `tools/<tool-dir>/data/` |
| Test fixtures | `tools/<tool-dir>/tests/` |

Each tool uses a `data/` directory for non-code assets (JSON schemas, seed files, templates). These are declared in `pyproject.toml` under `[tool.setuptools.package-data]` so they ship with installed packages.

---

## Part 2: Shared Libraries

Shared libraries live in `tools/shared/` and provide common functionality across all CLI tools. Tools must use shared libraries for all standard operations — output, authentication, HTTP, tree rendering, CLI test assertions. Only write tool-specific code for behavior the shared libs don't cover. Do not reimplement or duplicate what already exists.

### Available libraries

| Library | Purpose | Zero deps? |
|---------|---------|-----------|
| `display-lib` | Output functions (`success`, `error`, `info`, etc.), formatters, Spinner, colors | Yes |
| `tree-lib` | Tree rendering (static paths, process execution), tree primitives | Depends on display-lib |
| `backend-lib` | HTTP client, auth, DB queries, env resolution, metadata | No (httpx, jwt, etc.) |
| `repl-lib` | REPL dispatch, history, help, builtins | Yes |
| `test-lib` | CLI test assertion helpers (`assert_cli_ok`) | Depends on click |

Every tool depends on `display-lib`. `backend-lib` and `repl-lib` are added when needed via `--include-backend` and `--include-repl` scaffold flags. `tree-lib` is added when a tool needs tree rendering. `test-lib` is a dev dependency included in every scaffolded tool for test assertion ergonomics — it is not a runtime dependency.

### Packaging

Each shared library has a `pyproject.toml`. Tools link to them as editable dependencies via `[tool.uv.sources]`:

```toml
[tool.uv.sources]
display-lib = { path = "../shared/display-lib", editable = true }
```

Editable install means changes to the shared lib source are immediately visible to all tools during development — no reinstall needed. When a tool is installed as a standalone CLI on PATH (`just tool-install <name>`), the shared lib code is copied into the package.

#### IMPORTANT: Sync After pyproject.toml Changes — Resolves Dependencies, Updates Lockfile and Venv

- **Single tool changed:** `just tool-sync <name>` — re-resolves dependencies, updates the lockfile, installs into the venv, and regenerates package metadata
- **Shared library changed:** `just tool-sync-all` — same as above but for every tool and shared library, ensuring consumers pick up the change

#### IMPORTANT: Version Discipline

Every shared library and tool follows semver. Bump the version and update the CHANGELOG for every change, even on unreleased branches — the changelog is a permanent record that tells the story of each change in context. Collapsing changes to avoid version bumps rewrites history.

- **Patch** (1.0.0 → 1.0.1): bug fixes, internal changes, no API change
- **Minor** (1.0.0 → 1.1.0): new public API, backwards compatible
- **Major** (1.0.0 → 2.0.0): removed or renamed public API, breaking change

Breaking changes require updating dependency pins (`>=X.0.0,<Y`) in all consumers and syncing their environments (`just tool-sync-all`). The pin update cost is intentional — it forces every consumer to acknowledge the change.

CHANGELOGs follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format. Each version gets a heading (`## [1.2.0] - YYYY-MM-DD`), with a brief description prefixed by category (`**FEATURE:**`, `**FIX:**`, `**MAINT:**`). `scafcli` initializes with `## [Unreleased]` and `## [0.1.0]` sections.

### When to create a new shared library

Create a new shared library when:
- Two or more tools need the same functionality
- The functionality is a distinct concept (not just a utility function)
- It has a clear API boundary

Do not create a shared library for one-off helpers or tool-specific logic. Keep those in the tool's own `lib/` directory.

---

## Part 3: Tool Patterns

Uniformity enables automation. Every tool follows these patterns and works with the scaffold, test runner, and linter immediately — no setup, no special cases. Structure decisions favor readability and single sources of truth over flexibility.

> ⚠️ `scafcli` generates code conforming to these patterns. Use this reference when reading generated code or writing code the scaffold doesn't cover.

### Self-contained by design

Each tool is a self-contained Python package. Commands live in `commands/`, application code in `lib/`, non-code assets in `data/`, and tests in `tests/`. A tool must not depend on data files outside its own directory. Configuration is done exclusively through environment variables.

This matters because tools can be deployed as standalone CLIs on PATH via `uv tool install`. If a tool reaches outside its directory for data or config, it breaks the moment it leaves the repo.

### Two execution modes

Tools run either through a bash wrapper or as a standalone CLI on PATH. Functionality is identical — the wrapper exists to enable rapid local development.

**Bash wrapper** (`./tools/toolname`): Runs the tool from source. Version output shows `(dev source)` to distinguish from installed.

**Standalone CLI** (`toolname`): Installed on PATH via `uv tool install`. The user exports required env vars before running.

Both modes support `-h`/`--help` and `--version`.

#### Environment variables

The wrapper provides env vars with locally-scoped defaults so tools run without manual configuration during development. `CLI_ROOT_DIR` is the most important — tools that need to resolve paths within the project use it as their working directory.

Tool-specific vars (secrets, API keys) live in the project's `.env` file, loaded at startup via `CLI_ROOT_DIR`.

**Extending a tool's env vars**: Scaffolding does not update the wrapper after initial generation. If your tool requires a new env var, add it to the wrapper following the existing pattern, or to `.env` for secrets.

### Path resolution

Deployed tools must not walk the filesystem for paths. All paths come from environment variables or arguments. `CLI_ROOT_DIR` is used instead of `.git/` directory discovery because the project is not assumed to be a git repository — tools must work in pre-repo development, archive distributions, and environments where `.git/` may not exist.

Tools that need the project root use `CLI_ROOT_DIR` — the bash wrapper sets it automatically, and standalone CLIs require the user to export it. Path resolution logic lives in `lib/paths.py`, where `get_root_dir()` reads and validates `CLI_ROOT_DIR` and all other paths derive from it.

#### Context-free tools

Most tools built in this suite will be project-anchored — they resolve configs, manifests, seed data, or other resources relative to the project root. However, tools whose inputs come entirely from flags or external APIs and whose outputs go to stdout or user-specified paths have no dependency on the project's file structure. These context-free tools may ignore or remove the scaffolded pathing boilerplate and use traditional path resolution (CWD-relative, flag-based, or argument-based).

#### Package-data paths

Tools that ship bundled assets (templates, schemas, seeds declared in `[tool.setuptools.package-data]`) such as scafcli must resolve those paths from the package's own location, not `CLI_ROOT_DIR`. When installed via `uv tool install`, the bundled `data/` directory lives next to the installed package files — `CLI_ROOT_DIR` does not reach it.

The standard pattern is a separate helper in `lib/paths.py`:

```python
def get_package_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"
```

This is the one documented exception to "derived paths call `get_root_dir()`". It applies only to paths inside the tool's own package. Paths outside the package (project root, user inputs, etc.) still go through `get_root_dir()`.

### Scaffold flags

Tools are scaffolded with optional boilerplate:

- **Backend tools** (`--include-backend`) — env var validation, backend connectivity.
- **REPL tools** (`--include-repl`) — REPL dispatch, command registration.

Flags can be combined. See [scafcli](scafcli.md) for full usage.

### Directory layout

`scafcli tool new <name> <command>` generates this structure:

```
tools/<name>-src/
├── cli.py              # Entry point (help, version), groups, registrations
├── commands/           # Command implementations only (one per file)
│   ├── __init__.py
│   └── <command>.py    # exports <command>_cmd
├── lib/                # Business logic modules
│   └── __init__.py
├── data/               # Non-code assets (schemas, seeds)
│   └── __init__.py
├── tests/
│   ├── conftest.py
│   └── unit/
│       ├── __init__.py
│       ├── test_cli.py
│       └── test_<command>.py
├── pyproject.toml
├── uv.lock
└── CHANGELOG.md
tools/<name>            # Bash wrapper (executable)
```

**cli.py** — the single source of truth for CLI structure:
- Groups defined inline (3-line definitions, no logic)
- All `add_command()` registrations
- Version callback, imports

**commands/** — command implementations only:
- One file per command
- Bare `@click.command()` decorators
- No groups (groups are inline in `cli.py`)

**lib/** — organize by domain, not by command. Cross-command utilities belong here. Keep command-specific logic in the command file itself. Module names should be descriptive (`seed_runner.py`, `manifest.py`), not generic (`utils.py`, `helpers.py`). For code shared between multiple lib modules, use a `lib/shared/` subdirectory.

### Bash wrappers

`scafcli` generates a bash wrapper at `tools/<name>`. The conventions:

- `set -euo pipefail` (not just `set -e`)
- `SCRIPT_DIR` and `TOOL_DIR` resolution at top
- `export TOOL_EXEC_MODE=dev-source`
- `export PATH="$SCRIPT_DIR:$PATH"` (enables sibling tool discovery via `shutil.which`)
- `exec "$TOOL_DIR/.venv/bin/python" "$TOOL_DIR/cli.py" "$@"`

Backend tools also include:

- `export CLI_ROOT_DIR="${CLI_ROOT_DIR:-$(dirname "$SCRIPT_DIR")}"`
- `export CLI_BACKEND_URL="${CLI_BACKEND_URL:-http://localhost:8000}"`
- `export CLI_AGENTIC_BACKEND_URL="${CLI_AGENTIC_BACKEND_URL:-http://localhost:8001}"`
- `export CLI_AGENTIC_BACKEND_WS_URL="${CLI_AGENTIC_BACKEND_WS_URL:-ws://localhost:8001}"`

### Click conventions

`cli.py` is the single source of truth for CLI structure. Groups are defined inline, commands are registered here, and all names are set at registration.

**Entry point:**
- `prog_name` — always set in `if __name__ == "__main__": cli(prog_name="toolname")`. Without it, error messages show `__main__.py`.
- `-h` shortcut — all tools enable via `context_settings={"help_option_names": ["-h", "--help"]}`
- `metavars` — always set on options that require an argument: `metavar="ID"`, `metavar="MODEL"`

**cli.py structure** — sections appear in this order:

1. Imports (standard library, third-party, then local)
2. Version helpers
3. Main CLI entry point with help and version options
4. Top-level commands
5. Top-level groups, each followed immediately by:
   - Its direct command registrations
   - Any nested groups and their registrations
6. `if __name__ == "__main__"` block

**Groups** — defined inline in `cli.py`, never in separate files. Top-level groups use trailing underscore to avoid collisions with module imports:

```python
# cli.py — top-level group
@cli.group(name="inspect")
def inspect_():
    """Inspect scaffold contents."""
    pass

# Nested group uses parent prefix
@tool_.group(name="add")
def tool_add():
    """Add components to an existing CLI tool."""
    pass
```

**Commands** — logic in `commands/<name>.py`, bare decorator, registered in `cli.py`:

```python
# commands/billing.py — implementation only
"""billing command."""

import click
from display_lib.output import info, success

@click.command()
def billing_cmd() -> None:
    """Run billing operations."""
    info("Running billing...")
    success("Done")
```

```python
# cli.py — all registrations here
from commands import billing, seeds

# Top-level command
cli.add_command(billing.billing_cmd, name="billing")

# Group subcommand
inspect.add_command(seeds.seeds_cmd, name="seeds")
```

**REPL tools** — also add to `_CLICK_COMMANDS`:

```python
"billing": billing.billing_cmd,
```

### REPL dispatch

The REPL dispatch in `cli.py` must be a clean pass-through — it parses args via Click and passes `ctx.params` directly to the async function. No parameter reassignment, no per-command conditionals.

When Click flag names differ from backend API parameter names, the async function reassigns the values at the top of its body, right after the docstring:

```python
async def run_assessment(
    ...
    model: str | None = None,
    draft_model: str | None = None,
    verify_model: str | None = None,
    ...
):
    """Run assessment generation with optional streaming."""
    # --- Reassign Click flag values to backend API parameter names ---
    model_override = model
    cli_draft_model = draft_model
    cli_verify_model = verify_model
```

This works for both paths because the async function is the convergence point. Click's command function calls it via `asyncio.run()` (sync → async bridge). The REPL calls it directly with `await` (already async). Both pass Click's flag names, and the function handles the reassignment before doing any work.

#### Async dispatch pattern

For tools with async commands and session state, the dispatch uses three registries. Reference implementation: `tools/adcli-src/cli.py`.

```python
_CLICK_COMMANDS = {
    "billing": billing.billing_cmd,
    "report": report.report_cmd,
}

_ASYNC_FNS = {
    "billing": billing.run_billing,
    "report": report.run_report,
}

_NEEDS_SESSION = {"billing", "report"}


async def _dispatch(cmd_name: str, line: str, state: dict) -> None:
    session_id = state["session_id"]

    if cmd_name in _NEEDS_SESSION and session_id is None:
        error("Set session first: session <id>")
        return

    click_cmd = _CLICK_COMMANDS.get(cmd_name)
    if not click_cmd:
        error(f"Unknown command: {cmd_name}")
        return

    try:
        args = shlex.split(line)
    except ValueError:
        args = line.split()
    args = args[1:]  # drop command name

    if cmd_name in _NEEDS_SESSION:
        args = [str(session_id)] + args

    try:
        ctx = click_cmd.make_context(cmd_name, args)
    except click.UsageError as e:
        error(str(e))
        return
    except SystemExit:
        return  # --help was shown

    if cmd_name in _ASYNC_FNS:
        await _ASYNC_FNS[cmd_name](**ctx.params)
    else:
        ctx.invoke(click_cmd, **ctx.params)
```

- **`_ASYNC_FNS`** — maps command names to async functions for commands that need `await`
- **`_NEEDS_SESSION`** — commands that require a session ID; the dispatch injects it as the first positional arg
- **Sync fallback** — commands not in `_ASYNC_FNS` run via `ctx.invoke` (e.g., db queries, list commands)

#### Session state and builtins

Override `initial_state` and register builtins for the user to set state values:

```python
_repl = Repl(
    name="demotoolcli",
    dispatch=_dispatch,
    initial_state={"session_id": None},
    history_file=".demotoolcli_history",
)

_repl.builtin(
    "session",
    arg="<id>",
    arg_type=int,
    state_key="session_id",
    prompt_label="session",
    help_text="Set active session ID",
)
```

`scafcli` generates `initial_state={}` by default. This extends it for tools that need to track state across commands.

#### Builtin validator callback

To reject invalid values before they're stored in state, pass an optional `validator` callback. It receives the parsed value (after `arg_type` conversion) and must return `True` (accept) or an error string (reject). It may be sync or async, and runs before state assignment — on rejection, state is left untouched and the error is printed:

```python
def _validate_session(session_id: int) -> bool | str:
    results = query_sessions_info([session_id])
    if not results:
        return f"{session_id} not found"
    return True

_repl.builtin(
    "session",
    arg="<id>",
    arg_type=int,
    state_key="session_id",
    prompt_label="session",
    help_text="Set active session ID",
    validator=_validate_session,
)
```

### Scaffold markers

Scaffolded tools include `# [auto] scaffold:imports` and `# [auto] scaffold:commands` comments in `cli.py`. These are insertion points used by `scafcli tool add command` to auto-wire new commands. Do not remove them. REPL tools also have `# [auto] scaffold:repl-commands`.

### pyproject.toml

`scafcli` generates a `pyproject.toml` based on flags (`--include-backend`, `--include-repl`). Sections and their purpose:

```toml
# --- Required ---

# installed CLI name
[project.scripts]
demotoolcli = "cli:cli"

# package declaration
[tool.setuptools]
packages = ["commands", "lib", "data"]
py-modules = ["cli"]

# ship assets with installed CLI
[tool.setuptools.package-data]
data = ["**/*"]

# editable links to shared libraries
[tool.uv.sources]
display-lib = { path = "../shared/display-lib", editable = true }

# measure application code only
[tool.coverage.run]
omit = ["tests/*"]

# --- Optional ---

# use extend-exclude (not bare exclude) to preserve ruff defaults
[tool.ruff]
extend-exclude = ["tests/fixtures"]

# relaxed rating bands for integration-heavy tools; see section below
[tool.custom.has_integrations]
bump_rating_threshold = true
```

### Coverage ratings for integration-heavy tools

`bump_rating_threshold` — a flag for tools whose coverage rating should account for integration code that can't be reasonably tested without live services. Auditable trust is better than invisible trust — this flag makes a judgment that already exists (which code is testable) explicit and reviewable.

- Set this flag if your tool's coverage is dragged down by integration code.
  - Examples: HTTP clients, WebSocket streams, DB drivers — files that talk to external systems.
- Don't use it if your tool has low coverage because the application code isn't tested. The flag is for when integration code is the reason, not a workaround for missing tests.
- Use of this flag is the developer's responsibility. Misuse inflates the rating dishonestly and will be caught in code review.

When set, `just tool-coverage-all` applies relaxed rating bands (-10 across the board) and shows an asterisk in the rating column. The footnote at the bottom of the summary explains.

To decide whether the flag is justified, ask your AI assistant to scan the tool's uncovered files and identify which ones are integration touch points (subprocess wrappers, HTTP clients, WebSocket streams, DB drivers). The AI can compute what coverage would be without those files. If the gap is meaningful, the flag is honest.

### Testing

Each tool has its own venv and its own test suite. Tests live in `tests/unit/` and optionally `tests/integration/`.

```bash
cd tools/<name>-src && .venv/bin/pytest tests/ -v
just tool-test <name>
just tool-lint <name>
```

- `conftest.py` sets env var defaults with `os.environ.setdefault()`
- Integration marker: `config.addinivalue_line("markers", "integration: ...")`
- Always run `ruff format` before `ruff check`. Never use `--check` mode on format.

### Registering in the test runner

To include a tool in `just tool-test <name>` and `./scripts/run-tests.sh -c` runs, add the tool name to the `CLI_TOOLS` array in `scripts/run-tests.sh`. No Justfile registration is needed — `_get-tool-src-dir` is convention-based.

### Packaging

Tools are installed as standalone CLIs on PATH via `uv tool install`:

```bash
just tool-install <name>
```

### Smoke testing

Verify a tool installs and runs correctly as a standalone CLI:

```bash
just tool-smoke-test <name>
```

This installs the tool, checks `--version` and `--help`, then uninstalls.

### Folding patterns back into the scaffold

When a pattern proves itself across two or more tools, it's a candidate for scafcli or a shared library — not before. Premature extraction creates abstractions nobody needs. But failing to fold in proven patterns promotes duplication, and duplication silently diverges over time. Be prudent: extract too early and you over-engineer; extract too late and you maintain the same code in five places.

For the full process, decision criteria, and tooling, see [scaffold-upkeep.md](scaffold-upkeep.md).

---

## Part 4: Bash Script Output

Scripts that produce structured terminal output (status displays, progress reporting, colored tables) should follow these conventions. For a reference implementation, see `scripts/stack.sh`. Simple wrapper scripts that just invoke other tools don't need this level of formatting.

### 256-color palette

All scripts with colored output use the same 256-color palette:

```bash
RED='\033[38;5;160m'
GREEN='\033[38;5;34m'
YELLOW='\033[38;5;142m'
BLUE='\033[38;5;25m'
CYAN='\033[38;5;73m'
LIGHT_CYAN='\033[38;5;75m'
PINK='\033[38;5;175m'
NC='\033[0m'
```

### Color-to-output mapping

| Color | Code | Use for |
|-------|------|---------|
| LIGHT_CYAN | 75 | Main title only |
| BLUE | 25 | Section headers |
| PINK | 175 | Column headers / table headers |
| GREEN | 34 | Good status — no action needed |
| RED | 160 | Bad status — action required |
| CYAN | 73 | Fix hints — actionable commands |
| YELLOW | 142 | Descriptive labels — informational |

**Rule: never reuse a status color for a non-status purpose.** Green, red, and cyan have strict meanings. Yellow and pink are for decoration/structure only.

### Extending stack scripts

When adding new status sections:

1. Use `print_header "Section Name"` for the section title (renders in BLUE)
2. Use GREEN for healthy/passing states, RED for broken/pending states
3. Use CYAN for fix hints — always prefix with `Fix:`
4. Use YELLOW for container/service descriptions only
5. Use PINK if adding new table-style output with column headers
