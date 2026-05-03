# dynamic-mint__from-chapter3-laser_lenses_1-proof

> **SUPERSEDED 2026-05-01** by `mint__from-chapter3-laser_lenses_1-proof/` — that golden is produced directly by `rerw mint savefile` (the dynamic walker is now folded into production) and has fixes for both activity-icon carryover and chapter-progression banner carryover that were unresolved here.

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob` (chapter-3 boss-kill proof, 76,465 bytes)
- **Lineage chain:** chapter-3 proof → experimental dynamic mint
- **Edit name:** `dynamic-mint__from-chapter3-laser_lenses_1-proof`
- **SHA-256 (truncated):** `d4ce00f27502a6ff`
- **Size:** 76,465 bytes

## Reproduction recipe

Historical only — the dynamic walker has since been folded into the production CLI. Equivalent today:

```bash
./tools/rerw mint savefile \
    --source rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob \
    --dest   <dest> \
    --chapter 0 --stars 7 --level 1 -f
```

The original build path used `.ai/scratch/mint-dynamic-offsets/dynamic_mint.py` against an early version of `lib/hc_walker.py`. Both files were folded into `tools/rerw-src/lib/save_mint.py` + `lib/hc_walker.py` before this overhaul.

## Verified in-game

- Date: 2026-05-01 (initial)
- Loads cleanly (no SaveCompat modal — silencer not triggered).
- Chapter shows as 1 (chapter rollback worked).
- Playtime 00:00 (CRP+0xE5 zero took).
- Damages low / Score low (per-run state zeroed).
- Talents and magical objects from chapter-3 progression preserved.
- **Known carryover bugs at promotion time:** chapter-3 ActivityScore icons in score-details (resolved in `as-count-zero__...`), chapter-progression banner (resolved in `mint__from-chapter3-laser_lenses_1-proof/`).
