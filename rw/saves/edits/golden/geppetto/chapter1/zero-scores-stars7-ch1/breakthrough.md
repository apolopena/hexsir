# Breakthrough — minted chapter-1 starting save from chapter-2 proof (round-trip POC)

**Final CRC32:** `0xC14F2CBB`
**File size:** 73,694 bytes

## What this proves (the headline)

You can take **the most advanced game state available** (a chapter-2-boss-kill proof), zero out as much per-run state as we know how, **roll the chapter index back to chapter 1**, and produce a save the engine will load and play forward through chapter 1 → chapter 2 → boss-kill → save again.

The result of playing this minted save through is captured in `../../chapter2/2for1-thru-with-inventory/Profile_1.ob`, which loaded successfully, accepted the user's run-time inputs (talents, ingredient pickups, dream-shard collection, feather use, star spending), and wrote a fully-formed new chapter-2 save on boss kill.

This is the **proof of concept for the "mint" flow**: take a save with the most progression/talents available, reset its per-run state, repoint chapter to 1, and hand the player maximum rewrite options — a fresh playthrough on top of preserved meta-progression and talent state.

## How it was built (the chapter-2 → chapter-1 mint chain)

Starting input: `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` (the chapter-2 boss-kill proof).

Build steps applied in order:

1. **Zero per-run stats** (the v4 zeroing recipe):
   - `oCDtEntityCpntHeroControllerPersistentData` body damage region — 4 floats at +0x11/+0x15/+0x19/+0x1d zeroed (damage_dealt 77001 → 0, damage_taken 745 → 0, two damage breakdowns → 0)
   - `oCDtEntityCpntHeroControllerPersistentData` body +0x35d zeroed (originally 990 — likely dream-shards-collected, accidentally zeroed; not yet recovered)
   - `ActivityScore × 6` nested under `oCDtCurrentRunProfileData` replaced with minimum-valid 25-byte bodies
   - `HeroScoreData` 28 score floats zeroed in place (cached snapshot)
   - `oCDtCurrentRunProfileData` body +0xe5 zeroed (playtime float = 1409s = 23:29 → 0)
2. **Reset hero level**: `rerw write savefile --level 1` rewrote `oCDtEntityCpntGroupLevelPersistentData` body+0x11 from 5 → 1.
3. **Zero accumulated XP**: HeroController-adjacent XP field at GroupLevel body+0x15 zeroed (2690 → 0). Required to keep the per-run "Level reached" stat from being inflated by leftover XP.
4. **Stars-of-Fate baseline**: HeroController body+0x29 set to 7 (live spendable count). Verified spendable in-game during play.
5. **Probe edits at body+0x25 (= 4) and body+0x2d (= 1)**: see "Known limitations" below — these were probes that turned into stat-counter writes we couldn't subsequently zero.
6. **Roll chapter back to 1**: `rerw write savefile --chapter 0` rewrote the chapter index at file offsets `0xe9d1` and `0xf241` from 1 → 0 (= chapter 1).

Final CRC `0xC14F2CBB`.

## What we couldn't zero (yet) — known limitations

The mint recipe successfully zeroed most per-run state, but there are gaps. **Three categories of things we couldn't control in this golden:**

### (1) Held-inventory location is unmapped — we can't zero what we can't find

- **Keys (Nightmare Keys held)** — empirically persists across the save → restart cycle (verified by user's downstream chapter-2 follow-on test: 2 keys carried through). Save bytes that hold the count are not yet identified. The HeroIngredient vector at `HeroController.body+0x21` reads as empty in every save we've inspected (proof + golden + downstream play-through), so it's not the location. Mint can't zero this until the location is found.
- **Raven Feathers held** — same situation. Persists empirically but the byte location is unmapped.

### (2) Score-page "Raven Feathers consumed" stat stuck at 4 — can't clear it

- **HeroController body+0x25 = 4** (Raven Feathers consumed stat). We probe-edited this from 1 → 4 to validate that the field maps to the score-page row "Number of Raven Feather consumed". The score page does indeed read 4 from this byte. **But we couldn't figure out how to clear it back to 0** in a way that takes — every iteration we tried left the score page reading 4. Setting to 0 in the lab worked at the byte level but the displayed value didn't update accordingly. Stuck.
- **HeroController body+0x2d = 1** (unknown stat — possibly Nightmare Keys consumed). Probe edit, no visible HUD/score-page effect identified. Same kind of "stuck" behavior as +0x25 if we tried to clear it.

### (3) Chapter-achievement records cause the compounding-blanks bug — source unmapped

- **The score-details (statistics page 2) achievement icons** carry over from the proof's chapter-2 state into the minted chapter-1 save. On a play-through, chapter-1 achievements occupy left positions, the leftover (invalid in chapter-1 context) records show as blank grey diamonds in the middle, and chapter-2 achievements append to the right. **Which record stores chapter achievements is unknown.** ActivityScore × 6 was already replaced with minimum bodies in v4, so it's *unlikely* to be the source. The other named candidates (HeroMOPersistentData × 21, CounterPersistentData × 3, HeroProfileData × 12) didn't show changes between proof and play-through golden either. Until the source record is found, mint can't address the bug.

### Other notes (not "stuck", just collateral)

- **HeroController body+0x29 = 7** (Stars of Fate live count). Intentionally set to 7 to validate the live-count edit. Not a "couldn't zero" — by design. **Verified spendable in-game** (the major hack).
- **Dream-shards-collected (HC body+0x35d, originally 990) — accidentally zeroed**. The v4 mint zeroed this as "additional damage stat" before we realized 990 likely corresponded to dream-shards-collected. Not destructive to gameplay (just shows 0 collected on score page), but the mint recipe should either preserve or explicitly zero this with the correct understanding of what the field represents.

## What's proven (engineering)

- **Chapter index is editable via `rerw --chapter N`** without breaking save loadability (downstream proof: this save loads at chapter 1).
- **Stars of Fate at HeroController body+0x29 is the live spendable count** — verified by spending stars in-game with the 7-baseline.
- **The full "mint from advanced state" pipeline works end-to-end** — chapter-2 proof → zero edits → chapter rollback → loads at chapter 1 → plays through → boss-kill save → produces valid chapter-2 follow-on (which itself loads and decodes byte-for-byte).
- **Edits survive across chapter starts and the engine's natural save event** — meaning we're not getting silently overwritten by some loader-side reset.

## Install

```bash
./tools/rerw swap savefile \
    --source rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/Profile_1.ob
```

(Steam Cloud sync MUST be off for Ravenswatch — see `CLAUDE.md`.)

## Cross-references

- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — the chapter-2 input that was minted into this save
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/breakthrough.md` — the v4 zeroed golden (intermediate step before chapter rollback)
- `rw/saves/edits/golden/geppetto/chapter2/2for1-thru-with-inventory/breakthrough.md` — the chapter-2 follow-on save that proves this golden round-trips through play
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — pipeline + stat-source mapping
- `tools/rerw-src/lib/cooked.py` — decoder/encoder
- `tools/rerw-src/commands/write_savefile.py` — `rerw write savefile --chapter N --level N` implementation
