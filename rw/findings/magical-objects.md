[← Back to findings](README.md)

# Save: magical objects (items) — record format and edit primitives

The player's collected magical objects are encoded as `tag=0x1a` records nested inside the `tag=0x12` run-state record. Each pickup event in a run produces one record. The 16-byte runtime GUID inside each record identifies which item is at that slot; the engine reads these records to populate the player's Magical Objects panel and apply effects.

A separate `tag=0x05` compendium catalog (114 records, identical across all saves) tracks profile-level magical-object discovery state. Catalog records use a different GUID per item (the asset-level GUID) than the runtime records — both GUIDs come from the same entity-settings file, but they're not interchangeable.

**Status:** confirmed
**Status notes:** record format, SWAP primitive, ADD primitive, and REMOVE primitive verified end-to-end on Geppetto chapter 2 / chapter 3 / epilogue saves. Engine validation has TWO independent ceilings on ADD: **Rule A** is a fresh-reference-allocation cap (chapter 2: +2, chapter 3: +3, epilogue: +7) that is **fully bypassed by reusing an existing record's reference value**; **Rule C** is a separate record-count ceiling that triggers even with full ref reuse (Save A: ~94 records). See triage `rw/findings/items-add-primitive-cap.md` and Ghidra dive `rw/findings/ghidra-rule-c-investigation.md`. Ghost migration mechanism documented and lab-confirmed. See `item-table.md` for the full 114-item catalog.
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

### Records-array layout inside the run-state record body

The full tag=0x12 run-state body layout — items count at `body+0x61`, items records-array at `body+0x65`, trailing block (set-bonus tracker → picks block → 8-zero / float / 8-zero / close marker) — lives in [`../docs/workflow/cross-cutting.md`](../docs/workflow/cross-cutting.md). Item-domain specifics that stay here:

- **Item record (tag=0x1a) framing.** 32 bytes: `[marker 4: 11 11 bb aa][tag 4: 1a 00 00 00][runtime GUID 16][counter u32 LE][close 4: 22 22 bb aa]`.
- **Counter sequence.** Strictly +1 sequential within all observed saves. `last_counter + 1` is the safe value for newly inserted records (lab-verified across multiple saves).
- **Observed item-records counts.** Save A (Ch2) 21 records; Chapter 3 (varies); Epilogue (varies).

Set-bonus tracker observed sizes (the per-save N and per-save M counts, which determine total trailing-block size):

| Save | N (set-bonus items) | Set-bonus GUIDs | M (talents) |
|---|---|---|---|
| Save A (Ch2) | 0 | (none) | 5 |
| Chapter 3 | 1 | Moonstone | 8 |
| Epilogue | 3 | Moonstone, Raven Skull, Adder Stone | 10 |

## Locating items

Strategy used by `tools/rerw-src/lib/item_edit.py` (`find_run_state`, `parse_records`) to locate the items records-array inside the save:

1. Find the run-state record header: `data.find(bytes([0x12, 0, 0, 0]) + RUN_STATE_GUID_15)`. The 16th byte after the tag is a separator (`0xa5`).
2. Walk back to the start marker `11 11 bb aa` — this is the start of the run-state record.
3. Walk forward into the body. The items count u32 lives at `body+0x61`; the records array starts at `body+0x65`.
4. Read `count` records of 32 bytes each. Each record's bytes are validated against the framing (`11 11 bb aa` at byte 0 of the record, `22 22 bb aa` at byte 28).
5. After `body+0x65 + count*32`, the trailing block begins (set-bonus tracker → picks block → fixed close, per [`../docs/workflow/cross-cutting.md`](../docs/workflow/cross-cutting.md)).

### Assumptions the strategy makes

- The run-state record GUID `bf e7 f6 60 43 85 cb 48 87 f6 b4 b7 9f 68 12` is hero-independent (verified across Geppetto saves; cross-hero generality unverified).
- The body offsets `+0x61` for items count and `+0x65` for records-array start are constant across all observed Geppetto saves (chapter 2, chapter 3, epilogue).
- Each item record is exactly 32 bytes; the framing markers self-terminate.
- The counter sequence is strictly +1 sequential within a save (`last_counter + 1` is safe for new inserts).

### Known failure modes

- **Engine ceiling triggers on ADD.** Past per-save tolerances, the engine refuses the save on load:
  - **Rule A** — fresh-reference-allocation cap (chapter 2: +2, chapter 3: +3, epilogue: +7). **Fully bypassed by reusing an existing record's reference value** via `add --reuse-counter-from-slot N`.
  - **Rule B** — per-item +3-over-threshold cap. Independent of Rule A.
  - **Rule C** — separate record-count ceiling (~94 records on Save A) that triggers even with full ref reuse. See [`ghidra-rule-c-investigation.md`](ghidra-rule-c-investigation.md) and [`items-add-primitive-cap.md`](items-add-primitive-cap.md).
- **Ghost-target GUIDs.** Some legendary GUIDs are ghost-effect references (e.g. Baba Yaga's Mortar's runtime GUID resolves to Water of Life via inheritance). SWAPping into a ghost target is functional but produces unexpected display labels.
- **Stack-rarity SWAPs are unverified.** SWAP's safe domain is rigorously Legendary↔Legendary or Cursed↔Cursed where neither item is currently in inventory. Swapping into a stacked Common/Rare/Epic slot would split the stack, with unverified engine-side behavior.
- **Cross-hero generality.** All locator verification is on Geppetto saves. Other heroes are presumed compatible (the run-state record GUID identifies the type, not the hero) but not yet tested.

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

## Edit primitive: ADD — verified within per-save tolerance

Insert a new `tag=0x1a` record at the end of the records array. Variable-size; shifts the trailing block forward by 32 bytes.

```
1. Find the run-state record (find tag=0x12 + run_state_guid_15, walk back to marker).
2. Read items count = u32 LE at body+0x61.
3. Compute insertion offset = body+0x65 + count*32 (just before the [u32=0][u32=5] sentinel).
4. Build new record:
   [11 11 bb aa][1a 00 00 00][16-byte runtime GUID][u32 LE counter=last_counter+1][22 22 bb aa]
5. Splice the 32-byte record at the insertion offset (file grows by 32 bytes).
6. Write count+1 back at body+0x61.
7. Recompute CRC32 of body (data[16:]) and write at offset 0x0C.
```

**Safe domain:** ADD that respects both engine ceilings:
- **Rule A (fresh-ref allocation):** small fresh-ref tolerance per save (Save A / Ch2: +2; Ch3: +3; epilogue: +7). **Bypassable by reusing an existing record's counter value as the new record's counter** — Save A then tolerates +50 reused-ref records loading cleanly (53× Moonstone in inventory).
- **Rule C (total record count):** separate ceiling that triggers even with full ref reuse. Save A bisected to [89, 94] total records. Other saves' Rule C ceilings unmeasured.
- **Per-item rarity rules** (Common 5 / Rare 4 / Epic 3) are **set-bonus thresholds, not hard caps** — items can legitimately exceed them in normal play. True hard caps are only Legendary 1 and Cursed 1; save-edited overage tolerated up to +2 instances. See `rw/findings/items-add-primitive-cap.md` for the full investigation and `rw/findings/ghidra-rule-c-investigation.md` for the engine-side trace.

### Verified lab probes (selection — see triage for full table)

| Probe | Edit | Result |
|---|---|---|
| ADD #1 | Save A Moonstone 3 → 4 | ✅ load |
| ADD #2 | Save A Moonstone 3 → 5 | ✅ load + set bonus verified (damage 46 → 102, 2.22× ratio combining +50% set bonus and per-stack effect) — promoted to `golden/geppetto/chapter2/laser-lenses_1/item-add-fill-moonstone-stack-5of5/` |
| Save A boundary | +3 records → 17 MOs | ❌ crash |
| Chapter 3 boundary | +4 records → 29 MOs | ❌ crash (29 MOs is fine in epilogue natural — proves cap is per-save, not absolute) |
| Epilogue boundary | +8 records → 37 MOs | ❌ crash |

The set-bonus result on ADD #2 is the strongest possible confirmation that hand-injected records are fully functional — they participate in stack-counting, set-bonus checks, and per-stack damage calculations, not just inventory display.

## Engine validation on save load

The engine enforces **two independent ceilings** on the records array. Either can crash the engine on load if exceeded.

### Rule A — Fresh-reference-allocation cap

Each new (unique) record-counter value consumes a slot in the engine's load-time reference-fixup vector. The cap on this vector varies per save state. Bypassed entirely by reusing an existing counter value when adding records.

Empirical fresh-ref tolerance (records that can be added past natural baseline using fresh counters):

| Save | Baseline records | Fresh-ref tolerance | Max records (fresh) |
|---|---|---|---|
| Save A (Geppetto Ch2) | 21 (14 MO + 7 PU) | +2 | 23 |
| Chapter 3 proof | 43 (25 MO + 18 PU) | +3 | 46 |
| Epilogue proof | 51 (29 MO + 22 PU) | +7 | 58 |

Crash signature when exceeded:

```
Exception:        0xC0000005 ACCESS_VIOLATION (read)
Read target:      0xffffffffffffffff
Failure bucket:   BAD_INSTRUCTION_PTR_INVALID_POINTER_READ
Failure ID hash:  276109f4-3a0d-29ee-1ac0-fc5b348ff902
Crash address:    Ravenswatch+0x204760  (inside vec_u64_assign_resize)
Caller chain:     hero_controller_init_replay_persistent_data → entity_sync_component_vector → vec_u64_assign_resize
```

### Rule C — Total record-count ceiling

Independent of Rule A. Triggered by record count alone, regardless of ref novelty. Bisected on Save A: cap ∈ [89, 94] records (loads at 89, crashes at 95). Save A safely loads up to **+50 reused-ref records / 71 total** with comfortable headroom.

Other saves' Rule C ceilings are unmeasured. Crash signature differs from Rule A:

```
Exception:        0xC0000005 ACCESS_VIOLATION (write)
Write through:    null pointer
Failure bucket:   NULL_POINTER_WRITE_NULL_INSTRUCTION_PTR_INVALID_POINTER_WRITE
Failure ID hash:  6b52cc56-5a0e-1553-b6cb-84d1d5a95d5d
Symbol:           Ravenswatch+748653 (= 0x1400B6C6D, in startup-init code → return-address corruption hides the real fault site)
```

Ghidra investigation narrowed Rule C to a subscriber's `vtable[0x10]` in the post-loop count-event broadcast called from `hero_inventory_recompute_and_broadcast_counts` (after iterating all save records). Likely a skill-controller passive that creates child entities scaled by item count and overflows around 94+ items. Pinpointing requires dynamic analysis or full skill-controller vtable mapping. Full trace: `rw/findings/ghidra-rule-c-investigation.md`.

### Falsified hypotheses

- "Fixed 16-MO total cap" — disproved by epilogue's 29 MOs loading natively. The `object.0..object.15` strings in crash dumps are slot-name format outputs from `hero_inventory_bind_magical_object_name`, not array indices.
- "Going +3 over per-item set-bonus threshold crashes" — disproved by maxed-stacks (no item over threshold) crashing.
- "External chapter field controls tolerance" — disproved by tool-bumped chapter (Save A → ch3) keeping Save A's +2 tolerance.
- "Tolerance = set-bonus-tracker count + 2" — fit Save A and chapter 3, falsified by epilogue (predicted +5, actual +7).
- "Cap is stored as a literal integer somewhere" — searched all three saves for predicted cap values; zero common offsets.
- "Rule A is a per-save record-count cap" — superseded by the reference-allocation reframing (lab-confirmed via reuse-ref probe).
- "Rule C cap is at exactly 95 records (96-buffer)" — falsified by +74 reused-ref probe (95 records crashed, so cap < 95).

### Implication for tooling

ADD operations should reuse an existing record's ref value to bypass Rule A and gain much higher headroom. The remaining ceiling is Rule C, which on Save A is far above natural inventory sizes. Conservative recommendation: cap at +30 reused-ref records on any save until per-save Rule C ceilings are measured or the cap formula is decoded. SWAP is unaffected (record count never changes). REMOVE is verified end-to-end (see triage).

### Item stacking rules — corrected understanding

Earlier docs (and the wiki) treat Common 5 / Rare 4 / Epic 3 as "max stack" per rarity. Empirically these are **set-bonus thresholds, not hard caps**. Items can exceed them in normal play (epilogue's 4× Adder Stone exceeds the Epic threshold of 3 in a clean natural save).

| Rarity | Set-bonus threshold | Hard cap |
|---|---|---|
| Common | 5 | none (can exceed in normal play) |
| Rare | 4 | none |
| Epic | 3 | none |
| Legendary | — | 1 (no stack) |
| Cursed | — | 1 (no stack) |

Reaching a set-bonus threshold registers the item in the run-state's set-bonus tracker (the `[u32 = N][N × GUIDs]` block at the start of the trailing region). Going beyond the threshold doesn't add a new tracker entry; it counts unique items at-or-above threshold, not instances.

For Legendary/Cursed (true hard cap of 1), the engine still tolerates save-edited overage up to 3 instances on Save A (3-VB probe loaded; 4-VB crashed). The over-cap behavior is bounded by the per-save record-count tolerance, not by per-item rarity rules.

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

- `rw/findings/item-table.md` — full 114-item catalog (effect, icon, name-key, runtime GUID, catalog GUID, rarity, ghost rows)
- `rw/findings/save-catalog-flag-bytes.md` — partial decode of `tag=0x05` flag bytes
- `rw/findings/save-binary-format.md` — overall save format (CRC32, record markers, type registry)
- `rw/findings/talent-records.md` — talent record format (analogous structure for talents)
- `tools/rerw-src/data/magical-items.yaml` — magical-object registry (display_name + key + effect + runtime GUID + rarity + desc)
- `tools/rerw-src/data/powerup-items.yaml` — powerup registry

## Open questions

| Question | Status | Notes |
|---|---|---|
| Items count field location | ✅ resolved | u32 LE at run-state body+0x61. Records array starts at body+0x65 |
| Run-state record outer length field | ✅ resolved | No length prefix; marker/close framing self-terminates. Splices verified at +32 / +64 / +288 bytes without any other length field needing update |
| Sequence counter rules | ✅ resolved | Strictly +1 sequential within a save. `last_counter + 1` is safe (lab-verified at +1, +2, and +9 record adds) |
| Stack-limit engine validation on load | ✅ resolved | Engine has a per-save record-count cap (NOT a per-item stack cap). See "Engine validation on save load" section above and `rw/findings/items-add-primitive-cap.md`. |
| What computes the per-save cap? | ❓ unresolved | Cap correlates with chapter progression but isn't controlled by the chapter byte alone. Not stored as a literal integer at any common offset. Likely computed by the engine from inputs we haven't decoded — see triage. |
| Inventory slot cap (16-slot hint) | ❌ disproved as "fixed cap" | The `object.0`–`object.15` strings exist but don't represent a fixed 16-MO ceiling. Epilogue loads with 29 MOs natively. The 16-indexed strings probably name a fixed-size scratch buffer in the inventory-build path, role unverified. |
| Cross-rarity swap behavior | unverified | Swap of Legendary slot → stackable item: how does engine handle |
| Powerup record retention | unverified | Why are consumed powerups in the records list at all? Event log? Achievement tracking? |
| No-stack duplicate ADD behavior | ✅ resolved | Engine accepts duplicates of Legendary/Cursed (no-stack) items as separate functional instances. Lab-verified: 2× and 3× Vorpal Blade load, contribute to damage scaling, no display dedup or rejection. The +N tolerance applies normally regardless of whether the duplicates are no-stack. |

## Tooling

`rerw` integration is wired (MAINT-23, 2026-05-01):

- `tools/rerw-src/lib/item_edit.py` — pure-logic primitives `find_run_state`, `parse_records`, `swap_item`, `add_item`, `remove_item`, with `ItemEditError`. Reuses the run-state record GUID also used by `talent_edit`.
- `tools/rerw-src/lib/game_registry.py` — `magical_items().lookup(key)` resolves item key → 16-byte runtime GUID for the CLI.
- `tools/rerw-src/commands/write_savefile.py` — three subcommands under the `item` group:
  - `rerw write savefile item swap --slot N --key <ItemKey>`
  - `rerw write savefile item add --key <ItemKey> [--reuse-counter-from-slot N]`
  - `rerw write savefile item remove --slot N`
- Validation: byte-equality between the production CLI's output and all three reference artifacts (`item-add-fill-moonstone-stack-5of5` golden, `item-vorpal-blade-to-baba-yagas-mortar` lab, `item-remove-last-record` lab). 14 unit tests in `tests/unit/test_lib_item_edit.py` cover the primitives plus error paths.

Engine ceilings (Rule A / B / C) are not enforced by the tooling — the lib produces syntactically valid records and the caller is responsible for staying within the per-save tolerance documented above. `add --reuse-counter-from-slot N` is the recommended Rule A bypass.

The data side (`magical-items.yaml`, `powerup-items.yaml`, `item-table.md`) backs the strict-key registry. Key resolution rejects display names and aliases; valid keys are discoverable via `rerw game-assets inspect items`.

## Sources

- `rw/saves/proofs/geppetto/{clean,chapter2,chapter3,epilogue}/.../Profile_1.ob` — proof saves (catalog reference + Save A/B for active items).
- `rw/saves/edits/lab/geppetto/laser-lenses_1/item-vorpal-blade-to-baba-yagas-mortar/Profile_1.ob` — verified SWAP lab edit.
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/item-add-fill-moonstone-stack-5of5/Profile_1.ob` — verified ADD probe (5-of-5 Moonstones, set bonus active).
- `/mnt/d/steam-storage/steamapps/common/Ravenswatch/CrashDB/reports/180da781-979c-43c5-bb83-a4b9012b4af7.dmp` — crash dump from over-tolerance ADD probe (3 → 12 Moonstones, instruction-pointer corruption in `Skill Controller Passive Create Objects`).
- `rw/dumps/items_*.py` — recon scripts (gitignored). Notable: `items_inspect_post_records.py` (records-array layout RE), `items_make_lab_add.py` / `items_make_lab_add_5of5.py` (verified ADD probes), `items_make_lab_add_overstack.py` (over-tolerance crash probe).
- `rw/harvested/EntitySettings/Obzects/` — 204 cooked item entity files (gitignored).
