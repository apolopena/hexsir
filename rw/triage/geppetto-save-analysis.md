# Geppetto Save File Analysis

**Status:** triage
**Created:** 2026-04-25
**Last audited:** 2026-05-01

## Sources

- rw/saves/proofs/geppetto/clean/Profile_1.ob (69,459 bytes — no active run)
- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob (74,239 bytes)
- rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob (76,465 bytes)
- rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob (78,460 bytes)

## Conquered (moved out of this triage)

The following items, originally documented here as findings, have been confirmed and folded into key-findings docs. They are NOT repeated here per the rule that triage holds only unresolved items.

- **CRC32 location, save body offset, header structure** → `rw/key-findings/save-binary-format.md` and `rw/key-findings/save-edit-pipeline-2026-04-30.md`
- **XP value (per-chapter offsets, int32 LE) — at `oCDtEntityCpntGroupLevelPersistentData` body+0x15** → pipeline doc + `tools/rerw-src/data/save-fields.yaml`
- **Profile-Level Dream Shards GUID** → pipeline doc / save-fields.yaml
- **Hero Level GUID — at `oCDtEntityCpntGroupLevelPersistentData` body+0x11** → pipeline doc; written by `rerw write savefile --level N`
- **Chapter counter GUIDs (`13fa8e2c…` and `6661756c74…`)** → pipeline doc; written by `rerw write savefile --chapter N`
- **Damage is derived from level (multiplier-based)** → pipeline doc gotchas
- **Stars of Fate** — was listed unresolved here. **Conquered 2026-04-30**: lives at `oCDtEntityCpntHeroControllerPersistentData` body+0x29 (u32). See pipeline doc → "Edit recipes → Stars of Fate live count". Verified spendable in-game.
- **In-Run Dream Shards (held)** — was listed unresolved here. **Conquered 2026-05-01 (BREAKTHROUGH-2)**: lives at `oCDtEntityCpntHeroControllerPersistentData` body+0x1D as **float32** (byte-misaligned), front-anchored across all chapters. The HUD reads this byte range verbatim — no recompute from earned − spent. Verified end-to-end via lab `held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof` (golden); HUD shows 99 on load with earned=0/spent=0. The 2026-04-30 "990 at HC+0x35d" partial finding was the SPENT-at-dream-tree counter (also float32; lives at a chapter-shifting offset resolved by `lib/hc_walker.py`), not held. Adjacent +0x19 holds total earned-this-run (= held + spent). Reference: `rw/key-findings/held-dream-shards.md`. Edit via `rerw write savefile shards <number>`.
- **Held Raven Feathers** — was listed unresolved as "held inventory". **Conquered earlier this session**: lives at `oCDtCurrentRunProfileData` body+0x15D (u32). Verified end-to-end via held-feathers-14 lab. Edit via `rerw write savefile feathers <number>`.
- **Held Nightmare Keys** — was listed unresolved as "held inventory". **Conquered 2026-04-30 / -05-01**: HeroIngredient vector at HC body+0x21; per-record format `u32 type_id + u32 count`; type_id `0xc4cb986e` = Nightmare Key. Edit via `rerw write savefile keys <number>` (existing-record case).

## Still unresolved

### Health (149 → 288 → 439)

- NOT found as int32
- Hypothesis: derived from Vitality + Level (per the working hypothesis below)

### Stats (Vitality, Armor, Crit, Damage in Epilogue)

- Multiple matches, no consistent GUID pattern
- Structure shifts between files
- Damage found in Ch2/Ch3 but not Epilogue (481) — inconsistent storage
- Strong candidate for being computed at runtime, not stored as a single value

### Item Counts and Abilities

- **2026-05-01 update**: held inventory partially mapped. Conquered: Nightmare Keys (HeroIngredient vec at HC+0x21, per-record `u32 type_id + u32 count`), Raven Feathers (CRP body+0x15D, u32), Dream Shards (HC body+0x1D, float32). Still unmapped: held wood, held bean, and any other ingredient-type held resources beyond the three conquered. Magical objects (the 68 Dragon's Hide / Vorpal Blade etc. items) are decoded; add/swap/remove mechanism documented in `rw/key-findings/magical-objects.md` (1 verified golden, no CLI subcommand yet).
- Cross-reference: `rw/triage/save-mint-status.md` item (1)
- Abilities not investigated

## Notes

### Working hypothesis (still standing)

Run stats appear to be computed at runtime:
```
base_stats + equipment_bonuses + ability_bonuses = displayed_stat
```
This is why Level works (simple stored value) but individual stats don't have a single moddable location.

### Future work (still relevant)

1. Decode `Heroes\Geppetto.herodef.ot` for base stats and formulas (now decoded — see `rw/dumps/geppetto/Geppetto.herodef.ot.DtHeroDefinition.gen` and pipeline doc)
2. Find equipment/item data structures (likely GUID-based with complex nesting)
3. Reverse engineer the ability system
4. Binary diff CLEAN vs run saves to isolate run-specific data region
5. Look for array structures (length + item GUIDs pattern)

### Tool references

- `tools/rerw-src/lib/cooked.py` — primary save decoder/encoder (replaces older Python scripts)
- `tools/rerw-src/rerw write savefile` — typed field edits via GUID locator
- `./tools/hexsir checksum verify` — validates checksum location
