[← Back to findings](README.md)

# Save: hero swap

The hero is encoded in the save body as a length-prefixed ASCII path. Editing this record changes the hero on load.

**Status:** confirmed
**Status notes:** verified end-to-end across four swaps from the chapter2 Geppetto proof — same-length (Carmilla, no shift), shrink (Aladdin, −1 byte; Red, −5 bytes), and grow (Snow_Queen, +2 bytes). Engine tolerates body shifts in both directions across the full range tested (−5 to +2 bytes).
**Created:** 2026-04-27

## Hero record format

In the chapter2 Geppetto proof, located at offset `0x11da2`. Offsets vary per save — locate via `data.find(b'Heroes\\<Name>')`.

    [u32 length prefix]    ← 4 bytes LE; total length of the path string
    [ASCII path bytes]     ← format: Heroes\<Name>.herodef.ot
    [unparsed trailing data]

For the Geppetto chapter2 proof: length prefix = `0x1a` (26 bytes), path = `Heroes\Geppetto.herodef.ot` (26 bytes).

## Same-length swap procedure (verified)

Verified Geppetto → Carmilla on the chapter2 proof:

1. Locate the path bytes via `data.find(b'Heroes\\<old_name>')`.
2. Replace with `Heroes\<new_name>.herodef.ot` byte-for-byte. Length unchanged → length prefix unchanged → no body shift.
3. Recompute CRC32 of body (`zlib.crc32(data[16:])`) and write to offset `0x0C`.
4. Output as `Profile_1.ob`.

Same-length 8-char swap candidates (per `hero-table.md`): `Carmilla`, `Melusine`.

## Different-length swap procedure

Verified across the full shift range on the chapter2 proof:
- **Geppetto → Aladdin** (−1 byte shift): loaded cleanly.
- **Geppetto → Red** (−5 byte shift, largest shrink): loaded cleanly.
- **Geppetto → Snow_Queen** (+2 byte shift, grow): loaded cleanly.

For non-8-char target heroes:

1. New length = `18 + len(new_name)` (= byte-count of `Heroes\<NewName>.herodef.ot`).
2. Splice in the new length prefix and path; bytes after the hero record shift by `len(new_name) - len(old_name)`. File size changes by the same delta.
3. Recompute CRC32 of body and write to offset `0x0C`.

Engine parsing of the trailing region is robust to the body shift in both directions — the hero record and downstream data are not byte-offset-coupled. Tested range: −5 to +2 bytes. Larger shifts than these have not been tested but are structurally plausible.

## Observed swap behavior

Verified for four swaps from the same Geppetto chapter2 proof:

- **Geppetto → Carmilla** (same-length, no shift): identity fully Carmilla's; run state preserved; slot 1 = `Impalement` (her ult #2); slots 2/3/4/5 empty; L5 pick UI offered `Blood Lash` only (Impalement already placed in slot 1); no engine refusal.
- **Geppetto → Aladdin** (−1 byte shift): identity fully Aladdin's; run state preserved; slot 1 = `Dreamwish` (his ult #1); slots 2/3/4/5 empty; no engine refusal.
- **Geppetto → Snow_Queen** (+2 byte shift): identity fully Snow_Queen's; run state preserved; slot 1 = `Frost Ray` (her ult #1); slots 2/3/4/5 empty; no engine refusal.
- **Geppetto → Red** (−5 byte shift, largest shrink): identity fully Red's; run state preserved; slot 1 = `Hunter's Souvenir` (her ult #1); slots 2/3/4/5 empty; no engine refusal.

Common observations:

- **Slot 1 (starting slot) is auto-populated with the new hero's L5 ultimate on swap; slots 2/3/4/5 are empty.** All four verified swaps placed an L5 ultimate in slot 1: Carmilla's `Impalement`, Aladdin's `Dreamwish`, Snow_Queen's `Frost Ray`, Red's `Hunter's Souvenir`. In canonical play L5 ultimates are only obtainable at the L5 slot, so the slot 1 placement is non-canonical for all four heroes.
- **The resolver picks different ultimate indexes per target hero from the same source** — Carmilla got her ult #2; Aladdin, Snow_Queen, and Red each got their ult #1. Not a uniform "always ult #N" rule.
- **Identity** (model, name, intro, ability bar) **and run state** (chapter, level, XP, currencies, inventory) **are preserved** across both swaps.
- **No engine refusal** of the non-canonical state in either case.

## Open questions

- **Resolver determinism for slot 1.** Whether Geppetto's specific starting-talent pick determines which Carmilla talent ends up in slot 1 after the swap. Untested — would require a second Geppetto proof with a different starting talent picked.
- **Different-length swap viability.** Untested.
- **Cross-source-hero generality.** Only Geppetto → Carmilla has been tested. Other source / target combinations untested.
- **Persistence across runs.** Whether playing a swapped save through chapter completion (which triggers Ravenswatch's auto-save) uploads the swapped state to Steam Cloud and persists across game restarts. Untested.

## Sources

- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — source proof.
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-carmilla/Profile_1.ob` — verified golden, same-length swap.
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-aladdin/Profile_1.ob` — verified golden, −1 byte shrink.
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-snow_queen/Profile_1.ob` — verified golden, +2 byte grow.
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-red/Profile_1.ob` — verified golden, −5 byte shrink (largest tested).
- `rw/saves/edits/lab/geppetto/laser-lenses_1/hero-swap-to-melusine/Profile_1.ob` — Melusine swap pending in-game verification (8-char same-length).
- `rw/findings/hero-table.md` — hero list and swap-difficulty reference.
- `rw/findings/save-binary-format.md` — base save-format documentation.
