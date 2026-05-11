# Scaffold Upkeep

[← Back to Tools](README.md)

As tools are developed, patterns emerge that should be folded back into scafcli so future tools inherit them automatically. This document covers when to do that, what goes where, and how to verify the result.

Failing to fold in proven patterns promotes duplication, and duplication silently diverges over time. But premature extraction creates abstractions nobody needs. The goal is to be prudent: extract when a pattern has proven itself in two or more tools, not before.

For the conventions and patterns themselves, see [coding-standards.md](coding-standards.md). For scaffold-driven tool creation, see [creating-a-new-tool.md](creating-a-new-tool.md). For the scaffold CLI reference, see [scafcli](scafcli.md).

## What goes where

- **Scaffold templates** — directory layout, boilerplate code, test foundations. If every new tool should have it from day one, it belongs in the template.
- **Shared libraries** — reusable runtime code. If tools call it at runtime, it's a library, not a template.
- **Coding standards** — conventions and rules. If it's about how to write code rather than what code to generate, document it here.

Quite often, upkeep is a template change — updating files in `tools/scafcli-src/data/templates/` so new tools get the pattern from day one. Changes to scafcli's core logic are less common and typically involve new commands or codegen behavior.

## When to extract

1. **Two-tool rule.** A pattern is a candidate when it has proven itself in two or more tools. One tool with a clever approach is an experiment. Two tools with the same approach is a pattern.
2. **Stability.** The pattern should be settled — not actively being redesigned. If you're still iterating on the shape, keep it in the tool.
3. **Clear boundary.** The extracted code should have an obvious API surface. If you can't describe what it does in one sentence, it's not ready.

## Process

1. Build the pattern in your tool first. Ship it, test it, live with it.
2. When a second tool needs the same pattern, extract it.
3. Determine the destination:
   - Code that tools import at runtime → **shared library** (new or existing in `tools/shared/`)
   - Boilerplate that every new tool should start with → **scaffold template** (in `tools/scafcli-src/data/templates/`)
   - A rule about how to write code → **coding standards** (in `docs/tools/coding-standards.md`)
4. Implement the extraction. For shared libraries, follow the packaging and versioning conventions in [coding-standards.md > Shared Libraries](coding-standards.md#part-2-shared-libraries).
5. Diff the updated scaffold templates against affected tools before merging.
6. Update documentation:
   - [coding-standards.md](coding-standards.md) if the pattern introduces a new convention
   - [creating-a-new-tool.md](creating-a-new-tool.md) if it changes what scafcli generates

## Examples of past extractions

| Pattern | Origin | Destination | Trigger |
|---------|--------|-------------|---------|
| `display-lib` output functions | adcli inline code | `tools/shared/display-lib/` | evalcli needed the same output helpers |
| `repl-lib` REPL dispatch | adcli `cli.py` | `tools/shared/repl-lib/` | scaffold needed generic REPL for new tools |
| `tree-lib` tree rendering | scafcli + syscli inline | `tools/shared/tree-lib/` | three tools had duplicate tree-drawing code |
| `_cmd` suffix convention | emerged in adcli | coding-standards + scaffold template | adopted across all tools, codified as standard |
| `[tool.coverage.run] omit` | added per-tool manually | scaffold template `pyproject.toml` | every tool needed the same omit pattern |
