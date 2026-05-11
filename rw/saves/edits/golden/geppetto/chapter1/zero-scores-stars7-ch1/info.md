# zero-scores-stars7-ch1

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- **Lineage chain:** chapter-2 proof → v4 zero-scores-and-level1 (intermediate) → chapter rollback to chapter 1 + Stars of Fate baseline 7
- **Edit name:** `zero-scores-stars7-ch1`
- **Final CRC32:** `0xC14F2CBB`
- **File size:** 73,694 bytes

## Reproduction recipe

Layered on the v4 zero-scores-and-level1 golden (which itself layers HC body zeroing + ActivityScore minimum bodies + HeroScoreData zeroing + level reset + XP zero on the chapter-2 proof). With current CLI:

```bash
SRC=rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/Profile_1.ob
DST=rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1

# Stars of Fate live count
rerw write savefile stars 7 --source "$SRC" --dest "$DST" --force

# Roll chapter back to 1
rerw write savefile chapter 1 --source "$DST/Profile_1.ob" --dest "$DST" --force
```

For the historical zero-scores-and-level1 build chain that produced the input,
see `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/info.md`.

## Verified in-game

- Date: 2026-04-30
- Loads cleanly, no SaveCompat modal.
- HUD shows chapter 1 / hero level 1 / XP 0.
- Stars of Fate = 7 and verified spendable in-game.
- Played forward through chapter 1 → chapter 2 → boss kill; engine wrote a follow-on chapter-2 save (see `../../chapter2/2for1-thru-with-inventory/`).

The mint-recipe gaps observed against this golden (held-inventory not yet mapped, score-page Raven-Feathers-consumed stuck, chapter-achievement record source unknown) are tracked in `rw/findings/save-mint-status.md`.
