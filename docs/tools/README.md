# CLI Tools

[← Back to documentation](../README.md)

## Overview

CLI tools for development, testing, and scaffolding. Each tool has its own venv, test suite, and packaging. Shared libraries provide common functionality. The Justfile task runner wraps common workflows.

## Tools

| Tool | Purpose |
|------|---------|
| [hexsir](hexsir.md) | Probe binary files for common 4-byte checksums |
| [scafcli](scafcli.md) | Scaffold agentic layers into new repos, create tools |

## Shared Libraries

| Library | Purpose |
|---------|---------|
| `display-lib` | Output functions, Spinner, colors |
| `tree-lib` | Tree rendering (static paths, process execution), tree primitives |
| `test-lib` | CLI test assertion helpers — dev dependency |

Shared libraries live in `tools/shared/` and are linked as editable dependencies in each tool's `pyproject.toml`.

## Getting Started

```bash
# Initialize all venvs (with just):
just tool-init-all

# Without just:
for d in tools/shared/*/pyproject.toml tools/*/pyproject.toml; do
    (cd "$(dirname "$d")" && uv sync --group dev)
done
```

Create a new tool:

```bash
# With just:
just tool-new mytoolcli mycommand

# Without just:
./tools/scafcli tool new mytoolcli mycommand
```

## References

| Doc | Purpose |
|-----|---------|
| [Coding Standards](coding-standards.md) | Naming, output, shared libraries, tool patterns |
| [Creating a New Tool](creating-a-new-tool.md) | Scaffold-driven development guide |
| [Scaffold Upkeep](scaffold-upkeep.md) | When and how to fold patterns back into the scaffold |
| [scafcli](scafcli.md) | Scaffold CLI reference |
