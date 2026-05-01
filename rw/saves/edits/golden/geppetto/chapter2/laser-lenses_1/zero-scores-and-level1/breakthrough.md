# Breakthrough — zero-scores + hero-level-1 save edit

**Promoted from:** `rw/saves/edits/lab/zero_scores_v4/Profile_1.ob` (2026-04-30 session, second promotion)
**Source save:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
**Final CRC32:** `0xDA0EFBA5`
**File size:** 73,694 bytes

## What it is

A chapter-2 base save with **all per-run stats zeroed**, **Geppetto's hero level reset to 1**, AND **accumulated XP zeroed**. Loads cleanly into the game; runtime treats every edited value as real state — counters accumulate from zero on next play, hero HUD reflects level 1, and the cumulative "Level reached" stat now appends the correct per-run value (no longer inflated by leftover XP).

This is the first save we've produced via the `lib.cooked` decoder/encoder pipeline that exercises *every* working layer of the path-B mechanism end-to-end:

- Bidirectional decoder/encoder + recursive tree walker (`lib.cooked`).
- Nested sub-object body replacement with synthesized minimum-valid wire format (`ActivityScore`).
- In-place scalar/float zeroing while preserving structural counts and length-prefixed strings (`HeroScoreData`, `HeroController`, `CurrentRunProfileData` own body).
- CRC32 (zlib polynomial) auto-recomputation on encode.
- GUID-locator-based field write via `rerw write savefile --level N` layered atop our raw-byte edits.
- Combined edits committed in one final CRC pass.

Verified end-to-end: save loads, score page reads zero for damage/playtime/score-subtotals, hero level shows 1, XP starts at 0, runtime accumulates from zero on subsequent play, and "Level reached" appended on defeat reflects the actual run (not a leftover-XP-inflated value).

## How it was created (build chain)

Layered on top of the chapter-2 base save:

1. **ActivityScore × 6 → minimum-valid 25-byte body each.** Synthesized wire format: `u32(0) × 6 + u8(0)`. Replaces nested `ActivityScore` sub-objects under `oCDtCurrentRunProfileData`. Each shrinks from ~113-119 bytes to 25. Total CurrentRunProfileData body shrinks accordingly; surrounding markers reflow naturally.
2. **HeroScoreData → 28 score floats zeroed in place.** Body length unchanged (151 bytes). Counts (5, 10, 4, 3, 6) preserved, "Quadrotonic" + 4-byte tail preserved. Cached snapshot — kept clean for consistency even though it's not the read-source the score page consults.
3. **HeroController body → 16 bytes at +0x11 zeroed (the 4 damage floats: 77001, 745.8, 1091, 101) plus 4 bytes at +0x35d (the 990 float).** Byte-misaligned reads — these are the actual values the score page displays.
4. **CurrentRunProfileData own body → 4 bytes at +0xe5 zeroed (playtime float = 1409s = 23:29).** Also byte-misaligned.
5. CRC32 auto-recomputed on encode (via `lib.cooked.encode_file`).
6. Then layered on top: **`rerw write savefile --level 1`** rewrote the in-run hero level u32 from 5 to 1 at file offset `0xf1ea` (= `oCDtEntityCpntGroupLevelPersistentData` body+0x11), CRC re-recomputed.
7. Final layer: **accumulated XP zeroed at `GroupLevelPersistentData` body+0x15** (file offset `0xf1ee`, u32: 2690 → 0). Without this, the cumulative "Level reached" stat appended on defeat was inflated by `XP / xp_threshold` (saw 7.73 instead of the expected ~5.x). With XP zeroed, the appended value matches the saved hero level. Final CRC `0xDA0EFBA5`.

## Install

```bash
./tools/rerw swap savefile \
    --source rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/Profile_1.ob
```

(Steam Cloud sync MUST be off for Ravenswatch — see `CLAUDE.md`.)

## What further in-game testing would prove

We've already confirmed: save loads, score page reads zero for damage/playtime/score-subtotals, hero level shows 1, damage during a fresh run accumulates correctly from zero, runtime accepts the edits as real state. The next-tier confirmations worth getting:

1. **HUD downgrade verification at level 1.** Start a run, look at base attack damage, max HP, and per-skill cooldowns BEFORE engaging an enemy. Compare to known-good level-1 Geppetto values (a fresh-run save would have these). Confirms hero scaling is recomputed from saved level, not stored separately.
2. **XP bar starts at 0 / level-1-threshold.** Pick up an XP orb, observe gain → level-up trigger fires correctly. Confirms XP isn't held in some other record we missed.
3. **First level-up animations / effects.** Level 1 → 2 transition should play if XP is genuinely 0. If it skips levels 2-5 silently or jumps from 1 → 6, there's a hidden cumulative XP field somewhere we haven't zeroed.
4. **Talents-per-slot survive correctly.** Level 1 in Ravenswatch typically restricts talent rerolls / slot availability. Check whether the talents already bound (Philosopher's Stone, etc.) display correctly or get gated. If gated, the talent records may have level-requirement metadata we'd need to update too.
5. **Defeat → "Level reached" cumulative stat behavior.** Last session showed it appended (5.54 → 7.73). After this defeat, observe whether it appends again, and whether the *delta* it adds reflects actual played progress (e.g. play 30 sec → small append) or chapter level (e.g. always +chapter_index). Helps narrow where the cumulative store lives — likely `oCDtHeroProfileData` per-hero.
6. **Save-and-quit then reload.** Load → play briefly → save and quit through the modal → relaunch → continue. Verify the edits we made don't get rewritten by the natural save mechanism (i.e. runtime maintains the zero-baseline correctly when it serializes back).

If any of those misbehaves, the failure mode tells us specifically which record/field still needs schema work. If they all pass, the pipeline is fully validated for the hero-level + run-stat-reset use case.

## Cross-references

- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — full methodology, schema findings, tool reference.
- `rw/key-findings/save-subsystem.md` — canonical save-subsystem architecture.
- `tools/rerw-src/lib/cooked.py` — the decoder/encoder library.
- `.ai/TASKS.md` → EXPERIMENTAL-2 entry.
