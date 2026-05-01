# dynamic-mint__from-chapter3-laser_lenses_1-proof

**SUPERSEDED 2026-05-01** by `mint__from-chapter3-laser_lenses_1-proof/` — that golden is produced directly by `rerw mint savefile` (the dynamic walker is now folded into production) and has fixes for both activity-icon carryover and chapter-progression banner carryover that were unresolved here.

**Promoted to golden:** 2026-05-01
**Hash (SHA-256):** `d4ce00f27502a6ff` (full: see file)
**Size:** 76465 bytes

## Provenance

- **Source proof:** `rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob` (76465 bytes, original chapter-3 boss-kill proof, character Geppetto)
- **Mint method:** experimental dynamic mint (`.ai/scratch/mint-dynamic-offsets/dynamic_mint.py`) — applied via the `hc_walker.py` dynamic offset resolver, NOT via the production `rerw mint savefile` command (which is gated to chapter-2 sources only).
- **Mint config:** chapter=0 (ch1), stars_of_fate=7, hero_level=1, hero_xp=0

## What this golden proves

End-to-end viability of dynamic-offset minting across chapters. The HC body wire-format walker correctly resolves `dream_shards_spent`, `raven_feathers_consumed`, and `stars_of_fate` to their actual file positions in a chapter-3 source (HC body 1641 bytes), where hardcoded offsets would have corrupted the output.

Verified in-game:
- Loads cleanly (no SaveCompat modal — silencer not triggered)
- Chapter shows as 1 (chapter rollback worked)
- Playtime 00:00 (CRP+0xE5 zero took)
- Damages low / Score low (per-run state zeroed)
- Talents and magical objects from chapter-3 progression preserved

## Known bug — activity-icon carryover (RESOLVED 2026-05-01)

The score-details page used to display the 11 chapter-3 ActivityScore icons because each AS body (preserved verbatim by this mint to avoid the silencer) contained chapter-3 icon paths.

**Resolution:** the next golden in the chain — `as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof/` — removes all AS records and sets the parent count u32 to 0. The deserializer's per-record loop runs 0 times, no icons render, no silencer trip. See that golden's breakthrough.md for the mechanism.

The "score-zero suppression" hypothesis explored by `rw/saves/edits/lab/dynamic-mint-as-scores-zero__from-chapter3-laser_lenses_1-proof/` was **falsified** in-game (zeroing the trailing float still showed icons). AS-count=0 was the working fix.

**This golden is superseded** for clean-mint use by `as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof/`. The production `rerw mint savefile` command now applies AS-removal automatically.

## Cross-references

- `rw/key-findings/save-silencer-mechanism.md` — why ActivityScore bodies are preserved
- `rw/triage/mint-hardcoded-offsets.md` — origin of the dynamic-mint experiment
- `.ai/scratch/mint-dynamic-offsets/hc_walker.py` — the wire-format walker
- `.ai/scratch/mint-dynamic-offsets/dynamic_mint.py` — the experimental mint that produced this golden
- ActivityScore_Serialize: image+0x1da440 (3 fields: 2 asset descriptors + 1 trailing 4-byte float)
