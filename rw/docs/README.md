# Ravenswatch RE

Reverse engineering work for Ravenswatch (single-player roguelike, OEngine / OSome Studio / PassTech Games). No public documentation, no prior RE work — everything here is original research.

## Canonical state

| Doc | Purpose |
|-----|---------|
| [Save: binary format and edit primitives](../key-findings/save-binary-format.md) | Active key finding — save record format, verified editable fields, edit procedure, current open questions |

## Documentation

| Doc | Purpose |
|-----|---------|
| [Playbook](playbook.md) | Directory structure, what to track, promotion paths, workflow |
| [Tools](tools/README.md) | Tools used for RW work |

## Archive

Tabled-track methodology playbooks under [`archive/`](archive/) — preserved for the future read-only monitoring track when per-session ASLR re-discovery becomes practical. Not currently active.

## Quick Reference

- **Source of truth:** `ref/tree-ciphered.txt` — tracked snapshot of game asset structure
- **Sample saves:** `saves/proofs/<hero>/<chapter>/<run-id>/Profile_1.ob`
- **Confirmed mods:** `saves/edits/golden/<hero>/<chapter>/<run-id>/<mod-id>/Profile_1.ob`
- **Cipher tool:** `./tools/rerw decipher <name>` (and `cipher`)

## Skills

- **`rw-triage-report`** (`.claude/skills/rw-triage-report/`) — invoke with "create a triage report for this..." to generate a working analysis document at `rw/triage/` with the required Sources provenance header. See [playbook](playbook.md#triage-documents) for the triage workflow.
