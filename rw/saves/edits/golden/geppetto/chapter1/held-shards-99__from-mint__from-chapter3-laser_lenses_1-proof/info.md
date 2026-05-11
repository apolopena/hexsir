# held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof

## Provenance

- **Source path:** `rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof/Profile_1.ob`
- **Lineage chain:** chapter-3 `laser_lenses_1` proof → `rerw mint savefile` → mint golden (held=earned=spent=0, all per-run state zeroed) → set held = 99
- **Edit name:** `held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof`
- **SHA-256 (full):** `21821a19343e486111fe46e10dd3266be1136902c849fdcf9f0cd62a075c88c6`
- **Size:** 75,065 bytes

## Reproduction recipe

```bash
SRC=rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof
DST=rw/saves/edits/golden/geppetto/chapter1/held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof

rerw write savefile shards 99 --source "$SRC" --dest "$DST" --force
```

## Verified in-game

- Date: 2026-05-01
- Loads cleanly, no SaveCompat modal.
- HUD on the Sandman Shop hub: Dream Shards = **99**.
- Other state inherits from the source mint golden (Stars of Fate = 0, level = 1, XP = 0, no carryover icons or banner).

The HUD-displayed `99` against a source whose `dream_shards_earned = 0` and `dream_shards_spent = 0` is the invariant-break that confirms the held field is authoritative — captured in `rw/findings/held-dream-shards.md`.
