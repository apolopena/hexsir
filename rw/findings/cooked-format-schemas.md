[← Back to findings](README.md)

# Cooked-format per-class schemas — herodef + entity-settings

**Status:** confirmed
**Created:** 2026-05-07

Per-class schema decoders for the engine's `Cooked` binary serialization
format. Extends the existing framing-only decoder (`tools/rerw-src/lib/cooked.py`,
documented in `save-edit-pipeline.md` and `decoder-work-2026-04-30.md`) with
field-level body decoding for five classes: `oCDtHeroDefinition`,
`oCDtDefinition` (parent), `oCEntitySettings`, `oIEntityCpntSettings` (parent
of every entity-component-settings class), and
`oCEntityCpntEntitySpawnerSettings`. Also ships a plain-text `.ot` manifest
decoder for the pipe-delimited `UsedRscCache.ot` files, the full
`oCBinaryLoader` vtable map, and nine reusable helper readers that any
future class schema can compose from.

## Sources

- `tools/rerw-src/lib/cooked.py` — pre-existing framing decoder (Cooked
  format, `0xAABB1111`/`0xAABB2222` markers, header variants, round-trip
  encoder).
- `tools/rerw-src/lib/cooked_schemas.py` — extended this session: added
  `SCHEMA_oCDtHeroDefinition`, `SCHEMA_oCEntitySettings`,
  `SCHEMA_oIEntityCpntSettings`, `SCHEMA_oCEntityCpntEntitySpawnerSettings`,
  9 helper readers, registered all 4 + the existing
  `oCDtPlayerProfileData` in `SCHEMAS_BY_NAME`.
- `tools/rerw-src/lib/ot_text.py` — new this session: pipe-delimited `.ot`
  text-manifest decoder.
- `rw/findings/save-edit-pipeline.md` — parent doc; established the framing
  format and the `cooked.py` library this finding extends.
- `rw/findings/entity-spawner-mechanism.md` — parallel-session work; this
  finding closes its open question #3 (`oCEntityCpntEntitySpawnerSettings`
  field decode for tether mode + spawn-template ref).
- Ghidra DB renames + plate comments persisted this session:
  - **Class methods:**
    - `FUN_140192e10` → `oCDtHeroDefinition_typedesc_init`
    - `FUN_1403143b0` → `oCDtHeroDefinition_ctor` (struct size `0x8d0`)
    - `FUN_1403150c0` → `oCDtHeroDefinition_Serialize`
    - `FUN_1403076b0` → `oCDtDefinition_Serialize`
    - `FUN_1406c7760` → `oCEntitySettings_Serialize`
    - `FUN_1407116c0` → `oCEntityCpntEntitySpawnerSettings_Serialize`
    - `FUN_1406f4b90` → `oIEntityCpntSettings_Serialize`
  - **Helpers (engine-side serialization helpers):**
    - `FUN_1401c5e30` → `serde_two_string`
    - `FUN_140670af0` → `serde_composite_resource_link`
    - `FUN_140209ce0` → `serde_vec_obj_ref`
    - `FUN_14030d450` → `serde_vec_two_string`
    - `FUN_1403343d0` → `serde_u8_array_fixed5`
    - `FUN_140333ca0` → `serde_two_string_array_fixed5`
    - `FUN_1403340e0` → `serde_subobj_array_fixed7`
    - `FUN_1402f14d0` → `serde_vec_picker`
  - **`oCBinaryLoader` vtable methods:**
    - `FUN_1404e8240` → `oCBinaryLoader_read_u32`
    - `FUN_1404e8260` → `oCBinaryLoader_read_8bytes`
    - `FUN_1404e8280` → `oCBinaryLoader_read_u8`
    - `FUN_1404e82a0` → `oCBinaryLoader_read_string`
    - `FUN_1404e7ff0` → `oCBinaryLoader_read_named_subobject`
    - `FUN_1400c5bb0` → `oCBinaryLoader_is_writing` (returns 0 — read-mode loader)
    - `FUN_1404e46c0` → `oCBinaryLoader_get_class_schema_version`
  - **Data labels:**
    - `0x140f04110` → `oCDtHeroDefinition_vftable`
    - `0x140f23120` → `oCBinaryLoader_vftable`

## TL;DR

- **Per-class schema framework working end-to-end.** Decoder + encoder
  round-trip byte-equal on every test file. Validated against:
  - 13 hero `.gen` files (every harvested herodef in
    `rw/harvested/Definitions/Heroes/`) — round-trip OK ×13, schema decode
    clean (no errors, no unparsed bytes) ×13.
  - Geppetto's entity-settings (`Hero_Geppetto.entity.ot.gen`, 620 KB) —
    round-trip OK; 4× spawner-settings + 1× oCEntitySettings instances all
    schema-decode clean.
  - Geppetto's Puppet entity-settings (`Hero_Geppetto_Puppet.entity.ot.gen`,
    3 KB) — round-trip OK; 1× oCEntitySettings clean.
- **Tether-mode mystery resolved (parallel-session hand-off).** The
  parallel agent's open question on `oCEntityCpntEntitySpawnerSettings`
  field semantics — *which field encodes the tether-vs-independent
  setting?* — answered: struct field at C++ offset `+0x1bc` is a u32
  enum, and the engine validates `value <= 2` on read (i.e., 3 valid
  values: 0/1/2). Both spawner instances on Geppetto carry value `0`. The
  `<= 2` bound matches a "untethered / tethered / chapter-scoped"
  three-way enum cleanly.
- **Spawn-target template field located.** `+0x138` named-subobject body
  on each spawner-settings instance decodes to a `(resource_type, path)`
  two-string pair. On Geppetto's spawners: type=`EntitySettings`, path
  begins `Heroes\Hero_Geppetto\...` (the spawned entity's settings file).
  This is the engine-blessed equivalent of the runtime spawner's
  `+0x18` settings binding — readable statically from disk.
- **`oCBinaryLoader` vtable slot map decoded.** Every Cooked class's
  `Serialize()` virtual reads bytes via this vtable. With the slot
  meanings known, future Serialize decompiles parse trivially.
- **Plain-text `.ot` manifests decodable.** `UsedRscCache.ot` files are
  pipe-delimited ASCII; `lib/ot_text.py` pretty-prints them.

## Findings

### Confirmed

#### Plain-text `.ot` manifests are pipe-delimited ASCII

Files like `Geppetto.herodef.UsedRscCache.ot` use the format:

```
<resource_type>|<relative_path>|<class_name>
```

One record per non-empty line. UTF-8, no encryption, no compression. Used
by the cooking pipeline to track resources a definition references. The
`lib/ot_text.py` decoder parses these into a list of records and supports
summary view, full listing, and class-name filter.

#### `oCBinaryLoader` vtable @ `0x140f23120` — slot map

The serializer object passed as `param_2` to every `Serialize()` is an
`oCBinaryLoader`. Its vtable methods, called by C++ byte-offset:

| Vtable byte-offset | Slot index | Function | Reads |
|---|---|---|---|
| `+0x00` | 0 | `0x1404e7b50` | scalar deleting destructor |
| `+0x20` | 4 | `oCBinaryLoader_is_writing` (`0x1400c5bb0`) | returns `0` (read mode) |
| `+0x60` | 12 | `oCBinaryLoader_read_string` (`0x1404e82a0`) | u32 length + N bytes (no null on wire) |
| `+0x70` | 14 | `oCBinaryLoader_read_u8` (`0x1404e8280`) | 1 byte |
| `+0x90` / `+0x98` | 18 / 19 | `oCBinaryLoader_read_u32` (`0x1404e8240`) | 4 bytes |
| `+0xa0` | 20 | `oCBinaryLoader_read_named_subobject` (`0x1404e7ff0`) | `0xAABB1111` + u32 class-info-index + recursive body + `0xAABB2222` |
| `+0xa8` | 21 | `oCBinaryLoader_ReadObjectRef` (`0x1404e7f50`) | u32 obj-ref index (per `save-edit-pipeline.md`) |

The "is_writing" return-zero on slot `+0x20` is the consistent pattern
that makes Serialize methods decompile as `if (writing OR
file_version > N) { read_field(); }` — at runtime in this loader, only
the version check matters (writing always evaluates false).

#### Helper-function inventory

Every class's `Serialize()` composes from these helpers (stream byte-cost
listed):

| Helper | Renamed | Stream cost | What it reads |
|---|---|---|---|
| `serde_two_string` (`0x1401c5e30`) | yes | `8 + len1 + len2` | Two length-prefixed UTF-8 strings + in-memory flag (not on wire). |
| `serde_composite_resource_link` (`0x140670af0`) | yes | `4 + 8+len1+len2 + 4 + (4+len if ver≠0)` | u32 ver + two_string + u32 type + (conditional length-prefixed string). |
| `serde_vec_obj_ref` (`0x140209ce0`) | yes | `4 + 4·N` (+ optional preamble) | Vec of u32 ReadObjectRef indices. May emit a `0xAABB1111`-prefixed class-info preamble (string class_name + 2× u32, optionally a second class_name + 2× u32, then count, then trailing u32). |
| `serde_vec_two_string` (`0x14030d450`) | yes | as above with `two_string` elements | |
| `serde_u8_array_fixed5` (`0x1403343d0`) | yes | `4 + count` | u32 count + min(count, 5) bytes; if count>5, count−5 extra discard bytes. |
| `serde_two_string_array_fixed5` (`0x140333ca0`) | yes | `4 + ∑two_string` | Same, with two_string elements. |
| `serde_subobj_array_fixed7` (`0x1403340e0`) | yes | `4 + ∑named_subobject` | u32 count + min(count, 7) named sub-objects. |
| `serde_vec_picker` (`0x1402f14d0`) | yes | `4 + ∑named_subobject` (+ optional preamble) | Vec of named sub-objects (`oCEntityCpntPicker` instances). Same preamble pattern. |
| `serde_u8_array_fixed16` (`0x1405cfe40`) | (not renamed; only used in `oCEntitySettings::Serialize`) | `4 + count` | u32 count + min(count,16) bytes; extra discarded into a different slot. |

The `0xAABB1111` class-info preamble pattern is shared across every vector
helper: an inline class-metadata header read before the count when present,
absent on writes that omit it. The decoder probes the first u32 — if it
equals `0xAABB1111`, parses the preamble; otherwise treats that u32 as the
count itself.

#### `oCDtHeroDefinition` schema (vtable `0x140f04110`, schema_v=26, struct size `0x8d0`)

Decompiled from `oCDtHeroDefinition_Serialize`. Inheritance chain (from any
herodef's class registry):

```
oISerializable      (uid 0x001da16c, schema_v=0, no fields)
  oIResource        (uid 0x000017b6, schema_v=1, no fields visible in stream)
    oCDtDefinition  (uid 0x1768ce8e, schema_v=1, 2 bytes via parent dispatch)
      oCDtHeroDefinition  (uid 0x1768d0c9, schema_v=26)
```

`oCDtHeroDefinition_Serialize` first dispatches to `oCDtDefinition_Serialize`
(2 u8 reads at `+0x285`/`+0x284`), then walks 30+ version-gated fields. The
schema (in stream order, current build's schema_v=26 path):

| Stream pos | Field | Type | Min ver |
|---|---|---|---|
| — | parent oCDtDefinition |  | |
| 1 | u8 at +0x285 | u8 | 0 |
| 2 | u8 at +0x284 | u8 | 0 |
| — | own |  | |
| 3 | u32 at +0x2b0 | u32 | 0 |
| 4 | twoStr at +0x2b8 | two_string | 0 |
| 5 | composite at +0x328 | composite | 0 |
| 6–9 | twoStr at +0x5d8/+0x610/+0x648/+0x680 | two_string ×4 | 1 |
| 10 | vec_obj_ref at +0x8a0 | vec_obj_ref | 3 |
| 11 | vec_two_string at +0x7d0 | vec_two_string | 4 |
| 12 | twoStr at +0x2f0 | two_string | 6 |
| 13 | u8_array_fixed5 at +0x7e0 | u8_array_fixed5 | 8 |
| 14 | vec_obj_ref at +0x8b0 | vec_obj_ref | 10 |
| 15 | two_string_array_fixed5 at +0x6b8 | two_string_array_fixed5 | 11 |
| 16 | guid16 at +0x290 | guid16 | 12 |
| 17 | u8 at +0x2a0 | u8 | 12 |
| 18 | u32 at +0x2a4 | u32 | 12 |
| 19 | vec_obj_ref at +0x8c0 | vec_obj_ref | 13 |
| 20 | composite at +0x398 | composite | 14 |
| 21 | named_subobject at +0x828 | named_subobject | 15 |
| 22 | composite at +0x408 | composite | 16 |
| 23 | string at +0x4e8 | string | 17 |
| 24 | u8 at +0x4f8 | u8 | 18 |
| 25 | twoStr at +0x7e8 | two_string | 19 |
| 26 | u8 at +0x821 | u8 | 21 |
| 27 | u8 at +0x820 | u8 | 23 |
| 28 | composite at +0x478 | composite | 23 |
| 29 | u8 at +0x822 | u8 | 24 |
| 30 | u8 at +0x823 | u8 | 25 |
| 31 | named_subobject at +0x500 | named_subobject | 26 |

(Legacy migration paths for older schema_v values — v in [2, 5..0xb], etc.
— exist in the decompile but are not modeled in the schema; the
current-build path covers every observed file.)

Validated against every harvested hero (Beowulf, Juliet, Sun_Wukong,
Snow_Queen, Melusine, Merlin, Geppetto, Red, Romeo, Carmilla, Piper,
Aladdin) — all 13 round-trip OK and decode clean.

Notable extracted content from Geppetto's herodef:

- **Hero name lookup**: `Text|Hero_Geppetto_Common~GAM.xls|Hero_Name`
  (composite at +0x328) — points at the localization spreadsheet.
- **Unlock prerequisites**: 4 herodef refs at +0x7d0
  (`Red.herodef.ot, Piper.herodef.ot, Aladdin.herodef.ot,
  Carmilla.herodef.ot`) — Geppetto unlocks after these 4 are played.
- **Talent set**: 28 obj-refs at +0x8a0 → 28 nested
  `SkillProfileDataSettings` instances in the same file.
- **Memoirs**: 7 obj-refs at +0x8b0 → 7 `StoryProfileDataSettings`.
- **Codex**: 5 illustration paths at +0x6b8.
- **Hero identity GUID**: `20fc95f8c0bc284cb897a304d43756b3` at +0x290.

Free heroes (no unlock prereqs, vec at +0x7d0 empty): Juliet, Merlin,
Romeo. Deepest unlock chain: Aladdin (6 prereqs).

#### `oCEntitySettings` schema (vtable `0x140f4cee8`, schema_v=8)

Decompiled from `oCEntitySettings_Serialize`. Parent
`oCSpawnableSettings` (schema_v=0) contributes no on-wire fields; no
explicit parent dispatch in the Serialize.

| Field | Type | Min ver |
|---|---|---|
| vec_obj_ref at +0x118 | vec_obj_ref | 0 |
| u8 at +0x78 | u8 | 1 |
| u8_array_fixed16 at +0x1b8 | u8_array_fixed16 | 4 |
| vec_two_string at +0xe8 | vec_two_string | 5 |
| u32_obj_ref at +0x1c8 | u32 | 7 |
| vec_obj_ref at +0xf8 | vec_obj_ref | 8 |

Validated: Geppetto entity-settings (689 component refs, 16-byte content
hash, FX bundle path = `Heroes\Hero_Geppetto\Hero_Geppetto_FX.entity.ot`).
Puppet entity-settings (6 component refs, FX = `Hero_Geppetto.entity.ot`
— inherits FX from parent entity).

#### `oIEntityCpntSettings` schema (schema_v=20)

Decompiled from `oIEntityCpntSettings_Serialize`. Abstract base for every
entity-component-settings class; instances appear inline at the start of
each derived class's body (no separate framed instances).

| Field | Type | Min ver |
|---|---|---|
| named_subobject at +0xa8 | named_subobject | 12 |
| guid16 at +0x98 | guid16 | 11 |
| string at +0xe8 | string | 11 |
| u8 at +0x33 | u8 | 0 |
| u8 at +0x34 | u8 | 0 |
| u8 at +0x35 | u8 | 5 |
| u8 at +0x36 | u8 | 2 |
| string at +0x38 | string | 1 |
| u8 at +0x81 | u8 | 7 |
| u8 (discarded into local) | u8 | 8 |
| u32 (max=3) at +0x84 | u32 | 10 |
| u8 at +0x32 | u8 | 19 |

The "u8 discarded into local" at v≥8 is a legacy migration shim —
consumed from the stream but unused at v≥0x14 (its post-processing block
is gated to v<0x14). Modeled in the schema as a labelled-discard entry
because the byte position must still advance.

This schema is currently embedded as a pre-resolved v=20 prefix into
`oCEntityCpntEntitySpawnerSettings`'s schema — no standalone framed
instances expected.

#### `oCEntityCpntEntitySpawnerSettings` schema (vtable `0x140f515a0`, schema_v=21)

Decompiled from `oCEntityCpntEntitySpawnerSettings_Serialize`. Parent is
`oIEntityCpntSettings` (above), invoked first via parent dispatch.

Spawner-specific fields (current schema_v=21 path), in stream order after
the parent's:

| Field | Type | Min ver | Notes |
|---|---|---|---|
| named_subobject at +0x138 | named_subobject | 16 | **spawn-target template ref** (see TL;DR) |
| named_subobject at +0x7b0 | named_subobject | 5 | (large body — likely transform/bound-context) |
| u32 at +0x1bc | u32 | 9 | **TETHER MODE** — engine validates `≤ 2` |
| named_subobject at +0x1c0 | named_subobject | 9 | paired with tether-mode (likely owner override) |
| named_subobject at +0x200 | named_subobject | 19 | |
| named_subobject at +0x10e0 | named_subobject | 8 | |
| named_subobject at +0x1060 | named_subobject | 8 | |
| named_subobject at +0x1990 | named_subobject | 17 | |
| named_subobject at +0x19d0 | named_subobject | 17 | |
| named_subobject at +0xf8 | named_subobject | 13 | |
| vec_picker at +0x1a78 | vec_picker | 14 | filter conditions |
| u8 at +0x19f0 | u8 | 18 | |
| named_subobject at +0x19f8 | named_subobject | 18 | |
| u8 at +0x1b8 | u8 | 21 | (most recent addition) |

Validated: 4× spawner instances in Geppetto's entity-settings, all
schema-decode clean, file round-trips byte-equal.

##### Empirical observations on Geppetto's spawners

Both observed spawner instances:

```
u32_tether_mode_at_1bc = 0
named_subobject_at_138 body = 75 bytes, decoded as:
    u32(14) + "EntitySettings" + u32(53) + 53-byte path
named_subobject_at_1c0 body = 20 bytes, all-zero (null settings ref)
```

The `+0x138` body's content is exactly a `(resource_type, path)`
two_string pair — wrapped inside a named_subobject envelope (presumably
an `oCEntityCpntPicker` or similar settings-ref container, per the
vec_picker pattern elsewhere). This is the static-readable equivalent of
the runtime spawner component's `+0x18` settings binding documented in
`entity-spawner-mechanism.md`.

The `+0x1c0` paired slot was all-zero on every instance examined,
consistent with the runtime "+0x1c0 owner backref" being a runtime-only
field that's lazily populated by the spawner's `onAttachToParent` hook
rather than baked into the settings.

### Hypothesis (mapped, not fully verified)

- **Tether-mode enum semantics**: 0/1/2 likely correspond to the three
  pool flavors documented in `entity-spawner-mechanism.md` §"Pool-ownership
  taxonomy" — untethered (chapter-scope) / tethered (parent-pool) /
  prefab-scope. Geppetto's spawners showing `0` matches the expected
  player-context mode. To verify, harvest a Cultist Summoner's entity-
  settings and check whether its tentacle spawner has tether=1 or 2.
- **Per-component schemas for the remaining 99% of `.gen` files** can be
  authored using the same loop demonstrated here: find class via RTTI,
  follow vtable[3] = Serialize, decompile, drop a schema entry in
  `cooked_schemas.py` composing from the existing 9 helpers + primitives.
  Each class is roughly 30–60 minutes of dig.

### Tried and ruled out

- **Encryption / cipher hypothesis on `.ot` files**: ruled out by hex
  inspection — `UsedRscCache.ot` files are plain ASCII pipe-delimited
  text. The "cipher" in the project (`rerw cipher`/`decipher`) is a
  filename-letter-substitution, not a content cipher. Body content for
  cooked outputs is plain `Cooked` binary serialization (per
  `decoder-work-2026-04-30.md`, archived).
- **Inheriting parent schema dynamically**: considered making the parser
  walk class parent chains in the registry. Settled on inlining the
  parent's resolved fields into the derived schema (e.g., the v=20
  oIEntityCpntSettings prefix is hardcoded into the spawner schema).
  Simpler and ties the schema validation to the file's actual ver.
  Trade-off: a file with oIEntityCpntSettings v≠20 would break. None
  observed; revisit if a future build bumps the parent version.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating &lt;thing&gt;" — RE-side template.

### Anchors

| Symbol | Anchor strategy |
|---|---|
| `oCDtHeroDefinition` class | RTTI string `.?AVoCDtHeroDefinition@@` at `0x141352148` → TypeDescriptor → COL → vtable. |
| `oCDtHeroDefinition` class hash `0x1768d0c9` | Search bytes `c9 d0 68 17`. The typedesc-init function references it as a literal. |
| `oCDtHeroDefinition_typedesc_init` | xrefs to the plain string `"oCDtHeroDefinition"` at `0x140eddd78` (DATA xrefs from `0x140192f21` + `0x140192f28`). |
| `oCDtHeroDefinition_ctor` (RVA `0x3143b0`) | The thunk at `LAB_1401ab900` (stored at typedesc+0x80 in the registrar) tail-jumps to the ctor. |
| `oCDtHeroDefinition_vftable` (`0x140f04110`) | LEA in the ctor: `LEA RAX, [0x140f04110]; MOV [RDI], RAX` — the LAST vtable install in the ctor, after parent classes' vtables. |
| `oCDtHeroDefinition_Serialize` | vtable[3] of `0x140f04110`. |
| `oCEntitySettings` class | Already known from `entity-spawner-mechanism.md` (vtable `0x140f4cee8`, ctor RVA `0x6c7090`). |
| `oCEntitySettings_Serialize` | vtable[3] of `0x140f4cee8`. |
| `oCEntityCpntEntitySpawnerSettings` | Vtable `0x140f515a0` per `entity-spawner-mechanism.md`. |
| `oCEntityCpntEntitySpawnerSettings_Serialize` | vtable[3] of `0x140f515a0`. |
| `oIEntityCpntSettings_Serialize` | First call inside `oCEntityCpntEntitySpawnerSettings_Serialize` (parent dispatch). Class hash `0xc608329` referenced as a constant in its version-gating calls. |
| `oCBinaryLoader_vftable` (`0x140f23120`) | xref TO `oCBinaryLoader_ReadObjectRef` (`0x1404e7f50`) → DATA reference at `0x140f231c8` (vtable + 0xa8). Vtable starts 0xa8 bytes earlier. |
| Helper functions | xrefs FROM each Serialize. The 9 helpers identified are the most-called subroutines from the 5 Serializes documented above. |

### Re-anchoring quick recipe

1. RTTI string `.?AVoCDtHeroDefinition@@` → vtable RVA → ctor RVA.
2. From ctor: extract primary vtable address (last `LEA` install).
3. vtable[3] = Serialize. Decompile.
4. Classify each call inside Serialize using the 9 helper signatures
   below — this gives you the field types in stream order.
5. The `oCBinaryLoader` vtable byte-offsets (+0x60 string, +0x70 u8,
   +0x90/+0x98 u32, +0xa0 named_subobject, +0xa8 obj_ref) decode every
   primitive vtable call.

## Tool reference: `lib.cooked` schema decode + `lib.ot_text`

### Pre-existing capabilities (from `save-edit-pipeline.md`)

```python
from lib.cooked import (
    parse_file,           # bytes -> CookedFile
    parse_object_tree,    # CookedFile -> list[TreeNode] (recursive)
    parse_object_section, # CookedFile -> list[ObjectBlock] (flat)
    find_class_in_tree,   # locate all instances of a class
    encode_file,          # CookedFile -> bytes (auto CRC for .ob)
)
```

### New: schema-driven body decode

Schemas auto-apply during `--annotate`. The CLI iterates every framed
object (top-level and nested) and looks up the class name in
`SCHEMAS_BY_NAME`. If a schema is registered, the body is parsed
field-by-field and printed with `name = value` lines; otherwise the
existing heuristic annotator runs.

Currently registered:

```python
SCHEMAS_BY_NAME = {
    "oCDtPlayerProfileData": ...,
    "oCDtHeroDefinition": ...,
    "oCEntitySettings": ...,
    "oIEntityCpntSettings": ...,
    "oCEntityCpntEntitySpawnerSettings": ...,
}
```

### New: text `.ot` manifest decoder

`lib/ot_text.py` parses pipe-delimited `<resource_type>|<path>|<class>`
records from files like `Geppetto.herodef.UsedRscCache.ot`. Standalone
module — no dependency on `cooked.py`.

## Example invocations

All examples assume:

```bash
cd /home/ks73/repos/work/ravensmith/tools/rerw-src
HARV=/home/ks73/repos/work/ravensmith/rw/harvested
HERO_GEPPETTO="$HARV/Definitions/Heroes/Kqjjqiir.nqurtqh.ri.NiAqurNqhdzdidrz.yqz"
HERO_GEPPETTO_USED="$HARV/Definitions/Heroes/Kqjjqiir.nqurtqh.JvqtLvbSgbnq.ri"
ES_GEPPETTO='/home/ks73/repos/work/ravensmith/rw/harvested/EntitySettings/Heroes/Aqur_Kqjjqiir!Aqur_Kqjjqiir.qzidis.ri.MzidisFqiidzyvLqvrwubq.yqz'
ES_PUPPET='/home/ks73/repos/work/ravensmith/rw/harvested/EntitySettings/Heroes/Aqur_Kqjjqiir!Aqur_Kqjjqiir_Twjjqi.qzidis.ri.MzidisFqiidzyvLqvrwubq.yqz'
```

Note: harvested-tree paths contain `!` (the cipher pipeline's
group separator). Single-quote the assignment so `!` stays literal,
otherwise zsh/bash will try to expand it as history substitution.

### Read a plain-text `.ot` manifest

```bash
# Summary view (counts by class + by resource type)
.venv/bin/python -m lib.ot_text "$HERO_GEPPETTO_USED"

# Full listing
.venv/bin/python -m lib.ot_text "$HERO_GEPPETTO_USED" --full

# Filter to one class (substring match)
.venv/bin/python -m lib.ot_text "$HERO_GEPPETTO_USED" --full --filter-class oCTexture
```

### Verify round-trip on a `.gen` file

```bash
.venv/bin/python -m lib.cooked "$HERO_GEPPETTO" --check-roundtrip 2>&1 | tail -3
.venv/bin/python -m lib.cooked "$ES_GEPPETTO" --check-roundtrip 2>&1 | tail -3
.venv/bin/python -m lib.cooked "$ES_PUPPET"   --check-roundtrip 2>&1 | tail -3
```

Pass: `round-trip: OK (byte-for-byte match)`.

### Decode all framed objects with schemas applied

```bash
# Hero definition (1 oCDtHeroDefinition top-level, schema_v=26)
.venv/bin/python -m lib.cooked "$HERO_GEPPETTO" --annotate 2>&1 | grep -A 60 'schema decode'

# Geppetto entity-settings (4 spawner-settings + 1 oCEntitySettings)
.venv/bin/python -m lib.cooked "$ES_GEPPETTO" --annotate 2>&1 | grep -B 1 -A 25 'schema decode' | head -120
```

### Filter to spawner-settings instances only

```bash
.venv/bin/python -m lib.cooked "$ES_GEPPETTO" --annotate 2>&1 \
    | grep -B 1 -A 23 'oCEntityCpntEntitySpawnerSettings' | head -60
```

### Sanity-check a schema against multiple files

```bash
for f in $HARV/Definitions/Heroes/*.yqz; do
    decoded=$(/home/ks73/repos/work/ravensmith/tools/rerw decipher --path-aware "$(basename "$f")" 2>&1 \
        | tr -d '\033' | sed 's/\[[0-9;]*m//g' | grep -oE '[A-Za-z_]+\.herodef')
    result=$(.venv/bin/python -m lib.cooked "$f" --annotate 2>&1)
    if echo "$result" | grep -q 'schema decode failed'; then
        echo "$decoded: FAIL"
    elif echo "$result" | grep -q 'unparsed bytes follow'; then
        echo "$decoded: PARTIAL"
    else
        echo "$decoded: CLEAN"
    fi
done
```

Pass: every line ends `CLEAN`.

## Open questions / next steps

1. **Validate tether-mode enum on a known-tethered case.** Harvest a
   Cultist Summoner's entity-settings file and read its tentacle
   spawner's `+0x1bc` value. Hypothesis: 1 or 2 (vs 0 for Geppetto's
   untethered ability spawners). One-step test, would either confirm or
   refute the enum semantics hypothesis.
2. **Add schemas for the high-value entity-component classes.** Every
   `.gen` file's class registry exposes which classes' bodies you can
   currently READ but cannot DECODE. Highest-value candidates (per
   `entity-spawner-mechanism.md` and the registry of Geppetto's
   entity-settings):
   - `oCDtEntityCpntAbilityControllerSettings` (schema_v=32) — ability
     definitions.
   - `oCDtEntityCpntDamageSettings` (schema_v=21) — damage values.
   - `oCEntityCpntBasicMoveSettings` (schema_v=1) — move speed; small.
   - `oCDtEntityCpntSkillControllerSettings` (schema_v=17) — talents.
3. **Decode `oCEntityCpntPicker`** (the named-subobject at +0x138 of the
   spawner-settings is wrapped in a Picker, not a raw two_string). Would
   make the spawn-target field directly readable as a structured value
   instead of a hex preview.
4. **Folder-walk a whole entity-settings registry catalogue.** With the
   current schemas, every spawner instance across the game's 4000+ entity-
   settings files is now discoverable via grep. Useful for "which
   entities have spawners" type analytics.

## Cross-references

- `rw/findings/save-edit-pipeline.md` — pre-existing decoder + encoder
  reference. This finding extends its tooling with per-class schemas.
- `rw/findings/decoder-work-2026-04-30.md` — archived parent dig that
  produced `cooked.py`.
- `rw/findings/entity-spawner-mechanism.md` — parallel-session work on
  the runtime spawner component. This finding's spawner-settings schema
  closes that doc's open question #3.
- `tools/rerw-src/lib/cooked.py` — the framing decoder.
- `tools/rerw-src/lib/cooked_schemas.py` — per-class schemas (extended
  this session).
- `tools/rerw-src/lib/ot_text.py` — plain-text manifest decoder (new
  this session).
- `rw/findings/STATUS.md` — manifest of all findings.
