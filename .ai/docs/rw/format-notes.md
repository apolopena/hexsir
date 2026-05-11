# OEngine Format Notes

> **DEPRECATED — Do not use.** See `rw/docs/` for current documentation. This file is pending cleanup and may contain stale or incorrect information.


Proprietary engine (OSome Studio / PassTech Games). No public documentation, no modding community, no prior reverse engineering work exists. Everything here is original research.

**See also:**
- [save-file.md](save-file.md) - save file RE findings and hypotheses
- [tools.md](tools.md) - working scripts and usage

## File Types
| Ext | Format | Example |
|-----|--------|---------|
| `.ob` | Binary save | Profile_1.ob |
| `.ot` | Plaintext config | ApplicationSettings.ot |
| `.gen` | Compiled binary | Geppetto.herodef.ot.DtHeroDefinition.gen |

## Binary Save File (.ob)

### Layout
```
0x0000 - 0x000B  Header (magic/version)
0x000C - 0x000F  CRC32 checksum (4 bytes, little-endian)
0x0010 - 0x0700  Type registry (class names)
0x0700 - 0x10000 Profile/run data
0x10000+         String index
```

Run saves are ~5KB larger than clean saves (run-specific data added).

### CRC32
- Location: offset 0x0C
- Covers: offset 0x10 to EOF
- Computation: `zlib.crc32(data[16:]) & 0xFFFFFFFF`

### Record Format
```
11 11 bb aa     Start marker
XX XX XX XX     Type/length (4 bytes)
[15 bytes]      GUID
[4 bytes]       Value (int32 LE)
22 22 bb aa     End marker
```

## Modifying Level

**GUID:** `b5317efe6f4a95737325675793e600`

**Steps:**
1. Find GUID in file
2. Value is int32 LE immediately after GUID
3. Modify value
4. Recalculate CRC32 and write to offset 0x0C

**Tool:**
```bash
python scripts/python/rw/mod_save.py Profile_1.ob --show
python scripts/python/rw/mod_save.py Profile_1.ob --set Level 15 -o modded.ob
```

**Results:**
- Level 5→10: worked, talent slots opened, Max XP updated
- Level 25, 99, 100: worked, but damage overflows negative between 25-99 (float math)
- Game cap is 15, save accepts any value

## Other Modifiable Values

**Profile Dream Shards**
- GUID: `b43eeb58d162fa41acef99d128f2cb`
- Shows 101 in all saves including CLEAN
- This is persistent currency, NOT the in-run Dream Shards

**XP** (unique offset per save, no consistent GUID)
- Ch2: 0xf1ee (2690)
- Ch3: 0xf68a (16297)
- Epi: 0xf8ea (36569)

## What Doesn't Work

**Stars of Fate (1→2→0):** Exhaustive search found nothing. Tried 15-byte GUID, variable lengths, gaps, int8/16, floats, all record types. Not stored as GUID+value.

**In-Run Dream Shards (101→21→29):** No consistent pattern.

**Stats (Vitality, Damage, Health):** Multiple matches, no consistent GUID. Damage confirmed derived from Level.

These are likely stored in inventory/array structures with dynamic offsets.

## Patterns Found

**Chapter counter (1→2→3):**
- GUID `13fa8e2c314d88babb71a8e3c4df01`
- GUID `6661756c746465662e6f7426ba4519`

**Type=8 records:** 35 common GUIDs, all constant across files (static IDs).

## Text Config (.ot)
Type prefixes: `b|`=bool `i|`=int `u|`=uint `f|`=float `s|`=string

## Local File System

**Save location:** `Steam/steamapps/common/Ravenswatch/_Save/Profile_1.ob`

**Game assets:** `Steam/steamapps/common/Ravenswatch/` contains:
- `ApplicationSettings.ot` - plaintext config (XP tables, difficulty, modifiers)
- `EngineSettings.ini` - render settings
- `UsedRscList.ot` - asset manifest (ciphered paths)
- Assets folder with `.gen`, `.dxt` files

**Working copies:** `interim/Ravenswatch/` mirrors the above
**Decoded asset list:** `interim/dumps/UsedRscList-decoded.ot`

**Geppetto herodef files:**
- Windows: `Steam/steamapps/common/Ravenswatch/_Cooking/Nqhdzdidrzv/Aqurqv/Kqjjqiir.nqurtqh.ri.NiAqurNqhdzdidrz.yqz`
- Decoded: `_Cooking/Definitions/Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen`
- Local copy: `interim/Kqjjqiir.nqurtqh.ri.NiAqurNqhdzdidrz.yqz` (18KB)

## Filename Cipher

Asset filenames inside `_Cooking/` use substitution cipher. Now mostly solved.

**Decoder:** `interim/decode-name-cypher-fixed.js`

**Current cipher:**
```
PLAIN:  abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
CIPHER: gabtqhynd%mlxzrj%uviwkopscWBSNMVKAXEIGHU#TPLFQJDR#C#
```

**Key fix (2024-04-24):** Added 5 uppercase mappings that were passing through:
| Cipher | → Plain | Example |
|--------|---------|---------|
| N | D | NarkHills → DarkHills |
| M | E | Mraser → Eraser |
| V | F | Vog → Fog |
| P | Q | Puest → Quest |
| J | U | Jpdate → Update |

**Critical:** `.ri` → `.ot` (ciphered extension)

**Verified working:**
- `Kqjjqiir` → `Geppetto`
- `Aqurqv` → `Heroes`
- `Qqpiwuq` → `Texture`
- `Uruxglv` → `Normals`
- `NgumAdllv` → `DarkHills`
- `VryOhRgu` → `FogOfWar`

**Remaining unknowns:** 6 positions (j, q lowercase; O, S, Y, Z uppercase) - rarely used.

**Decoded tree:** `interim/tree-decoded.txt` - regenerated with working cipher.
