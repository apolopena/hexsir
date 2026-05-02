# held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof

**Promoted to golden:** 2026-05-01
**Hash (SHA-256, full):** `21821a19343e486111fe46e10dd3266be1136902c849fdcf9f0cd62a075c88c6`
**Size:** 75065 bytes

## Provenance

Single-byte-range patch on top of the canonical chapter-1 mint golden:

```bash
# source = chapter-1 mint golden (held=earned=spent=0, all per-run state zeroed)
src=rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof/Profile_1.ob
# patch HC body+0x1D from float 0.0 -> 99.0 (held Dream Shards)
# encoded via lib.cooked.encode_file (auto-recomputes CRC32)
```

The post-CLI equivalent (now that the `shards` subcommand exists):

```bash
rerw write savefile shards 99 \
  --source rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof \
  --dest   rw/saves/edits/golden/geppetto/chapter1/held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof \
  --force
```

Source mint golden held all four per-run floats at 0.0 (held=0, earned=0, spent=0).
This save changes only HC body+0x1D from 0.0 → 99.0; CRC recomputed on encode.

## What this golden proves

**Held Dream Shards is stored at HC body+0x1D as a float32, and is the authoritative direct-read field for the HUD's Dream Shards display.** The HUD reads this byte range verbatim and does NOT recompute the value from `dream_shards_earned − dream_shards_spent` at load time.

The proof matters because the four-float block at HC+0x11/0x15/0x19/0x1D is internally consistent in observed natural saves (`held = earned − spent`). Without an in-game test that breaks the invariant, we couldn't tell whether held was the source of truth or a derived cache.

This save explicitly breaks the invariant: earned (HC+0x19) and spent (dynamic offset) are both 0.0; held (HC+0x1D) is 99.0. If the HUD recomputed, it would show 0. It shows 99 → held is authoritative.

## Verified in-game (2026-05-01)

- Loads cleanly, no SaveCompat modal.
- HUD on the Sandman Shop hub: Dream Shards = **99**.
- Other state inherits from the source mint golden (Stars of Fate = 0, level = 1, XP = 0, no carryover icons or banner).

## Cross-references

- `rw/key-findings/held-dream-shards.md` — bytefield reference for HC+0x1D.
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — full HC body schema; the per-run float block at HC+0x11..+0x21 is documented in the HeroController section.
- `tools/rerw-src/lib/hc_walker.py` — runtime walker; exposes `held_dream_shards`, `dream_shards_earned`, `dream_shards_spent`.
- `tools/rerw-src/lib/setters.py:set_held_dream_shards` — the underlying mutator.
- `tools/rerw-src/commands/write_savefile.py:shards_cmd` — the CLI subcommand.
- Source mint golden: `rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof/`.
