---
description: Generate a context handoff document so another agent can pick up where you left off
---

## Instructions

Generate a **timestamped** handoff document under `.ai/scratch/` that lets a fresh agent (with zero conversation history) resume the current work cleanly. **Never overwrite an existing handoff** — every invocation produces a new file.

**Optional argument:** `$ARGUMENTS` — if provided, focus the handoff on that specific topic. If empty, summarize whatever is currently in flight.

### Gather context first (run in parallel)

- `date +%Y%m%d-%H%M%S` — capture the timestamp for the output filename. Use this exact value; do not invent or approximate.
- `git status --short`
- `git log -10 --oneline`
- `ls -lt .ai/scratch/`

The output filename is `.ai/scratch/rw-context-handoff-<TIMESTAMP>.md`, where `<TIMESTAMP>` is the value from the `date` command above (format: `YYYYMMDD-HHMMSS`). Example: `.ai/scratch/rw-context-handoff-20260425-143022.md`.

### Required sections (in this order)

0. **PRIME DIRECTIVE — must be the first content in the file, before any other section.** Use this exact block, verbatim:

   ```
   > **CRITICAL — READ FIRST:** This handoff file is self-contained and is the single source of truth for resuming this work. **Do NOT read other handoff files in this directory** (`.ai/scratch/rw-context-handoff-*.md`) — they are prior snapshots and will pollute your context with stale state. **Do NOT read neighboring scratch files** in `.ai/scratch/` unless they are explicitly listed in "Required reading" below. The "Required reading" section is the complete and exclusive list of supplementary files you should consult.
   ```

1. **TL;DR** — 3–5 bullets. The shortest possible summary: project, current task, what the next agent should do first.
2. **Required reading** — files the next agent must read before acting, in priority order, with absolute paths. At minimum: `CLAUDE.md`, relevant docs in `.ai/docs/`, recent scratch files.
3. **Objective** — what the user is trying to accomplish. Distinguish the immediate task from the broader project goals.
4. **Current state** — what was done in this session. Be specific: file paths, line numbers, exact commands run. List files created/modified.
5. **Findings** — facts established (mark as confirmed) vs hypotheses (mark as unconfirmed). Never blur the line.
6. **Tried and ruled out** — approaches that failed, with the specific failure mode. Prevents the next agent from re-running dead ends.
7. **Open questions and pending decisions** — anything waiting on user input, research, or external systems. Note what each is blocking.
8. **Blockers** — active obstacles. Omit section if none.
9. **Key context not obvious from the code** — conventions, gotchas, constraints, environmental quirks, user preferences, decisions. The "things you only learned through trial and error" category.
10. **Next steps** — concrete actions in priority order. For each: exact command, file path, or decision needed. Mark anything requiring user confirmation.

### Style rules

- Write for an agent with zero prior context. Never reference "earlier in this conversation."
- Use absolute file paths.
- Be specific. "Run the scan" is useless. "Run `python scripts/python/rw/mod_save.py Profile_1.ob --set Level 99` then attach x64dbg to `Ravenswatch.exe`" is useful.
- Quote exact error messages and command output where they matter.
- Skip narrative. The next agent doesn't care how you arrived; they care where to start.
- Distinguish facts from hypotheses everywhere. Mark hypotheses explicitly.

### Output

Write to the timestamped path constructed above (`.ai/scratch/rw-context-handoff-<TIMESTAMP>.md`). **Do not overwrite any existing handoff file.** If the timestamped path somehow already exists (rare — same-second invocation), append a 2-digit suffix: `-01`, `-02`, etc.

After writing, print to the user the exact filename written and a 2–3 bullet summary of what's in it. Nothing else.
