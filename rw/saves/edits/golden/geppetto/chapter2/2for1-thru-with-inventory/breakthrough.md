# Breakthrough — chapter-2 follow-on from minted chapter-1 save (round-trip confirmed)

**Source:** Live in-game save pulled from `_Save/Profile_1.ob` after a chapter-1 → chapter-2 play-through using the minted chapter-1 starting golden.
**Upstream golden (the minted starting save):** `rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/Profile_1.ob` (CRC `0xC14F2CBB`)
**File size:** 73,694 bytes

## What this proves (downstream of the mint POC)

This save is the **output** of the mint round-trip described in the upstream chapter-1 golden's breakthrough. Its existence proves:

1. The minted chapter-1 starting save (built by zero-out + `rerw --chapter 0` from a chapter-2 proof) **loads, plays, and writes a new save** through the engine's normal chapter-boss-kill save event.
2. The full pipeline — `chapter-2 proof → zero-out → chapter-1 mint → play → chapter-2 boss kill → new save` — works end-to-end without corrupting the save format.
3. Run-state edits (Stars of Fate live count = 7) **persist through the play-through** and the new save retains the edit at the same wire-format offset.
4. Run-time inventory (talents picked, ingredients held, dream shards collected, feather use, star spending) is **captured by the engine's natural save event** in some persisted record(s).

Together with the upstream golden, this is the **completed proof of concept for the mint flow**: take advanced game state → zero to chapter 1 → maximum rewrite options for the player → play forward → produce a new advanced save.

## Held inventory at save time

Reported by user during play / at boss kill:
- **Stars of Fate**: 7 (matches the upstream edit baseline; some may have been spent during play)
- **Raven Feathers**: 1 extra collected (so 2 carried into save)
- **Nightmare Keys**: 2
- **Bean (ingredient)**: 1 (unused — leftover from Three Pigs map encounter)
- **Dream Shards**: extra collected during play

## Three things we couldn't control (carried over from the upstream golden)

These are the same gaps documented in the upstream chapter-1 golden's breakthrough, manifesting in this play-through save. None invalidate the round-trip POC — they're items the mint recipe doesn't yet handle.

### (1) Held inventory location is unmapped — keys / feathers / bean

**Empirically confirmed**: keys persist across save → restart cycles. User test: collected 2 keys before chapter 2 → save at boss kill → quit → restart → loaded with 2 keys still in inventory → quit and restart again → still 2 keys. The save file carries this state correctly.

**What we have NOT yet pinpointed**: the specific byte location(s) holding the key count. Diffs ran against the chapter-2 proof did not surface a clear "keys=2" delta in the records we inspected (HeroController body, HeroIngredient vector at HC+0x21 which reads empty, CounterPersistentData × 3, HeroMOPersistentData × 21, HeroProfileData × 12, HeroScoreData, the inspected CurrentRunProfileData parent-body region). The user noted that key acquisition is also tracked as a chapter achievement, so the achievement-record path is a strong candidate (and that path is currently unmapped too — see (3) below).

### (2) "Raven Feathers consumed" stat stuck at 4 — can't clear

The score-page row "Number of Raven Feather consumed" reads 4 in this golden because the upstream chapter-1 minted golden has `HeroController body+0x25 = 4` (a probe edit). **We could not figure out how to clear this stat back to 0** in a way that takes — every iteration left the score page reading 4. The byte in the file can be set to 0 successfully, but the displayed value didn't update accordingly. Stuck.

### (3) Chapter-achievement records cause the compounding-blanks bug

See the "Score Details" page screenshot — chapter-1 achievements on the left, leftover blank diamonds in the middle, chapter-2 achievements on the right. **Which record stores chapter achievements is unknown** (see next section for full description).

## The score-details compounding-blanks bug (reproduced here)

The **Score Details** panel (statistics page 2 — the end-of-statistics page) exhibits a compounding-blanks bug. This panel shows the **chapter achievements earned during the run** — each colorful icon represents an in-chapter achievement that added to the final score (e.g., bought a Raven Feather at a heroes' altar, conquered a cauldron, killed a Nightmare Tumor, completed a side activity). It is NOT the Talents and Magical Objects row (that's a separate section on page 1).

**What happens on the page** (see `score-details-blanks-bug.png`):
- Active achievement icons from the **chapter-1 run** appear in the leftmost positions of the grid.
- A run of **empty grey diamond placeholder slots** sits in the middle — these are inherited achievement records carried from the original chapter-2 proof through the v4 zeroing → chapter-1 mint chain. They occupy positions but cannot display icons because the achievements they represented (chapter-2 context) weren't valid achievements available in the fresh chapter-1 run.
- Active achievement icons from the **chapter-2 run** appear in positions to the right of the blanks.
- `Base score: 160` and `SCORE: 326` at the top suggest the score system is summing both the chapter-1 and chapter-2 contributions plus a baseline, but the blank positions still occupy real grid cells in the visible row.

**Why it happens**: the mint recipe added new chapter-achievement state on top of inherited records instead of clearing them. Every mint from the same chapter-2-proof base inherits the same compounding blanks. The bug stacks each time you play a minted save through.

**Which record stores chapter achievements — UNKNOWN.** We have not traced this panel to its source record. ActivityScore × 6 was already zeroed in v4 (replaced with minimum-valid 25-byte bodies), so it's *unlikely* to be the source — unless ActivityScore is consumed differently than expected. The other named candidates (HeroMOPersistentData × 21, CounterPersistentData × 3, HeroProfileData × 12) didn't show changes between proof and play-through golden either. The location is currently unmapped territory.

Held inventory (keys, bean, feathers) is similarly unmapped — we diffed every named record we know of and didn't find them anywhere.

**Fix path for the mint recipe**: identify the record(s) that drive the Score Details panel by probe-and-observe — edit candidate records in a controlled save and watch what changes on the panel. Once the source is confirmed, add a zero-out step to the mint for that record. Until then, the bug stays.

## Screenshots

- `hud-inventory-during-play.png` — mid-run HUD with map open, showing live inventory bar at bottom (stars / feathers / keys / dream shards visible)
- `defeat-score-overview.png` — defeat / score-book overview (top of the statistics flow)
- `statistics-leftover-blanks-bug.png` — statistics page 1: hero portrait, talents-and-magical-objects row, and the per-run stat breakdown (no bug visible on this page)
- `score-details-blanks-bug.png` — statistics page 2 (Score Details): the actual compounding-blanks bug. Chapter-1 achievement icons on the left, blank placeholder slots in the middle (inherited from the chapter-2 proof, can't render in fresh chapter-1 context), chapter-2 achievement icons on the right.

## Install (for replay / inspection / further diff work)

```bash
./tools/rerw swap savefile \
    --source rw/saves/edits/golden/geppetto/chapter2/2for1-thru-with-inventory/Profile_1.ob
```

## Cross-references

- `rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/breakthrough.md` — the upstream minted chapter-1 starting save
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/breakthrough.md` — the v4 zeroed golden (intermediate step in the mint chain)
- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — the original chapter-2 input to the mint chain
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — pipeline + stat-source mapping
- `tools/rerw-src/lib/cooked.py` — decoder/encoder
