# mint__from-chapter3-laser_lenses_1-proof

**Promoted to golden:** 2026-05-01
**Hash (SHA-256, full):** `b8e730c6e47888c20249eb767314cb7a9b467af892c7af75aad47f481542cd4b`
**Size:** 75065 bytes

## Provenance

Direct output of `rerw mint savefile` on the chapter-3 proof, with default config (`--chapter 0 --stars 7 --level 1`). No manual layering, no scratch scripts — produced by the production CLI in one shot:

```bash
./tools/rerw mint savefile \
    --source rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob \
    --dest rw/saves/edits/golden/geppetto/chapter1/mint__from-chapter3-laser_lenses_1-proof \
    --chapter 0 --stars 7 --level 1 -f
```

## What this golden proves

End-to-end production mint produces a clean chapter-1 starting save from a chapter-3 boss-kill proof, with no carryover artifacts visible to the player.

Two carryover bugs were fixed iteratively this session and both fixes are baked into this golden:

1. **Activity-icon carryover** (chapter-3 ActivityScore icons appearing on the score-details panel). Fix: REMOVE the AS records from CRP and zero the parent count u32 — the deserialize loop runs zero iterations, no icons render, no silencer trip. Replaces the earlier "preserve AS bodies verbatim" approach.

2. **Chapter-progression banner carryover** (banner at the top of the end-screen showing `I` red / `II` red / `III` red-X — the chapter-3 proof's run history). Fix: zero the u32 in CRP at `(first-AS-frame.start - 8)`. In source proofs this u32 = `3 × chapters_completed_before_death` (ch2 proof = 3, ch3 proof = 6, epilogue proof = 9). Zero suppresses the banner.

## Verified in-game (2026-05-01)

- Loads cleanly, no SaveCompat modal.
- Score-details panel: empty (no chapter-3 ActivityScore icons).
- Chapter-progression banner: empty (no completed-chapter markers, no death-X).
- Sandman Shop arena loads with chapter-1 baseline state (Stars of Fate=7, hero level=1, XP=0).

## Cross-references

- `tools/rerw-src/lib/save_mint.py` — production mint, both fixes folded in
- `tools/rerw-src/lib/hc_walker.py` — dynamic HC body offset walker (lifts the chapter-2 source gate)
- `rw/key-findings/save-silencer-mechanism.md` — why the AS-removal approach sidesteps the silencer
- Prior chapter-1 goldens (superseded by this one):
  - `rw/saves/edits/golden/geppetto/chapter1/dynamic-mint__from-chapter3-laser_lenses_1-proof/` — first chapter-3 -> chapter-1 mint POC, had both carryover bugs
  - `rw/saves/edits/golden/geppetto/chapter1/as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof/` — fixed activity-icon carryover, still had banner carryover
- ActivityScore_Serialize: image+0x1da440 (the per-record deserializer that no longer runs for count=0 files)
