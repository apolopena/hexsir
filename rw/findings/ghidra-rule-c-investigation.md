[← Back to findings](README.md)

# Ghidra dive — Rule C cap source investigation

**Status:** in-progress
**Status notes:** PARTIAL — Rule C narrowed to a specific code path but exact cap source not pinpointed. All function renames + comments applied to the Ghidra project so the trail persists across sessions.
**Created:** 2026-04-29
**Session:** Claude Code with `mcp__ghidra` (HTTP MCP at `127.0.0.1:8080/mcp`).

## Sources

- `rw/findings/items-add-primitive-cap.md` — parent triage with empirical Rule A/B/C data and prior Codex-driven Ghidra findings.
- `rw/saves/edits/lab/geppetto/laser-lenses_1/item-add-moonstone-{6,11,53,65,71,77,103,203,503}-reuse-ref-738/` — bisect probe outputs.
- Ghidra project: `/C:/Users/KidSqid/GhidraProjects/Ravensmith.rep` (Ravenswatch.exe, image base 0x140000000).

## Goal

Two questions when the session started:

1. **Where is Rule C enforced?** Empirically: ~94 records on Save A (chapter 2) crashes with signature `6b52cc56-...` (NULL_POINTER_WRITE_NULL_INSTRUCTION_PTR), even when all added records reuse an existing object reference. The crash address `Ravenswatch+0xB6C6D` resolves into startup-init code with no xrefs — implies stack/return-address corruption hides the real fault site.
2. **Is there a stack-count field in the save record?** Compactness concern: 500 records adds 16KB to the file; if the engine accepts a single record with N stacks, tooling could represent many instances cheaply.

## Step-by-step trail

### 1. Confirm crash address sits in dead code

Disassembled `0x1400B6C50..0x1400B6CB0`. The crash address `0x1400B6C6D` lands inside what looks like C++ static-storage initialization (writes zeros + sentinels into globals around `0x1412cdd00`). `xrefs to 0x1400B6C6D` returned **no references**. Conclusion: the address is a Windows WER fallback after stack corruption — not the actual fault site. Pivot: chase the records-replay call chain from the prior triage's Ghidra findings.

### 2. Decompile `hero_controller_init_replay_persistent_data` (0x140384610)

1,695-line function. Used a subagent to extract just the records-iteration loop and any fixed-size buffer candidates. Findings:

- **The 0x1a records loop** (lines 1492–1522): iterates `*(uint*)(persistent+0xb0)` records of stride 0x20 from `*(persistent+0xa8)`. Each iteration calls `magical_object_registry_lookup_by_guid` (renamed from `FUN_140254be0`), writes the record's saved object-ref into the resolved entity at +0x18, then `entity_sync_component_vector()`, `hero_inventory_create_magical_object`, `FUN_1402cfa50(_, 2)`, and `hero_inventory_bind_magical_object_name`.
- **Loop is unbounded at this level.** No fixed-capacity stack array, no constant memcpy size, no comparisons against a literal cap. The cap lives in a callee, not here.
- **All other vector growth** in the function uses doubling-from-8 (8/16/32/64/128/...), so 94 isn't a direct vector-resize threshold either.

Subagent's prediction (kept for context): if the cap is a doubling-grown vector, it'd be 128 (next power of 2 above 94). Empirically that's wrong — the doubling vectors all grow fine, the cap is in a different mechanism.

### 3. Decompile `FUN_140254be0` → renamed `magical_object_registry_lookup_by_guid`

Pure 16-byte GUID lookup over a registry. Two-stage search (primary array, then secondary). Returns a registry entry pointer (or 0). No buffer, no cap. Renamed and plate-commented. Not the cap source.

### 4. Decompile `hero_inventory_create_magical_object` (0x14039dee0)

This is where the **stack-count mechanism** lives. For each save record:

- A new entity (`lVar6`) is allocated via `FUN_1406ca380`.
- Loops the existing rarity vector (`param_1+0xd80` for rarity 0..4, `+0xf48` for rarity 5) for entities with the same item GUID. For each match, increments the matched entity's stack count at `+0x2a8` and dispatches stack-changed events via `dispatch_event_with_swap_remove` (renamed `FUN_14026f260`).
- The new entity is appended to the rarity vector with its own stack index.
- The vector grows by doubling — no fixed cap.

**Implication for task #7 (stack-count compactness):** the engine creates one entity per save record on load; the stack count is a derived in-memory value at `+0x2a8`. There is no per-record stack-count field. Saves cannot represent N instances compactly — each instance needs its own 32-byte record.

Plate-commented at 0x14039dee0.

### 5. Decompile `FUN_14026f260` → renamed `dispatch_event_with_swap_remove`

Generic vector iteration: for each entry in `vec[0..count)`, calls `entry->vtable[0x10](event_arg, entry)`. If the call sets `vec[2] = -1`, the entry is swap-erased. Pattern: "broadcast event to subscribers, remove subscribers that opted out." Renamed and plate-commented. Not the cap source on its own.

### 6. Decompile `entity_sync_component_vector`

Calls `vec_u64_assign_resize` on `(*plVar1, count)` — that's the **Rule A** site (already confirmed in the prior triage). Function snapshots the entity's component vector, then walks a settings list and adds/removes components to make them match. Idempotent with reused refs (same target entity each call). Not the Rule C source.

### 7. Decompile `FUN_1402cfa50`

Small 4-iteration state-update loop. Manipulates ushort fields at `+0xc` and `+0x5e` of 4 components at `param_1+0x70..+0x90`. Switches on `param_2 == lVar5` for the "current" component. Looks like a UI/animation tick rather than a cap. Not investigated further.

### 8. Decompile `hero_inventory_bind_magical_object_name`

For each item in the rarity vector, formats `"object.{N}"` (using the format string at `0x140f08f48` — the only static occurrence) and binds it via `FUN_1405051a0`. The crash dump strings `object.0..object.15` and `object.0..object.29+` are produced here. Loop is unbounded — runs `*(uint*)(param_1+0xd88)` times (= total item count). The strings shown in crash dumps are simply the names successfully generated before the crash; they don't imply a fixed-16 buffer in this function.

### 9. Decompile `FUN_14038a310` → renamed `hero_inventory_recompute_and_broadcast_counts`

**This is the strongest lead.** Called ONCE after the records loop. Walks the rarity vector, tabulates:
- 5 per-rarity counts at `param_1+0xe50..0xe60`.
- 7 per-effect counts (categories 0..6 from each entity's `+0x128` list).

Then dispatches counts to **subscriber vectors** via `dispatch_event_with_swap_remove`:
- `param_1 + 0x1c00` — total-items subscribers (1 vector, fired with total count).
- `param_1 + 0xd98..+0xe18` — per-rarity subscribers (5 vectors, 0x20 stride).
- `param_1 + 0xe70..+0xfa0` — per-effect subscribers (7 vectors, 0x20 stride).

Each subscribed entry is dispatched as `entry->vtable[0x10](count, entry)`. The crash dump string `Skill Controller Passive Create Objects` matches the kind of subscriber that lives in these vectors — a passive that creates child entities scaled by item count. If such a subscriber allocates a fixed-size pool sized for typical inventory and writes past the end at high counts, it would clobber a return pointer, producing the observed Windows-stack-walks-into-startup-init crash signature.

Renamed and plate-commented.

## What was renamed / commented

| Address | Old name | New name | Comment |
|---|---|---|---|
| 0x140254be0 | FUN_140254be0 | `magical_object_registry_lookup_by_guid` | yes (plate) |
| 0x14026f260 | FUN_14026f260 | `dispatch_event_with_swap_remove` | yes (plate) |
| 0x14038a310 | FUN_14038a310 | `hero_inventory_recompute_and_broadcast_counts` | yes (plate) |
| 0x14039dee0 | (already named) `hero_inventory_create_magical_object` | unchanged | yes (plate) — added stack-count mechanism notes |

`hero_controller_init_replay_persistent_data` (0x140384610), `entity_sync_component_vector`, `hero_inventory_bind_magical_object_name`, `vec_u64_assign_resize` were all already named by Codex's prior session; left as-is.

## What we know now (and didn't before)

1. **Stack count is in-memory only** (entity+0x2a8). No save-side compactness possible. Closes task #7 with a negative result.
2. **Rule A's mechanism is fully traced.** `vec_u64_assign_resize` (the +0x204760 crash address) is called from `entity_sync_component_vector`, which copies the entity's component vector into a local snapshot using fresh refs. Reused refs avoid this growth. Already known but now more precisely documented.
3. **Rule C is narrowed but not pinned.** It lives in `entry->vtable[0x10]` of one specific subscriber inside the post-loop count-event broadcast in `hero_inventory_recompute_and_broadcast_counts`. Most likely a skill controller / passive that creates child objects scaled by item count.
4. **The reported crash address (0xB6C6D) is misleading.** It's where Windows WER lands after return-address corruption — not the fault site. Stack corruption explains why the "instruction pointer" goes null.

## What's unresolved

- **Which exact subscriber crashes.** Pinpointing requires either (a) dynamic analysis (attach a debugger, dump the subscriber vectors at hero startup, identify what `vtable[0x10]` does for each), or (b) statically mapping every possible skill-controller class and checking which ones overflow at high item counts. Both are big efforts.
- **The cap formula.** Empirically Save A's cap is ~94 records, but other saves probably differ. Without pinning the subscriber, we can't compute "max records for any given save state." Empirical bisecting per save class remains the fallback.
- **Per-record vs per-rarity vs per-effect scoping.** The crash could be a function of total count, of single-rarity count (95 Moonstones = 95 Common, hits a 96-element Common-handler array?), or of an effect category count. Different probes (e.g., 50 Moonstones + 50 Adder Stones to spread across Common/Epic) would distinguish.

## Suggested next-session plan

1. **Skill-controller class enumeration.** Search the binary for skill-controller vtable entries. Decompile each `vtable[0x10]` slot for likely candidates (Spawn_Consumables, Power_Up_Damage, Create_Objects-named handlers). Look for fixed-size arrays / loops bounded by item count.
2. **Probe to disambiguate scoping.** Build a save with mixed rarities — e.g., +50 Moonstones (Common) + +30 Adder Stone (Epic), all reusing refs. If it loads, the cap is per-rarity not total. If it crashes at the same total count, cap is total-item-driven.
3. **Static dump of subscriber registration.** Find the function that pushes onto `hero+0x1c00` (total subscribers). That function is likely called during hero entity construction with each skill controller as it registers itself. Identifying the registrants narrows the suspect list dramatically.

## Cross-references

- `rw/findings/items-add-primitive-cap.md` — empirical Rule A/B/C data and bisect history.
- `rw/findings/magical-objects.md` — record format, edit primitives, engine validation summary.
- Prior Ghidra findings section in `items-add-primitive-cap.md` (Codex's session, dated 2026-04-29 earlier in the day).

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. In-progress dig; tight section. Most anchors are on the hero-character (HC) runtime instance and skill-controller subscriber list.

| Symbol | Anchor |
|---|---|
| Skill-controller vtables | RTTI: classes named `oCDtEntityCpntSkillController*`. The `vtable[0x10]` slot is the subscriber-registration handler. |
| HC's `+0x1c00` total-subscribers head | Re-derive: find any function that subscribes to inventory-changed events and walk to its target. |
| Per-skill-controller fixed-size arrays | Loops bounded by item count are the giveaway — runtime crash on Rule C suggests an array-bounds violation. |

Inherits broader anchors from `multiplayer-host-authority.md` (HC layout patterns), `items-add-primitive-cap.md` (validation crash points), `magical-objects.md` (record-format reference).
