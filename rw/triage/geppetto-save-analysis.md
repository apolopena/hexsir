# Geppetto Save File Analysis

**Status:** triage
**Created:** 2026-04-25

## Sources

- rw/saves/proofs/geppetto/clean/Profile_1.ob (69,459 bytes — no active run)
- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob (74,239 bytes)
- rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob (76,465 bytes)
- rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob (78,460 bytes)

## Confirmed Findings

### CRC32 Checksum
- Location: offset `0x0C` (12), 4 bytes little-endian
- Body starts at offset `0x10` (16)
- `hexsir checksum verify` confirms the location

### XP Value (unique per file, modifiable)
- Ch2: `2690` at offset `0xf1ee`
- Ch3: `16297` at offset `0xf68a`
- Epilogue: `36569` at offset `0xf8ea`
- Stored as int32 LE, unique match in each file

### Profile-Level Dream Shards
- GUID: `b43eeb58d162fa41acef99d128f2cb`
- Shows `101` in ALL files including CLEAN
- This is **NOT** the in-run Dream Shards shown in HUD — it's persistent profile currency

### File Structure
- Type registry: `0x00` – `0x700`
- Profile data: `0x700` – `~0x10000`
- String index: `0x10000` – `0x12000`
- Run saves are ~5KB larger than CLEAN (run-specific data)

### Level (modifiable)
- GUID: `b5317efe6f4a95737325675793e600`
- Tested: changing Level from 5 to 10 worked. Max XP updated, talent slots opened correctly.
- Game cap is 15; save accepts higher values.
- Levels 25/99/100 tested:
  - Damage scales with level (confirms damage is derived)
  - Float overflow between L25–L99: damage goes negative
  - UI handles 6-digit damage numbers gracefully

### Damage Is Derived
- Damage scales with level modifications
- Float overflow occurs between L25–L99
- Likely formula: `base_damage * level_multiplier` (float math)

### Chapter Counter Pattern (1 → 2 → 3)
- GUID `13fa8e2c314d88babb71a8e3c4df01`
- GUID `6661756c746465662e6f7426ba4519` (ASCII: `faultdef.ot&`)

### Type=8 Records
- 35 common GUIDs found, all constant across files (static IDs).

## Unresolved

### In-Run Dream Shards (101 → 21 → 29)
- NOT found as int32 with any consistent GUID/pattern
- Exhaustive search returned zero matches
- Likely stored differently: packed, in an inventory array, or computed

### Health (149 → 288 → 439)
- NOT found as int32
- Probably derived from Vitality + Level

### Stats (Vitality, Armor, Crit, Damage in Epilogue)
- Multiple matches, no consistent GUID pattern
- Structure shifts between files
- Damage found in Ch2/Ch3 but not Epilogue (481) — inconsistent storage

### Stars of Fate (1 → 2 → 0)
Search pattern: Ch2=1, Ch3=2, Epi=0. None of these worked:
- 15-byte GUID + int32 value
- Variable GUID lengths (12, 14, 15, 16)
- Gaps between GUID and value (1, 2, 4 bytes)
- int8 and int16 value types
- Float representations
- All record types (0–40)
- Raw byte pattern matching
- Region search near Dream Shards

Conclusion: not stored as GUID+value. Likely an item count in an array/inventory structure.

### Item Counts and Abilities
- No clear storage pattern for items
- Abilities not investigated

## Notes

### Working Hypothesis
Run stats appear to be computed at runtime:
```
base_stats + equipment_bonuses + ability_bonuses = displayed_stat
```
This is why Level works (simple stored value) but individual stats don't have a single moddable location.

### Future Work
1. Decode `Heroes\Geppetto.herodef.ot` for base stats and formulas
2. Find equipment/item data structures (likely GUID-based with complex nesting)
3. Reverse engineer the ability system
4. Binary diff CLEAN vs run saves to isolate run-specific data region
5. Look for array structures (length + item GUIDs pattern)

### Tool References
- `./tools/hexsir checksum verify` — validates checksum location
- `scripts/python/rw/analyze_save.py` — record markers, strings, value search
- `scripts/python/rw/mod_save.py` — modify values by GUID or offset
