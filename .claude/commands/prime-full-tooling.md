---
description: Full prime for tooling with generated context
disable-model-invocation: true
---

Read CLAUDE.md then generate tooling context **incrementally** — only regenerate sections for tools that have changed.

Docs in `docs/tools/` are authoritative for usage. Generated files cover only what the docs don't: cross-tool flow, internals, undocumented tools, and an index.

**Two classes of tools** drive everything below (see Step 1 for the tables):
- **Tool Suite** — conform to `docs/tools/coding-standards.md`. Change-tracked. Drive source exploration and per-member sections in `tooling-arch.md`, `tooling-dev.md`, and `tooling-index.md`. Their docs are read at prime.
- **Indexed-only** — skills, scripts, service CLIs. Get one-liner treatment in `tooling-context.md` only (single source of truth — not duplicated in `tooling-index.md`). Their docs are not read at prime. No source exploration, no change tracking.

**File ownership** — avoids redundancy and per-run rewrites:

| File | Owns | Touched when |
|------|------|--------------|
| `tooling-arch.md` | Tool Suite cross-tool flow, artifacts, entry points | Tool Suite `CHANGED`/`NO_MARKER`/`MISSING` |
| `tooling-context.md` | Ecosystem intro, Tool Suite overview, **Indexed-only overview** | Tool Suite regen → intro + Tool Suite; any run → Indexed-only section surgically edited iff drifted from command-file tables |
| `tooling-dev.md` | Tool Suite per-member internals (modules, shared-lib use, tests) | Tool Suite `CHANGED`/`NO_MARKER`/`MISSING` |
| `tooling-index.md` | Tool Suite navigation (doc links) + dev resources + regen + last-generated | Tool Suite `CHANGED`/`NO_MARKER`/`MISSING` |

On a `CLEAN` run with no Indexed-only drift, **zero files are written**.

## Filesystem scope (strict)

**Allowed paths** — the only places this command may read, write, list, or otherwise interact with:
- `tools/` (Tool Suite source)
- `docs/tools/` (authoritative usage docs)
- `.ai/scratch/tooling-context/` (generated pack)
- `CLAUDE.md` (read by harness)
- `.claude/commands/prime-full-tooling.md` and `.claude/commands/prime-quick-tooling.md` (only when Step 0 detects new Main CLIs and asks for permission to edit, or when referencing the canonical user-report format)

**Prohibited** — do not `ls`, `cat`, `grep`, Glob, Read, or otherwise inspect anything outside the allowed paths. In particular, never list or browse `.ai/scratch/` itself (siblings of `tooling-context/`), `.ai/planning/`, `qa/`, or any other project directory. If a step's wording could be interpreted as requiring exploration, interpret it narrowly — do only what the step literally asks for.

## Step 0: Overview and Discovery

1. **Print this exact line before any tool calls** (this line is exempt from Step 4's "no other output" / "no separate summary printed earlier" rules and must appear regardless of verdict):

   ```
   🔧 Priming tooling context — checking for changes…
   ```

2. **List Main CLI wrappers** (Tool Suite only) — run exactly this bash, no additions, no variations:

   ```bash
   for f in tools/*; do [ -f "$f" ] && [ -x "$f" ] && basename "$f"; done | sort
   ```

   Output is a newline-separated list of wrapper names directly under `tools/`. Do not parse the wrappers' contents here; parsing (`*_DIR=`, `exec` line) is deferred to Step 0.5 and runs only for wrappers that turn out to be unknown.

3. **Cross-reference** the listed wrapper names against Group names in the Tool Suite list (in-memory — no tool call). Indexed-only is not scanned — its entries (skills, Service CLIs, Scripts) are manually maintained. Retain `Listed` and `New from scan` counts for Step 4's unified report.

4. **If no new Main CLIs**: continue to Step 1.

5. **If new Main CLIs found** (detection loop):
   - For each unknown wrapper, `Read` it and extract the source directory (`*_DIR=` variable) and exec line. Convert to a proposed bullet entry for the Tool Suite list.
   - List each with its proposed bullet entry.
   - Print the manual-add block below (in case the user wants to add Indexed-only entries at the same time).
   - Ask: "Write these entries into `.claude/commands/prime-full-tooling.md` (Tool Suite section)?"
   - If confirmed: edit this command file, then STOP and suggest restarting Claude and rerunning `/prime-full-tooling`.
   - If declined: continue with existing groups only.

   **Manual-add block** (also appears inside the Step 4 unified report):
   ```
   To add an Indexed-only entry, append a bullet to the Indexed-only list
   in .claude/commands/prime-full-tooling.md:

     - **groupname**
       - kind: Service CLI | Skill | Scripts
       - location: <path(s)>
       - doc: <path or none>

   Then rerun /prime-full-tooling.
   ```

## Step 1: Tool Groups

Two sections below. Both use nested bullet lists (no MD tables) so entries are easy to read and hand-edit.

### Tool Suite (full participants)

These conform to `docs/tools/coding-standards.md`. They drive change detection, source exploration, and the three Tool-Suite-owned context files plus the Tool Suite portion of `tooling-context.md`.

- **hexsir**
  - paths: `tools/hexsir-src/cli.py`, `tools/hexsir-src/commands/`, `tools/hexsir-src/lib/`, `tools/hexsir`
  - doc: `rw/docs/tools/hexsir.md`
- **rerw**
  - paths: `tools/rerw-src/cli.py`, `tools/rerw-src/commands/`, `tools/rerw-src/lib/`, `tools/rerw`
  - doc: `rw/docs/tools/rerw.md`
- **scafcli**
  - paths: `tools/scafcli-src/cli.py`, `tools/scafcli-src/commands/`, `tools/scafcli-src/lib/`, `tools/scafcli`
  - doc: `docs/tools/scafcli.md`

### Indexed-only

These do NOT conform to tool-suite standards. They appear only in `tooling-context.md`'s Indexed-only section (not in `tooling-index.md`). Their docs are not read at prime. They do not participate in change detection.

- **scripts**
  - kind: Scripts
  - location: `scripts/run-tests.sh`
  - doc: none

**Adding an indexed-only group manually** (service CLIs, scripts, or any skill Step 0 didn't pick up):
1. Open `.claude/commands/prime-full-tooling.md`
2. Add an entry to the Indexed-only list above using the same structure:
   ```
   - **groupname**
     - kind: Service CLI
     - location: <path(s)>
     - doc: <path or none>
   ```
   - `kind` values: `Service CLI`, `Skill`, `Scripts`
   - `location`: one or more paths (comma-separated) where the tool or its wrapper lives
   - `doc`: path to a doc if one exists, else `none`
3. Save and rerun `/prime-full-tooling`. On the next run, the Indexed-only section of `tooling-context.md` will be detected as drifted and surgically updated.

### Change Detection (Tool Suite only)

Run **one** bash invocation that returns a verdict. Do not split across multiple calls. Trust the first verdict — do not "re-verify" unless the output is ambiguous.

**Shell-portability note**: this project's default shell is zsh, which does **not** word-split unquoted variable expansions the way bash does. Do not store paths in a shell variable and expect splitting — inline them directly as separate `--` args, exactly as shown below.

```bash
MARKER=.ai/scratch/tooling-context/.last-gen-commit
if [ ! -f "$MARKER" ]; then
  echo "NO_MARKER"
elif [ ! -f .ai/scratch/tooling-context/tooling-arch.md ] \
  || [ ! -f .ai/scratch/tooling-context/tooling-context.md ] \
  || [ ! -f .ai/scratch/tooling-context/tooling-dev.md ] \
  || [ ! -f .ai/scratch/tooling-context/tooling-index.md ]; then
  echo "MISSING_CONTEXT_FILES"
elif [ "$(cat "$MARKER")" = "$(git rev-parse HEAD)" ] \
  && [ -z "$(git status --porcelain -- \
       tools/hexsir-src/cli.py tools/hexsir-src/commands tools/hexsir-src/lib tools/hexsir \
       tools/rerw-src/cli.py tools/rerw-src/commands tools/rerw-src/lib tools/rerw \
       tools/scafcli-src/cli.py tools/scafcli-src/commands tools/scafcli-src/lib tools/scafcli)" ]; then
  echo "CLEAN"
else
  echo "CHANGED"
  git diff --name-only "$(cat "$MARKER")..HEAD" -- \
       tools/hexsir-src/cli.py tools/hexsir-src/commands tools/hexsir-src/lib tools/hexsir \
       tools/rerw-src/cli.py tools/rerw-src/commands tools/rerw-src/lib tools/rerw \
       tools/scafcli-src/cli.py tools/scafcli-src/commands tools/scafcli-src/lib tools/scafcli
  git status --porcelain -- \
       tools/hexsir-src/cli.py tools/hexsir-src/commands tools/hexsir-src/lib tools/hexsir \
       tools/rerw-src/cli.py tools/rerw-src/commands tools/rerw-src/lib tools/rerw \
       tools/scafcli-src/cli.py tools/scafcli-src/commands tools/scafcli-src/lib tools/scafcli
fi
```

**Keep this path list in sync** with the Tool Suite `paths:` entries above. When a Tool Suite member is added/removed or a member's paths change in Step 1, update both lists in the same edit.

Verdicts and what to do:

- **`CLEAN`** → Tool Suite unchanged. This is the hot path — it must be fast.
  1. **Skip Steps 2, 3, and 4 entirely.** No regeneration, no generation-side doc reads, no marker update, no unified report, no summary table.
  2. Hand off to `/prime-quick-tooling`: read `.claude/commands/prime-quick-tooling.md` and follow its directives verbatim. Its parallel-read batch already includes `tooling-context.md`, so the drift check below does NOT need its own Read.
  3. **Indexed-only drift check (in-memory, no extra tool call)**: after prime-quick-tooling's reads complete, `tooling-context.md` is in context. Compare its `## Indexed-only` section against the Indexed-only list in this command file. If drifted → `Edit` only that section before the user report prints. If identical → no write.
  4. Done. No "Verdict: CLEAN" line, no regeneration summary, no closing emoji beyond what prime-quick-tooling prints.
- **`NO_MARKER`** or **`MISSING_CONTEXT_FILES`** → full regeneration for all four files. Proceed through Step 2.
- **`CHANGED`** → identify changed members from the bash output, regenerate their sections in `tooling-arch.md` / `tooling-dev.md` / `tooling-index.md` / `tooling-context.md` (intro + Tool Suite portion). The Indexed-only section of `tooling-context.md` still follows the drift-check rule above. Proceed through Step 2.

**Marker update**: after Step 3, when any Tool-Suite-owned file was written this run, run `git rev-parse HEAD > .ai/scratch/tooling-context/.last-gen-commit`. Skip the marker update on `CLEAN` (it's already current); Indexed-only-only edits also skip it since the marker tracks Tool Suite commit state, not Indexed-only drift.

## Step 2: Incremental Update Logic (Tool Suite only)

**Only enter Step 2 if the verdict in Step 1 was `NO_MARKER`, `MISSING_CONTEXT_FILES`, or `CHANGED`.** On `CLEAN`, Step 1 already handed off to `/prime-quick-tooling` — you are not here.

Indexed-only entries don't go through change detection or source exploration.

**Read the cross-cutting docs once, fully** (needed for generation context — every doc listed here and anywhere else in this command is read end-to-end, never sampled or partially read):
- `docs/tools/README.md` — tool index and pipeline overview
- `docs/tools/coding-standards.md` — shared-lib conventions, tool patterns
- `docs/tools/creating-a-new-tool.md` — scaffold-driven new-tool workflow

**For each changed Tool Suite group with a `doc` path**: read only the `doc:` file(s), fully. They are authoritative for usage (env vars, commands, flags, examples). Do **not** read `aux_doc:` entries — those are deep-reference material linked from `tooling-index.md` but contain no summary content needed for generation. Only explore source for gaps not covered by the primary doc: module paths, shared-lib call sites, test file locations, internal flow.

**For each changed Tool Suite group without a `doc` path**: explore source fully.

Generation scope (derived from the Step 1 verdict):

- **`NO_MARKER` / `MISSING_CONTEXT_FILES`**: full generation for ALL Tool Suite members across all four files.
- **`CHANGED`**: read existing context files, regenerate sections for changed members only, preserve unchanged sections verbatim.

**EXCLUDE**: git-ai.sh, observability-*.sh, detailed script internals

## Step 3: Update Context Files

**First action of Step 3** — run this bash command verbatim, no additions, no variations. It ensures the target directory exists and clears any stale context files so `Write` can create fresh files without Claude Code's Read-before-Write guardrail firing. Scope is entirely inside `tooling-context/`:

```bash
mkdir -p .ai/scratch/tooling-context && rm -f .ai/scratch/tooling-context/tooling-*.md
```

Do not `ls` the directory afterward. Do not inspect siblings. Proceed directly to writing the four context files.

**Scope note for `CHANGED`**: the `rm -f` above would also apply on `CHANGED`, which is wrong — CHANGED must preserve unchanged sections by reading the existing files. Run the command above **only** on `NO_MARKER` and `MISSING_CONTEXT_FILES`. On `CHANGED`, skip this step entirely; Read the existing context files as Step 2 requires and use `Edit` / surgical `Write` per file.

All files live in `.ai/scratch/tooling-context/`.

### 1. `tooling-arch.md` (Tool Suite only)
Cross-tool content not in any single doc. Update only sections for changed Tool Suite members:
- Pipeline & wrapping relationships (e.g., evalcli wraps adcli; syscli seeds data consumed by adcli/evalcli)
- Artifact I/O paths across the pipeline (where eval runs land, where insight JSON writes)
- Entry point map per member: bash wrapper → Python module

Do not duplicate individual tool usage — docs cover that.

### 2. `tooling-context.md` (Tool Suite + Indexed-only)
Single-source-of-truth ecosystem overview. Source for the Step 4 unified report.

Contents (compact, at-a-glance — no commands, flags, or examples):
- Intro: 2-3 sentences. Lead with the purpose: a standardized, automation-friendly ecosystem so CLI tools are built uniformly rather than ad hoc. Name what it covers (development, validation, evaluation, scaffolding, deployment of agent-focused workflows). Mention that the Tool Suite enforces shared conventions and that Indexed-only entries are related helpers included for discoverability. Keep each sentence to one idea — write it to be read aloud.
- Tool Suite: bullet list — `name` — one-line purpose.
- Indexed-only: bullet list — `name` (Kind) — one-line purpose — doc link in parens if present.

**Regeneration rules (critical — this is the hot path for fast reprimes)**:
- **Intro + Tool Suite sections**: regenerated only on `NO_MARKER` / `MISSING_CONTEXT_FILES`, or on `CHANGED` for the specific members that changed. Never touched on `CLEAN`.
- **Indexed-only section**: on every run, extract the current section from the file, compare against the command-file Indexed-only tables. If identical → do not write. If drifted → use `Edit` to replace only that section (not `Write`).

One-line purposes come from the relevant doc preamble when present; from a brief source peek when not. Doc preamble reads only happen when the section is being regenerated — not on the drift check, which is a pure string comparison.

### 3. `tooling-dev.md` (Tool Suite only)
Per-member internals. Update only sections for changed members:
- Module file paths
- Shared-lib call sites (which libs used where)
- Test file locations

Do not duplicate `docs/tools/coding-standards.md` or `docs/tools/creating-a-new-tool.md`. Reference them by path.

### 4. `tooling-index.md` (Tool Suite only — no Indexed-only)
Persistent navigation map. Read at prime time; serves as a compression-resilient pointer hub. **Never contains Indexed-only** (that lives in `tooling-context.md`).

**Rule**: links + one-line explanations only. No re-narration of doc content.

**Structure** (headers + short orienting sentences + lists/tables; no conclusion):

```
# Tooling Context Index

[Intro: 2-3 sentences — what this context pack is (contents of .ai/scratch/tooling-context/),
how it's organized, and when to regenerate. Include: "Indexed-only entries live in
tooling-context.md — see that file."]

## Tool Suite
[From Tool Suite. One bullet per group: name — one-line purpose — Doc link(s) or "(undocumented; see tooling-dev.md)". Link both `doc:` and `aux_doc:` paths from the Step 1 Tool Suite config so auxiliary references stay discoverable.]

## Cross-Tool Flow
One sentence + pointer to tooling-arch.md.

## Development Resources
[Bullets: docs/tools/coding-standards.md, creating-a-new-tool.md, scaffold-upkeep.md, tooling-dev.md]
One line per item on when to reach for it. Applies to Tool Suite development; Indexed-only groups develop inside their own ecosystems.

## Regeneration
Force-regen command: `rm -rf .ai/scratch/tooling-context/` then rerun `/prime-full-tooling`.
One line on when to do this (changed tool conventions, stale state, suspected drift).

## Last Generated
Commit hash from `.last-gen-commit` + generation date.
```

**Regeneration rules**: same as `tooling-arch.md` and `tooling-dev.md` — only touched on `NO_MARKER` / `MISSING_CONTEXT_FILES` / `CHANGED`. Never on `CLEAN`.

## Step 4: Unified Report (non-CLEAN only)

**Skip this step entirely on `CLEAN`** — Step 1 already handed off to `/prime-quick-tooling`. Step 4 applies only to `NO_MARKER`, `MISSING_CONTEXT_FILES`, and `CHANGED` runs, where a regeneration actually happened and the user needs to see what changed.

**No prime reads.** Do not re-read anything at this step.
- The four context files were just written in Step 3 — their content is already in context via the `Write` calls.
- Cross-cutting docs (`docs/tools/README.md`, `coding-standards.md`, `creating-a-new-tool.md`) and per-group docs for any changed members were read in Step 2.
- On `CHANGED`, per-group docs for **unchanged** members are intentionally not primed. The four context files (especially `tooling-index.md`) point to them; open on demand only if the task actually needs that tool's deep usage detail. Do not preload.

Proceed directly to the unified report.

**Print ONE unified report** — a single block, no other output after Step 3 completes.

The block has two parts, in order, with no interleaving:

1. **Regen extras** — scan summary, manual-add block, regeneration summary. These are unique to prime-full-tooling.
2. **User report** — emitted verbatim per the canonical format in `/prime-quick-tooling` § User Report Format. Must match `/prime-quick-tooling`'s output byte-for-byte in the header, body, and closing literals.

### Regen extras (emit first)

**Summary table** (same row format every run):

```
Class           Listed   New from scan   Scan coverage
Tool Suite         N          M          tools/*
Indexed-only       P         N/A         none (manual)
```

- `Listed` = count of entries in the respective Step 1 list.
- Tool Suite `New from scan` = count of discovered Main CLIs not yet in the Tool Suite list (retained from Step 0).
- Indexed-only `New from scan` = literal `N/A`.
- `Scan coverage` cells are the literal strings shown.

**Manual-add block** (same text as Step 0's):

```
To add an Indexed-only entry, append a bullet to the Indexed-only list
in .claude/commands/prime-full-tooling.md:

  - **groupname**
    - kind: Service CLI | Skill | Scripts
    - location: <path(s)>
    - doc: <path or none>

Then rerun /prime-full-tooling.
```

**Regeneration summary**:
- One line: "Verdict: `<CLEAN|CHANGED|NO_MARKER|MISSING_CONTEXT_FILES>`."
- Tool Suite members detected as changed this run (or "none — primed from cache").
- Per context file: `written` / `preserved` / `section-edited` / `untouched`.

### User report (emit second, verbatim per canonical)

Follow `/prime-quick-tooling` § User Report Format exactly. No additions, no omissions, no wrapping headings. The three parts — header (`🧰 🛠️ 🧪`), body (from `tooling-context.md` `## Intro` through `## Indexed-only`), closing (`🔧 Tooling primed and ready!`) — appear consecutively and unmodified.

No prose outside this unified block. No separate summary printed earlier. No handoff narration.
