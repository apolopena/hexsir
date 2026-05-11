# Development Cycle

[← Back to Agentic Workflow](README.md)

The full cycle for planning, implementing, and shipping work with AI assistance.

## The Cycle

```
propose → peer review → generate spec → peer review → summary + test steps → execute → validate → commit → changelog
```

### 1. Propose

Write a proposal in `.ai/planning/prp/proposals/`. A proposal defines what, why, how, success criteria, affected files, and implementation steps. Use the naming convention `{CODE}_{description}.md` (e.g., `POST-IMPL-12_new-feature.md`).

### 2. Peer Review (Proposal)

Run `/peer-review-plan` on the proposal. Address all blockers and major findings. Repeat until clean.

### 3. Generate Spec

Run `/generate-prp .ai/planning/prp/proposals/{proposal-file}`. This creates an instance in `.ai/planning/prp/instances/` — a detailed, executable spec. The instance must be larger than the proposal (it expands, not summarizes).

### 4. Peer Review (Spec)

Run `/peer-review-plan` on the generated instance. This catches implementation-level issues the proposal review missed. Repeat until clean.

### 5. Summary + Test Steps

Before execution, create two files in `.ai/scratch/`:

- `{CODE}_summary.md` — overview of what will be built, key decisions, architecture
- `{CODE}_test-steps.md` — step-by-step validation plan: unit test commands, smoke tests, manual verification steps, expected results

These define "done" before any code is written. The AI implementer uses the test steps to validate its own work during execution. This is what makes the loop self-closing — acceptance criteria exist before implementation begins.

### 6. Execute

Run `/execute-prp .ai/planning/prp/instances/{instance-file}`. The AI implements the spec step-by-step, running validation commands from the test steps after each phase.

### 7. Validate

Run the full validation suite:

```bash
ruff format . && ruff check .    # Lint (format first, then check)
./scripts/run-tests.sh           # All tests
```

Plus any smoke tests defined in the test steps.

### 8. Commit

Reference the task code in the commit message. Keep messages under 60 characters, imperative mood.

### 9. Changelog

Dispatch Pedro (`update changelog`) to add entries for the completed work.

## Task Codes

| Code | Purpose |
|------|---------|
| `POST-IMPL-X` | Substantial implementations (new features, new tools) |
| `MAINT-X` | Maintenance (fixes, tweaks, small enhancements) |
| `REFACT-X` | Refactors (architectural changes, decoupling) |

Check `.ai/TASKS.md` for the next available number.

See [Plan-Driven Development](../procedures/plan-driven-development.md) for the methodology and philosophy behind this system.

## When to Skip PRP

Not all work requires the full cycle.

**Use direct execution when:**
- Work is clear — you can execute without detailed planning
- Small-to-medium scope — single file or a few files, no architectural decisions
- No AI context transfer needed — you're doing the work yourself

**Direct execution workflow:**
1. Do the work
2. Commit and push
3. Update `.ai/TASKS.md` (Done section)

**Examples:** bug fixes with obvious solutions, small refactors, config changes, documentation updates.

**Use full PRP when:**
- Multiple files with interdependencies
- Architectural decisions needed
- Complex logic requiring step-by-step breakdown

## Idempotency

- `/generate-prp` skips rows with existing PRP instances
- Safe to re-run commands

## Validation Pattern

The self-closing loop works because validation is baked into the cycle:

1. **Test steps written before code** — forces definition of done upfront
2. **Per-phase validation** — unit tests run after each implementation phase
3. **Lint as a gate** — `ruff format` then `ruff check`, never `--check` on format
4. **Smoke tests** — manual verification after unit tests pass
5. **The loop doesn't close until green** — specs define validation commands, execute-prp runs them

This pattern produces tight specs that actually work because the validation is baked into the cycle, not bolted on. The specs are highly technical because they know they'll be machine-verified. The summary and test steps created before execution are proven to strengthen implementation quality — they give both human and AI implementers clear acceptance criteria before a single line of code is written.
