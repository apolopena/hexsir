# zero-scores-and-level1

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- **Lineage chain:** chapter-2 proof → ActivityScore minimum-bodies + HeroScoreData zero + HeroController damage-block zero + CurrentRunProfileData playtime zero → level=1 → XP=0
- **Edit name:** `zero-scores-and-level1`
- **Final CRC32:** `0xDA0EFBA5`
- **File size:** 73,694 bytes

## Reproduction recipe

Historical build chain — most of these zero-out steps are now folded into `rerw mint savefile` (`tools/rerw-src/lib/save_mint.py`). The byte-level recipe used at promotion time, against `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`:

1. **ActivityScore × 6 → minimum-valid 25-byte body each.** Synthesized wire format `u32(0) × 6 + u8(0)` replacing nested `ActivityScore` sub-objects under `oCDtCurrentRunProfileData`. Each shrinks from ~113-119 bytes to 25.
2. **HeroScoreData → 28 score floats zeroed in place.** Body length unchanged (151 bytes).
3. **HeroController body → 16 bytes at +0x11 zeroed (the four damage floats: 77001, 745.8, 1091, 101) plus 4 bytes at +0x35d (the 990 float).**
4. **CurrentRunProfileData own body → 4 bytes at +0xe5 zeroed (playtime float = 1409s = 23:29).**
5. CRC32 auto-recomputed on encode (`tools/rerw-src/lib/cooked.py:encode_file`).
6. `rerw write savefile level 1` rewrites in-run hero level u32 from 5 → 1 at file offset `0xf1ea` (`oCDtEntityCpntGroupLevelPersistentData` body+0x11). CRC re-recomputed.
7. **Accumulated XP zeroed at `GroupLevelPersistentData` body+0x15** (file offset `0xf1ee`, u32: 2690 → 0). Required to keep the per-run "Level reached" stat from being inflated by leftover XP. Final CRC `0xDA0EFBA5`.

The specific zero-out scripts used at promotion lived in `.ai/scratch/` (gitignored). Equivalent today is `rerw mint savefile` for steps 1-5; steps 6-7 remain as separate `rerw write savefile level 1` and `rerw write savefile xp 0` invocations.

## Verified in-game

- Date: 2026-04-30
- Save loads cleanly.
- Score page reads zero for damage / playtime / score-subtotals.
- Hero level shows 1; XP starts at 0.
- Damage during a fresh run accumulates correctly from zero.
- Runtime accepts the edits as real state (counters accumulate from zero on next play).
- "Level reached" cumulative stat appended on defeat reflects the actual run, not a leftover-XP-inflated value.
