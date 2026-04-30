# First Frida-triggered save — proof artifact

**Date:** 2026-04-29 20:41
**File:** `Profile_1.ob` (71,644 bytes, md5 `48c24953cc845b7f5304e0268caf23d6`)
**Source:** clean baseline `rw/saves/proofs/geppetto/clean/Profile_1.ob` (md5 `e326854ea65c0e710543116f5e84acb1`)

## How this file was produced

1. Clean baseline (`Profile_1.ob`, 69,459 bytes, never-played state) was swapped into Ravenswatch's `_Save\` directory via `tools/rerw swap savefile`.
2. Ravenswatch was launched. User clicked New Game, picked Geppetto, started chapter 1, picked starting talent, killed at least one monster, paused.
3. From WSL bash, `tools/frida/save_now.js` was invoked via `frida.exe` interop:
   ```bash
   echo 'go()' | frida.exe -n Ravenswatch.exe -l save_now.js
   ```
4. The script scanned the heap, found the `oCDtRootGs` instance at `0x2ba502214a0`, and called `save_request_sync(NULL, 0x2ba50222dc8)`.
5. The engine's saves manager wrote the current in-memory state to `Profile_1.ob`.

This file therefore represents the in-memory chapter-1 run state at the moment of the Frida-triggered save. Difference from the clean baseline = whatever the engine populated during the new-game start + 1 talent pick + brief gameplay.

## Significance

This is the first proof that:
- The Frida save **mechanism** works end-to-end on this Ravenswatch build (file written, mtime updated, CRC valid).
- The decoded save subsystem (`save_request_sync` at `image_base + 0x6797b0`, data source class `oCDtRootGs`, job at instance + 0x1928, etc.) is correctly understood at the I/O layer.

⚠️ **Critical caveat — this file is INCOMPLETE:**

After saving, the engine did NOT recognize this file as a continuable save (relaunching showed only "New Game", no "Continue"). Analysis vs working chapter-2 saves:
- 0 real `tag=0x1a` item records (the file has 56 byte-pattern matches but none with proper close markers — false positives).
- Run-state body items count = 0 (chapter 2 has 21).
- Catalog records, hero GUID, and the picked talent ARE present.

**Why it's incomplete:** `save_request_sync` only enqueues a write of bytes already at `job+0x30`. The natural save chain has a **prep function** that walks current run state and serializes it into that buffer before triggering the save. We bypassed that prep step. The buffer at the moment of our trigger held only catalog + hero header + talent (whatever was always-on-populated), not the live run state.

See `tools/frida/HANDOFF.md` "Find the prep function" section for the next investigation needed to unlock complete saves.

This file should NOT be modified. Future Frida-triggered saves (after the prep gap is closed) will produce different bytes; they belong in their own `frida-trigger-N` proof folders.

## Static offsets used (image-base relative)

| Offset | Symbol |
|---|---|
| `+0x1c6830` | `oCDtRootGs::vftable[0]` (typedesc-getter; the unique discriminator) |
| `+0x6797b0` | `save_request_sync` |
| `+0x14475a0` | `g_oCDtRootGs_typedesc` storage |

| Field offset within data_source | Field |
|---|---|
| `+0x1928` | embedded IO job struct |
| `+0x19a4` | u32 pending-save sequence |
| `+0x19a8` | u32 completed-save sequence |
| `+0x19ac` | u8 result code |
| `+0x1ef4` | u8 saves-disabled flag |

## Cross-references

- `tools/frida/save_now.js` — the script that triggered this save
- `tools/frida/HANDOFF.md` — how the discovery worked
- `rw/key-findings/save-subsystem.md` — full save subsystem map
