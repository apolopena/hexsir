# 2for1-thru-with-inventory

## Provenance

- **Source path:** in-game `_Save/Profile_1.ob` after a chapter-1 → chapter-2 play-through using the chapter-1 minted starting golden as the loaded save
- **Lineage chain:** chapter-2 proof → v4 zero-scores-and-level1 → zero-scores-stars7-ch1 (chapter-1 mint POC) → played forward → boss kill → engine-written follow-on save
- **Edit name:** `2for1-thru-with-inventory`
- **Final CRC32:** `0xC14F2CBB`
- **File size:** 73,694 bytes

## Reproduction recipe

This save is the **output** of a play-through, not a CLI edit. Reproduction:

1. Build `rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/Profile_1.ob` (see that golden's `info.md`).
2. `rerw swap savefile --source <chapter1 golden>` (game closed).
3. Launch game, load save (chapter 1), play through chapter 1 to chapter-2 boss kill.
4. At the chapter-2 boss-kill save dialog, choose save and exit.
5. Copy `_Save/Profile_1.ob` into this directory.

The exact post-edit byte content depends on what the player did during the run (talents picked, items collected, etc.). Replay won't byte-match.

## Verified in-game

- Date: 2026-04-30
- Held inventory at save time: Stars of Fate=7 (matched upstream edit baseline), Raven Feathers=2 (1 collected during play), Nightmare Keys=2, Bean=1, Dream Shards collected during play.
- Save loads, displays expected chapter-2 state.
- Roundtrip POC: minted chapter-1 starting save → played → chapter-2 follow-on save was written by the engine's natural save event.

The follow-on save reproduces the held-inventory and chapter-achievement carryover gaps that the upstream chapter-1 mint inherits from its source proof. Those gaps are tracked as open work in `rw/findings/save-mint-status.md`.
