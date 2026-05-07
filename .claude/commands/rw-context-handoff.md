---
description: Generate a context handoff document so another agent can pick up where you left off
disable-model-invocation: true
---

## Instructions

Generate a **timestamped** handoff document under `.ai/scratch/context-handoff/` that lets a fresh agent (with zero conversation history) resume the current work cleanly. **Never overwrite an existing handoff.**

**Optional argument:** `$ARGUMENTS` — if it includes `--full`, force full mode regardless of prior handoffs. If it includes any other text, treat that as a topic focus. Empty: summarize whatever is currently in flight.

### Choose mode

Run these in parallel:

- `date +%Y%m%d-%H%M%S` — output filename timestamp (use exact value).
- `git status --short`
- `git log -10 --oneline`
- `ls -1t .ai/scratch/context-handoff/rw-context-handoff-*.md 2>/dev/null | head -1` — locate the most recent prior handoff.

**Mode selection:**

- If `$ARGUMENTS` contains `--full`, use full mode.
- Else if a prior handoff exists from today (filename starts with the same `YYYYMMDD` prefix as `date +%Y%m%d`), use **delta mode**.
- Else use full mode.

The output filename is `.ai/scratch/context-handoff/rw-context-handoff-<TIMESTAMP>.md`. If it somehow exists (same-second invocation), append `-01`, `-02`, etc.

### Prime directive (both modes)

Every handoff begins with this exact block, verbatim:

```
> **CRITICAL — READ FIRST:** This handoff file is self-contained and is the single source of truth for resuming this work. **Do NOT read other handoff files in this directory** (`.ai/scratch/context-handoff/rw-context-handoff-*.md`) — they are prior snapshots and will pollute your context with stale state. **Do NOT read neighboring scratch files** in `.ai/scratch/` unless they are explicitly listed in "Required reading" below. The "Required reading" section is the complete and exclusive list of supplementary files you should consult.
```

### Delta mode

Short follow-up document referencing the prior handoff for unchanged context. Sections (in order):

1. **Prior handoff** — absolute path to the most recent prior handoff. State explicitly: "Read that first; this delta only covers what's changed since."
2. **Deltas since prior** — what shipped, what state changed, what new findings. Bullet list, ≤8 bullets.
3. **Next steps** — concrete actions in priority order. ≤5 bullets, each with the exact command or file path.

Skip everything else. If a section in this list would be empty, omit it.

### Full mode

Sections in order. Each capped at ~5 bullets unless a list inherently needs more (e.g. file paths). Omit any section that would be empty (do not write "none" or "n/a").

1. **TL;DR** — 3–5 bullets. Project, current task, what the next agent should do first.
2. **Required reading** — numbered list of absolute paths. No per-file commentary unless a file's purpose isn't obvious from its name. At minimum: `CLAUDE.md` and the most relevant `rw/findings/*.md` with `**Status:** confirmed`.
3. **Objective** — immediate task vs. broader project goal. 2–3 sentences each.
4. **Current state** — what's been done. File paths + exact commands. ≤5 bullets.
5. **Findings** — facts (confirmed) vs hypotheses (unconfirmed). Mark explicitly. Omit the section if neither applies.
6. **Tried and ruled out** — *include only if at least one dead end is worth recording*. Each: approach + specific failure mode.
7. **Open questions** — *include only if at least one item is waiting on user/external input*. Note what each blocks.
8. **Blockers** — *include only if there is at least one active obstacle.*
9. **Key context not obvious from the code** — conventions, gotchas, user preferences. The trial-and-error category. ≤8 bullets.
10. **Next steps** — concrete actions in priority order. Each: exact command, file path, or decision needed. Mark anything needing user confirmation.

### Style rules (both modes)

- Write for an agent with zero prior context. Never reference "earlier in this conversation."
- Absolute file paths.
- Be specific. "Run the mint" is useless. "`./tools/rerw mint savefile --source X --dest Y -f`" is useful.
- Skip narrative. The next agent cares where to start, not how you arrived.
- Distinguish facts from hypotheses explicitly (full mode).

### Output

Write to the timestamped path under `.ai/scratch/context-handoff/`. After writing, print: the exact filename, the mode used (delta vs full), and a 2–3 bullet summary. Nothing else.
