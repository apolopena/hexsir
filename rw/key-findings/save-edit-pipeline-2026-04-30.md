# Save edit pipeline — session findings 2026-04-30

End-to-end save-edit pipeline reached a working state. We can read any save into a structured tree, edit values inside any record (top-level or nested), recompute the file's CRC, and the game accepts the result. Verified empirically: edits persist, the game runtime treats them as real state changes (zeroed counters accumulate from zero on next play), and false-negative error modals can be distinguished from true failures.

This document is the canonical reference for what was learned this session. Cross-referenced from `save-subsystem.md` and `decoder-work-2026-04-30.md`.

---

## TL;DR

- **Decoder + recursive tree walker live**: `tools/rerw-src/lib/cooked.py`. Round-trip byte-equal on every save tested.
- **CRC32 (zlib polynomial)** verified empirically and recomputed automatically on encode.
- **Two-tier object model** discovered: top-level instances listed in the leading instance index table + nested sub-objects embedded inside parents' bodies. Confused us several times before being identified.
- **Cross-save record transplant is impractical** because object references are u32 indices into the per-load object pool; the same logical record has different indices in different saves and clean's bodies break under chapter2's ordering. (Ruled out as a path B mechanism.)
- **Nested body editing works.** This is the actual mechanism behind path B.
- **Stat-source mapping verified:** specific records hold specific user-visible stats, mapped by edit-and-test.
- **Hero level edit via existing `rerw write savefile --level N`** confirmed working in combination with our zero-out edits.
- **Save-load error modal is sometimes a false negative** (already documented in `CLAUDE.md`).

---

## Architecture findings

### Two-tier object structure

Save files contain two distinct kinds of object frames:

1. **Top-level instances.** Listed in the leading "instance index table" at the start of the object section. Parsed in the loader's main per-object loop. These are the *progression / registry / persistence* records (e.g. `SkillProfileData`, `oCDtHeroProfileData`, all the unlock-condition classes, plus per-run `oCEntityPersistentDataContainer`, `oCDtEntityCpntSkillControllerPersistentData`, etc.).
2. **Nested sub-objects.** Embedded inside another top-level frame's body via inline `0xAABB1111`/`0xAABB2222` markers. The parent's `Serialize()` reads them via sub-object dispatch. Most of the user-visible runtime classes — `oCDtGameProfile` (the wrapper root), `oCDtPlayerProfileData`, `oCDtCurrentRunProfileData`, `ActivityScore`, `HeroScoreData`, `HeroMOPersistentData`, all 649+ event listeners, all 574 game-lock records — live here.

The diff "+102 instance frames" between a clean and a chapter-2 save (which we initially used to pick transplant targets) was a recursive count. The *top-level* diff is only **+60 frames**. The remaining 42 are nested.

The wrapper `oCDtGameProfile` appears AFTER the 1199 top-level instance frames in chapter 2 — it is the "outer object" that gets serialized last by the loader. Its body holds two children: `oCDtPlayerProfileData` and `oCDtCurrentRunProfileData`.

### Object reference encoding

Cross-object references in serialized streams are **u32 indices** named `uOjbectId` (sic) into the per-load object pool, not GUIDs. Reader: `oCBinaryLoader_ReadObjectRef` (image+0x4e7f50). Sentinel values:

- `0xFFFFFFFF` — null reference.
- `0xFFFFFFFE` — self reference.
- Otherwise the value indexes the per-load array of constructed objects.

This is why naive cross-save transplants fail: a chapter2 body's `uOjbectId = 695` points at a SkillController in chapter2's table; in clean's table position 695 is a different class (HeroRankCondition). Index alignment alone isn't enough either, because clean's bodies contain references back to clean-specific positions.

### CRC32 verification (save files only)

`.ob` save files carry a 4-byte CRC32 at file offset `0x0C`. Algorithm: standard zlib polynomial (`crc32_zlib` at image+0x505cc0). Computed over body bytes from `0x10` to end-of-file. Encoder auto-recomputes. Confirmed by `zlib.crc32(data[0x10:]) == 0xc7923b53` for a clean save; the loader compares this in `save_load_parse_top_level` (image+0x64aa50).

`.gen` files (cooked entity definitions) do NOT have a CRC slot — they carry an ASCII `"Cooked"` magic at the same offset.

### Per-class metadata in the class registry

Each class entry after its name is **16 bytes**, layout:

| Offset | Type | Field |
|---|---|---|
| +0x00 | u32 | `m_uId` (FNV-style class identifier, stable across saves) |
| +0x04 | u16 | `m_uVersionMaj` |
| +0x06 | u16 | `m_uVersionMin` |
| +0x08 | u32 | `schema_version` (the gate Serialize uses for backward-compat field reads) |
| +0x0C | u32 | `m_uParentId` (class id of parent; `0xFFFFFFFF` = no parent) |

`schema_version` is what we initially mislabeled as `field4`. It's the value class `Serialize()` methods compare against to decide which fields to read. For our test saves: `oCDtPlayerProfileData` schema_v=8, `oCDtCurrentRunProfileData` schema_v=18, `ActivityScore` schema_v=0, `HeroScoreData` schema_v=2.

### Class registry can grow between saves

The leading class registry is per-file. Between a clean save (26 classes) and a chapter-2 save (39 classes), 13 ch2-only classes are added (skill controllers, value modifiers, item records, GameMode/GameModeDefault, ActivityScore, HeroMOPersistentData, etc.). Class indices for shared classes can therefore differ between saves even when the same class is present, requiring remap logic for any cross-save operation.

---

## Decoded class schemas (Serialize methods reversed)

### oCDtPlayerProfileData

- Class id `0x18fd68c1`, size `0x20`, schema_v=8 currently.
- Serialize: `oCDtPlayerProfileData_Serialize` (image+0x1da580), vtable[3] of `oCDtPlayerProfileData_vftable` (`0x140eaf598`).
- Body wire format (after the 16-byte vtable pointer is NOT serialized): 5 fields, all version-gated.

| Body offset | Type | Min schema_v | Notes |
|---|---|---|---|
| +0x00 | i32 | 0 (always) | `field_at_08`. Identified as **selected hero index** — set to 99 to confirm; game routes to "Random hero" selector. Geppetto = 6. |
| +0x04 | i32 | 2 | `field_at_0c` |
| +0x08 | i32 | 6 | `field_at_10` |
| +0x0C | u8 | 7 | `field_at_14` |
| +0x0D | u32 | 8 | `field_at_18` |

Total wire size at schema_v=8: 17 bytes. Body has migration logic for older versions (normalizes `field_at_08` for version<3 / version<5). No cross-object references; safe to edit directly.

### oCDtCurrentRunProfileData

- Class id `0x18fd68c3`, size `0x220`, schema_v=18 currently.
- Serialize: `oCDtCurrentRunProfileData_Serialize` (image+0x1da9a0), vtable[3] of `oCDtCurrentRunProfileData_vftable` (`0x140ed8528`).
- Body is 1311 bytes (chapter2 example). Mostly composed of:
  - Leading uObjectId reference list (`0xAABB1111` + count + N×u32 indices + `0xAABB2222`) pointing to all per-run top-level entity objects (the 60 ch2 extras at indices 693–727+728).
  - String fields for hero definition path, run seed, etc.
  - Embedded sub-objects: 2× `oCEntityPersistentDataContainer`, 6× `ActivityScore`, 1× `HeroScoreData`.
  - Several `vtable[0xa8]` (uObjectId) reads referencing other top-level run-state records.

The body uses many helper-function sub-serializers (`FUN_1401c5e30`, `FUN_140670af0`, `FUN_14020b310`, `FUN_14020af30`, `FUN_140205710`, `FUN_14020ab90`) — version-gated by schema_v 2/7/10/14/15.

Confirmed: the **playtime float (1409.92 = 23:29 in seconds)** lives at body offset `+0xe5` (byte-misaligned). Chapter index lives elsewhere in this body (not yet pinpointed exactly; rerw `--chapter` does it).

### ActivityScore (path B's first nested-edit success)

- Class id `0x1b2ed792`, size `0xb8`, schema_v=0.
- Serialize: `ActivityScore_Serialize` (image+0x1da440).
- Three-call wire format:
  1. `FUN_1401c5e30(stream, this+0x08)` — reads 2 length-prefixed strings (8 bytes minimum when both empty).
  2. `FUN_140670af0(stream, this+0x40)` — reads u32 + nested 2 strings + u32 + (optional string if first u32 ≠ 0). 16 bytes minimum.
  3. `vtable[0x78](stream, this+0xb0, 0)` — reads 1 byte.
- **Minimum valid body = 25 bytes** (4+4+4+4+4+4+1). Empty strings, all-zero scalars.
- No `vtable[0xa8]` calls → no uObjectId references in body → safe to replace with synthesized minimum.

A chapter2 run typically has 6 ActivityScore instances nested under `oCDtCurrentRunProfileData` (one per scoring category: Damage Dealt, Support, Suffering, Resources, etc.). Replacing each with the 25-byte minimum body resets that category in-game.

### HeroScoreData

- Class id `0x1b809782`, schema_v=2.
- Body wire format (151 bytes for chapter2 example):

| Offset | Field |
|---|---|
| +0x00 | `u32 count1 = 5` followed by 5 floats (per-stat ratios — e.g. 0.27, 0.38, 24, 0.17, 0.5) |
| +0x18 | `u32 count2 = 10` + 10 floats — **damage dealt total** is first (77000), then per-source breakdown |
| +0x44 | `u32 count3 = 4` + 4 floats |
| +0x58 | `u32 count4 = 3` + 3 floats — **damage taken** is first (745.8) |
| +0x68 | `u32 count5 = 6` + 6 floats |
| +0x84 | `u32 strlen = 11` + 11 bytes player nickname (e.g. `"Quadrotonic"`) + 4-byte tail `02 00 00 00` |

To zero stats while keeping load-valid: preserve the count values and trailing string, zero only the 28 floats in between. We did this and it loaded fine — but the displayed stats DIDN'T reset, because **HeroScoreData is a cached snapshot**, not the source of truth. Confirmed by finding identical float bytes in `HeroController` body — that's the actual source.

### oCDtEntityCpntHeroControllerPersistentData

- Top-level instance, class id from the chapter2 registry (1 per active hero). Body is 873 bytes in chapter2 example.
- Per-run **damage stats** stored at body offsets starting at `+0x11` (byte-misaligned reads, NOT 4-aligned):

| Body offset | Float | Meaning |
|---|---|---|
| +0x11 | 77001.3 | Damage dealt total |
| +0x15 | 745.8 | Damage taken |
| +0x19 | 1091 | Damage breakdown |
| +0x1d | 101 | Damage breakdown |
| +0x35d | 990 | Additional damage stat |

Zeroing these (16 bytes at +0x11, plus 4 bytes at +0x35d) **resets the displayed run-summary damage values** correctly. This is what we hit in the v2 zeroing test.

The first 16 bytes of the body (offsets 0x00-0x0F) are 4 hash-shaped u32s — likely the hero's identity (4-part GUID-like locator). Don't touch these.

### oCDtEntityCpntGroupLevelPersistentData

- Top-level instance, 1 per run. Body is 25 bytes.
- Layout:
  - +0x00–0x0F: 16-byte locator GUID (`9e8fb5317efe6f4a95737325675793e6` for the chapter2 example — used by rerw to find the level field).
  - +0x10: 1-byte alignment / type tag (`00`).
  - +0x11: u32 = **in-run hero level** (`5` originally; rerw `--level 1` flips this to `1`). Byte-misaligned 4-byte read.
  - +0x15: u32 (= 0xa820 = 2690 in chapter2; meaning unknown).

`rerw write savefile --level N` writes 4 bytes at this offset. Confirmed working: edits hero level + downstream HUD values (XP, damage scaling) update correctly.

### Records identified but not edited this session

- `oCEntityCpntCounterPersistentData` (3 instances at top level): 21-byte bodies, look like `(16-byte ID hash + 4-byte u32 + 1-byte tag)` triples. Specific stats unidentified.
- `oCEntityValueModifier` (6 nested): 24-byte bodies, hold buff/debuff multipliers (0.1, 0.05, -10, etc. observed).
- `oCEntityValueUnion` (6 nested): 12-byte bodies, single typed value each.
- `oCEntityCpntModifierHolderPersistentData` (1 top-level, 265 bytes): collection of modifier values.

---

## Stat-source mapping (verified)

The displayed end-of-run score page values map to file fields as follows:

| Displayed stat | Stored in | Notes |
|---|---|---|
| Damage dealt | `HeroController` body +0x11 (primary) AND mirrored in `HeroScoreData` group 1[0] | Game reads from HeroController; HeroScoreData is a cached snapshot. |
| Damage taken | `HeroController` body +0x15 AND `HeroScoreData` group 3[0] | Same dual storage. |
| Other damage breakdown (1091, 990) | `HeroController` body +0x19 / +0x35d | Per-source counters. |
| Playtime (e.g. 1409s = 23:29) | `oCDtCurrentRunProfileData` own body +0xe5 | Float in seconds, byte-misaligned. |
| **Level reached** (cumulative across runs) | NOT YET LOCATED — almost certainly in `oCDtHeroProfileData` (per-hero lifetime stats) | This is APPENDED on each run end, not replaced. Next dig if you want it. |
| Per-category run summaries | `ActivityScore × 6` (nested in `oCDtCurrentRunProfileData`) | Replaceable with 25-byte minimum body. |

---

## Working operations

What our pipeline can do today, end-to-end and verified by in-game testing:

1. **Read any save file structurally.** Header, class registry, full recursive object tree. Round-trips byte-for-byte through the encoder.
2. **Zero per-run stats** (damage, playtime, score sub-totals) via targeted byte edits inside the relevant nested records. Game accepts; runtime starts at zero and accumulates correctly.
3. **Synthesize minimum-valid bodies** for classes whose Serialize wire format we know (proven for ActivityScore).
4. **Edit hero level** via existing rerw `write savefile --level N`. Combines cleanly with our zeroing edits.
5. **Edit chapter index** via rerw `write savefile --chapter N` (untested in this session but tooling exists).
6. **Edit talents** via rerw `write savefile --talent-slot N --talent-id ID --tier T` (existing, not exercised this session).
7. **Auto-recompute CRC32** on every encode.

---

## What does NOT work (with explanation)

1. **Cross-save record transplant by appending or replacing.** Object references are u32 indices into the per-load pool. Clean's instance ordering ≠ chapter2's, so neither save's bodies hold valid indices in a reassembled file. Even index-aligned transplants fail in the reverse direction (clean's body refs break under chapter2's ordering). Genuine cross-save migration would require per-class schema knowledge to remap every `uOjbectId` u32 inside every body — substantial work, deferred.

2. **Whole-body byte zeroing of variable-size records.** Bodies contain length-prefixed strings; if you zero a string-length to 0, the parser stops reading after 4 bytes per string, but the body's declared byte count is unchanged, so the *next* end-marker read lands in zero bytes instead of the marker. The body must be replaced with a synthesized minimum that fits the wire format exactly. We hit this with our first ActivityScore "zero entire body" attempt; fix was to write a 25-byte synthesized minimum.

3. **Whole-class-body zeroing for classes with `vtable[0xa8]` references.** Would zero a uObjectId index → resolves to "object 0" (`oCDtGameProfile`), which is the wrong class for whatever slot wants it. Causes object-graph corruption. Avoid.

4. **Heavy modification of `oCDtCurrentRunProfileData`'s leading uObjectId list.** Removing entries breaks the parent's expectation of N references. Not attempted.

---

## Tool reference: `lib.cooked`

Module path: `/home/ks73/repos/work/ravensmith/tools/rerw-src/lib/cooked.py`. Run from that directory or with `tools/rerw-src/` on `PYTHONPATH`.

### Imports

```python
from lib.cooked import (
    parse_file,           # bytes -> CookedFile
    parse_object_tree,    # CookedFile -> list[TreeNode]  (recursive)
    parse_object_section, # CookedFile -> list[ObjectBlock] (flat)
    find_class_in_tree,   # locate all instances of a class
    encode_file,          # CookedFile -> bytes (auto CRC for .ob)
    MARK_START, MARK_END, # 0xAABB1111 / 0xAABB2222
    ClassEntry, TreeNode,
)
```

### Parse a save / .gen file

```python
with open('Profile_1.ob', 'rb') as f:
    cf = parse_file(f.read())
print(f'classes: {len(cf.classes)}  object_section: {len(cf.object_section)} bytes')
print(f'is .gen file: {cf.header.is_cooked}')
print(f'CRC (or magic): {cf.header.magic_or_hash.hex()}')
```

`cf` is a `CookedFile` with:
- `cf.header` — the 16-byte header + variable trailer
- `cf.classes` — list of `ClassEntry` (name, uid, version_major, version_minor, schema_version, parent_id)
- `cf.object_section` — bytes; everything from leading instance index table through end of file

### Walk the recursive object tree

```python
roots = parse_object_tree(cf)
# roots[0..N-1] are top-level instances per the leading index table.
# The final root (after the last instance) is typically oCDtGameProfile,
# the wrapper "outer object" that contains the per-run state nested under it.

for path_idx, root in enumerate(roots[-3:], start=len(roots)-3):
    print(f'roots[{path_idx}]: {cf.classes[root.class_index].name} '
          f'({len(root.children)} children)')
```

Each `TreeNode` exposes:
- `node.start` / `node.end` — section offsets bounding the frame
- `node.class_index` — index into `cf.classes`
- `node.children` — list of nested `TreeNode`s
- `node.body_start` / `node.body_end` — section offsets of the body bytes (between class_index and end marker)

### Find all instances of a class anywhere in the tree

```python
hits = find_class_in_tree(cf, roots, 'ActivityScore')
for path, node in hits:
    body_size = node.body_end - node.body_start
    print(f'path {".".join(map(str, path))}  body {body_size} bytes')
# returns list of (path, node) — path is the chain of child indices
# from a root, e.g. [1199, 1, 2] = roots[1199].children[1].children[2]
```

### Edit a node's body bytes (replace, zero, splice)

```python
section = bytearray(cf.object_section)

# replace the full body of an ActivityScore with a minimum-valid 25-byte body
import struct
MIN_BODY = struct.pack('<I', 0) * 6 + b'\x00'   # 25 bytes
for path, node in sorted(find_class_in_tree(cf, roots, 'ActivityScore'),
                         key=lambda h: -h[1].start):  # high offsets first
    section[node.body_start:node.body_end] = MIN_BODY

# zero specific bytes inside a node (e.g. damage floats in HeroController body)
hc = find_class_in_tree(cf, roots, 'oCDtEntityCpntHeroControllerPersistentData')[0][1]
section[hc.body_start + 0x11 : hc.body_start + 0x21] = b'\x00' * 16

cf.object_section = bytes(section)
```

When you change the size of any body, the surrounding markers shift naturally — the file's bytes are just reflowed. The encoder doesn't need to be told.

### Re-encode with auto CRC

```python
out = encode_file(cf)
with open('output.ob', 'wb') as f:
    f.write(out)
```

For `.ob` save files, `encode_file` recomputes `zlib.crc32(body[0x10:])` and writes it at offset `0x0C`. For `.gen` files, the `"Cooked"` magic is preserved verbatim.

### CLI usage

```bash
cd /home/ks73/repos/work/ravensmith/tools/rerw-src

# header + class registry
python3 -m lib.cooked /path/to/Profile_1.ob

# byte-equal round-trip check (file → parse → encode → compare)
python3 -m lib.cooked /path/to/Profile_1.ob --check-roundtrip

# heuristic dump of object section (annotated by class)
python3 -m lib.cooked /path/to/Profile_1.ob --annotate

# recursive tree print (limit depth)
python3 -m lib.cooked /path/to/Profile_1.ob --tree --tree-depth 2

# locate a specific class anywhere in the tree
python3 -m lib.cooked /path/to/Profile_1.ob --tree-class ActivityScore
```

### rerw integration

Existing `rerw write savefile` (in `tools/rerw-src/commands/write_savefile.py`) operates by GUID-locator lookup against `tools/rerw-src/data/save-fields.yaml`. Combines additively with our raw-byte edits — produce a save edited via `cooked.py`, then run rerw `write savefile --level N` on it; both edits land cleanly with one final CRC.

Example combined flow (proven this session):

```bash
# 1. zero stats via cooked.py edit script (writes to lab dir)
python3 -m lib.cooked …  # custom script using lib.cooked APIs

# 2. set hero level via rerw on top of the zeroed file
./tools/rerw write savefile \
    --source rw/saves/edits/lab/zero_scores_v2/Profile_1.ob \
    --dest rw/saves/edits/lab/zero_scores_v2_level1 \
    --level 1

# 3. install
./tools/rerw swap savefile \
    --source rw/saves/edits/lab/zero_scores_v2_level1/Profile_1.ob
```

---

## Critical gotchas — read before doing edits

1. **Save-load error modal can be a false negative.** Already documented in `CLAUDE.md`. Modal saying "Error code: 4" → click OK and watch destination. If routed to Continue/New-Game dialog → save loaded successfully, modal was a warning. If routed to fresh-account hero selection → true failure, quit before next save event clobbers local with fresh defaults.

2. **HeroController float region is byte-misaligned.** The 4-byte floats at `+0x11`, `+0x15`, etc. are at 1-byte-shifted offsets, NOT 4-aligned. A 4-aligned dump will show garbage at `+0x10`, `+0x14`. Use `struct.unpack_from('<f', body, 0x11)` not `struct.unpack_from('<f', body, 0x10)`.

3. **CurrentRunProfileData playtime is also byte-misaligned** at body `+0xe5`.

4. **GroupLevel hero-level is byte-misaligned** at body `+0x11` (after a 16-byte locator GUID + 1 alignment byte at +0x10).

5. **Variable-length encoding traps.** Don't naively zero a variable-size body — the wire format requires that bytes-read = bytes-in-body, and zeroing string-length fields makes the parser stop early, leaving uneaten bytes that the loader misreads as the next marker. Either (a) preserve the existing structure (zero only float fields, leave counts and strings intact) or (b) replace the body wholesale with a synthesized minimum that exactly matches what `Serialize()` will read.

6. **Stats can be duplicated across records.** Damage values appear in *both* `HeroController` (the read-source) and `HeroScoreData` (a cached snapshot). Zeroing only one location won't change displayed values; zero the *primary* location (HeroController for damage). HeroScoreData zeroing is still good practice for consistency.

7. **"Level reached" on the score page is cumulative across runs**, not per-run. Stored separately from in-run hero level. Couldn't locate this session — likely lives in `oCDtHeroProfileData` (per-hero lifetime stats). Edit-and-test approach: pick a target HeroProfileData body field, zero, observe.

8. **Class indices are per-file.** Don't hardcode them — always look up `cf.classes[idx].name` against the file you're working with. A class at index 14 in clean might be at index 24 in chapter2.

9. **Top-level vs nested confusion.** Many of the most editable classes (`ActivityScore`, `HeroScoreData`, `HeroMOPersistentData`, `oCEntityValueModifier/Union`, all event listeners) are NESTED, not top-level. They don't appear in the leading instance index table. Use `parse_object_tree` (recursive) and `find_class_in_tree`, not `parse_object_section` (flat).

10. **Steam Cloud sync MUST be off** for Ravenswatch in Steam properties, or local edits get overwritten on game launch. Already documented in `CLAUDE.md`.

---

## Renamed Ghidra functions (this session)

Persisted in the Ghidra DB. Cross-walk the older `FUN_xxxxxxxx` references via these:

| Address | New name | Role |
|---|---|---|
| `0x1401da580` | `oCDtPlayerProfileData_Serialize` | vtable[3] of vtable @ 0x140eaf598 |
| `0x140193900` | `oCDtPlayerProfileData_typedesc_init` | Class registration |
| `0x1401da9a0` | `oCDtCurrentRunProfileData_Serialize` | vtable[3] of vtable @ 0x140ed8528 |
| `0x140193ad0` | `oCDtCurrentRunProfileData_typedesc_init` | |
| `0x1401da440` | `ActivityScore_Serialize` | vtable[3] of vtable @ 0x140eb0030 |
| `0x140193710` | `ActivityScore_typedesc_init` | |
| `0x1404e7f50` | `oCBinaryLoader_ReadObjectRef` | The uObjectId u32 index reader |
| `0x14064aa50` | `save_load_parse_top_level` | Function returning error code 4 |
| `0x1404e8690` | `save_load_parse_object_section` | Inner function, validates objects |
| `0x1404e7c50` | `save_load_read_header_flags` | Reads 0xAABB1111 marker + named flags |
| `0x140505cc0` | `crc32_zlib` | Standard table-driven CRC32 (zlib polynomial) |

Data labels also added: `ActivityScore_vftable`, `oCDtPlayerProfileData_vftable`, `oCDtCurrentRunProfileData_vftable`, `oCBinaryLoader_vftable`, `g_ActivityScore_typedesc`, `g_oCDtPlayerProfileData_typedesc`, `g_oCDtCurrentRunProfileData_typedesc`.

---

## Open work (deferred, not blocking path B's stat-reset use case)

1. **Locate the cumulative "Level reached" stat.** Almost certainly in `oCDtHeroProfileData` (12 top-level instances, one per hero). Approach: dump Geppetto's HeroProfileData body, edit candidate u32/float positions, observe in-game.
2. **Per-class schemas for cross-save transplant.** Would unlock GUID/index remapping for arbitrary record migration between saves. Each class with `vtable[0xa8]` references needs its Serialize reversed in detail. Substantial effort, only worth it if scenario-crafting requires "import this run state into a clean save."
3. **Decode `oCEntityCpntCounterPersistentData` semantics** (the 3 top-level counter records). Likely tracks specific things like raven-feathers-consumed but values weren't obviously matchable.
4. **Map remaining `oCDtPlayerProfileData` field meanings** (4 of 5 fields still unidentified — only `field_at_10` = selected hero is named).

---

## Cross-references

- `rw/key-findings/save-subsystem.md` — canonical save-subsystem architecture; this doc is supplementary.
- `rw/key-findings/save-flow-diagrams.md` — mermaid diagrams of save chain.
- `rw/key-findings/decoder-work-2026-04-30.md` — the three-step plan that produced `cooked.py`.
- `tools/rerw-src/lib/cooked.py` — the decoder library.
- `tools/rerw-src/lib/cooked_schemas.py` — per-class schema definitions (currently `oCDtPlayerProfileData` only).
- `tools/rerw-src/data/save-fields.yaml` — rerw's existing GUID-locator field map (for `--chapter`, `--level`, talent edits).
- `CLAUDE.md` — operational gotchas (modal false negative, Steam Cloud, save-swap warnings).
