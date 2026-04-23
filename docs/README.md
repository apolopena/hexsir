# Documentation

This documentation serves as both a reference for humans and directives for AI agents working in this repository. The patterns, conventions, and workflows described here are opinionated — follow them to maintain consistency across the codebase.

## Prerequisites

- **uv** (required) — Python package management ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **just** (recommended) — task runner that wraps common workflows (`cargo install just` or `brew install just` or `sudo apt install just`)

Run `just` with no arguments to see all available recipes.

## Quick Start

### 1. Initialize tool venvs

```bash
# With just:
just tool-init-all

# Without just:
for d in tools/shared/*/pyproject.toml tools/*/pyproject.toml; do
    (cd "$(dirname "$d")" && uv sync --group dev)
done
```

### 2. Run tests

```bash
# With just:
just tool-test-all

# Without just:
./scripts/run-tests.sh -c
```

### 3. Create a new tool

```bash
# With just:
just tool-new mytoolcli mycommand

# Without just:
./tools/scafcli tool new mytoolcli mycommand
```

## All Documentation

### Agentic Workflow

| Document | Purpose |
|----------|---------|
| [Overview](agentic-workflow/README.md) | System overview — commands, agents, key files |
| [Development Cycle](agentic-workflow/development-cycle.md) | Full cycle: propose → spec → review → implement → validate → ship |
| [Priming](agentic-workflow/priming.md) | Context generation: when to prime, which commands, what they produce |

### CLI Tools

| Document | Purpose |
|----------|---------|
| [Overview](tools/README.md) | Tool listing, shared libraries, Justfile recipes |
| [Coding Standards](tools/coding-standards.md) | Naming, output, shared libraries, tool creation |
| [Creating a New Tool](tools/creating-a-new-tool.md) | Step-by-step scaffold guide |
| [scafcli](tools/scafcli.md) | Scaffold CLI reference |

## Justfile Recipes

All recipes have manual equivalents — `just` is not required.

| Task | Just recipe | Manual equivalent |
|------|------------|-------------------|
| Create a tool | `just tool-new mytoolcli mycommand` | `./tools/scafcli tool new mytoolcli mycommand` |
| Init a tool | `just tool-init scafcli` | `cd tools/scafcli-src && uv sync --group dev` |
| Init all | `just tool-init-all` | Loop over `tools/shared/*/` then `tools/*/` |
| Run tool tests | `just tool-test scafcli` | `./scripts/run-tests.sh -c scafcli` |
| Run all tests | `just tool-test-all` | `./scripts/run-tests.sh -c` |
| Tool coverage | `just tool-coverage scafcli` | `cd tools/scafcli-src && uv run --with pytest-cov pytest tests/ --cov=. --cov-report=term-missing` |
| All coverage | `just tool-coverage-all` | Loop over all tool dirs |
| Lint a tool | `just tool-lint scafcli` | `cd tools/scafcli-src && .venv/bin/ruff format . && .venv/bin/ruff check .` |
| Lint all | `just tool-lint-all` | Loop over all tool dirs |
| Sync a tool | `just tool-sync scafcli` | `cd tools/scafcli-src && uv sync --group dev` |
| Sync all | `just tool-sync-all` | Loop over `tools/shared/*/` then `tools/*/` |
