# Geppetto Save File Analysis

**Status:** triage
**Created:** 2026-04-25
**Last audited:** 2026-04-30

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

## Still unresolved

### In-Run Dream Shards (101 → 21 → 29)

Pattern across saves: the in-run held shards count is NOT the persistent profile shards (which sits at 101 in every save).

- NOT found as int32 with any consistent GUID/pattern (confirmed 2026-04-25)
- Exhaustive GUID-based search returned zero matches
- **2026-04-30 partial finding**: a float = 990 was found at HeroController body+0x35d in the chapter-2 proof. We zeroed it during v4 mint. Suspected to be dream-shards-collected (per-run cumulative). This is *adjacent* to but distinct from the held-shards count puzzle. The held count (the spendable HUD value) is still unmapped.
- Likely stored differently: packed, in an inventory array, or computed

Cross-reference: `rw/triage/save-mint-unresolved.md` item (1) "held inventory" — possibly the same record as held shards.

### Health (149 → 288 → 439)

- NOT found as int32
- Hypothesis: derived from Vitality + Level (per the working hypothesis below)

### Stats (Vitality, Armor, Crit, Damage in Epilogue)

- Multiple matches, no consistent GUID pattern
- Structure shifts between files
- Damage found in Ch2/Ch3 but not Epilogue (481) — inconsistent storage
- Strong candidate for being computed at runtime, not stored as a single value

### Item Counts and Abilities

- No clear storage pattern for items
- **2026-04-30 update**: held inventory (Nightmare Keys, Raven Feathers, Bean ingredient) is now empirically confirmed to persist across save → restart cycles. Byte location remains unmapped.
- Cross-reference: `rw/triage/save-mint-unresolved.md` item (1)
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
