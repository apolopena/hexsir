# laser-lenses_1 — level-change memory diff test set

This `info.md` is the parent-level provenance for the 5 sibling `level<N>/` directories (each containing a `Profile_1.ob`) used as inputs to the `mem_snapshot.py intersect` workflow that isolates the runtime address of the in-run Level integer.

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` (canonical Geppetto chapter-2 boss-kill proof)
- **Lineage chain:** chapter-2 proof → unaltered copy as `level5` (baseline) → 4 mod_save passes setting Level = 8 / 14 / 17 / 20

The 5 saves under `level<N>/Profile_1.ob`:

| Path | Level | CRC32 | Origin |
|------|------:|-------|--------|
| `level5/Profile_1.ob` | 5 | `0xB5C816B3` | Unaltered copy of `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` |
| `level8/Profile_1.ob` | 8 | `0xAA78B011` | Modded from `level5` via `mod_save.py --set Level 8` |
| `level14/Profile_1.ob` | 14 | `0xA4C5D44D` | Modded from `level5` via `mod_save.py --set Level 14` |
| `level17/Profile_1.ob` | 17 | `0x92474F7B` | Modded from `level5` via `mod_save.py --set Level 17` |
| `level20/Profile_1.ob` | 20 | `0x9BA49909` | Modded from `level5` via `mod_save.py --set Level 20` (disambiguator) |

- **Level GUID** (save format): `b5317efe6f4a95737325675793e600`
- **Level offset** (this build): `0xf1ea` (int32 LE)
- **Chapter context:** chapter 2 / start-of-chapter, immediately after completing chapter 1.

## Reproduction recipe

The 5 level-N saves are produced by:

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob

# level5 — unaltered copy
cp "$SRC" rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/level5/Profile_1.ob

# level8/14/17/20 — mod_save.py --set Level N derived from level5
for N in 8 14 17 20; do
  tools/rerw-src/.venv/bin/python rw/scripts/mod_save.py \
    --in rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/level5/Profile_1.ob \
    --set Level $N \
    --out rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/level$N/Profile_1.ob
done
```

For the memory-snapshot disambiguation procedure that consumes these 5 saves (Windows-side `mem_snapshot.py` capture/intersect workflow, the two-intersects pattern that disambiguates the runtime Level integer), see [`../../../../../docs/workflow/frida.md`](../../../../../docs/workflow/frida.md) §"Memory analysis (full-process snap/diff)" → §"Disambiguation pattern."

## Verified in-game

- Each save loads cleanly to the chapter-2 / start-of-chapter context.
- The HUD reflects the file's `Level` value (5 / 8 / 14 / 17 / 20) on load.
- Used end-to-end to isolate the runtime Level int32 address via two-pass `intersect` disambiguation.
