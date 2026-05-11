# Agentic Workflow

[← Back to docs](../README.md)

AI-assisted development infrastructure for Claude Code. Slash commands, agents, a planning system, codebase priming, and a self-closing development cycle.

## Guides

| Guide | Purpose |
|-------|---------|
| [Development Cycle](development-cycle.md) | Full cycle: propose → spec → review → implement → validate → ship |
| [Priming](priming.md) | Context generation: when to prime, which commands, what they produce |
| [Setup](setup.md) | Dependency installation, uv, venvs, ruff |

## System Components

### Slash Commands

| Command | Purpose |
|---------|---------|
| `/generate-prp` | Generate an implementation spec from a proposal |
| `/execute-prp` | Implement features following a spec |
| `/peer-review-plan` | Rigorous review of proposals and specs |
| `/prime-prp-workflow` | Quick explanation of the PRP workflow |
| `/prime-full` | Generate full codebase context (dispatches Atlas agent) |
| `/prime-quick` | Read existing context for fast orientation |
| `/generate-context` | Generate detailed context file |
| `/generate-arch` | Generate architecture summary |

### Agents

| Agent | Purpose |
|-------|---------|
| Atlas (primer-generator) | Orchestrates context generation for `/prime-full` |
| Mark (ghcli) | All GitHub write operations via workflow dispatch |
| Pedro (changelog-manager) | Maintains CHANGELOG.md with proper formatting |

### Key Files

| File | Role |
|------|------|
| `.ai/AGENTS.md` | Planning workflow directives (AI-facing) |
| `.ai/TASKS.md` | Work ledger (untracked) |
| `CLAUDE.md` | Root-level AI directives |
| `scripts/git-ai.sh` | SSH-safe git wrapper with AI attribution |
| `.github/workflows/gh-dispatch-ai.yml` | Provenance workflow for Mark agent |
