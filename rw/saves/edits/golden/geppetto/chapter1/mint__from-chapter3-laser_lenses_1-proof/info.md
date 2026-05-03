# mint__from-chapter3-laser_lenses_1-proof

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob` (chapter-3 boss-kill proof, Geppetto)
- **Lineage chain:** chapter-3 proof → `rerw mint savefile`
- **Edit name:** `mint__from-chapter3-laser_lenses_1-proof`
- **SHA-256 (full):** `b8e730c6e47888c20249eb767314cb7a9b467af892c7af75aad47f481542cd4b`
- **Size:** 75,065 bytes

## Reproduction recipe

Direct output of `rerw mint savefile` with default mint config — no manual layering, no scratch scripts.

```bash
./tools/rerw mint savefile \
    --source rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob \
    --dest   rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof \
    --chapter 0 --stars 7 --level 1 -f
```

`rerw mint savefile` applies AS-removal + chapter-progression-banner zeroing automatically — both fixes that this golden bakes in. See `tools/rerw-src/lib/save_mint.py`.

## Verified in-game

- Date: 2026-05-01
- Loads cleanly, no SaveCompat modal.
- Score-details panel: empty (no chapter-3 ActivityScore icons).
- Chapter-progression banner: empty (no completed-chapter markers, no death-X).
- Sandman Shop arena loads with chapter-1 baseline state (Stars of Fate=7, hero level=1, XP=0).

The carryover-bug fixes baked into this golden — the AS-records-removed + parent-count-zeroed approach (sidesteps the silencer) and the chapter-progression banner zero — live in `rw/findings/save-silencer-mechanism.md` and `rw/findings/save-mint-status.md`. This golden supersedes the prior `dynamic-mint__from-chapter3-laser_lenses_1-proof/` and `as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof/` chapter-1 goldens.
