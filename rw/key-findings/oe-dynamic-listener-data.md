# OEngine: `oe::DynamicCpntValueListenerData<T>`

OEngine (Passtech Games' game engine; namespace `oe::`) wraps observable game
state values in a templated class `oe::DynamicCpntValueListenerData<T>`. Each
instance holds a current value of type `T` plus listener-callback infrastructure.
Multiple instances of the same specialization may exist concurrently — one
source-of-truth plus listener mirrors held by each consumer (UI, save
serializer, network replication, etc.).

Inheritance: `oe::DynamicCpntValueListenerData<T>` <- `oe::IDynamicValueListenerData<T>`.

## Object layout (all `<T>` specializations)

    +0    vtable*       (specialization-specific)
    +8    T value       (the observed value)
    +16+  heap ptrs     (listener / binding internals)

The value field at `+8` is the practical anchor for memory analysis — read or
write it to interact with the observed state.

## Specializations found in `Ravenswatch.exe` (build of 2026-02-18)

All located via mangled-name search in `.data` and COL-walk in `.rdata`. Vtable
RVAs are stable across launches; runtime addresses shift per ASLR.

| `T` | Decoded | Vtable RVA |
|-----|---------|-----------|
| `H` | `int` | **`0xef4ad0`** |
| `M` | `float` | `0xef4cb0` |
| `_N` | `bool` | `0xefb1c0` |
| `VoCVec3` | `oCVec3` (3D vector) | `0xef9890` |
| `VoCVec2` | `oCVec2` (2D vector) | `0xefd270` |
| `V?$oCTStr@D` | `oCTStr<char>` (engine string) | `0xefb0e8` |
| `VoCColor` | `oCColor` | `0xefeb60` |
| `VoCTypedPtr` | `oCTypedPtr` | `0xefec98` |
| `AEBV?$oCTResourcePtr@VoCMaterial` | `const oCTResourcePtr<oCMaterial>&` | `0xefd260` |
| `AEBV?$oCTResourcePtr@VoCTexture` | `const oCTResourcePtr<oCTexture>&` | `0xeff1c8` |

### `<int>` specialization — observed bindings (Geppetto, session 1)

Population census across L1..L5 in-process snaps (14,121 instances stable
across all 5 snaps in the heap):

| Pattern | Count | Notes |
|---------|------:|-------|
| Strictly +1 per level (Level mirrors) | 5 | observe `Level` |
| Strictly increasing, other rates | 5 | XP threshold (1) + counter pairs |
| Constant across all 5 snaps | 11,186 | caps / config / base stats |
| Nonzero, non-monotonic changes | 2,925 | dynamic combat / inventory state |

Confirmed bindings (HUD-progression match against L1..L5 values):

| Stat | Listener address(es) | Notes |
|------|---------------------|-------|
| Level | `0x27cdcfe8660` + 4 mirrors | progression (1,2,3,4,5) |
| XP threshold (next level) | `0x27cdcfef370` | progression (400, 1100, 1800, 2500, 5000) |
| XP current | `0x27cdcfefaf0` | adjacent to threshold |
| Dream shards | `0x27cdcfdcd60` + 5 mirrors | tight cluster |

Counters observed but not yet identified: paired mirrors with progression
`(0,3,10,14,20)` and `(0,1,5,7,8)` — possibly skill / talent counters.

### `<float>` specialization — observed bindings

`<float>` listener total: ~140K stable instances (10× more than `<int>` —
floats dominate game-state storage because most stats participate in
arithmetic). 37,129 are all-zero (matches stats genuinely zero this run, e.g.,
vitality, armor).

Confirmed bindings:

| Stat | Listener address(es) | Notes |
|------|---------------------|-------|
| Health current | `0x27cdcfe8840` | unique match; progression (80,108,97,106,117) |
| Health max | `0x27cdcfe8890` (+27 in others) | 50 bytes after health_current; same struct |
| Crit chance | `0x27cdcfd91b0` + 4 mirrors | percent (5.0/9.0), NOT fraction (0.05/0.09) |

The "player main stat block" lives in heap range `~0x27cdcfd0000–0x27cdcffffff`
(~2 MB region). Listener addresses inside this range are likely the
source-of-truth instances; addresses outside are mirror copies in UI / save
serializer / replication.

Stats not findable as a listener instance:
- **Damage** — not stored as a stable int32 or float32 anywhere in heap with
  the expected progression (0,0,11,17,26). Confirmed via raw heap scan.
  Almost certainly computed at display time as `base + Σ(item_modifiers)`.
- **Stars of fate** — found as a **plain int32** in the player struct at
  `0x27cdcfe87f8`, NOT wrapped in a listener. The player struct mixes
  listener-wrapped fields (Level, HP, XP, etc.) with plain integer fields
  (stars of fate, possibly other counters). Caps and currencies without
  observable-binding requirements are stored as raw struct fields.

## Locating an instance at runtime

ASLR changes runtime addresses every launch — the RVAs above are stable, the
absolute addresses are not. To find a stat's current address in a fresh
session:

1. Get the EXE module's runtime base (e.g., via `mem_snapshot.py modules`).
2. Compute `vtable_runtime = module_base + vtable_RVA` for the desired `T`.
3. Scan heap regions of the snap for 8-byte LE values equal to
   `vtable_runtime`. Each match is the start of an instance.
4. Read the value at instance + 8 (size depends on `T` — int is 4 bytes, vec3
   is 12 bytes, etc.).
5. To pin which instance binds to which stat: either filter by
   value-progression across multiple snaps (level-up, take damage, etc.) or
   use struct-relative offsets from another known anchor.

Full per-session workflow & rationale (what survives a restart, what
doesn't): `rw/docs/oe-listener-mining.md`.

## Method to recover this map

- MSVC RTTI is intact in the binary (not stripped).
- Type descriptor names (mangled, with prefix `.?AV?$DynamicCpntValueListenerData@`)
  live in `.data`. Each `TypeDescriptor` struct is `[vtable* (8)] [spare (8)]
  [name (null-term)]`, so the name string starts 16 bytes into the struct.
- For each type descriptor, search `.rdata` for a Complete Object Locator
  (COL) whose `pTypeDescriptor` field (offset 12, 4-byte RVA) matches —
  validate by checking signature == 1 and self-pointing `pSelf` field.
- Each COL's address (as image-base + RVA, 8 bytes LE) appears as the value
  immediately before its associated vtable. So search `.rdata` for that
  8-byte value to find the vtable's location.

## Sources

- rw/triage/level-runtime-address.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_analysis.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_struct_probe.txt
