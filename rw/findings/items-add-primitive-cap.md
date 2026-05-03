[← Back to findings](README.md)

# Items ADD primitive — save-load cap discovery

**Status:** in-progress
**Status notes:** OPEN (Rule A reframed, new Rule C discovered) — Rule A is a fresh-reference-allocation cap, fully bypassable by ref-reuse (lab-confirmed). Rule B (per-item +3-over-threshold) still applies independently. **Rule C** is a separate record-count ceiling that triggers even with full ref reuse (signature `6b52cc56-...`, NULL_POINTER_WRITE_NULL_INSTRUCTION_PTR). Rule C bisected to [89, 94] records on Save A. Ghidra investigation narrowed Rule C to a subscriber's vtable[0x10] in the post-loop count-event broadcast (see `ghidra-rule-c-investigation.md`). REMOVE primitive verified end-to-end.
**Created:** 2026-04-28
**Last updated:** 2026-04-29 (reference-allocation hypothesis confirmed + Rule C discovered + bisected + Ghidra dive)

## Sources

- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob (Save A — chapter 2, 14 MOs / 21 records)
- rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob (chapter 3, 25 MOs / 43 records)
- rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob (epilogue, 29 MOs / 51 records)
- rw/saves/edits/lab/geppetto/laser-lenses_1/item-add-* (verified working/crashing ADD probes)
- rw/saves/edits/lab/geppetto/laser_lenses_1/chapter3-plus-{3,4,5,6}-moonstones/ (chapter-3-baseline ADD probes)
- rw/saves/edits/lab/geppetto/laser-lenses_1/epilogue-plus-{5,6,7,8}-moonstones/ (epilogue-baseline ADD probes)
- /mnt/d/steam-storage/steamapps/common/Ravenswatch/CrashDB/reports/*.dmp (crash dumps from over-tolerance probes)
- rw/findings/magical-objects.md (canonical doc; engine-validation section needs revision after this triage)
- rw/dumps/items_make_lab_add_*.py (probe-builder scripts, gitignored)
- rw/dumps/items_make_lab_add_moonstone_{6,11,53,65,71,77,103,203,503}_reuse_ref.py (reuse-ref bisect builders, gitignored)
- rw/dumps/items_inspect_post_records.py (records-array layout analyzer)
- rw/findings/ghidra-rule-c-investigation.md (companion Ghidra dive — call chain, function renames, narrowing of Rule C)

## Three independent crash mechanisms (REVISED 2026-04-29)

Probes revealed three orthogonal rules. Any can independently trigger a crash:

### Rule A: Per-save fresh-reference-allocation cap (REFRAMED)

Each save has a cap on the number of NEW object references the load-time deserializer can register from save records. Hand-inserting records with unique counter values consumes new-ref slots; the cap was previously thought to be a per-save record-count tolerance. Lab-confirmed 2026-04-29: records that REUSE an existing reference (instead of allocating a fresh one) are fully exempt from this cap. The +3 reuse-ref-738 probe loaded with 17 MOs / 24 records on Save A, vs the same total with fresh refs crashing. Crash signature `276109f4-3a0d-29ee-1ac0-fc5b348ff902`, ACCESS_VIOLATION read at `Ravenswatch+0x204760` inside `vec_u64_assign_resize`. Cap varies per save state.

### Rule B: +3 instances over per-item set-bonus threshold (or hard cap for Legendary/Cursed)

If any single item has 3 or more instances OVER its set-bonus threshold (Common 5, Rare 4, Epic 3) or hard cap (Legendary 1, Cursed 1), the engine crashes regardless of total record count. Verified for Common (Moonstone, Voodoo Doll) and Legendary (Vorpal Blade). Predicted for Rare (7 instances → crash) and Epic (6 instances → crash) but UNTESTED.

The earlier "+3 records added" hypothesis was a Rule A artifact in saves where the +3 added happened to coincide with the natural cap boundary OR with a per-item threshold violation. Disambiguated by the chapter-1 stripped epilogue + 8 unique (loaded) vs + 8 Voodoo (crashed) test pair — same record count, only difference was per-item threshold violation.

### Rule C: Total-record-count ceiling, even with full ref reuse (NEW)

Independent of Rule A. Triggered by total record count alone, regardless of whether refs are fresh or reused. Bisected on Save A (chapter 2):

- **Loads:** ≤ 89 records (+68 reused-ref Moonstones)
- **Crashes:** ≥ 95 records (+74 reused-ref Moonstones)
- **Cap:** somewhere in [89, 94] records on Save A. Not a clean power-of-2; the 96-buffer hypothesis was falsified (+74 / 95 records crashed).

Crash signature differs from Rule A:
- Failure ID hash: `6b52cc56-5a0e-1553-b6cb-84d1d5a95d5d`
- Bucket: `NULL_POINTER_WRITE_NULL_INSTRUCTION_PTR_INVALID_POINTER_WRITE`
- Symbol: `Ravenswatch+748653` (= absolute `0x1400B6C6D`)
- Operation: invalid WRITE through null pointer (vs Rule A's invalid READ)

The reported crash address is in startup-init code with no xrefs — implies stack/return-address corruption hides the real fault site. Ghidra investigation narrowed the cap to a subscriber's `vtable[0x10]` in the count-event broadcast called once after the records-replay loop (`hero_inventory_recompute_and_broadcast_counts`, renamed from `FUN_14038a310`). See `rw/findings/ghidra-rule-c-investigation.md` for the full call-chain trace and remaining unknowns.

## Empirical per-save tolerance map (Rule A — FRESH-ref only)

These tolerances apply when added records use fresh (unique) counter values. With ref reuse, Rule A is bypassed entirely and only Rule C applies. ADD operations using FRESH refs tolerate up to N additional records past the natural baseline. N varies by save:

| Save | Chapter | Baseline (MOs / total records) | Last working +N | First crashing +N |
|---|---|---|---|---|
| Save A (`laser-lenses_1`) | 2 | 14 / 21 | +2 (16 MOs) | +3 (17 MOs) |
| Chapter 3 proof | 3 | 25 / 43 | +3 (28 MOs) | +4 (29 MOs) |
| Epilogue proof | epilogue | 29 / 51 | +7 (36 MOs) | +8 (37 MOs) |
| Stripped epilogue (chapter byte = epilogue) | epilogue | 0 | +7 (Voodoo) | +8 (soft crash); +9 hard |
| Stripped epilogue → chapter 1 | 1 | 0 | +9 (unique items) / +10 (with 2 set-bonus tracker entries from Rose+Porridge AT threshold) | varies, see late-session probes |

The boundary is sharp — crashes are deterministic, identical signature, no flakiness. **The same MO total can load or crash depending on which save it came from** (29 MOs loads as natural epilogue; 29 MOs crashes when reached by adding 4 records to chapter 3).

### Stripping destroys the cap

Tested: stripped epilogue (kept all Region 1, Region 4, talents) crashed at 9 records of unique items. Natural epilogue holds 36 records cleanly. **Stripping records does not preserve the natural cap** — the cap drops dramatically. Workaround "strip a high-cap save then refill with custom items" is heavily constrained.

### Set-bonus tracker entries grant additional tolerance

Tested on stripped epilogue → chapter 1:
- 0 tracker entries (9 unique items, none at threshold): max 9 records
- 2 tracker entries (5 Eternal Rose + 5 Goldilocks' Porridge, both AT Common 5 threshold): max 10 records (verified 10 loads, 11 with 1 extra below-threshold soft-crashes)
- 3 tracker entries (5 Rose + 5 Porridge + 5 Mermaid Tears AT threshold): crashes at 15 records (so tolerance is ≤14)

Each set-bonus tracker entry appears to grant ~+0.5 to +1 record of additional tolerance. Effect is real but small.

### Chapter byte affects tolerance on stripped saves (but not full saves)

- Save A bumped to chapter 3 (full save) + 3 records: hard crash (tolerance stays at +2, chapter byte irrelevant)
- Stripped epilogue bumped to chapter 1 + 9 unique items: loads (tolerance increased from +7 voodoo to ≥+9 unique vs original chapter-epilogue state)

So the chapter byte matters more in stripped saves than in unstripped saves. Mechanism unclear.

## Crash signature (constant across all over-tolerance probes)

```
Exception:        0xC0000005 ACCESS_VIOLATION
Read target:      0xffffffffffffffff (sentinel/uninitialized pointer)
Failure bucket:   BAD_INSTRUCTION_PTR_INVALID_POINTER_READ
Failure ID hash:  276109f4-3a0d-29ee-1ac0-fc5b348ff902
Crash address:    Ravenswatch+0x204760 (or +0x204764 in one variant — same function, 4 bytes apart)
Module:           Ravenswatch.exe (no symbols)
Context strings:  hero.inventory, Skill Controller Passive Create Objects, object.0..object.15
```

Identical hash across the 4-VB / 12-Moonstone / maxed-stacks / chapter-3+4 / chapter-3+6 / epilogue+8 crashes confirms shared root cause / shared code path. The crash is at the inventory-construction site during `Skill Controller Passive Create Objects` initialization.

## Falsified hypotheses (with the lab probes that disproved each)

### "Engine has a fixed 16-MO total cap"

Original interpretation of the `object.0`–`object.15` strings in the first crash dump. Empirically false: epilogue natural save loads with 29 MOs. Maxed-stacks lab edit (28 MOs, all stackable items at their set-bonus thresholds) crashes with the same hash, demonstrating the cap can't be a fixed 16. The `object.0`–`object.15` strings probably index into a fixed-size scratch buffer somewhere in the inventory-build path, but that buffer's exact role is unverified.

### "Going +3 over the per-item set-bonus threshold crashes"

Fit the Vorpal Blade boundary perfectly (cap 1, crashes at 4 = +3 over; loads at 3 = +2 over). Falsified by the maxed-stacks probe which had every stackable item exactly at its set-bonus threshold (none over) and crashed regardless. Per-item rules don't predict the crash boundary.

### "External chapter field controls tolerance"

Bumped Save A's chapter from 2 → 3 via `rerw write savefile --chapter 2` (sets two int32 LE counters at 0xe9d1 and 0xf241), then added 3 records. Same crash, same hash. Tolerance stayed at +2 despite the chapter byte saying chapter 3. So the cap isn't held in the chapter field that the tool maintains.

### "Tolerance = (set-bonus-tracker count) + 2"

Fit the first two saves: Save A has 0 items at set bonus → tolerance +2; chapter 3 has 1 item at set bonus → tolerance +3. Predicted epilogue (3 set-bonus items) → tolerance +5. Actual epilogue tolerance is +7, falsifying the formula.

### "Cap value is stored as a literal integer somewhere in the save"

Searched all three saves for the predicted cap values (16 / 28 / 36) at common body, pre-region, and post-region offsets, in u8, u16 LE, and u32 LE encodings. Also searched for cap-1 and total-record variants (23 / 46 / 58). Zero common offsets across all three saves for any encoding. The cap is not stored as a plain integer at a fixed location.

## Discovery: trailing block is variable-length, not fixed 112 bytes

Earlier docs called the post-records-array region a "fixed 112-byte trailing block." That's wrong. The block grows with progression:

```
[u32 = N items at set bonus]
[N × 16-byte runtime GUIDs of items at set bonus]
[u32 = M talents picked]
[M × 16-byte talent runtime GUIDs]
[8 zero bytes]
[u32 — per-save scalar (looks IEEE-754 float-shaped; growth/run-time?)]
[8 zero bytes]
[22 22 bb aa close marker]
```

Observed across the three saves:

| Save | N (set-bonus items) | Set-bonus item GUIDs | M (talents) | Trailing block size |
|---|---|---|---|---|
| Save A | 0 | (none) | 5 | 112 bytes |
| Chapter 3 | 1 | Moonstone | 8 | 176 bytes |
| Epilogue | 3 | Moonstone, Raven Skull, Adder Stone | 10 | 240 bytes |

`tolerance = set_bonus_count + 2` formula fit Save A and chapter 3 but failed for epilogue. The set-bonus tracker is real and meaningful — it just doesn't fully predict the cap.

## Stacking rules — corrected understanding

Earlier docs called Common 5 / Rare 4 / Epic 3 the "max stack" per rarity. Actually these are **set-bonus thresholds**, not hard caps. Items can legitimately exceed these counts in normal gameplay (epilogue has 4× Adder Stone, exceeding the Epic threshold of 3, in a clean natural save). True hard caps are only Legendary 1 and Cursed 1 (no-stack) — and even those tolerate save-edited overage up to +2 instances before the engine crashes (3 Vorpal Blades loads; 4 crashes).

| Rarity | Set-bonus threshold | Hard cap |
|---|---|---|
| Common | 5 | none (can exceed) |
| Rare | 4 | none |
| Epic | 3 | none |
| Legendary | — | 1 |
| Cursed | — | 1 |

The set-bonus threshold matters because reaching it appears to register the item in the save's set-bonus-tracker block (the `[u32 = N][N × GUIDs]` section). Going over the threshold doesn't add a new tracker entry — that section counts unique items at-or-above threshold, not instances.

## Open questions

| Question | Status | Notes |
|---|---|---|
| What computes the per-save Rule A cap? | partially resolved | Reframed as a fresh-ref-allocation cap. Ghidra confirmed it lives in `vec_u64_assign_resize` invoked from `entity_sync_component_vector`. Bypassed entirely by ref reuse. The exact cap value still varies per save state — formula unknown. |
| What computes the per-save Rule C cap? | unresolved | Ghidra narrowed it to a subscriber's `vtable[0x10]` in `hero_inventory_recompute_and_broadcast_counts`. Pinpointing requires either dynamic analysis or full skill-controller vtable mapping. See `ghidra-rule-c-investigation.md`. |
| Is Rule C scoped per-rarity, per-effect, or per-total? | untested | Bisect was done with all-Moonstone probes (single Common rarity). A mixed-rarity probe (e.g., +50 Moonstones + +30 Adder Stones) would distinguish per-rarity vs total scoping. |
| Does tolerance vary within a chapter? | untested | All probed chapter-2 data is from Save A's specific run state. A chapter-2 save with different baseline MO count or different progression might tolerate differently. |
| Does Region 1 (pre-run-state, +412 bytes between ch2/ch3) or Region 4 (post-run-state, +1046 bytes) hold cap-relevant state? | untested | Both grew with chapter progression; either could contribute to either cap. |
| Why does chapter 3 + 5 fresh-ref hang instead of crash, while +4 and +6 both crash? | unresolved | Suggests the engine's near-boundary behavior is not simple — maybe a buffer overflow that sometimes corrupts the loop counter (hang) vs sometimes corrupts a function pointer (crash). |
| What does the per-save scalar near the trailing-block close (`00 80 77 44` Save A, `00 80 fc 44` chapter 3) encode? | untested | Looks IEEE-754 float-shaped; grows between chapters. Possibly run-time elapsed or distance/score. |
| Are records of a given item beyond its set-bonus threshold "extra slots", or do they get folded into a single inventory display slot? | resolved | Each save record creates its own entity (Ghidra-confirmed). Stack count at entity+0x2a8 is incremented on duplicates. UI shows correct counts. |
| Stack-count field in save record (compactness) | resolved | NEGATIVE — does not exist. Save record is exactly 32 bytes per instance; stack count is in-memory only. |
| Does the engine renumber refs on save? | static answer: **likely preserved** (high confidence ~85%); empirical pending | Static analysis 2026-04-29 (see "Counter durability — static analysis" below). Empirical confirmation pending the in-flight chapter-end save with the +50 reuse-ref-738 + 3 BM Mirror probe. |

## Ghidra findings — 2026-04-29

Static analysis with GhidrAssistMCP changes the likely model for Rule A.

Crash RVA `Ravenswatch.exe+0x204760` resolves to `0x140204760`, inside a generic vector-copy/resize helper now labeled `vec_u64_assign_resize` in the Ghidra project. The crashing instruction is not an item parser or direct cap check; it copies 8-byte entries between vector buffers.

The save-load item replay path is:

1. `serde_hero_controller_persistent_data` (`0x140380490`) deserializes the hero persistent data.
2. `serde_vec_hero_owned_mo_persistent_data` (`0x1403b4550`) reads a vector of 32-byte `Dt Hero Controller Owned MO Persistent Data` entries into `persistent+0xa8`, with count at `persistent+0xb0`.
3. `hero_controller_init_replay_persistent_data` (`0x140384610`) replays that vector. Its loop at `0x140386e38` iterates `count = *(uint *)(persistent+0xb0)`, element stride `0x20`, base `*(persistent+0xa8)`.
4. For each element, it resolves the item ID at `entry+0x8`, reads a pointer/reference from `entry+0x18`, writes the resolved runtime entity ID into that pointed object at `+0x18`, calls `entity_sync_component_vector` (`0x1406db4b0`), then creates/binds the live inventory object with `hero_inventory_create_magical_object` (`0x14039dee0`) and `hero_inventory_bind_magical_object_name` (`0x14039e290`).

Important detail: `serde_hero_owned_mo_persistent_data` (`0x140380360`) reads two fields:

```c
FUN_140212f90(stream, entry + 0x8);          // 16-byte item/runtime ID
stream->vtable[0xa8](stream, entry + 0x18); // object/reference field
```

This means the final field of the 32-byte save record is not merely a harmless sequence counter from the engine's perspective. It deserializes into an in-memory pointer/reference at `entry+0x18`, and replay trusts it before calling `entity_sync_component_vector`.

Working hypothesis: Rule A is an object-reference/fixup-cap issue rather than a gameplay inventory-size check. Hand-inserted records can resolve their item GUID correctly, but once the serialized object-reference field no longer maps to a valid owned object, `entity_sync_component_vector` receives an invalid/sentinel object and crashes while copying that object's component vector. This matches the observed invalid read at `0xffffffffffffffff` inside the vector helper.

Still unresolved: exactly where the serializer/object-reference table decides that a given added record's reference is valid. The next decompiler target is the implementation behind the stream vtable slot `+0xa8` used by `serde_hero_owned_mo_persistent_data`, or a save-file comparison focused on all serialized object-reference IDs around the item-record counters.

### Reference-allocation hypothesis — CONFIRMED (2026-04-29)

The validation probe `item-add-moonstone-6-reuse-ref-738` (24 records, third added Moonstone reusing existing ref 738 instead of fresh ref 753) **loaded cleanly with 6 Moonstones** — same total record count that crashes when refs are unique. Rule A is decisively a reference-allocation cap, not a record-count cap.

Stress-tested at scale: `item-add-moonstone-53-reuse-ref-738` (Save A + 50 Moonstone records all reusing ref 738, 71 records / 22 MOs) loaded with 53 Moonstones in inventory — well past Save A's natural +2 fresh-ref tolerance and past anything in any natural save (epilogue tops out at 29 MOs / 51 records). Reuse is a true bypass for Rule A.

### Rule C ceiling — bisected on Save A (2026-04-29)

Pushing the reuse trick further found a separate crash mechanism (Rule C). Bisect on Save A using all-ref-738 Moonstone probes:

| Probe | Records | Result | Notes |
|---|---|---|---|
| +6 (3 Moonstones in inv) | 24 | ✅ load | First reuse-ref validation |
| +50 (53 Moonstones) | 71 | ✅ load | Reuse-ref scaling confirmed |
| +62 (65 Moonstones) | 83 | ✅ load | Bisect step |
| +68 (71 Moonstones) | 89 | ✅ load | Bisect step |
| +74 (77 Moonstones) | 95 | ❌ Rule C crash | 96-buffer hypothesis falsified |
| +75 (78 Moonstones) | 96 | ❌ Rule C crash | |
| +100 (103 Moonstones) | 121 | ❌ Rule C crash | |
| +200 (203 Moonstones) | 221 | ❌ Rule C crash | |
| +500 (503 Moonstones) | 521 | ❌ Rule C crash | First Rule C observation; led to bisect |

Cap on Save A: somewhere in **[89, 94] records**. Not a clean round number.

Bankable safe number for tooling on Save A: **+50 reused-ref records (71 total) loads cleanly with comfortable headroom.**

### Ghidra investigation summary (2026-04-29)

Decoded the load-replay call chain. Renamed/commented in the Ghidra project for persistence across sessions:

- `magical_object_registry_lookup_by_guid` (was `FUN_140254be0`) — pure 16-byte GUID lookup, not the cap.
- `dispatch_event_with_swap_remove` (was `FUN_14026f260`) — generic broadcast-with-removal vector iteration, used for stack-count and count-event notifications.
- `hero_inventory_recompute_and_broadcast_counts` (was `FUN_14038a310`) — called ONCE after the records loop, tabulates per-rarity (5) + per-effect (7) + total counts and dispatches them to subscriber vectors at hero+0x1c00 / +0xd98..+0xe18 / +0xe70..+0xfa0. **Strongest Rule C suspect lives here** — one of those subscribers' `vtable[0x10]` allocates a fixed-size pool sized for typical inventory and overflows around 94+ items, clobbering a return pointer.
- `hero_inventory_create_magical_object` — plate-commented with the stack-count mechanism: each save record creates a new entity; existing matching entities have their stack count at `+0x2a8` incremented. The `object.0..object.15` strings in crash dumps are slot-name format outputs from `hero_inventory_bind_magical_object_name`, not array indices.

Closes the open question on stack-count compactness with a negative result: there is **no per-record stack-count field** — the engine creates one entity per save record on load, and stack count is a derived in-memory value. Saves cannot represent N instances compactly.

Full call-chain trace, function renames, remaining unknowns, and suggested next-session probes: see `rw/findings/ghidra-rule-c-investigation.md`.

## Risk for tooling

ADD operations now have two distinct ceilings:

| Ceiling | Trigger | Bypass | Empirical bound |
|---|---|---|---|
| Rule A (fresh-ref allocation) | Each new ref consumes a fixup slot | Fully bypassed by reusing an existing ref value | Save A: +2; ch3: +3; epilogue: +7 (fresh refs) |
| Rule C (record count) | Record count alone, regardless of ref reuse | None known | Save A: ~94 records (bisected; unknown for other saves) |

**Recommended tooling strategy:** ADD operations should reuse an existing record's ref instead of allocating a new one. This sidesteps Rule A and gives much higher headroom (+50 verified safe on Save A). The remaining ceiling is Rule C, which on Save A is well above any natural inventory size (~94 records vs natural epilogue of 51).

Other-save Rule C ceilings haven't been measured. Tooling that wants to be safe across all save classes can either (a) re-bisect each save class empirically, or (b) wait for a Ghidra session to pin the cap formula. Until then, a conservative cap of +30 reused-ref records past baseline should be safe on any save.

SWAP is unaffected — record count never changes, no cap involved.

## Counter durability — static analysis (2026-04-29)

Static-only verdict on the open question "does the engine renumber refs on save?" pending the chapter-end empirical confirmation.

**Verdict: counters likely preserved across save cycles. Confidence ~85%.**

Evidence chain:

1. **Unified read/write serde.** Both `serde_vec_hero_owned_mo_persistent_data` (`0x1403b4550`) and `serde_hero_owned_mo_persistent_data` (`0x140380360`) are unified read/write functions branching on `stream->vtable[0x20]` ("is loading?"). There is no separate write-side function that could renumber.

2. **Field-typed slot, not a generic transform.** The 16-byte item GUID at `entry+0x8` uses stream `vtable[0x90]` (plain u32, via the `serde_guid_as_4xu32` helper at `0x140212f90`). The counter at `entry+0x18` uses `vtable[0xa8]` — a different, typed slot. Whatever transform the slot does on read, the unified-serde guarantees the inverse on write.

3. **Replay never modifies `entry+0x18`.** `hero_controller_init_replay_persistent_data` reads `entry+0x18` as a pointer P and writes `*(P+0x18) = resolved_runtime_entity_id`. It writes through the pointer, not to the entry field itself. So between load and save, the in-memory bytes at `entry+0x18` are exactly what the deserializer placed there.

4. **Empirical baseline shape.** Across observed saves (chapter 2 / chapter 3 / epilogue), counter values are large sequential integers (730+) — not reset-per-save numbers. Strongly consistent with stable IDs assigned at object creation, not per-save renumbering.

5. **Ref-reuse durability follows.** Multiple records sharing one counter (e.g., 50× ref 738) all resolve to the same in-memory pointer P at load. On save, `vtable[0xa8]` reads the same pointer and serializes the same u32 each time → all records re-emit as 738 byte-for-byte.

**The 15% I can't rule out statically:** the write-mode `vtable[0xa8]` body itself isn't decompiled. There's a tail risk that pointer→u32 conversion uses a fresh numbering pass over the live object pool rather than reading a stable ID off the object. The in-flight chapter-end empirical (the +50 reuse-ref-738 + 3 BM Mirror probe) closes this question once and for all.

## Possible next investigations

1. **Pin Rule C's exact subscriber.** Per the Ghidra dive (`ghidra-rule-c-investigation.md`), Rule C lives in a `vtable[0x10]` of one subscriber attached to the hero's count-event vectors. Static enumeration of skill-controller classes + their dispatch handlers would identify it. Dynamic analysis (debugger attach, dump subscriber lists) is faster.
2. **Probe Rule C scoping.** Build a save with mixed rarities — e.g., +50 Moonstones + +30 Adder Stones, all reusing refs. If it loads, Rule C is per-rarity. If it crashes at the same total count, Rule C is total-driven.
3. **Probe save-and-reload durability.** Take the +50 reuse-ref Save A through a chapter-2 → chapter-3 run and capture the resulting save. Diff to see if the engine renumbers refs on save (would invalidate the reuse trick across save cycles).
4. **Re-bisect Rule C on chapter 3 / epilogue.** The cap likely scales with save state; knowing the chapter-3 and epilogue ceilings lets tooling generalize without static analysis.
5. **Decode Region 1 / Region 4.** These regions grew significantly between chapters; either could contribute to the Rule A or Rule C cap inputs.

## Lab-probe outcomes (full list)

### Source: Save A (chapter 2 proof, 14 MOs / 21 records baseline)

| Edit | MOs | Records | Result |
|---|---|---|---|
| +1 Moonstone | 15 | 22 | ✅ load |
| +2 Moonstone (5 total — at Common threshold, set bonus active) | 16 | 23 | ✅ load + damage 46→102 |
| +1 Vorpal Blade (2 total) | 15 | 22 | ✅ load + damage scaled |
| +2 Vorpal Blade (3 total — +2 over Legendary) | 16 | 23 | ✅ load + damage scaled |
| +3 Vorpal Blade (4 total — +3 over Legendary, hits Rule B) | 17 | 24 | ❌ hard crash |
| +9 Moonstone (12 total — +7 over Common, hits Rule B) | 23 | 30 | ❌ hard crash |
| +11 Vorpal Blade (12 total — +11 over Legendary, hits Rule B) | 25 | 32 | ❌ hard crash |
| +14 (maxed all stacks, no item over threshold — hits Rule A only) | 28 | 35 | ❌ hard crash |
| −1 (Philosopher's Stone, last record) | 13 | 20 | ✅ load (REMOVE primitive verified) |

#### Save A reuse-ref probes (all-Moonstone, all reusing existing ref 738)

Probes built to test whether Rule A is record-count-bounded or ref-allocation-bounded.

| Edit | Moonstones | Records | Result |
|---|---|---|---|
| +3 reuse-ref-738 (mixed: 751, 752, 738) | 6 | 24 | ✅ load — proved Rule A is ref-allocation, not records |
| +50 all ref 738 | 53 | 71 | ✅ load — Rule A bypass at scale |
| +62 all ref 738 | 65 | 83 | ✅ load — bisect step |
| +68 all ref 738 | 71 | 89 | ✅ load — bisect step (last loading) |
| +74 all ref 738 | 77 | 95 | ❌ Rule C crash — falsified 96-buffer hypothesis |
| +75 all ref 738 | 78 | 96 | ❌ Rule C crash |
| +100 all ref 738 | 103 | 121 | ❌ Rule C crash |
| +200 all ref 738 | 203 | 221 | ❌ Rule C crash |
| +500 all ref 738 | 503 | 521 | ❌ Rule C crash — first observation, prompted bisect |

Rule C ceiling on Save A: cap ∈ [89, 94] records. Crash signature `6b52cc56-...`, NULL_POINTER_WRITE, distinct from Rule A's `276109f4-...`.

### Source: Save A bumped to chapter 3 (via tool's `--chapter 2`)

| Edit | MOs | Result |
|---|---|---|
| +2 Moonstone | 16 | ✅ load (chapter byte alone didn't change Rule A cap) |
| +3 Moonstone | 17 | ❌ hard crash (Rule A: tolerance still +2) |

### Source: Chapter 3 proof (25 MOs / 43 records baseline)

| Edit | MOs | Result |
|---|---|---|
| +3 Moonstone | 28 | ✅ load |
| +4 Moonstone | 29 | ❌ hard crash |
| +5 Moonstone | 30 | 🟡 soft crash (hang) |
| +6 Moonstone | 31 | ❌ hard crash |
| −5 Moonstone (kept stale tracker) | 20 | ✅ load |
| −5 Moonstone + 10 Voodoo | 30 | ❌ hard crash (Rule A: stripping didn't free cap) |

### Source: Epilogue proof (29 MOs / 51 records baseline)

| Edit | MOs | Result |
|---|---|---|
| +5 Moonstone | 34 | ✅ load |
| +6 Moonstone | 35 | ✅ load |
| +7 Moonstone | 36 | ✅ load |
| +8 Moonstone | 37 | ❌ hard crash |

### Source: Epilogue stripped to 0 records (set-bonus tracker cleared, talents kept)

| Edit | Records | Composition | Result |
|---|---|---|---|
| (stripped) | 0 | empty | ✅ load (Test A success — zero-record save loads) |
| +4 Voodoo | 4 | Common, under threshold | ✅ load |
| +6 Voodoo | 6 | Common, +1 over threshold | ✅ load |
| +7 Voodoo | 7 | Common, +2 over | ✅ load |
| +8 Voodoo | 8 | Common, +3 over (Rule B trigger) | 🟡 soft crash |
| +9 Voodoo | 9 | Common, +4 over | ❌ hard crash |
| +10 Voodoo | 10 | Common, +5 over | ❌ hard crash |
| +12 Voodoo | 12 | (built but never tested) | — |
| +15 Voodoo | 15 | Common, +10 over | ❌ hard crash |
| +30 Voodoo | 30 | Common, +25 over | ❌ hard crash |
| +7 Voodoo + 1 Vorpal | 8 | mixed | ❌ hard crash |

### Source: Stripped epilogue → chapter 1 (via tool's `--chapter 0`)

| Edit | Records | Tracker entries | Composition | Result |
|---|---|---|---|---|
| +7 unique items | 7 | 0 | mixed rarities, none at threshold | ✅ load |
| +8 unique items | 8 | 0 | mixed rarities | ✅ load |
| +9 unique items (Commons) | 9 | 0 | all Common, none at threshold | ✅ load |
| +10 unique items (Commons) | 10 | 0 | all Common, none at threshold | ❌ crash (type unrecorded) |
| +8 Voodoo | 8 | 0 | Common, +3 over (Rule B) | ❌ hard crash |
| +5 Rose + 5 Porridge | 10 | 2 (auto on load) | both Common AT threshold | ✅ load |
| +5+5+1 (Rose, Porridge, Mermaid) | 11 | 2 + 1 below | mixed | 🟡 soft crash |
| +5+5+5 (Rose, Porridge, Mermaid) | 15 | 3 (all AT threshold) | all Common | ❌ crash (type unrecorded) |
| +15 mixed stacked under threshold | 15 | 0 | 5 unique stacked | 🟡 soft crash |
| +15 unique items | 15 | 0 | 15 different items | 🟡 soft crash |
| +20 unique items | 20 | 0 | 20 different items | 🟡 soft crash |

## REMOVE primitive — verified

Verified end-to-end on Save A. Steps:
1. Locate the run-state record (find tag=0x12 + run_state_guid_15, walk back to marker).
2. Read items count = u32 LE at body+0x61.
3. Compute target offset for the record to remove = body+0x65 + (slot_index × 32). For "remove last record": slot_index = count − 1.
4. Splice OUT the 32-byte record: `data = data[:offset] + data[offset+32:]`. File shrinks by 32 bytes.
5. Write count−1 back at body+0x61.
6. Recompute CRC32 of body (data[16:]) and write at offset 0x0C.

Lab-confirmed: removed Save A's Philosopher's Stone (Legendary, counter 750) → save loads, inventory shows 13 MOs, vitality effect doesn't linger on next pickup. Set-bonus tracker auto-syncs on load (engine recomputes from records), so no need to update the trailing block manually.

**Safe domain (rigorously):** removing any record from a save where the save's set-bonus tracker doesn't reference that item. For a stripped operation that touches set-bonus-tracked items, the engine re-syncs the tracker on load — no manual cleanup needed (per session observation).

**Untested:** removing records by counter that are NOT the last (mid-array splice). Mechanically should work the same way (splice + count decrement + CRC) but never lab-verified. The Test A "strip all records" probe did this implicitly with batch removal; one-at-a-time mid-array removal not separately tested.
