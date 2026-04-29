# Save: magical objects (items) — record format and edit primitives

The player's collected magical objects are encoded as `tag=0x1a` records nested inside the `tag=0x12` run-state record. Each pickup event in a run produces one record. The 16-byte runtime GUID inside each record identifies which item is at that slot; the engine reads these records to populate the player's Magical Objects panel and apply effects.

A separate `tag=0x05` compendium catalog (114 records, identical across all saves) tracks profile-level magical-object discovery state. Catalog records use a different GUID per item (the asset-level GUID) than the runtime records — both GUIDs come from the same entity-settings file, but they're not interchangeable.

**Status:** record format and SWAP primitive verified end-to-end on chapter-2 Geppetto saves. ADD / REMOVE primitives unverified. Ghost migration mechanism documented and lab-confirmed. See `item-table.md` for the full 114-item catalog.
**Created:** 2026-04-29

## Item record (tag=0x1a) — verified

Each item-pickup record is **32 bytes**, nested inside the run-state record:

```
[marker        4: 11 11 bb aa]
[tag           4: 1a 00 00 00]
[runtime GUID 16: <hex>]
[counter       4: u32 LE — sequence number]
[close marker  4: 22 22 bb aa]
```

The 16-byte **runtime GUID** matches the GUID extracted from the item's cooked entity-settings file. The **counter** is a u32 sequence number; in chapter-2 Geppetto Save A the records use counters 730–750 (consecutive, +1 per record), in Save B 730–740. Counter scope (per-run / per-profile / global) is unverified.

### Locating the runtime GUID in entity files

Each entity file at `EntitySettings/Obzects/Magical_Obzects!<Rarity>!<Effect>.entity.ot.EntitySettingsResource.gen` contains the runtime GUID immediately preceding a class-name registration:

```
[16 bytes: runtime GUID][u32 strlen=22][string "Dt Magical Object Data"]
```

Verified: anchor is unique within each of the 114 magical-object entity files (114 of 114 had exactly one anchor match). 5 anchor-extracted GUIDs cross-checked against actual save records.

Extraction script: `rw/dumps/items_extract_runtime_v2.py` (gitignored).

## Catalog record (tag=0x05) — partially decoded

114 records, byte-identical across all observed saves. Each is 40 bytes:

```
[marker        4: 11 11 bb aa]
[tag           4: 05 00 00 00]
[catalog GUID 16: <hex, distinct from runtime GUID>]
[flag bytes  12: see save-catalog-flag-bytes.md]
[close marker  4: 22 22 bb aa]
```

Catalog GUIDs are the asset-level identifiers. Runtime GUIDs (in `tag=0x1a` records) are the entity-component instance identifiers. Both come from the same entity-settings file but are different bytes; the engine doesn't interchange them.

The 12-byte flag region has 7 distinct patterns across the 114 items — see `save-catalog-flag-bytes.md` for the partial-decode hypothesis.

## Edit primitive: SWAP — verified

Replace one slot's runtime GUID with another's. Constant-size, no body shift, single CRC pass.

```
1. Find the run-state record:
   record_off = data.find(b'\x12\x00\x00\x00' + run_state_guid_15)
2. Walk forward in the body, find the Nth tag=0x1a marker (slot N, 1-indexed by counter order).
3. Locate the 16-byte runtime GUID at marker_off + 8.
4. Overwrite with the new item's runtime GUID.
5. Recompute CRC32 of body (data[16:]) and write at offset 0x0C.
```

**Safe domain (rigorously):** Legendary↔Legendary or Cursed↔Cursed swaps where neither item is currently in inventory (single-instance items, no stacking concern).

**Unsafe / untested:** any swap involving a stackable rarity (Common/Rare/Epic). Swapping one of N stacked instances would split the stack, with unverified engine-side behavior.

### Verified lab swap

Save A (`laser-lenses_1`), slot 8 (counter 737, runtime GUID `cf7d88d6e39d0e488d0efbec81723360` — Vorpal Blade): swapped GUID at offset `0xef70` to `1cc781a598b8314e9f52ae3c19d3edb3` (`Avoid_Death_Once_Per_Chapter` — the Mortar ghost). New CRC `0x1bdce948`.

In-game observed: slot displayed as Water of Life (the ghost's display target via inheritance), +25 vitality applied, and the legacy revive-on-lethal-damage effect fired (lab-confirmed 2026-04-29 on a follow-up lethal-damage test). Confirms (a) runtime GUID drives both display and effect resolution, (b) the swap is constant-size and CRC-safe.

Lab golden: `rw/saves/edits/lab/geppetto/laser-lenses_1/item-vorpal-blade-to-baba-yagas-mortar/Profile_1.ob` (lab-side, not promoted because the destination GUID was a ghost rather than a clean canonical).

### Item stacking rules (player gameplay reference, unverified at engine validation level)

| Rarity | Max stack |
|---|---|
| Common | 5 |
| Rare | 4 |
| Epic | 3 |
| Legendary | 1 (no stack) |
| Cursed | 1 (no stack) |

These rules govern in-run pickup behavior. Whether the engine enforces them on save load (rejecting hand-injected over-stack records) is **untested** — that's the next lab probe.

## Ghost migration — verified

Some entity files have been deprecated by patch but are kept in the catalog for backward compat. The deprecated file's display assets are rerouted to a different live entity via an inheritance reference (literal path string `Objects\Magical_Objects\<Tier>\<Effect>.entity.ot` inside the entity file body). When a save record carries the deprecated runtime GUID, the engine renders the live target's name + icon. **Sole confirmed case:** old Baba Yaga's Mortar (`Avoid_Death_Once_Per_Chapter`, Legendary folder) → Water of Life (`Full_Heal_At_Day_Night`).

The Mortar case is unique because the new Mortar (`Cursed!Destroy_Legendary_To_Damage`) consumes legendaries on equip, so in-place migration would destroy other items in old saves — devs rerouted to Water of Life as a benign Legendary fallback. The legacy revive effect was retained alongside Water of Life's vitality (lab-confirmed hybrid).

## Items by tier (run-state breakdown — chapter-2 Geppetto Save A)

| Counter | Effect | Display | Tier | Notes |
|---|---|---|---|---|
| 730 | Defense_To_Damage | Moonstone | Common | 1-of-3 stack |
| 731 | Defense_To_Damage | Moonstone | Common | 2-of-3 |
| 732 | Collection_To_Damage | Cryptic Prophecy | Rare | 1-of-2 |
| 733 | Spawn_Consumables | Horn of Plenty | Common | |
| 734 | Power_Up_Damage | (powerup) | Powerup | one-shot history |
| 735 | Power_Up_Sandman_Minor_Reroll | (powerup) | Powerup | |
| 736 | Power_Up_Sandman_Minor_Reroll | (powerup) | Powerup | |
| 737 | Kill_Low_Life_Enemies | Vorpal Blade | Legendary | (lab-swapped to Water of Life) |
| 738 | Defense_To_Damage | Moonstone | Common | 3-of-3 |
| 739 | Gain_Armor_From_Talents_Rarity | Dragon Hide | Rare | 1-of-2 |
| 740 | Gain_Armor_From_Talents_Rarity | Dragon Hide | Rare | 2-of-2 |
| 741 | Temp_Dmg_Per_Health_Globe | Hungry Grass | Cursed | |
| 742 | Defensive_Gain_Charge | Adder Stone | Epic | 1-of-2 |
| 743 | Power_Up_Grimoire_Crit_Chance_High | (powerup) | Powerup | |
| 744 | Damage_Attack | Ace of Spades | Rare | |
| 745 | Power_Up_Sandman_Mazor_Duplicate_Epic_Obzect | (powerup) | Powerup | |
| 746 | Defensive_Gain_Charge | Adder Stone | Epic | 2-of-2 |
| 747 | Power_Up_Sandman_Medium_Duplicate_Rare_Obzect | (powerup) | Powerup | |
| 748 | Collection_To_Damage | Cryptic Prophecy | Rare | 2-of-2 |
| 749 | Power_Up_Sandman_Minor_Reroll | (powerup) | Powerup | |
| 750 | Vitality_Per_Health_Globe | Philosopher's Stone | Legendary | |

Powerups appear in the records list (one record per pickup event) but don't show in the in-game inventory panel — the engine likely treats consumed powerups as event log only. This is unverified mechanism — open question.

## Cross-references

- `rw/key-findings/item-table.md` — full 114-item catalog (effect, icon, name-key, runtime GUID, catalog GUID, rarity, ghost rows)
- `rw/key-findings/save-catalog-flag-bytes.md` — partial decode of `tag=0x05` flag bytes
- `rw/key-findings/save-binary-format.md` — overall save format (CRC32, record markers, type registry)
- `rw/key-findings/talent-records.md` — talent record format (analogous structure for talents)
- `tools/rerw-src/data/magical-items.yaml` — magical-object registry (display_name + key + effect + runtime GUID + rarity + desc)
- `tools/rerw-src/data/powerup-items.yaml` — powerup registry

## Open questions

| Question | Status | Notes |
|---|---|---|
| Items count field location | unverified | Save A (21 records) vs Save B (11 records) byte-diff inside run-state record body should reveal it |
| Run-state record outer length field | unverified | Adding/removing items shifts body bytes; does outer record have a length prefix that needs updating? |
| Sequence counter rules | unverified | A's records 730–750, B's 730–740. What value is valid for inserting a new record? |
| Stack-limit engine validation on load | unverified | Does engine reject hand-injected over-limit records? Lab-test progression in next probe |
| Cross-rarity swap behavior | unverified | Swap of Legendary slot → stackable item: how does engine handle |
| Powerup record retention | unverified | Why are consumed powerups in the records list at all? Event log? Achievement tracking? |

## Tooling

Tooling integration with `rerw` is **not yet wired**:
- `lib/item_edit.py` — does not exist (analog of `lib/talent_edit.py`).
- `lib/items.py` registry loader — does not exist (analog of `lib/skill_controllers.py`).
- `commands/{read,write}_savefile.py` — no `--item-slot N --item-id <id>` flag yet.
- `data/save-fields.yaml` — no `item_record:` entry yet.

The data side (`magical-items.yaml`, `powerup-items.yaml`, `item-table.md`) is ready for integration. SWAP primitive can be wired now; ADD/REMOVE primitives need the open-questions resolved first.

## Sources

- `rw/saves/proofs/geppetto/{clean,chapter2,chapter3,epilogue}/.../Profile_1.ob` — proof saves (catalog reference + Save A/B for active items).
- `rw/saves/edits/lab/geppetto/laser-lenses_1/item-vorpal-blade-to-baba-yagas-mortar/Profile_1.ob` — verified SWAP lab edit.
- `rw/dumps/items_*.py` — recon scripts (gitignored).
- `rw/harvested/EntitySettings/Obzects/` — 204 cooked item entity files (gitignored).
