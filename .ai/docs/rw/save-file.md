# Save File Reverse Engineering

> **DEPRECATED — Do not use.** See `rw/docs/` for current documentation. This file is pending cleanup and may contain stale or incorrect information.


## Critical: Save System Constraints

Ravenswatch is a roguelike. The game autosaves only at chapter boundaries (every ~20 minutes). A full run is ~60 minutes with 3 chapters.

**This means:**
- Maximum 3 save snapshots per run, 20 minutes apart
- Cannot save before/after a single action to diff
- No way to isolate "picked up one item" changes
- All analysis must work with coarse-grained snapshots

This severely limits binary diff approaches for identifying item/inventory storage.

## Files Analyzed
| File | Size | Description |
|------|------|-------------|
| interim/gepetto_run_1/CLEAN_Profile_1.ob | 69,459 | No active run |
| interim/gepetto_run_1/chapter2/laser-lenses_1/Profile_1.ob | 74,239 | Mid-run |
| interim/gepetto_run_1/chapter3/laser_lenses_1/Profile_1.ob | 76,465 | Chapter 3 |
| interim/gepetto_run_1/epilogue/laser-lenses_1/Profile_1.ob | 78,460 | Near end |

Run saves are ~5-9KB larger than clean (run-specific data).

## Confirmed Structure

### Header
```
0x0000 - 0x000B  Magic/version (12 bytes)
0x000C - 0x000F  CRC32 (4 bytes, little-endian)
0x0010+          Body (CRC covers this)
```

### Regions
```
0x0000 - 0x0700   Type registry (class names)
0x0700 - 0x10000  Profile/run data
0x10000 - 0x12000 String index
```

### Record Format
```
11 11 bb aa     Start marker
XX XX XX XX     Type/length
[15 bytes]      GUID
[4 bytes]       Value (int32 LE)
22 22 bb aa     End marker
```

## Working Modifications

### Level
- **GUID:** `b5317efe6f4a95737325675793e600`
- **Tested:** 5→10 worked. Talent slots opened, Max XP updated.
- **Extended:** 25, 99, 100 all work. Damage scales with level but overflows negative between 25-99 (float math).
- **Game cap:** 15, but save accepts any value.

### Profile Dream Shards
- **GUID:** `b43eeb58d162fa41acef99d128f2cb`
- Shows 101 in ALL files including CLEAN
- This is persistent profile currency, NOT in-run shards

### XP
Unique offset per save file (no consistent GUID):
- Ch2: 0xf1ee (2690)
- Ch3: 0xf68a (16297)
- Epi: 0xf8ea (36569)

## Failed Searches

### Stars of Fate (1→2→0)
Exhaustive search found nothing:
- 15-byte GUID with int32 value
- Variable GUID lengths (12, 14, 15, 16)
- Gap between GUID and value (1, 2, 4 bytes)
- int8 and int16 value types
- Float representations (0.0, 1.0, 2.0)
- All record types (0-40)
- Raw byte pattern matching
- Region search near Dream Shards

**Conclusion:** Not stored as GUID+value. Likely item count in array structure.

### In-Run Dream Shards (101→21→29)
No consistent GUID or pattern found. Separate from Profile Dream Shards.

### Stats (Vitality, Damage, Health)
| Stat | Ch2 | Ch3 | Epi | Notes |
|------|-----|-----|-----|-------|
| Vitality | 27 | 85 | 75 | Went DOWN in epilogue |
| Damage | 38 | 159 | 481 | 481 NOT FOUND |
| Health | 149 | 288 | 439 | NOT FOUND as int32 |

Multiple matches per value, no consistent GUID. Structure shifts between files.

## Current Hypotheses

### Why Level Works But Stats Don't
Level is a core persistent attribute stored as simple GUID+value.

Stats are computed at runtime:
```
displayed_stat = base + equipment_bonuses + ability_bonuses
```

### Damage is Derived
Level 25/99/100 testing confirmed damage scales from level using float math. Overflow between 25-99 causes negative values.

### Inventory Storage
Items like Stars of Fate likely stored as:
- Array with length prefix
- Item entries with dynamic offsets
- Container GUID wrapping nested structures

### Run-Specific Data
The ~5KB size difference between CLEAN and run saves contains:
- Current equipment
- Collected items
- Active abilities
- Run currency

## Patterns Found

### Chapter Counter (1→2→3)
Two GUIDs increment with progression:
- `13fa8e2c314d88babb71a8e3c4df01`
- `6661756c746465662e6f7426ba4519` (ASCII: "faultdef.ot&")

### Type=8 Records
35 common GUIDs across all files. All constant values - static IDs, not dynamic.

## Next Steps
1. Binary diff CLEAN vs run to isolate inventory region
2. Find array container GUID (length + items pattern)
3. RE herodef .gen for base stat formulas
4. Look for nested object structures
