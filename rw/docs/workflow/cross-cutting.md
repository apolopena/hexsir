[← Back to workflow](README.md)

# Cross-cutting layouts

Byte-level facts that span multiple finding-doc domains. Extracted here so that talent-record work and item-record work share a single description of the structure they both navigate, rather than each domain finding carrying its own copy that drifts out of sync.

## What this is for

The Ravenswatch save format has one large mixed-content record — the **run-state record** (tag=`0x12`) — that holds both the player's collected magical objects (item records, tag=`0x1a`) and the player's selected talents (the picks block). Multiple findings describe parts of this record. Without a shared reference, each finding ends up restating the same set-bonus tracker / picks block adjacency, the same close-marker bytes, the same field offsets — and when one of those facts changes, the other copies rot.

This chapter is the single description of the shared structure. Domain findings ([`talent-records.md`](../../findings/talent-records.md), [`magical-objects.md`](../../findings/magical-objects.md)) cite it instead of repeating it.

## Concepts

### Marker / close framing

Records inside the save body are framed by 4-byte sentinels:

- **`11 11 bb aa`** — record start marker.
- **`22 22 bb aa`** — record close marker.

Tags follow the start marker as a u32 LE. The framing self-terminates: a record has no outer length prefix; the parser walks fields and stops at the close marker.

### Tag values seen in this project

| Tag | Record type | Domain |
|---|---|---|
| `0x05` | Catalog record (114 immutable per-save) | `magical-objects.md` |
| `0x10` | First-occurrence rarity record (per skill controller) | `talent-records.md` |
| `0x12` | Run-state record (mixed: items + talents) | This chapter (overview), both `talent-records.md` and `magical-objects.md` (domain facts) |
| `0x1a` | Item-pickup record (nested inside run-state) | `magical-objects.md` |

## The run-state record (tag=0x12)

A single record that holds both the run's collected items and the player's talent picks. The body's high-level layout, with offsets into `body[]` (the bytes after the record's 16-byte header which is `[marker][tag][record GUID 15][separator]`):

```
body+0x00: header region
  - timing / state floats
  - slot.rarity array (10 × u32 LE) at body+0x35..+0x5c
    -> per-slot rarity (0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker / uninitialized)
    -> read by the picker when a slot's loaded talent is null

body+0x61: u32 LE — items count (number of tag=0x1a records that follow)
body+0x65: items records-array — count × 32 bytes of tag=0x1a records

body+0x65 + count*32: trailing block (variable-length)
  [u32 = N items currently at set-bonus threshold]
  [N × 16-byte runtime GUIDs of those items]    <-- "set-bonus tracker"
  [u32 = M talents picked]
  [M × 16-byte talent runtime GUIDs]            <-- "picks block"
  [8 zero bytes]
  [u32 — per-save scalar (float-shaped; possibly run-time/score)]
  [8 zero bytes]
  [22 22 bb aa]                                 <-- record close marker
```

### Item record (tag=0x1a) — 32 bytes

Each tag=0x1a record nested inside the run-state body:

```
[marker        4: 11 11 bb aa]
[tag           4: 1a 00 00 00]
[runtime GUID 16: <hex>]
[counter       4: u32 LE — sequence number]
[close marker  4: 22 22 bb aa]
```

The 16-byte runtime GUID matches the GUID extracted from the item's cooked entity-settings file. The counter is a u32 sequence number.

### Set-bonus tracker → picks block adjacency (the key invariant)

This is the single fact that ties talent-records work and item-records work together: the picks block's count u32 sits **immediately after** the set-bonus tracker. There is no separator, no padding, no length prefix between them.

Mechanically:

```
[u32 N items at set-bonus threshold][N × 16-byte GUIDs] [u32 M talents picked][M × 16-byte GUIDs]
                                                       ^
                                                       picks count u32 starts here
```

Two consequences:

1. **Picks-block locator strategies** (see [`talent-records.md`](../../findings/talent-records.md) §"Picks-block locator (generalized)") rely on walking the run-state forward through the items records-array and set-bonus tracker, then reading the picks count u32 at the very next byte.
2. **A coincidental sentinel `00 00 00 00 05 00 00 00`** in chapter-2 saves arose because chapter-2 `laser-lenses_1` has zero set-bonus items at threshold — the tracker collapsed to `[u32 = 0]` = 4 zero bytes, immediately followed by the picks count u32 = 5. Chapters with N > 0 set-bonus items have non-zero tracker GUIDs as the four bytes preceding the picks count, and the sentinel doesn't match. **The sentinel is a chapter-2 coincidence, not a structural anchor.** Do not search for it.

### Trailing close

After the picks block, the trailing region is fixed-shape:

```
[8 zero bytes]
[u32 — per-save scalar (float-shaped)]
[8 zero bytes]
[22 22 bb aa]    <-- record close marker
```

Total trailing = 24 bytes after the last picks GUID, plus the 4-byte close marker = 28 bytes.

### Observed sizes

Verified by byte-diff across saves:

| Save | items count | N (set-bonus) | M (talents) | Trailing block (variable region only) |
|---|---:|---:|---:|---|
| Save A — Geppetto chapter 2 `laser-lenses_1` | 21 | 0 | 5 | 112 bytes |
| Geppetto chapter 3 | (varies) | 1 (Moonstone) | 8 | 176 bytes |
| Geppetto epilogue | (varies) | 3 (Moonstone, Raven Skull, Adder Stone) | 10 | 240 bytes |

Trailing block size grows with N and M plus the fixed 28-byte close. Trailing block is variable; the run-state record itself self-terminates via the close marker.

## Per-controller rarity (tag=0x10)

Each skill controller (28 controllers for Geppetto) has a tag=0x10 record near the hero record. **25 bytes**:

```
[u32 = 0x10]              <-- type tag
[16 bytes: talent GUID]
[byte = 0x01]             <-- flag, constant; purpose unknown
[byte = TIER]             <-- the rarity byte the engine reads for HUD display
[3 bytes: 0x00 padding]
```

Rarity byte (offset GUID+17 within the record) values:

| Byte | Rarity |
|---|---|
| `0x00` | Common |
| `0x01` | Rare |
| `0x02` | Epic |
| `0x03` | Legendary |
| `0x04` | ult-marker / uninitialized |

The engine reads two distinct rarity sources: the **tag=0x10 byte** (per-controller, used for HUD display) and the **slot.rarity u32 array** at `body+0x35..+0x5c` of the tag=0x12 record (per-slot, used by the picker when a slot's loaded talent is null). `rerw write savefile all-talent-rarities <name>` writes both in one pass.

## Run-state record GUID

The 15 bytes that follow the tag in the run-state record header are the run-state record's own GUID:

```
bf e7 f6 60 43 85 cb 48 87 f6 b4 b7 9f 68 12
```

This is the `RECORD_GUID_15` constant cited by the locator strategies in [`talent-records.md`](../../findings/talent-records.md) and [`magical-objects.md`](../../findings/magical-objects.md). The 16th byte after the tag is a separator (`0xa5`).

## Pointers

- **Domain findings:** [`talent-records.md`](../../findings/talent-records.md) (talent picks + per-slot rarity array + per-controller tag=0x10 records), [`magical-objects.md`](../../findings/magical-objects.md) (item records + set-bonus tracker + ADD/SWAP/REMOVE primitives + engine ceilings).
- **Format master:** [`save-binary-format.md`](../../findings/save-binary-format.md) (top-level save container, header, CRC).
- **Picker behavior:** [`rng-behavior.md`](../../findings/rng-behavior.md) (when the picker reads slot.rarity vs the tag=0x10 byte).
- **Locator template:** [`talent-records.md`](../../findings/talent-records.md) §"Picks-block locator (generalized)" — the canonical example for the `## Locating <thing>` subsection convention used by other findings.
- **Vocabulary:** [`../terminology/README.md`](../terminology/README.md).
