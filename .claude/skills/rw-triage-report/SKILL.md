---
name: rw-triage-report
description: Use when the user asks to "create a triage report" or otherwise mentions making a triage report/document for Ravenswatch RE analysis work. Creates a working analysis document at `rw/triage/` with a Sources provenance header per the RW playbook workflow.
---

# rw-triage-report

Creates a triage document for in-flight Ravenswatch RE analysis. Triage documents are working analyses that may eventually be split — confirmed findings get promoted to `rw/key-findings/`, unresolved items stay or move to `rw/dumps/`.

## When to invoke

Trigger on phrases like:
- "create a triage report"
- "triage report for this"
- "make a triage doc"

## What it does

1. **Determine sources.** From the conversation context, identify which files were analyzed (saves, harvested binaries, dumps, etc.). If unclear, ask the user.

2. **Determine filename.** Use a kebab-case slug describing the subject (e.g., `geppetto-save-format.md`, `entity-binary-strings.md`). Ask if not obvious.

3. **Create the file** at `rw/triage/<slug>.md`. Required sections only — omit any section without real content:

**Always include:**

```markdown
# <Title>

**Status:** triage
**Created:** <YYYY-MM-DD>

## Sources

- <relative path to source file 1>
- <relative path to source file 2>
```

**Then include only the sections that apply:**

- `## Confirmed Findings` — facts with evidence. Skip if there's nothing confirmed yet.
- `## Unresolved` — open questions, partial leads. Skip if everything is confirmed.
- `## Notes` — context, methodology. Skip if not adding value.

A triage doc with only confirmed findings is fine. A triage doc with only unresolved questions is fine. Don't pad sections to fit a template — empty or near-empty sections become noise.

4. **Fill in only the sections with real content** based on the conversation. Be honest about what's confirmed vs speculative — that's the whole point of triage.

5. **Use relative paths** for sources (relative to repo root), so they remain valid as files move.

## Workflow context

Triage documents are tracked in git. They sit between raw `dumps/` (untracked working outputs) and curated `key-findings/` (confirmed artifacts).

Promotion path: as findings firm up, extract them into focused docs in `rw/key-findings/`. The triage document can shrink or be deleted as its content gets absorbed elsewhere.

See `rw/docs/playbook.md` for the full directory structure and conventions.

## Constraints

- Do NOT invent findings. Only document what the conversation supports.
- Do NOT promote anything to `key-findings/` from this skill — that's a separate manual step.
- Always include the Sources section, even if it's a single file.
- Keep the file tight. Triage docs accumulate cruft fast; don't add filler.
