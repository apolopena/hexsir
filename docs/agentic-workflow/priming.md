# Priming

[← Back to Agentic Workflow](README.md)

Context generation gives Claude Code awareness of the codebase, recent work, and architecture before starting a task.

## When to Prime

- **New session** — always prime at the start
- **After a branch switch** — context files may be stale
- **After major changes** — large merges, refactors, new components

## Commands

### `/prime-full`

Full context generation. Dispatches the Atlas agent which runs `/generate-context` and `/generate-arch` in sequence. Takes 15-30 seconds.

**Produces:**
- `.ai/scratch/context-primer.md` — branch context, recent work, progress, next steps (~300 lines)
- `.ai/scratch/arch-primer.md` — stack, structure, core patterns, how to add features (~200 lines)

**Use when:** Starting a new session, switching branches, or after significant codebase changes.

### `/prime-quick`

Reads existing context files and presents a 100-150 word synthesis. No generation — just reads what `/prime-full` already produced.

**Use when:** Resuming a session where context was already generated. Fast orientation.

### `/generate-context`

Generates the detailed context file. Reads TASKS.md, CHANGELOG.md, git history. Usually called by Atlas, not directly.

### `/generate-arch`

Generates the architecture summary. Reads key files, maps the stack. Usually called by Atlas, not directly.

## Output Location

All generated context lives in `.ai/scratch/` which is gitignored. Context is ephemeral — it's generated fresh when needed, not persisted across branches or commits.
