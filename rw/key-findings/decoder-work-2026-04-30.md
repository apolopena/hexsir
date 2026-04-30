# DecoderWork — `.gen` and `Profile_1.ob` decoder

**Created:** 2026-04-30 · **Format target:** the `Cooked` binary serialization used by every `.gen` file in `_Cooking/` and (with a 16-byte header variant) by `Profile_1.ob`.

## Background

Static analysis has confirmed the framing format (`0xAABB1111` class registry → `0xAABB2222`, then object section with same markers) is shared between cooked entity files and save files. The body is plain serialized object graph — no encryption, no compression, no salt. Only divergence is the 16-byte header: `.gen` files carry the ASCII string `"Cooked"`; `Profile_1.ob` has 4 non-text bytes in the same slot, presumed checksum. Full analysis: `save-subsystem.md` ("Modal_Save_Or_Quit.entity.ot decoded" section).

## Tasks

- [ ] **Step 1 — Build `.gen` decoder against Modal_Save_Or_Quit**
  - Add `tools/rerw-src/lib/cooked.py`. Parse header, class registry, object section into a structured tree. Validate: byte-for-byte re-encode of the original must match.
  - Test corpus: `rw/dumps/modal_save_or_quit/Modal_Save_Or_Quit.entity.ot.EntitySettingsResource.gen` (2,856 bytes, 14 classes — small and fast).

- [ ] **Step 2 — Validate against Geppetto herodef**
  - Run the same decoder on Geppetto's `herodef.ot.gen` (18,925 bytes, real game data). Adjust parser for any variant fields that surface.
  - Reference dump for cross-check: `rw/dumps/geppetto/herodef_analysis.txt`.

- [ ] **Step 3 — Read `Profile_1.ob` + Ghidra checksum check (parallel)**
  - Add header variant: skip the 4 mystery bytes at `+0x0C` (no `"Cooked"` magic), then dispatch to the existing body parser. Read-only target: `rw/saves/proofs/geppetto/clean/Profile_1.ob`.
  - Concurrently: find the `.ob` load function in Ghidra, check if those 4 bytes are read+compared, identify the algorithm (CRC32 / FNV / etc.). Determines whether re-encoding for save-edits is feasible without a runtime hook.

## Notes

- Cipher fix landed: `tools/rerw-src/lib/cipher.py` position 40 (`O`) corrected from `#` (unknown) to identity `O`. Empirical confirmation in commit context.
- Step 1 is gated only on writing code; steps 2 and 3 are gated on step 1's parser passing the round-trip test.
- The decoder unlocks analysis on every `.gen` in the game (heroes, items, talents, modals, entity defs) — payoff is much wider than just the save-trigger investigation.
