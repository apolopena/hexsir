# Bun — Lockfile Format

> **Source:** https://bun.sh/docs/install/lockfile (redirects to bun.com/docs/install/lockfile)
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Resolve PRP-7's `bun.lockb` vs `bun.lock` acceptance check.

## Current Format

Running `bun install` creates `bun.lock` (text-based).

> "Bun v1.2 changed the default lockfile format to the text-based `bun.lock`."

## Migration Path

Existing binary `bun.lockb` lockfiles can be migrated:

```bash
bun install --save-text-lockfile --frozen-lockfile --lockfile-only
# then delete bun.lockb
```

## Automatic Migration of Other Lockfiles

When running `bun install` in a project without `bun.lock`, Bun auto-migrates from:

- `yarn.lock` (v1)
- `package-lock.json` (npm)
- `pnpm-lock.yaml` (pnpm)

Original lockfile is preserved; remove manually after verification.

## Should the Lockfile Be Committed?

> "Yes"

## Notes for PRP-7

- PRP-7 must accept `bun.lock` (text), not `bun.lockb` (binary, deprecated).
- The earlier rationale for pinning `bun@1.1.38` (to keep binary lockfile) is reversed; pin the latest stable bun and accept text lockfiles.
- Verified latest bun: **1.3.13** (GitHub releases, 2026-05-04). PRP-7 should pin `bun@1.3.13` or higher.
- Acceptance check: `test -f app/ravensmith/bun.lock` (drop the `bun.lockb` fallback).
