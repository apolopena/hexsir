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

Use `uv run rerw` for normal CLI commands. If `uv run` fails in the agent
sandbox with a read-only `~/.cache/uv` error, prefix the command with
`UV_CACHE_DIR=/tmp/uv-cache`.

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

### Saves are only generated at chapter-boss kills — there is no other save event
Ravenswatch only writes a new `Profile_1.ob` after a chapter boss is defeated. After the boss-kill animation a dialogue offers to save; if the player chooses yes, a save is generated AND the game exits. There is no autosave, no quicksave, no save-on-quit, no save-on-death. Mid-run state, defeats, score-page values, and HUD changes are NOT captured in any new save file.

Implications for save-edit testing:
- We cannot do "edit → swap → play → save → re-inspect" round-trips. Mid-run state changes never make it back to disk.
- Valid observations are limited to (a) HUD values immediately on save load, (b) end-of-run score page after defeat, (c) anything visible during play. None of these produce a new save we can diff against.
- "Verifying" an edit means visually confirming the loaded HUD/score-page reflects the edited value. There is no automated round-trip check beyond the parse-encode byte-equality test on the file itself.
- Reaching a new chapter-boss kill to generate fresh save data is a real-time play investment — typically ~20 minutes of focused play per save. Treat existing proof saves as scarce. Proposing a new save run is NOT off the table, but it must be extremely warranted — strong justification (e.g., the test cannot be done any other way and the resulting save unblocks meaningful progress). Don't suggest a fresh-save test casually.

### Ghidra: decompilation available on request
The game's `Ravenswatch.exe` is loaded in Ghidra and reachable via `mcp__ghidra__*` tools. If decompilation would help answer a question, ask the user before digging — don't assume.

### WinDbg: live debugging available on request
A WinDbg MCP server is registered in `.mcp.json` (port 8000); when running, tools appear under `mcp__windbg__*`. Use only for live-process debugging of the running game (breakpoints, memory inspection, stepping). If the tools aren't loaded, the server isn't up — ask the user to start it. Ask before initiating a debugging session — don't assume.

### Frida: WSL → Windows interop workflow
Frida scripts live at `tools/frida/*.js` in WSL; `frida.exe` runs Windows-side via interop (default path `/mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe`) and loads the WSL absolute path directly on initial invocation. The REPL eats backslashes on `%load` reloads — never reload from the REPL; after any edit, exit Frida and re-launch with a fresh one-liner.

### Ghidra: annotate findings on the spot
This section governs all Ghidra reverse-engineering work. When you identify what something does — even partially — annotate it in Ghidra immediately. Do not batch annotations at session end. Each annotation makes future decompilation more readable for both you and the user, and prevents losing the identification when context drops. The bar is low: partial understanding is worth annotating. `unknown_serializer_at_this+0xc8` is more useful than `FUN_1403b3da0`.

Annotation kinds and the tool to use:

- **Functions** — rename via `mcp__ghidra__rename_symbol` (target_type=function) or `mcp__ghidra__batch_rename`. Convention: snake_case for free functions, `Class_method` or `Class::Method` for members, `Class_vftable` for vtables.
- **Data / globals** — rename via `mcp__ghidra__rename_symbol` (target_type=data). Used for vftables, RTTI, string tables, registries.
- **Function parameters and local variables** — rename via `mcp__ghidra__rename_symbol` (target_type=variable) inside a decoded function. Replace `param_1` with `this` / `stream` / `hero_state`, `local_88` with `count_delta`, `uVar3` with `ingredient_index`.
- **Struct definitions** — when a class layout is understood, define the struct via `mcp__ghidra__struct` (action=create). Once defined, accesses like `*(int *)(this + 0x08)` auto-render as `this->type_id` everywhere the type is applied.
- **Equates / enums** for magic constants — `0xAABB1111` → `MARK_START`, schema-version IDs, ingredient class IDs. Use `mcp__ghidra__types` (action=create_enum).

The "why" of a finding belongs in `rw/key-findings/*.md`, not in Ghidra plate/EOL comments. Ghidra annotations are for symbol-level identity (names, types, structures); narrative context lives in the key-findings docs.

### Save-edit lab base rule — never layer on a failed experiment
New save edits are ALWAYS layered on top of either (a) a golden save, or (b) a proof / verified-success lab save that is a candidate for promotion to golden. NEVER layer a new edit on top of a failed lab variant — that carries dead-end edits forward and confounds the test. If unsure whether a prior lab is a success, ask before using it as the base.

### Save-edit lab naming convention
Lab folder names MUST encode their source/lineage so the layering chain is visible at a glance. Pattern: `<edit-name>__from-<source-name>[__<extra-suffix>]/Profile_1.ob`. The `__from-` separator is a literal double-underscore. Examples:

- `feathers-14__from-test3-mint/` — sets feather field to 14, layered on the test3-silencer-fix-verified mint
- `keys-count-5__from-test3-mint/` — sets keys count subfield to 5, same source
- `mint-feathers-consumed-zero__from-laser-lenses_1-proof__chapter1-stars7/` — output of `rerw mint savefile` with the feathers-consumed-zero recipe step, sourced from the laser-lenses_1 chapter-2 proof, set to chapter 1 with Stars of Fate baseline 7

Use the source's directory name (the leaf, not the full path) as the source identifier. Disambiguate proof vs golden vs mint with a suffix when the leaf name alone could be ambiguous.

### Save-file taxonomy
Three top-level categories under `rw/saves/`:

- `proofs/` — natural unmodified gameplay saves (player reached a chapter-boss kill and saved; no edits applied)
- `mints/` — saves derived from running the mint chain: a proof was minted into a starting save, that mint was loaded and played forward, the player reached another chapter-boss kill and saved. Mint-derived saves are NOT proofs because the mint influenced their starting state.
- `edits/lab/` and `edits/golden/` — work-in-progress edits and promoted/verified-success edits respectively. Both follow the lab naming convention above.

### Save-load error modal — read the actual outcome, not the modal
The "Save Loading Error (Error code: N)" modal does NOT always indicate a hard failure. It can appear in two distinct scenarios:

- **True failure.** Click OK → routed to fresh-account hero-selection screen. The game now treats the file as unreadable; the next save event overwrites local with fresh-account defaults, wiping unlocks and any other progression. Quit immediately to preserve local.
- **False negative (warning).** Click OK → routed to the Continue / New Game dialog. The save *did* load successfully — the modal was a non-fatal warning about something the loader chose to flag. Game state is intact and the user can proceed.

**Always click through the modal once and observe destination before concluding a test result.** Save-edit experiments must report not "got error 4" but "error 4 → fresh-account" or "error 4 → continue dialog." This applies retroactively: any past test report stating only "got the error modal" is ambiguous and may need re-running with click-through to determine actual outcome.
