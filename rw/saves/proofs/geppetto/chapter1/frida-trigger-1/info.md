# frida-trigger-1 (Frida-triggered chapter-1 save)

## Provenance

- **Source path:** clean baseline `rw/saves/proofs/geppetto/clean/Profile_1.ob` (md5 `e326854ea65c0e710543116f5e84acb1`)
- **Lineage chain:** clean baseline → swapped into game → New Game → Geppetto / chapter 1 / starting talent → killed at least one monster → Frida-triggered save
- **Edit name:** `frida-trigger-1`
- **md5 (full):** `48c24953cc845b7f5304e0268caf23d6`
- **File size:** 71,644 bytes
- **Date:** 2026-04-29 20:41

## Reproduction recipe

This file was produced by the Frida save-trigger pipeline, not by `rerw`. Reproduction:

1. `rerw swap savefile --source rw/saves/proofs/geppetto/clean/Profile_1.ob` (game closed; clean baseline now in `_Save/`).
2. Launch Ravenswatch. Click New Game, pick Geppetto, start chapter 1, pick a starting talent, kill at least one monster, pause.
3. From WSL bash, drive `tools/frida/save_now.js` via `frida.exe` interop:
   ```bash
   FRIDA="/mnt/c/Users/<USER>/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe"
   cp /home/<USER>/repos/work/ravensmith/tools/frida/save_now.js \
      /mnt/c/Users/<USER>/AppData/Local/Temp/save_now.js
   printf 'go()\nexit\n' | "$FRIDA" -n Ravenswatch.exe \
      -l 'C:\Users\<USER>\AppData\Local\Temp\save_now.js'
   ```
4. The script scans the heap, finds the `oCDtRootGs` instance, and calls `save_request_sync(NULL, instance + 0x1928)`. The engine writes the in-memory state to `Profile_1.ob`.
5. Copy the resulting `_Save/Profile_1.ob` into this directory.

Heap addresses are per-launch; this exact byte content is single-session.

## Verified in-game

- Date: 2026-04-29
- File written, mtime updated, CRC valid.
- Game UI displayed "Now Saving" during the Frida call.
- **File is INCOMPLETE.** On relaunch the engine shows only "New Game" — no "Continue" — because `save_request_sync` only enqueues a write of bytes already at `job+0x30`, and the natural-save preparation step that populates that buffer with full run state was bypassed.
- Analysis vs working chapter-2 saves: 0 real `tag=0x1a` item records; run-state body items count = 0; catalog records / hero GUID / picked talent ARE present.

This file should NOT be modified. It exists as a proof artifact for the Frida save-trigger mechanism. The hardware-breakpoint task to find the missing prep function lives in [`rw/findings/frida-pipeline-hardware-breakpoint.md`](../../../../findings/frida-pipeline-hardware-breakpoint.md).
