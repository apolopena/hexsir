### Verify Before Asserting
When answering questions, think before responding. If you're not certain, say so. Never give a confident answer you haven't verified. A wrong confident answer costs more than a slow correct one.

When a test fails, read the full error output before diagnosing. Do not guess at the cause from truncated messages.

When adding flags or subprocess calls, test that the wiring works across the full call chain.

### Stale Context
When a discrepancy emerges between your context and the user's, verify your side at its source before asserting — do not default to trusting prior-turn context.

### CRITICAL: Documentation
Before starting any task, read `docs/README.md`. It is the index to all project documentation — conventions, standards, workflows, and patterns. Follow the directory to determine which docs are relevant to your task. Do not skip this step.

### Git: Planning Artifacts
Files in .ai/scratch/ and .ai/planning/prp/{instances,proposals,archive,abandoned}/ are gitignored. Do not attempt to commit them.

### Commit Messages
<60 chars, brief, imperative mood

### AskUserQuestion Tool
Never use this tool. Ask questions directly in response text.

### Planning System
When using `/generate-prp` or `/execute-prp`, read `.ai/AGENTS.md` for complete planning workflow directives.

### Changelog
When asked to update the changelog, dispatch the Pedro agent (subagent_type=Pedro).

### CRITICAL: SSH Git Commands
ALWAYS use `./scripts/git-ai.sh` for git commands requiring SSH (commit, push, pull, fetch, clone, remote, ls-remote, submodule). Prevents SSH askpass errors via keychain + adds AI attribution.

### GitHub Operations
CRITICAL: Mark agent (subagent_type=mark) is responsible for ALL GitHub write operations (PRs, issues, comments, releases).
Mark gathers context and dispatches .github/workflows/gh-dispatch-ai.yml with proper provenance.

### Save-file swap operations
ALWAYS ask the user before running `rerw swap savefile` (or any operation that overwrites the active game save in `_Save/Profile_1.ob`). Two distinct gotchas to be aware of:

- **Mid-session writes don't register.** While the game is running, the file is technically writable, but the running game holds its own in-memory state and doesn't re-read `Profile_1.ob` — the swap simply has no effect on the active session.
- **Steam Cloud sync overwrites on game quit.** When the user quits Ravenswatch, Steam syncs cloud → local, restoring whatever the cloud copy holds. Local edits made before / during the session get reverted on quit. Persistent edits require disabling Steam Cloud sync for Ravenswatch (Steam → Library → Ravenswatch → Properties → uncheck "Keep games saves in the Steam Cloud") or accepting that swaps are session-scoped only.

Confirm before swapping; do not assume; if the user reports a swap "didn't take" after a play session, the most likely explanation is the cloud-sync-on-quit overwrite.

### Save-load error modal — read the actual outcome, not the modal
The "Save Loading Error (Error code: N)" modal does NOT always indicate a hard failure. It can appear in two distinct scenarios:

- **True failure.** Click OK → routed to fresh-account hero-selection screen. The game now treats the file as unreadable; the next save event overwrites local with fresh-account defaults, wiping unlocks and any other progression. Quit immediately to preserve local.
- **False negative (warning).** Click OK → routed to the Continue / New Game dialog. The save *did* load successfully — the modal was a non-fatal warning about something the loader chose to flag. Game state is intact and the user can proceed.

**Always click through the modal once and observe destination before concluding a test result.** Save-edit experiments must report not "got error 4" but "error 4 → fresh-account" or "error 4 → continue dialog." This applies retroactively: any past test report stating only "got the error modal" is ambiguous and may need re-running with click-through to determine actual outcome.
