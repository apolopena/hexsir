# Ravenswatch RE

Reverse engineering work for Ravenswatch (single-player roguelike, OEngine / OSome Studio / PassTech Games). No public documentation, no prior RE work — everything here is original research.

## Canonical state

| Doc | Purpose |
|-----|---------|
| [Save: binary format and edit primitives](../key-findings/save-binary-format.md) | Save record format, verified editable fields, edit procedure, open questions |
| [Save: magical objects (items)](../key-findings/magical-objects.md) | Item record format, edit primitives (SWAP/ADD/REMOVE), engine-validation ceilings (Rules A/B/C) |
| [Save: subsystem architecture and live-trigger map](../key-findings/save-subsystem.md) | Save trigger functions, queue/worker architecture, deterministic-injector recipe |
| [Save: account binding and portability](../key-findings/save-account-binding.md) | Why saves appear "locked" to Steam accounts (it's Steam Cloud, not the game) |

## Documentation

| Doc | Purpose |
|-----|---------|
| [Playbook](playbook.md) | Directory structure, what to track, promotion paths, workflow |
| [Ghidra and WinDbg MCP for WSL](ghidra-windbg-mcp-for-wsl.md) | WSL mirrored-networking fix plus Windows-hosted Ghidra and WinDbg MCP setup for Codex |
| [Tools](tools/README.md) | Tools used for RW work |
| [Frida save tools](../../tools/frida/README.md) | `save_now.js` and `repl.js` — Frida scripts that drive the save subsystem from outside the game. Setup, usage, troubleshooting. |
| [Frida pipeline handoff](../../tools/frida/HANDOFF.md) | **Active investigation.** Discovery context for the in-progress save-on-demand work. Open task: find the prep/serializer function that populates the save buffer before `save_request_sync`. Without this, Frida-triggered saves are partial. |

## Archive

Tabled-track methodology playbooks under [`archive/`](archive/) — preserved for the future read-only monitoring track when per-session ASLR re-discovery becomes practical. Not currently active.

## Quick Reference

- **Source of truth:** `ref/tree-ciphered.txt` — tracked snapshot of game asset structure
- **Sample saves:** `saves/proofs/<hero>/<chapter>/<run-id>/Profile_1.ob`
- **Confirmed mods:** `saves/edits/golden/<hero>/<chapter>/<run-id>/<mod-id>/Profile_1.ob`
- **Cipher tool:** `./tools/rerw decipher <name>` (and `cipher`)

## Skills

- **`rw-triage-report`** (`.claude/skills/rw-triage-report/`) — invoke with "create a triage report for this..." to generate a working analysis document at `rw/triage/` with the required Sources provenance header. See [playbook](playbook.md#triage-documents) for the triage workflow.
