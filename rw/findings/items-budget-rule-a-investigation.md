# Items budget Rule A investigation — persistent struct field map + cross-type-reuse failure mode

**Status:** in-progress
**Created:** 2026-05-04

## Scope honesty (read first)

**Investigation stopped 2026-05-04.** No actionable save-side fix found for adding items not present in the source proof beyond the per-save fresh-ref budget (+2/+3/+7).

This finding conflates two distinct failure modes that share crash hash `276109f4-3a0d-29ee-1ac0-fc5b348ff902`:

1. **Documented Rule A** — deserialize-time fresh-reference-allocation cap per-save. Crashes ON LOAD when too many fresh-counter records exist. Budget input field unfound; not directly probed this session. The cleanest unrun test is documented in Unresolved.
2. **Cross-type reuse-counter corruption** — characterized this session as a separate failure mode. Saves built with `--reuse-counter-from-slot N` where N's slot type ≠ the new item's type produce malformed entities at deserialize. Saves LOAD cleanly but crash on first action that reads the corrupted entity. Hashes vary (`276109f4`, `38a19e94`) depending on which downstream consumer hits the corruption first.

**Why investigation stopped:**

- The "missing sidecar" hypothesis (rerw adds records but doesn't update a parallel data structure the engine expects) was empirically disproved by user-reported behavior: when items added via `rerw write savefile item add` cross a set-bonus threshold (e.g., 5 Moonstones reaching Common's threshold), the **set bonus fires correctly in-game**. The engine recomputes the set-bonus tracker at runtime from the rarity vector contents — `+0xb8/+0xc0` is not a save-side input.
- That leaves only one viable save-side fix path: locate and edit the +2/+3/+7 budget input field. This field is not in the persistent struct's `+0x50..+0x100` range across the three dumps captured this session. Could be at higher offset, in a parent struct, or runtime-derived.
- Even if found, the budget input may not be edit-side actionable (could be a hard-coded chapter-correlated constant or runtime-derived value).
- For the practical use case (build a defense-stack lab with items not in source on chapter-2 base), no save-side path delivers without first solving the budget question.

**Practical fall-back patterns (proven to work this session):**

- **Same-type reuse**: items already present in source proof can be stacked without limit via `--reuse-counter-from-slot N` where N's slot is same item type. Engine handles set bonuses correctly.
- **Fresh-ref add within budget**: items not in source can be added up to the per-save fresh-ref budget (+2 on Save A / chapter 2, +3 on chapter 3, +7 on epilogue). Engine handles entity creation and set bonuses correctly.
- **Source proof selection** is the practical knob: epilogue source has more item types pre-populated AND a higher fresh-ref budget.

**What this finding contributes regardless of stopping:**

- Persistent struct field map (lVar21 at records-loop time) — usable for any future items-domain RE
- Full characterization of cross-type-reuse failure mode — actionable warning for `rerw` users
- 3 baseline persistent dumps (chapter 2 / 3 / epilogue) — input data for any future budget probe
- 5 Ghidra renames + 2 plate comments — symbol identity persists in the project
- New Frida probe `tools/frida/probe_item_budget.js` — usable for any future runtime inspection of save load
- Discovery that `serde_hero_controller_persistent_data` (0x140380490) is misnamed (write-side, not load-side); actual load-side entry is `hero_controller_init_replay_persistent_data` (0x140384610) — corrects an earlier session's annotation

## Sources

- rw/findings/items-add-primitive-cap.md (parent triage with empirical Rule A/B/C data)
- rw/findings/ghidra-rule-c-investigation.md (prior Ghidra dive — call chain, function renames)
- rw/findings/magical-objects.md (canonical items-domain doc)
- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob (Save A — chapter 2, +2 budget, 14 MOs / 21 records)
- rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob (chapter 3, +3 budget, 25 MOs / 43 records)
- rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob (epilogue, +7 budget, 29 MOs / 51 records)
- rw/saves/edits/lab/geppetto/loaded-defense-stack-slot9__from-laser-lenses_1/Profile_1.ob (cross-type reuse-counter lab built from Save A; 8 RS + 6 AS + 20 MS + 3 DH + stars=10000, all reusing slot 9's Moonstone counter 738)
- /mnt/d/steam-storage/steamapps/common/Ravenswatch/CrashDB/reports/3c61dae2-b784-4270-b37c-cd03a7bd95b5.dmp (cross-type-reuse crash dump for the 1RS+1AS+1DH probe)
- tools/frida/probe_item_budget.js (Frida probe written this session for runtime inspection)
- Ghidra project: Ravenswatch.exe, image base 0x140000000

## Confirmed Findings

### `serde_hero_controller_persistent_data` (0x140380490) does NOT fire on save load

Misnamed by an earlier Codex session. Empirically verified via Frida hook on the function entry — never fired across multiple save loads. Almost certainly the **write-side serializer** (called during save-to-disk), not the deserializer. The actual save-load entry point is `hero_controller_init_replay_persistent_data` at `0x140384610`.

**Implication:** any prior analysis using `serde_hero_controller_persistent_data` to characterize load-time behavior should be revisited. Field offsets observed in that function's decomp are correct for the persistent struct's serialized layout, but its execution context is the wrong direction.

### Records-loop persistent-struct address is dynamic, not statically derivable

In `hero_controller_init_replay_persistent_data` (1,695-line function), the local `lVar21` holding the persistent struct pointer is **reassigned three times** (decomp lines 1086, 1115, 1132). The records-loop at line 1495 reads from `lVar21 = local_b60`, populated by `FUN_1402b7810(param_1, &local_b60)` at line 1445. `local_b60` is initialized at line 393 via `scene_manager_find_context_by_type(puVar11, &local_678)` and then mutated.

**Practical:** the entry-time chain `*(*(hero_state+8)+0x30)+0x1a8` resolves to a different (intermediate) struct than the one the records-loop processes. Static analysis alone cannot give the records-loop pointer; runtime capture (Frida hook of `FUN_1402b7810` onLeave) is required.

### Persistent struct field map (lVar21 at records-loop time)

Derived by hooking `FUN_1402b7810` onLeave, dereferencing args[1] (the `&local_b60` address), and dumping the resulting struct across three baseline saves + one lab. Validated by `+0xb0 items.count` matching record counts in each save.

| Offset | Type | Role | Evidence |
|---|---|---|---|
| `+0x50..+0x60` | 4 floats | Per-save run stats; monotonic across chapters (likely run-timer / playtime) | Values grow ch2 < ch3 < epilogue |
| `+0x64` lo u16 | u16 | Unknown flag (always 1 in 4 captures) | Constant across all loads |
| `+0x64` hi u16 | u16 | **Stars-of-Fate currency** | Lab with stars=10000 edit shows 0x2710 here; baselines show stars values 0/1/2 matching saves |
| `+0x68..+0x8c` | 10 × u32 | Talent slot rarities (4 = uninitialized sentinel) | Different talent sets per save, slot 5 always uninit/ult per terminology |
| `+0xa8 / +0xb0 / +0xb4` | ptr / count / cap | Items vec | items.count == file's record count; cap always == count (no slack) |
| `+0xb8 / +0xc0` | ptr / count | **Set-bonus tracker vector** | Counts of 0/1/3 across ch2/ch3/epilogue match `items-add-primitive-cap.md` empirical data exactly |
| `+0xc8 / +0xd0` | ptr / count | Empty in all 4 captures | — |
| `+0xd8 / +0xe0` | ptr / count | String vec; empty in all 4 captures | — |
| `+0xe8 / +0xf0` | ptr / count | Unknown vec; counts 5/8/10 across ch2/ch3/epilogue (likely talent picks) | Lab inheriting ch2 baseline shows 5; talents weren't edited |
| `+0xf8 / +0x100` | ptr / count | Empty in all 4 captures | — |

### Crash hash `38a19e94-c229-df99-1263-35634269c852` is a third documented save-load failure class

Captured on the 1RS+1AS+1DH cross-type-reuse probe. Distinct from documented Rule C (`6b52cc56`).

**Distinct from documented Rule A (`276109f4`) by code path, NOT by hash.** This is important and easy to miss: the higher-volume cross-type-reuse labs (8RS+6AS+20MS+3DH) ALSO produce hash `276109f4`. Rule A and cross-type-reuse can collide on the same hash because both ultimately fail in `vec_u64_assign_resize` reading from a wild source pointer — Windows Error Reporting buckets them identically. The 1RS+1AS+1DH probe happens to hit hash `38a19e94` instead, probably because the smaller corruption causes the wild deref to land in different upstream code (memcpy via std::string copy in the set-bonus reconstruction). Both crashes are downstream symptoms of cross-type-reuse corruption; the hash that fires depends on which subscriber callback hits the corrupt entity first.

**Crash chain (Ghidra-traced, runtime-validated):**

```
fire_named_event (0x14067df11)
  -> set_bonus_subscriber_handler (0x14067d560)
    -> set_bonus_flag_lists_build_and_apply (0x14067d840)
      -> std_string_assign_realloc (0x1401145b0)
        -> memcpy (0x140c96e80, fault inside at +0xc97000)
```

**Mechanism:** Mismatched cross-type counter sharing produces a malformed entity. After records replay, `hero_inventory_recompute_and_broadcast_counts` (`0x14038a310`) walks the inventory and broadcasts per-rarity / per-category counts via `dispatch_event_with_swap_remove`. One subscriber (`set_bonus_flag_lists_build_and_apply`) reads `(ptr, count)` pairs at `*(item+8)+0x20/+0x38` to build `oCCustomFlagList` objects. In a corrupted entity, those fields contain wild string pointers; `std_string_assign_realloc` (small-string-opt + `_malloc_base` + `memcpy`) deref's the wild source and crashes inside memcpy's AVX2 fast path.

**Distinction from documented Rule A:** Rule A's `276109f4` is also a `vec_u64_assign_resize` access violation but triggered by **fresh-ref overflow during deserialize** — too many unique counters exhaust an upstream allocation. The new `38a19e94` is triggered by **cross-type reuse-counter producing data-shape corruption** that crashes downstream consumers. Same generic helper (memcpy) ends up the blamed frame in Windows Error Reporting; root causes differ.

### Cross-type reuse-counter labs LOAD successfully but crash on first action

Verified via Frida: lab `loaded-defense-stack-slot9__from-laser-lenses_1` (8 RS + 6 AS + 20 MS + 3 DH + stars=10000, all reusing slot 9's Moonstone counter, sourced from chapter-2 `laser-lenses_1`) successfully completes `hero_controller_init_replay_persistent_data` (`sync=58 resize=116`, function returned). The persistent struct dump shows `items.count = 58` and looks structurally valid.

The crash fires on first attack action with hash `276109f4` — same hash as documented Rule A but reached via a different code path. The corrupted entities sit in inventory and trigger crash on event traversal.

**Implication for "Rule A" framing:** the empirical "+2 / +3 / +7 fresh-ref budget" documented in `items-add-primitive-cap.md` is the **deserialize-time** failure boundary. Cross-type reuse-counter is a **separate failure mode** that produces undetected corruption at deserialize and crashes during gameplay. Both share the `276109f4` hash because both ultimately fail in `vec_u64_assign_resize` reading from corrupt component data.

### Set-bonus tracker (`persistent+0xb8/+0xc0`) is runtime-computed, NOT a save-side input

User-reported empirical observation: when items added via `rerw write savefile item add` push a count past a set-bonus threshold (e.g., 5 Moonstones for Common), the set bonus fires correctly in-game. This means the engine recomputes the tracker at runtime from the rarity vector contents during `hero_inventory_recompute_and_broadcast_counts`, then re-serializes it on save-write.

**Implication:** `rerw` does not need to update `+0xb8/+0xc0` when adding records. The engine handles it. This kills the "missing sidecar" hypothesis as an explanation for cross-type-reuse failures and removes the only candidate for an "items-add structural invariant" that wasn't already being maintained.

### Same-type reuse-counter is the only safe pattern for high-volume item adds

Empirically validated via the bisect probe `bisect-stars-moonstone-20-slot9` (20 Moonstones reusing slot 9's existing Moonstone counter 738 + stars=10000) — loaded cleanly. Confirms the existing finding's claim about reuse-counter bypassing the budget, but adds the constraint that the validated probe was always **same-type** (slot 9 in `laser-lenses_1` is itself a Moonstone, counter 738).

**Constraint:** for items NOT present in the source proof, fresh-ref add is the only safe path, capped at the per-save budget (+2/+3/+7). Cross-type reuse-counter (e.g., adding RavenSkull while reusing a Moonstone slot's counter) **silently corrupts entities** rather than failing at deserialize.

### Ghidra annotations applied this session

5 function renames + 2 plate comments via `mcp__ghidra__*`:

| RVA | Old | New | Plate comment |
|---|---|---|---|
| `0x140c96e80` | `FUN_140c96e80` | `memcpy` | — |
| `0x140c97530` | `FUN_140c97530` | `memset` | — |
| `0x1401145b0` | `FUN_1401145b0` | `std_string_assign_realloc` | — |
| `0x14067d840` | `FUN_14067d840` | `set_bonus_flag_lists_build_and_apply` | yes (records crash chain for hash 38a19e94) |
| `0x14067d560` | `FUN_14067d560` | `set_bonus_subscriber_handler` | — |
| `0x140c97000` | (crash site, mid-function) | — | yes (plate comment characterizing the 38a19e94 crash) |

## Unresolved

### The `+2/+3/+7` per-save fresh-ref budget input field is unfound

**Important caveat:** the dumps used to evaluate this question were captured from **clean, loadable saves only**. No fresh-ref-overflow lab was built or captured. Diffing three working saves' fields against the empirical budget numbers is a weak test — fields could correlate with chapter or save state in ways unrelated to the budget mechanism. The strong test (Lab A vs Lab C from the same source, only the fresh-ref count varies) was not run this session.

What was tried, weakly:

Compared the three baseline persistent-struct dumps' `+0x50..+0x100` fields against the empirical +2/+3/+7. Tried obvious formulas:

- `set_bonus + 2`: fits ch2 (0+2=2) and ch3 (1+2=3); falsifies on epilogue (predicts 5, actual 7)
- Linear in `items.count`: no clean fit (21→43→51 doesn't map to 2/3/7)
- Linear in talent slots used (4→8→10): no fit
- `(unknown_vec_count) - 3`: 5-3=2, 8-5=3, 10-3=7 — inconsistent constant

The budget is enforced somewhere upstream of `vec_u64_assign_resize` (which itself uses `_realloc_base` and grows freely). Three remaining candidate locations:

1. **Higher offset in the persistent struct.** Current dump only covers `+0x50..+0x100` (0xB0 bytes). Struct may extend to 0x300+.
2. **Parent struct.** `puVar11` (the context owner that holds `persistent` at `+0x1a8`) and `puVar19` (above puVar11) are unmapped. Budget could be a sibling field there.
3. **Runtime-derived buffer outside the persistent struct.** Allocated per-load by code we haven't traced.

### Cleanest unrun test (the actual Rule A boundary test that this session avoided): fresh-ref boundary labs A/B/C

Same source (chapter-2 `laser-lenses_1`), same item type (RavenSkull, not present in source), three lab variants:

- Lab A: + 1 fresh RavenSkull (within +2 budget) → expected to load
- Lab B: + 2 fresh RavenSkull (at budget) → expected to load
- Lab C: + 3 fresh RavenSkull (over budget by 1) → expected to crash on load with hash `276109f4`

Capture persistent dumps (and ideally puVar11 / hero_state dumps via an extended probe) for each. The diff between A/B (succeed) and C (fail) on the SAME source isolates the budget-input field if it lives in any captured struct.

Build commands (each requires full game-quit-and-restart cycle to test, per the swap discipline):

```
cd /home/ks73/repos/work/ravensmith/tools/rerw-src && uv run rerw write savefile item add --key RavenSkull --source /home/ks73/repos/work/ravensmith/rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob --dest /home/ks73/repos/work/ravensmith/rw/saves/edits/lab/geppetto/budget-probe-1rs-fresh__from-laser-lenses_1 -f
```

For 2 and 3 RavenSkulls, chain the adds (use the previous lab's Profile_1.ob as the new `--source`) without `--reuse-counter-from-slot` so each new add gets a fresh counter.

### Probe extension needed

`tools/frida/probe_item_budget.js` currently dumps only `persistent +0x50..+0x100`. To cover the candidate locations, extend `dumpPersistent()` to also emit:

- `persistent +0x100..+0x400` (higher offsets in same struct)
- `puVar11 +0..+0x300` (parent struct; captured in chain at hook entry but not currently dumped)
- `hero_state +0..+0x200` (top-level struct)

Then re-run all three baselines + the A/B/C boundary labs.

### "Expand the budget" may not be edit-side achievable even if the field is found

Honest framing: the budget input could be a save-file field (editable) OR a hard-coded chapter constant baked into the binary (only path is binary patching). The empirical numbers vary per chapter (+2/+3/+7), suggesting a chapter-correlated input — could be either. Determining which requires finding the field first, then testing whether mutating it changes the budget.

## Notes

### Why the cross-type reuse-counter trap exists

`hero_inventory_create_magical_object` (0x14039dee0, prior session's analysis) merges records by **GUID match** — same item type → increment stack count on the existing entity. Different GUID → append new entity. The COUNTER value is independent: reused counters with same GUID merge cleanly (stack count). Reused counters with different GUID produce two records claiming the same object reference; the engine creates two entities but their internal cross-references collide, producing malformed state. The finding's earlier "reuse-counter bypasses Rule A" claim was validated only with single-item-type Moonstone probes (`rw/dumps/items_make_lab_add_moonstone_*_reuse_ref.py`), where same-type merge sidestepped the corruption.

### Frida probe operational notes

- `probe_item_budget.js` is standalone (no `rw_lab.js` dependency)
- Quiet mode is the default; per-call sync/resize logging is gated to the deserialize window AND requires `armBudgetTrace({verbose:true})`
- Wild-pointer detection was removed — Frida's `Memory.readU8` over-flags valid heap addresses (false positives on every load)
- Run command: `/mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe -n Ravenswatch.exe -l /home/ks73/repos/work/ravensmith/tools/frida/probe_item_budget.js`
- REPL: `armBudgetTrace()` → click Continue in-game → capture printed to console + log file at `C:\Users\KidSqid\AppData\Local\Temp\frida_seed_diag.log`
- Per the workflow doc, every save-load test requires a **full game quit-and-relaunch** with the swap done while the game is fully closed; quitting a chapter to main menu does NOT allow a fresh load (returns a clean proof)

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. In-progress finding, tight section.

### Function anchors

| Symbol | Anchor |
|---|---|
| `hero_inventory_create_magical_object` (image+0x39dee0) | Distinctive GUID-merge logic (compare existing record GUIDs, increment stack count on match). xrefs from item-pickup events. Already named in Ghidra. |
| `hero_inventory_add_magical_object` | Wrapper around create; calls fire_named_event for inventory-changed. |
| Budget validator(s) | Anchor via runtime crash backtrace when triggering Rule A failure. |

### Struct field anchors (`HC` = hero-character runtime instance)

| Offset | Field |
|---|---|
| Various per-rarity counters | Discoverable via the create function's stack-count increment paths. |
| Persistence struct | RTTI for the persistence class plus `find_persistent_data_for_entity` xrefs. |

### Cross-finding anchoring

Inherits from `magical-objects.md` (record format), `items-add-primitive-cap.md` (count cap rules), `multiplayer-host-authority.md` (HC layout / shard wallet pattern is similar).
