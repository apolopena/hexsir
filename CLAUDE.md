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

### Scripts: dumps vs scripts
`rw/dumps/` is gitignored — for one-shot debugging only. **Any script referenced by a recipe, breakthrough, key-finding, or other committed doc must live in `rw/scripts/` (committed), not `rw/dumps/`.** The moment a script is invoked from documentation, move it.

### Commit Messages
<60 chars, brief, imperative mood

### Terminology
Standardized terms for talents, items, seeds, and indexing live in `rw/docs/terminology/README.md`. Read before writing about these domains. Indexing rule: code is 0-based, user-facing is 1-based — translate at the access boundary.

### AskUserQuestion Tool
Never use this tool. Ask questions directly in response text.

### Planning System
When using `/generate-prp` or `/execute-prp`, read `.ai/AGENTS.md` for complete planning workflow directives.

### Changelog
When asked to update the changelog, dispatch the Pedro agent (subagent_type=Pedro).

### CLI Design Rules
Design the command grammar before adding flags. A CLI should have clear nouns,
verbs, and ownership boundaries; do not grow a flat pile of loosely related
options.

- Separate discovery from mutation. Use `inspect`, `list`, or equivalent
  read-only commands to discover valid keys and current state; use `set`,
  `write`, or equivalent commands for destructive changes.
- Destructive commands must be explicit. Show the current state before
  overwrite when practical, and do not hide mutation behind an inspect/list
  command.
- Use strict keys when the tool has registry-backed identifiers. Do not silently
  accept display names, aliases, fuzzy matches, or normalized variants when a
  command says `key`.
- Single required value: prefer a positional argument, e.g.
  `set level <int>` or `set item <key>`.
- Multiple required values: use named flags, e.g.
  `set talent --key <key> --slot <int>`.
- Do not create comma-delimited mini-languages or order-dependent argument
  grammars. If the operation cannot be expressed cleanly, create a subcommand.
- Avoid generic flags whose meaning changes by context, such as a top-level
  `--tier` that only applies to talents. Put scoped options on the relevant
  leaf command.
- Do not batch destructive edits inside ordinary `set` commands. If batching is
  genuinely needed, design a separate transaction/apply command with its own
  explicit input format and validation.
- Parent groups should organize commands, not smuggle ambiguous options into
  children. Repeat common leaf options like `--source`, `--dest`, `--force`,
  and `--verbose` when that makes the command contract clearer.
- If a group requires a subcommand, prefer showing help instead of guessing a
  default action.

### RERW Python Environment
`tools/rerw-src` is its own Python project. For scripts that need project
dependencies such as PyYAML, use the project venv:

```bash
tools/rerw-src/.venv/bin/python ...
```

Use `uv run rerw` for normal CLI commands. Do not prefix commands with
`UV_CACHE_DIR=...` in docs, recipes, or tool calls — `UV_CACHE_DIR` is set
project-wide via `.claude/settings.json`.

### CRITICAL: SSH Git Commands
ALWAYS use `./scripts/git-ai.sh` for git commands requiring SSH (commit, push, pull, fetch, clone, remote, ls-remote, submodule). Prevents SSH askpass errors via keychain + adds AI attribution.

### GitHub Operations
CRITICAL: Mark agent (subagent_type=mark) is responsible for ALL GitHub write operations (PRs, issues, comments, releases).
Mark gathers context and dispatches .github/workflows/gh-dispatch-ai.yml with proper provenance.

### Save-file swap
Always use `rerw swap savefile --source <path>`. Never raw `cp`. Confirm the game is closed before swapping; once authorized, execute the bare swap and stop — no backups, md5s, stats, or process checks. Full narrative including the mid-session-swap-clobber gotcha lives in `rw/docs/workflow/save-editing.md` §Gotchas.

### Steam Cloud sync
Assume Steam Cloud sync is disabled for Ravenswatch. Saves persist on disk; `rerw swap savefile` sticks across game sessions. The mid-session swap clobber rule still applies — never swap while the game is running.

### Saves are only generated at chapter-boss kills — there is no other save event
Ravenswatch only writes a new `Profile_1.ob` on chapter-boss kill (no autosave / quicksave / save-on-quit / save-on-death). Mid-run "edit → swap → play → save → re-inspect" round-trips are not possible; a new chapter-boss kill is ~20 minutes of focused play. Treat proof saves as scarce — propose new save runs only with strong justification. Full narrative in `rw/docs/workflow/save-editing.md` §Gotchas.

### Ghidra: decompilation available on request
The game's `Ravenswatch.exe` is loaded in Ghidra and reachable via `mcp__ghidra__*` tools. If decompilation would help answer a question, ask the user before digging — don't assume.

### WinDbg: live debugging available on request
A WinDbg MCP server is registered in `.mcp.json` (port 8000); when running, tools appear under `mcp__windbg__*`. Use only for live-process debugging of the running game (breakpoints, memory inspection, stepping). If the tools aren't loaded, the server isn't up — ask the user to start it. Ask before initiating a debugging session — don't assume.

### Frida: WSL → Windows interop workflow
Frida scripts live at `tools/frida/*.js` in WSL; `frida.exe` runs Windows-side via interop (default path `/mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe`) and loads the WSL absolute path directly on initial invocation. The REPL eats backslashes on `%load` reloads — never reload from the REPL; after any edit, exit Frida and re-launch with a fresh one-liner.

### Frida: code standards
Before adding or modifying any Frida script under `tools/frida/`, read `tools/frida/CODE_STANDARDS.md`. It is opinionated and covers project layout (powers vs mods), naming, the docstring contract (block-comment with two fences; mechanism below the second fence), state and re-load safety, the `delay<Verb>` convention, shared utilities (`RW.after`, `RW.help`), and the validation checklist for new powers. Adhere to it.

### Ghidra: annotate findings on the spot
When you identify what a function/struct/global does — even partially — annotate it in Ghidra immediately via the `mcp__ghidra__*` tools. Don't batch at session end. Symbol identity (names, types, struct definitions, enums) goes in Ghidra; narrative context goes in `rw/findings/*.md`. Full annotation kinds, naming conventions, and the symbol-identity-vs-narrative split live in `rw/docs/workflow/ghidra.md`.

### Save-edit lab base rule — never layer on a failed experiment
New save edits MUST layer on top of a golden, a proof, or a verified-success lab. Never layer on a failed lab variant. If unsure whether a prior lab is a success, ask before using it. Full rationale in `rw/docs/workflow/save-editing.md` §Concepts → "Lab base rule."

### Never source labs from the clean proof
Push back if asked to build a lab from `rw/saves/proofs/geppetto/clean/Profile_1.ob` — clean saves lack the records required for player-info edits (no item records, no Nightmare Keys record, etc.), so the byte shape triggers rerw writer bootstrap failures. Ask the user to pick a different source proof.

### Save-edit lab naming convention
Lab folder names encode lineage: `<edit-name>__from-<source-name>[__<extra-suffix>]/Profile_1.ob`. The `__from-` separator is a literal double-underscore. Use the source directory's leaf name. Examples and full convention live in `rw/docs/workflow/save-editing.md` §Concepts → "Folder taxonomy and naming."

### Save-file taxonomy
Four buckets under `rw/saves/`: `proofs/` (unmodified chapter-boss-kill saves), `mints/` (saves derived from a mint chain), `edits/lab/` (gitignored WIP edits), `edits/golden/` (tracked verified edits). Full definitions and path conventions in `rw/docs/workflow/save-editing.md` §Concepts → "Folder taxonomy and naming."

### Save-load error modal — read the actual outcome, not the modal
The "Save Loading Error (Error code: N)" modal does NOT always indicate a hard failure. It can appear in two distinct scenarios:

- **True failure.** Click OK → routed to fresh-account hero-selection screen. The game now treats the file as unreadable; the next save event overwrites local with fresh-account defaults, wiping unlocks and any other progression. Quit immediately to preserve local.
- **False negative (warning).** Click OK → routed to the Continue / New Game dialog. The save *did* load successfully — the modal was a non-fatal warning about something the loader chose to flag. Game state is intact and the user can proceed.

**Always click through the modal once and observe destination before concluding a test result.** Save-edit experiments must report not "got error 4" but "error 4 → fresh-account" or "error 4 → continue dialog." This applies retroactively: any past test report stating only "got the error modal" is ambiguous and may need re-running with click-through to determine actual outcome.
