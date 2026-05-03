[← Back to findings](README.md)

# RNG behavior — Ravenswatch per-event RNG
**Status:** confirmed


## Sources

- pre-policy — written before the Sources header was mandatory.

## What this doc is — for non-experts

**Plain-English summary.** Ravenswatch picks talents, rarities, and other "random" outcomes from one shared random stream (a single 32-bit number that gets stepped each time something rolls). We located that number in memory, learned how to overwrite it with Frida, and verified that doing so makes the talent picker pick the same talents and rarities every time you trigger it.

**Rules of thumb when working with this finding:**

1. **There is one seed.** No per-talent seeds, no per-rarity seeds. Every roll comes from the same chain. Force it once at the right moment and the entire downstream cascade is deterministic.
2. **The talent picker writes rarity into TWO places.** A per-controller "tier byte" (one per controller in the hero's pool) AND a per-slot u32 (10 entries inside the talent-record body at offset `+0x35`). The picker stamps from one or the other depending on whether the slot's loaded talent is valid for the active hero — both must be set if you want consistent rarity across all picker fires (see `talent-records.md`).
3. **Hooking the leaf PCG function is the WRONG hook point.** The actual gameplay rolls inline the PCG step, they don't call the leaf. Hook at the per-feature picker function's entry instead.
4. **GS-relative TLS access from Frida shims is unreliable.** Use `NtQueryInformationThread` syscall to get the TEB, or read R9 from the function's own context after the function has resolved TLS itself. Don't trust your shim's `mov rax, gs:[0x58]`.
5. **Anything that touches the TLS slot between picker fires shifts the chain.** Combat entity spawns, AI, particle effects all step the seed. So "force the seed at picker entry" works because we always overwrite right before the picker's first read; you can't pre-seed once and expect determinism for picker calls minutes later.

**Skip to the deeper sections if you're implementing or extending forcing.**

## Single TLS-backed PCG stream drives everything

Per-event gameplay RNG (talent picker, item picker, chest rewards, shop offers, almost certainly tier/rarity rolls and similar gameplay decisions) all read and step a **single 32-bit seed** stored in thread-local storage at offset `0xff3c` of the main module's static TLS data block.

Access pattern (verified on `SkillController_roll_proposed_skills` at `image+0x39c300`):

```
mov rax, gs:[0x58]             ; TLS array pointer (TEB+0x58)
mov rcx, [rax]                  ; module 0 TLS data
mov eax, [rcx + 0xff3c]         ; read seed
; ... PCG step (inlined, see below) ...
mov [rcx + 0xff3c], eax         ; write back stepped seed
```

Constants are the standard Lemire/PCG-Hash-style mix: `0x2c9277b5`, `0xac564b05`, `0x108ef2d9`. Each "step" produces a new value AND advances the seed. There is no per-event seed allocation — every consumer pulls from this one slot.

## A seed is a stream, not a per-roll value

Common misconception: "the picker shows 3 talents, so there must be 3 separate seeds." Wrong. There is one seed at any moment; the PCG steps it forward to produce a sequence:

```
S in TLS at function entry
step 1 → S₁   pick #1 from picker pool of size N         (idx = S₁ % N)
step 2 → S₂   pick #2 from picker pool of size N-1       (idx = S₂ % (N-1))
step 3 → S₃   pick #3 from picker pool of size N-2       (idx = S₃ % (N-2))
step 4 → S₄   tier of pick #1
step 5 → S₅   tier of pick #2
step 6 → S₆   tier of pick #3
```

Same `S` at entry → identical `S₁..S₆` chain → identical 3 picks AND identical 3 tier rolls. This is why a single forced seed locks the entire talent picker outcome — selection and rarities are on the same deterministic chain.

The picker's loop performs sample-without-replacement via Fisher-Yates partial: after each pick, swap the chosen index with the last picker-pool slot and shrink the picker pool by one. Tier rolls happen after the selection loop, in `FUN_1402e7b80` / `FUN_1402e7a40`, and continue stepping the same TLS seed.

## Determinism scope

A given seed at entry produces a given proposal **as long as the input picker-pool composition is identical**. Picker-pool composition depends on:

- The hero (filters which talents are eligible).
- Currently held talents (`param_1 + 0xff0`) — these are filtered out of the pool.
- The previous proposal passed in via `param_3` (R8 in win64 ABI) — these are filtered out during a reroll. **Different on each reroll**, so naturally same seed gives different picks across rerolls of the same level-up.
- Modifier stats like "Extra skill choice" (hash `0x1a7a3166`) controlling how many to draw.

For seed→proposal to be bijective (same seed always produces the same picks), `param_3` must be neutralized. The Frida harness does this by zeroing R8 on entry (`forceFresh` mode).

## Why hooking `pcg_step_thread_local_seed` (the leaf function) doesn't work

The PCG step in `SkillController_roll_proposed_skills` is **inlined** — it does not call the leaf function `pcg_step_thread_local_seed` (`image+0x4ffb70`). Hooking the leaf catches a different category of consumers (the master chapter seed, some entity-component seed inits) but misses gameplay-event RNG entirely. There are 30+ inline PCG sites in the binary, each operating on the same TLS slot.

This is the root cause of the long-standing "forced seed in INI doesn't make runs deterministic" observation: the Forced Seed UInt feeds the master-seed path, but per-event picks bypass that path and run the inlined PCG against the always-mutating TLS slot.

## Forcing strategy that works

Hook the picker function's entry. Get the calling thread's TEB via `NtQueryInformationThread` (the syscall path; user-mode GS register is unreliable inside Frida NativeFunction shims). Walk `TEB+0x58 → array → array[0] = TLS data`. Write desired seed to `TLS data + 0xff3c`. Function executes its own TLS resolution into R9 and reads our seed.

For a verifiable smoke test, also null `param_3` (R8) so consecutive rerolls in the same level-up see the same picker pool and produce identical picks across rerolls.

Verified: `forceFresh(0xDEADBEEF)` on `SkillController_roll_proposed_skills` produces identical talents and identical rarities across many in-game rerolls.

## Implications for offline seed solving

Because the entire chain is deterministic from one 32-bit seed and the algorithm is fully understood (PCG + Fisher-Yates partial), brute-forcing 2³¹ seeds offline takes seconds on a CPU. To find a seed that produces a target proposal:

1. Capture the candidate picker pool at runtime (Frida hook reads `local_168` after picker-pool construction, before the RNG loop).
2. Mirror the inline PCG and Fisher-Yates in a script.
3. Iterate seeds, find one whose output matches the target.
4. Replay via `force(target_seed)` in the Frida harness.

Tier-rarity targeting requires also mirroring `FUN_1402e7b80` / `FUN_1402e7a40` (not yet decompiled).

### Solver and CLI built (2026-05-02)

The above plan is implemented:

- `tools/rerw-src/lib/picker_seed_solver.py` — pure-Python PCG step + partial Fisher-Yates simulator. `simulate(seed, pool, num_picks)` for forward simulation; `find_seeds(pool, num_picks, target, ...)` for brute-force.
- `tools/frida/rw_lab.js` — `dumpTalentPoolNext()` REPL command writes the unpruned pool array to the diag log on the next picker entry, including 256 bytes of inner-deref so talent GUIDs can be matched against the hero registry.
- `rerw experimental find-talent-seeds` — parses the diag log, picks the requested `[#N]` block, maps pool[i] -> talent name, brute-forces seeds whose simulated output matches the target talent set, prints matches.

Validation: the algorithm matches the engine exactly on the simplest case (slot=4 ult picker, 2-of-2 pool). Verified `0x14e61463` -> `top=WildWaltz, bottom=BlackRoses` against an in-game forced-seed run. Cross-session determinism (same seed, same target, separate game launches) is the next test — see `.ai/scratch/test-plan-cross-session-seeds-20260502.md`.

## Other consumers of TLS+0xff3c (partial list)

The same TLS slot is read or stepped by many other code paths. Empirically observed during combat (via earlier diagnostic Frida hook on the leaf):

- Per-entity-component random seed inits: `oCEntityCpntSelector`, `oCEntityCpntRangedRandom`, `oCEntityCpntBasicRandom` (= `FUN_140767bc0`), `oCEntityCpntWeightedRandom`-shaped sites.
- Entity construction paths (`entity_init_from_config_block` chain) fire seed-init for spawned components.

This means the seed in TLS drifts continuously during play. Forcing the seed in `SkillController_roll_proposed_skills` only locks that one function; other RNG-using subsystems continue to advance the seed in between calls. For our talent-picker forcing this is fine because the function reads the seed AT entry — whatever was there from prior consumers gets overwritten by our forced value before the picker's first PCG step.

## Caveats

- The seed slot belongs to dynamic TLS (the function calls `__dyn_tls_on_demand_init` on the very first per-thread access). On the first call ever on a thread, the TLS data block may be too small to access offset `0xff3c` — reads/writes from outside (e.g., Frida) will fault. After that first init, subsequent calls work. In practice the talent picker is reached well after first init, so the harness sees a usable slot every time.
- User-mode GS register access from a Frida `NativeFunction`-allocated shim does NOT preserve the calling thread's GS base. Even `mov rax, gs:[0x30]` faults in that context. The TEB must be obtained via a kernel-thunked syscall (`NtQueryInformationThread`) or via the function's own context (e.g., reading R9 inside an Interceptor at an instruction where the function has already loaded the TLS pointer).
- Hooking inside the picker's tight inline-PCG loop (e.g., at the `IMUL` instruction at `image+0x39c774`) crashed the game during testing — Frida's relocator did not handle the IMUL with `[R12 + R9*1 + 4]` SIB addressing inside that loop. Hook at function entry only.

## Dual-storage tier model (verified 2026-05-02)

Talent-pick rarity is stored TWICE in the save and the picker reads either one depending on context:

1. **Per-controller tier byte** in tag=0x10 records (28 entries per hero, one per controller in the hero's pool). Offset: `[GUID_offset + 17]` per `talent-records.md`. The picker reads this when the slot has a valid loaded talent (the runtime sync function `SkillController_sync_slot_tiers_from_talents` at `image+0x39bc80` copies talent.tier → slot.tier when slot's pointer is non-null).
2. **Per-slot u32 tier array** in the tag=0x12 talent record body, at offset `+0x35`. Ten u32 entries `[0..4]` (0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker / uninitialized). The picker reads this when the slot's loaded talent is null (e.g., after a hero swap where the saved talent IDs don't match the active hero's pool).

**Empirical confirmation:** With only the tag=0x10 bytes set to legendary, level 1 and 2 pickers showed legendary (slots had valid sync'd talents), but level 4 picker showed common (slot had no valid loaded talent → picker fell back to the per-slot u32 array which still held the original Geppetto run's common value). After also setting all 10 per-slot u32s to legendary via `rerw write savefile all-talent-rarities legendary`, every picker showed legendary.

**Sync function decompile:** `image+0x39bc80` iterates 10 slots at `param_1+0xff0..+0x1110` (stride `0x20`); for each non-null talent pointer, reads talent's tier byte at `+0x68` of the talent record, writes to `*(param_1+0x1d48) + 0x18 + slot*4` (the runtime slot.tier array, mirrored to the on-disk u32 array at talent-record `+0x35`).

**Tier-roll function** (`talent_roll_tier_weighted` at `image+0x2e7b80`) is invoked only when slot.tier == 4 at picker time — the engine treats 4 as the "uninitialized, roll fresh" sentinel. The roll calls `uniform_float_in_range_pcg` (`image+0x4ffce0`), which inlines the same TLS+0xff3c PCG. Weights are biased by the "Skill better quality chance" modifier (hash `0x1709d22b`, read 3 times in a loop in the picker).

## References

- Function: `SkillController_roll_proposed_skills` at `image+0x39c300` (renamed from `FUN_14039c300`; previously misnamed `read_extra_skill_choice_modifier`).
- Frida harness: `tools/frida/rw_lab.js`.
- Related Ghidra renames committed in this session: `SkillController_state_dispatch`, `SkillController_repropose_skills`, `SkillController_persist_proposed_list`, `is_skill_pick_free`, `oCDtEntityCpntSkillController_typedesc_init`, `oCDtEntityCpntSandmanMenuUiController_typedesc_init`, `sandman_purchase_commit`, `fire_named_event`, `register_named_event_table`, `register_named_event`, `register_modifier_stat`, `register_gameplay_modifier_stats`, `subscribe_run_tracker_to_named_events`, `vector_move_assign`, `broadcast_to_handler_list`, `invoke_callable_and_cleanup`, `entity_init_from_config_block`.
