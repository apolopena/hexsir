[← Back to findings](README.md)

# Save: catalog flag-byte analysis (tag=0x05 records)

**Status:** confirmed
**Status notes:** partial / in-flight. Observations confirmed; field interpretation hypothesized. Not yet promoted from observation to verified semantics.
**Created:** 2026-04-29

The 114 `tag=0x05` records in every save body are the magical-object + powerup catalog (one record per entity in the cooked `EntitySettings/Obzects/` tree). Each record carries 12 metadata bytes after the 16-byte catalog GUID. This document captures what those 12 bytes look like across the catalog and what they might mean.

## Record layout

Each catalog record is 40 bytes:

```
[marker 4: 11 11 bb aa]
[tag    4: 05 00 00 00]
[catalog GUID 16]
[flag bytes 12]                  ← this analysis
[close marker 4: 22 22 bb aa]
```

Flag bytes occupy file-relative bytes 24–35 within each catalog record.

## Observed flag patterns (114 records, Save A + Clean)

Both saves yield the same pattern distribution; flag bytes are profile-level state, not per-run.

| # | Count | 12 bytes hex |
|---|------:|---|
| 1 | 43 | `00 00 00 00 01 00 01 ff ff ff ff 00` |
| 2 | 28 | `00 00 00 00 01 01 00 03 00 00 00 00` |
| 3 | 28 | `00 00 00 00 01 00 00 03 00 00 00 00` |
| 4 | 6  | `00 00 00 00 01 01 00 03 00 00 00 01` |
| 5 | 4  | `00 00 00 00 01 00 00 03 00 00 00 01` |
| 6 | 3  | `00 00 00 00 00 00 00 ff ff ff ff 00` |
| 7 | 2  | `00 00 00 00 01 01 00 ff ff ff ff 00` |

Total: **114 records, 7 distinct patterns**.

## Hypothesized field layout

The 12 bytes break naturally into:

```
[u32 = 0]              ← bytes 0–3, always zero
[u8 A]                 ← byte 4, 0x00 or 0x01
[u8 B]                 ← byte 5, 0x00 or 0x01
[u8 C]                 ← byte 6, 0x00 or 0x01
[u8 D]                 ← byte 7, 0x03 or 0xff       ← strong signal
[u32 X]                ← bytes 8–11, `00 00 00 00` or `ff ff ff ff` (correlates with D) plus byte 11 sometimes 0x01
```

## Hypothesized interpretation (NOT YET VERIFIED)

| Field | Hypothesis | Evidence |
|---|---|---|
| Byte D = `0x03` (X = `00 00 00 00`) | Magical Object | Patterns 2 + 3 + 4 + 5 = 66 records. We have 68 MOs in the catalog. Off by 2. |
| Byte D = `0xff` (X = `ff ff ff ff`) | Powerup | Patterns 1 + 6 + 7 = 48 records. We have 46 powerups. Off by 2. |
| Last byte (byte 11) = `0x01` | Some MO-only attribute (is_unique? unlock-quest? sub-tier?) | Only seen in patterns 4 + 5 (10 records total). All within the `0x03` group. |
| Byte 4 = `0x00` (pattern 6) | Outlier — possibly a per-asset edge case | 3 records share this. |
| Byte 5 = `0x01` with `0xff` byte D (pattern 7) | Outlier — possibly a powerup variant | 2 records. |

The off-by-2 counts in MO and Powerup totals could be `_Model` template files or other edge cases mis-counted.

## What's confirmed vs hypothesized

| Claim | Status |
|---|---|
| 114 records with 7 distinct flag patterns | **confirmed** by enumeration in Save A + Clean |
| Pattern distribution identical between Save A and Clean | **confirmed** |
| Flag bytes are profile-level / static (not per-run) | **confirmed** (identical across all saves we have) |
| Byte D distinguishes MO vs Powerup | **hypothesis** — counts off by 2 in each category, needs cross-reference verification |
| Byte 11 = `0x01` flags a special MO attribute | **hypothesis** — untested |
| Patterns 6 & 7 are edge cases / data-cleanup artifacts | **hypothesis** — purposes unknown |

## Open questions

- What is each individual byte's semantic role?
- Cross-reference: which 6 MOs have pattern 4 (`...03 00 00 00 01`)? Same rarity? Same in-game category?
- Are these flags editable to change in-game behavior (e.g., compendium discovery, locked/unlocked, quest-gated)?
- Are flag bytes the actual unlock-state data, or is unlock state stored in a different record type (`ObjectCollectionUnlockConditionData` class string is in the type registry — not yet decoded)?

## How this relates to the items hunt

Discovered while probing for a per-slot display-override mechanism in the save (looking for ways to make ghost items display as their original entity). No such per-slot mechanism was found. The catalog flag bytes ARE meaningful and varied, but they're catalog-level (one set of flags per item type, identical across all saves), so they cannot drive per-slot rendering.

The catalog is a separate data layer from active-item run-state — see `magical-objects.md` (TODO) for the active-item record format.

## Next steps to fully decode

1. **Cross-reference each flag pattern with item characteristics.** Group catalog GUIDs by flag pattern, then look up each via `item-table.md` to see if patterns correlate with rarity, MO-vs-Powerup, is-cursed, has-quest-trigger, or other observable attributes.
2. **Lab-edit a single flag byte and verify in-game.** Pick one item, flip byte 11 from `0x00` to `0x01` (or vice versa), see if compendium / discovery / unlock state changes. Risk: minor — catalog records, not run state.
3. **Find an `ObjectCollectionUnlockConditionData` record.** Its class string is in the type registry but its records are not yet located. Likely the actual unlock-state location (or one of them).
4. **Compare against a partial-unlock save.** A save from a player with incomplete catalog discovery would show different flag bytes than ours (where everything is presumably already discovered). No such proof save currently exists.

## Sources

- `rw/saves/proofs/geppetto/clean/Profile_1.ob`
- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- `rw/saves/proofs/geppetto/chapter2/twin-dummies-all-legendary-talents/Profile_1.ob`
- `rw/dumps/items_probe_display_override.py` — probe script that produced the pattern enumeration.
- `rw/findings/item-table.md` — for cross-referencing catalog GUIDs to item attributes.
- `rw/findings/save-binary-format.md` — for record format conventions and the type-registry mention of `ObjectCollectionUnlockConditionData`.

## Locating these byte patterns on a new build

Per `rw/docs/README.md` §"Locating <thing>" — byte-stream template. Byte-pattern heavy; anchors are the patterns themselves plus their structural position within `tag=0x05` records.

### Strategy

1. Byte-pattern search the save for `tag=0x05` record headers (per `save-binary-format.md` framing).
2. Walk each record body to the 12-byte flag-byte block following the 16-byte catalog GUID.
3. Match observed patterns against this finding's enumeration table.
4. Cross-check via `item-table.md` for catalog-GUID → item attributes.

### Assumptions

- The 40-byte tag=0x05 record layout (16-byte GUID + 12-byte flag block + framing) stable engine-wide.
- Flag-byte semantics stable across builds.
- The 114-record count is stable (one per entity in the catalog) — unless devs add new objects.

### Known failure modes

- **New catalog entries.** Each new MO / powerup adds a record. Total count grows; pattern table may need new entries.
- **New collection state.** A previously-unseen flag pattern indicates a new state. Doc table needs updating, not the locator strategy.
- **Cipher / framing change.** Inherits from `save-binary-format.md` failure modes.

### Cross-finding anchoring

Inherits from `save-binary-format.md` (record framing) and `item-table.md` (GUID → attribute mapping).
