# Ravenswatch findings

All Ravenswatch RE findings, in any state. Each doc carries a `**Status:**` line at the top: `in-progress`, `confirmed`, or `archived`. Promotion is editing the status line in place — files do not move between directories.

## Index

- **[STATUS.md](STATUS.md)** — auto-generated manifest of every finding's current status. Regenerate with `/findings-status`.

## Workflow

- Status `in-progress` — claims not yet independently verified. New findings always seed here.
- Status `confirmed` — claims verified by lab edit, in-game readback, or independent re-derivation. Promotion is a one-line edit; no `git mv`.
- Status `archived` — superseded by another finding or rendered obsolete by code/CLI. Demotion adds a banner explaining what replaced it; the file stays at the same path so existing cross-references keep working.

The `**Status:**` line MUST match `^\*\*Status:\*\* (in-progress|confirmed|archived)$` exactly. The `/findings-status` command greps for that pattern; non-matching lines surface as `?` rows in the manifest.

For end-to-end status semantics (when to promote, when to archive, what a banner looks like), see [`../docs/workflow/README.md`](../docs/workflow/README.md). For naming and writing conventions across all `rw/` directories, see [`../docs/README.md` §Doc conventions](../docs/README.md).

## Adding a new finding

Use the `rw-findings-report` skill — invoke with "create a findings report for this..." (or the legacy "create a triage report ..."). The skill enforces the Sources header and seeds `**Status:** in-progress`. Do not hand-roll new findings — the template prevents drift.

## Vocabulary

Standard terms for talents, items, seeds, and indexing live in [`../docs/terminology/README.md`](../docs/terminology/README.md). Read before writing about these domains.
