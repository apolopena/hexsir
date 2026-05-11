[← Back to findings](README.md)

# Enemy spawn architecture and live-enemy control

**Status:** in-progress


Architecture finding from the 2026-05-06 dig. Identifies the
`oCDtEntityCpntEnemyController` class (RTTI, vtable, hash key, ctor RVA), maps the
universal entity factory chain that every `oCEntity` construction passes through, and
documents the unified runtime-construction model for cauldron waves observed via live
`SpawnCapture` runs. Also documents the `+0x620` self-pointer (useful for memory-alive
checks), two adjacent slots at `+0x08`/`+0x10` that hold other entity pointers (the
AI-target interpretation of these slots is tracked separately in
`rw/findings/enemy-ai.md`), and the `enemy_herd.js` mod that uses these primitives to
herd live enemies during combat. Gameplay-level rules about cauldron randomization and
the test-design constraint they imply live in `rw/docs/game-rules.md`.

The session shipped four Frida mods (`cauldron_test`, `spawn_capture` v0.8.1,
`enemy_capture` (deprecated — see §"Tried and ruled out"), `enemy_herd`) and renamed three
Ghidra functions plus one vtable. The `enemy-controller-via-ctor` hook approach was tried
and ruled out (the class-metadata-registered ctor never fires for runtime enemies).

---

## Sources

- `tools/frida/mods/spawn_capture.js` (v0.8.1) — entity-construction hook with name
  resolution, caller capture, and parent-scan utility.
- `tools/frida/mods/enemy_capture.js` — **deprecated** mod that hooks the
  EnemyController ctor at RVA `0x37bbe0` directly. Hook fires 0 times in gameplay; kept
  as a record of the dead-end approach.
- `tools/frida/mods/enemy_herd.js` — the live-enemy-control breakthrough.
- `tools/frida/mods/cauldron_test.js` — orchestrates the manual cauldron-spawn-capture
  protocol (Transporter + spawn_capture).
- Ghidra DB renames in this session:
  - `FUN_14037bbe0` → `oCDtEntityCpntEnemyController_ctor`
  - `FUN_14037bbd0` → `oCDtEntityCpntEnemyController_classId`
  - `FUN_1403be570` → `oCDtEntityCpntEnemyController_registerClass`
  - `0x140f0a6c8` (vtable) → `vtable_oCDtEntityCpntEnemyController`
- Live REPL captures from a Spider_Nightmare cauldron (chapter-load enemies) and a
  Cultist/Tentacle cauldron (runtime-spawned enemies) — provide the empirical evidence
  for the hybrid-spawn theory.

## TL;DR

- **`oCDtEntityCpntEnemyController` class fully identified.** Ctor RVA `0x37bbe0`,
  vtable RVA `0xf0a6c8`, hash key `0x1561073c`, RTTI string at `0x141353c30`. Renamed
  in Ghidra.
- **Hooking the class-metadata-registered ctor at `0x37bbe0` fires 0 times during
  gameplay.** Runtime enemies do *not* go through that function pointer. The class
  metadata exists for type-info / introspection, not as the actual instantiation path.
- **Universal factory chain** (every `oCEntity` construction):
  `oCEntity::ctor` (RVA `0x6c96f0`) ← `FUN_1406de800` (allocator: `malloc(0x640) + ctor
  + virtual init at vtable[+0x08]`) ← `FUN_1406c7a40` (trampoline) ← function-pointer
  dispatch via class-metadata table at `0x140f4cf38`. The trampoline is *only* reached
  via that table slot.
- **Unified runtime-construction model for cauldron waves** (corrects an earlier
  "hybrid pre-placed vs runtime" theory). Cauldrons do not wake pre-placed sleeping
  enemies. Activation triggers main-enemy construction at trigger time via the
  universal factory chain; some main enemies (spiders, summoners) then summon their
  own minions mid-fight via the same chain. Every captured construction —
  Snake/Summoner/Tentacle/egg/projectile/puddle — passes through `oCEntity::ctor`.
  The Spider-cauldron observation that "main spiders are absent from the capture
  buffer" is best explained by `SpawnCapture` not being armed before fight-start, not
  by the spiders being pre-existing. See "Hypothesis" §"Why-the-spider-mains-were-
  missing" below for the unverified piece.
- **Stable structural offsets on `oCEntity`** found this session:
  - `+0x620`: self-pointer. Every entity has `*(entity + 0x620) == entity`. Useful as
    a memory-alive check (passes on freed-and-reused slabs that have been
    re-constructed; fails on freed-and-zeroed memory).
  - `+0x08` and `+0x10`: hold *other* entity pointers — engagement state (last damager,
    intrusive list-node `prev`/`next`). NOT parent-spawned-by pointers.
- **Parent-traversal does not work via entity bytes.** Scanned a captured Tentacle
  entity's first 1600 bytes for any backref to its known summoner — summoner address
  was not present. The summoner→tentacle relationship lives elsewhere (likely on the
  EnemyController component, or in an external manager).
- **`enemy_herd.js` ships.** Reads `SpawnCapture._captures`, filters to entities with
  EnemyController + `+0x620` self-pointer alive, every N seconds warps all but the
  anchor to within radius units of the anchor via `vtable[+0x50] setPosition`. Verified
  working in combat on Snakes and Summoner; root-locked on Tentacles.

## Findings

### Confirmed

- **`oCDtEntityCpntEnemyController` is the enemy-marker component.** Same 6-component
  stack as the player except the controller slot is `EnemyController` instead of
  `HeroController`. Hash key `0x1561073c`. RTTI mangled name
  `.?AVoCDtEntityCpntEnemyController@@` at `0x141353c30`.
- **Ctor (RVA `0x37bbe0`) zero-inits ~0x108 bytes and installs vtable at
  `0x140f0a6c8`.** Single-arg `void ctor(this)` — no settings/parent passed. Sequential
  layout in `.text` immediately above it: a 2-instruction class-id getter
  (`mov eax, 0x1561073c; ret`) at RVA `0x37bbd0`.
- **Class registration function** (`oCDtEntityCpntEnemyController_registerClass` at RVA
  `0x3be570`) wires `&LAB_1403c1280` (a JMP thunk to `0x37bbe0`) into the component
  metadata's ctor slot at `+0x80` of a sub-struct reached via `+0x88` of the main
  metadata struct (per the decompile pattern `*(plVar2[0x11] + 0x80) = ctor_thunk`,
  where `plVar2[0x11]` indexes 17 qwords = `+0x88` from the metadata base). Same call
  also writes the literal class name string and the `0x1561073c` hash key into the
  metadata. One-time init guarded by `DAT_1414489b0`.
- **Destructor at RVA `0x37bd00`** (`FUN_14037bd00`). Re-installs the EnemyController
  vtable at `[this+0]` (typical MSVC dtor pattern for virtual-dispatch unwind), runs
  cleanup on sub-objects (calls `0x140204810` on `[this+0xc8]`), and conditionally
  invokes `operator delete` based on `param_2 & 1` (standard MSVC dtor flag — `0`
  destructs in place, `1` also frees the slab). Not load-bearing for runtime
  instrumentation; useful for completeness when re-anchoring on a new build.
- **Hook on `0x37bbe0` never fires for runtime enemies.** Verified by arming Frida
  Interceptor on the function during a Cultist cauldron fight; capture buffer ended at
  zero. Conclusion: this ctor is reached only via the class-metadata function-pointer
  slot, and the engine doesn't go through that slot for typical enemy instantiation.
- **Universal entity factory chain.** Every `oCEntity` construction passes through:
  1. `FUN_1406c7a40` (RVA `0x6c7a40`) — thin trampoline. Reached *only* via
     function-pointer dispatch from class-metadata slot at `0x140f4cf38`.
  2. `FUN_1406de800` (RVA `0x6de800`) — the allocator. Pseudocode:
     ```c
     plVar2 = malloc(0x640);
     plVar2 = FUN_1406c96f0(plVar2, settings);   // oCEntity::ctor
     (**(code **)(*plVar2 + 8))(plVar2);          // virtual init at vtable[+0x08]
     return plVar2;
     ```
  3. `FUN_1406c96f0` (RVA `0x6c96f0`) — `oCEntity::ctor`. The hook target used by
     `spawn_capture.js`. Fires for every entity construction.
- **Class-metadata registry pattern** — the table at `0x140f4ce00..0x140f4d020+`
  contains class entries with embedded class-name strings (`oIEntityRetriever` at
  `0x140f4ceb0`, `oCEntityGpnAttackSettings` at `0x140f4ce28`) and function-pointer
  slots. The trampoline `FUN_1406c7a40` lives at `0x140f4cf38` — slot `+0x80` of the
  class entry that follows `oIEntityRetriever` (matches the same `+0x80` offset that
  `oCDtEntityCpntEnemyController_registerClass` writes into). The pattern is universal:
  every class registers its ctor pointer into this table at `+0x80` of its metadata.
- **`+0x620` self-pointer.** Verified on 2 captured enemy entities (Summoner and
  Tentacle) via `findCommonParents` scan — both showed `*(entity + 0x620) == entity`.
  Useful as a cheap memory-alive check. Generalization to all `oCEntity` types
  (decorations, UI entities, anchors) is consistent with the universal-allocator
  shape but **not yet directly verified** — pending broader confirmation across the
  captured entity-type set.
- **`+0x08` and `+0x10` hold other-entity pointers, NOT parent backrefs.** Tentacle's
  `+0x08` = Geppetto Dummy entity (the player actor that was hitting it); Tentacle's
  `+0x10` = Geppetto Dummy debris piece. Summoner's `+0x08` = Snake[0]; Summoner's
  `+0x10` = Snake[1]. Confirmed by scanning 1600 bytes of the Tentacle entity for a
  backref to its known summoner — summoner address was *not* in those bytes. The
  semantic of these slots is unsettled: the Tentacle observation fits an
  AI-target/current-focus reading, the Summoner observation does not (cultists do not
  target their own snakes). Promoted to its own doc:
  `rw/findings/enemy-ai.md` — first dig is verifying whether the slot is the AI-target
  field, a multi-purpose pointer, or a different field entirely.
- **`vtable[+0x50] setPosition` works on most enemies but not on Tentacles.** Snakes
  and Summoner respond to the warp; Tentacles are root-locked (engine likely re-asserts
  their root transform every frame, or the vtable slot is a no-op for tentacle-class
  entities).
- **InitArg name resolution mirrors the encyclopedia walker pattern.** Each entity's
  `initArg` (param_2 of `oCEntity::ctor`) is an `oCEntitySettingsResource*`. Display
  name lives at `+0x08` (char*); length at `+0x10` (u32). Use `readUtf8String(len)`.
  Stable across the entity's lifetime; survives entity destruction (the settings
  template lives in the asset cache, not the entity slab).
- **Unified runtime-construction model for cauldron waves.** All cauldron-wave
  enemies are constructed at activation time via the universal factory chain
  (`oCEntity::ctor` at RVA `0x6c96f0`). Main enemies phase in when the cauldron
  fires; some main-enemy templates (spider mothers, cultist summoners) then summon
  their own minions mid-fight via the same factory chain. Mid-fight player-ability
  casts (Geppetto Cogsbomb, Geppetto Dummy) also go through this chain. Effect /
  projectile / puddle entities (eggs, line attacks, poison puddles) are also always
  runtime-constructed via this chain. Confirmed across both Spider Nightmare and
  Cultist/Summoner cauldron runs.

  **Cauldron content is randomized per chapter run** — the wave family (cultist,
  spider, ghoul, pig, ...) is drawn from a pool whose size and exact composition is
  unmeasured. Live tests must be type-agnostic. Full rules and rationale in
  `rw/docs/game-rules.md` §"Cauldrons and waves."

### Hypothesis (mapped, not fully verified)

- **The "spawned by" / parent relationship lives on the EnemyController component, not
  the entity wrapper.** Components are separately allocated objects pointed at from the
  entity's hashmap. Walking the entity to its EnemyController and scanning the
  component's bytes is the next dig.
- **A global per-instance entity registry exists somewhere.** The class metadata table
  is just type-info; finding the *instance* registry would let us enumerate all live
  enemies without spawn capture. Best path: look at scene-context iteration in
  `session_finalize_and_save` — that walks live entities for serialization and may
  expose the registry.
- **Why the spider-cauldron mains were missing from the capture buffer.** In a
  prior Spider Nightmare cauldron run, the 4 main spiders did not appear in
  `SpawnCapture._captures` even though the cauldron's secondary content (eggs,
  projectiles, puddles) did. The current best explanation, consistent with the
  unified runtime-construction model, is that `SpawnCapture` was armed *after* the
  main spiders had already phased in — they were constructed, the construction
  fired before our hook was active, and the post-arm capture only saw mid-fight
  minion-summons. To verify: re-run a Spider cauldron with `SpawnCapture` armed
  before approaching the cauldron, observe whether the main spiders appear at
  cauldron-fire time. Until verified, the alternate hypothesis ("spider mains are
  pre-placed and woken, not constructed") is not strictly excluded — it's just less
  consistent with the rest of the model.

## Tried and ruled out

- **Hooking `oCDtEntityCpntEnemyController_ctor` at RVA `0x37bbe0` directly.** Single
  fight, 0 captures. The class-metadata-registered ctor function pointer is never
  invoked by the engine for normal enemy construction. `enemy_capture.js` is
  consequently a dead-end mod; kept on disk for reference but should not be loaded.
- **Parent-traversal via entity-byte scan.** Scanned 1600 bytes of a runtime-spawned
  Tentacle for any backref to its summoner; summoner pointer not present. The
  back-pointer (if it exists) lives on the component, not the entity.
- **Heap scan for `oCEntity` vtable to enumerate all entities.** Pre-existing
  ruled-out from prior session — crashed the game.

## Template name catalog (observed in 2026-05-06 captures)

Names are stable across sessions (driven by asset files). Addresses are not — captured
addresses are session-specific.

### Real-time-spawned enemies (full 6 components: EnemyController + 5)

- `Elite_Snake_Nightmare` (Cultist cauldron — eels)
- `Elite_Cultist_Summoner` (Cultist cauldron — boss tier)
- `Cultist_Summoner_Summoned_Tentacle` (summoned mid-fight, root-locked)

### Real-time spawn projectiles / effects (single-component or partial-stack)

- Spider Nightmare family: `Spider_Nightmare_Egg`, `Spider_Nightmare_Egg_Spawner_Projectile`,
  `Spider_Nightmare_Poison_Puddle`, `Spider_Nightmare_Giant_Poison_Projectile`,
  `Spider_Nightmare_Web_Projectile`
- Cultist family: `Cultist_Summoner_Line_Attack`
- Generic enemy effects: `Enemy_Nightmare_Puddle` (4 captured per fight, suggests
  one-per-elite-enemy; has Network component)
- Player ability spawns: `Hero_Geppetto_Cogsbomb`, `Hero_Geppetto_Dummy`,
  `Hero_Geppetto_Dummy_Interaction`, `Geppetto_Dummy_Scrap_Arm/Head/Wood_C/Wood_D`
  - Note: `Hero_Geppetto_Dummy` carries **5** components (CharacterController,
    RegisteredEntitiesHolder, ModifierHolder, RemoteDamageOwner, Network) — the
    enemy stack minus `EnemyController`. Distinguishes player-summoned actors from
    enemies: same character-AI machinery, but the EnemyController slot is what
    flips the actor onto the hostile side. Useful pattern for "is this a player
    ally or an enemy?" classification.

### Cauldron arena scaffolding

- `Activity_Arena_Barrier_Model` (the magical fence around the cauldron arena)
- `Activity_Banner_Leprechaun_Cauldron` (the cauldron's visual flag)
- `Nightmare_Arena_Fence_Light` (lighting on the arena perimeter)

### Decorations / destructibles (no enemy components)

- Candle family: `Candle_Small`, `Candle_Tall`, `Destructible_Candle_Small`,
  `Destructible_Candle_Tall`, `Random_Destructible_Candle_Spawner`
- Pumpkin family: `Pumpkin_A`/`B`/`C`/`D`/`E`/`F`, `Pumpkin_base_B`,
  `Pumpkin_Patch_A`/`B`/`C`/`D`, `Pumpkin_Chunk_B2`/`C2`,
  `Destructible_Pumpkin_Patch_A`/`B`/`C`/`D`
- Grass / vegetation: `Destructible_Grass_Small_A`/`B`/`C`,
  `Random_Destructible_Grass_Small_Spawner`,
  `Random_Destructible_Grass_Red_Big_Biggest_Spawner`,
  `Destructible_Grass_Red_Biggest_A`, `Grass_Big_A_Destroyed`/`B_Destroyed`/`C_Destroyed`,
  `Grass_Big_B`, `Grass_Spawner_Big_Broken_A`/`C`, `TallGrass_Big`,
  `Herbs_Pampa_Green_Small`/`Medium`/`Big`, `Reed_Composition_Medium`
- Misc: `Pebbles_2x2`, `Pebbles_4x4`, `Destructible_Torch_A`,
  `Lantern_WhiteLadies_Broken_Light`

### UI entities (yes, UI elements are also `oCEntity`)

- `Life_Bar_NPC_Small`, `Life_Bar_NPC_Common`, `Life_Bar_NPC_Large`,
  `Life_Bar_Geppetto_Dummy`
- `Skill_Description`, `Skill_Miniature`, `Skill_Menu`, `Status_Ui`, `Tips_Ui`
- `Hit_Feedback`, `Notification_UI_Model`, `Notification_UI_Boss`,
  `Escape_Menu_Button`, `In_Game_Escape_PC_Menu`

### Spawn anchors (no model, drives engine state)

- `[Entity spawner] NoModel` — generic anchor entity (multiple instances per chapter)
- `[Entity spawner] NoModel+2Cpnt` — the chapter hourglass (from prior session)
- `[Entity spawner] Fireflies_2` — ambient effect anchor

## Live-enemy control: the `enemy_herd.js` mod

Built on the primitives discovered this session:

1. **Roster source**: `RW.SpawnCapture._captures` (entities captured during the fight).
2. **Enemy filter**: walk component hashmap (`+0x5e8`/`+0x5f0`/`+0x5f8`/`+0x600`) and
   match component RTTI substring `"EnemyController"`.
3. **Liveness check**: `*(entity + 0x620) == entity`.
4. **Warp primitive**: `vtable[+0x50] setPosition(entity, &xyz_buf)`.
5. **Loop**: `setInterval(intervalSec * 1000, tick)` where each tick filters live
   roster, picks `roster[0]` as anchor, warps every other entity to anchor + uniform-
   disc XZ scatter scaled by `radius`, preserving anchor's Y.
6. **Auto-stop**: when roster is empty after liveness filter, clear interval.

Caveats observed in live use:
- Chapter-load-pre-existing enemies don't appear in the roster unless `SpawnCapture`
  was armed *before* chapter-load (currently impractical without a chapter-transition
  hook).
- Tentacles are root-locked; the warp call succeeds but the position doesn't take.
- `+0x620` is a memory-alive check, not a gameplay-alive check. A killed enemy whose
  memory has not been reused will still pass the check (corpse). The script keeps
  herding around a dead anchor until its memory is freed.

## Open questions

1. **Where is the parent-spawned-by pointer encoded?** Not in the entity's first 1600
   bytes. Likely on the EnemyController component. Next: walk entity's component
   hashmap → controller pointer → scan controller bytes for parent backref.
2. **Why are Tentacles root-locked?** Specific to summon-tentacle entities. Either
   their `setPosition` vtable slot is a different index, or the engine re-asserts
   root transform every frame from a parent's transform. Worth a probe: read
   `+0x324` on a Tentacle immediately after our warp call — did the field even take?
3. **Is there a global per-instance entity registry?** Open dig (wishlist item from
   prior session). If found, we can enumerate path-A enemies without chapter-load
   capture.
4. **Why does the class metadata `+0x80` ctor slot exist if the engine doesn't use it
   for runtime enemy creation?** It's used somewhere — likely for prototype/template
   instantiation at startup, or via reflection-style code paths we haven't surfaced.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template.

### Anchors

| Symbol | Anchor strategy |
|---|---|
| `oCDtEntityCpntEnemyController` class | Search RTTI string `.?AVoCDtEntityCpntEnemyController@@` → TypeDescriptor → COL → vtable. |
| `oCDtEntityCpntEnemyController_ctor` (RVA `0x37bbe0`) | Search byte pattern of the class hash key `3c 07 61 15` (= `0x1561073c` little-endian); the ctor function lives sequentially after the 2-instruction class-id getter that contains it. |
| `oCDtEntityCpntEnemyController_classId` (RVA `0x37bbd0`) | Same byte search; the *first* match in code is this getter (`mov eax, 0x1561073c; ret`). |
| `oCDtEntityCpntEnemyController_registerClass` (RVA `0x3be570`) | Same byte search; the registration function references the hash key *twice*. |
| EnemyController destructor (RVA `0x37bd00`) | Among xrefs to the EnemyController vtable address `0x140f0a6c8`: two `LEA` xref pairs exist (one inside the ctor, one inside the dtor). The dtor's pair lives at `0x14037bd11 / 0x14037bd18`; the function start is the closest preceding `MOV qword ptr [RSP+8], RCX` prologue (RVA `0x37bd00`). |
| EnemyController vtable (RVA `0xf0a6c8`) | Located via the COL chain from the RTTI string. |
| Component hashmap layout on `oCEntity` (`+0x5e8/+0x5f0/+0x5f8/+0x600`) | See `rw/findings/transporter-placement-primitive.md` (parent doc for spawn_capture). |
| `+0x620` self-pointer | Empirical — verify on a known-good entity by reading `*(entity + 0x620) == entity`. Survives recompile unless struct shape changes. |
| `+0x324` position field | Documented elsewhere; same as `oCEntity` position offset. |
| `vtable[+0x50] setPosition` | Documented elsewhere; same slot as Transporter uses. |
| Universal allocator `FUN_1406de800` | Search byte pattern of malloc-size constant `40 06 00 00` (= `0x640`) inside `_malloc_base` callers; only 1-2 functions in the binary allocate this size + immediately call into a 200-field zero-init function. |
| Class-metadata table at `0x140f4ce00..0x140f4d020+` | Anchor: embedded class-name strings (`oIEntityRetriever`, `oCEntityGpnAttackSettings`). Search those strings in `.rdata` and the table is the surrounding region. |

### Re-anchoring quick recipe

1. Search RTTI `.?AVoCDtEntityCpntEnemyController@@` → record vtable RVA.
2. Search bytes `3c 07 61 15` → record the three RVAs above (classId getter, ctor,
   registerClass).
3. Verify the universal factory chain:
   - Find callers of `oCEntity::ctor` (only one expected — the universal allocator).
   - Find callers of that allocator (only one expected — the trampoline).
   - Find data-references to the trampoline (one expected — class-metadata slot).
4. Verify `+0x620` self-pointer empirically on the player entity at runtime.

## Cross-references

- `rw/findings/transporter-placement-primitive.md` — parent doc for spawn_capture and
  the placement primitive (vtable[+0x50] setPosition).
- `rw/findings/enemy-ai.md` — the AI-target / focus interpretation of the
  `+0x08`/`+0x10` slots and the redirect-AI-to-fight-each-other question.
- `rw/docs/game-rules.md` §"Cauldrons and waves" — the gameplay-level rules
  (cauldron randomization, test-design constraint) implied by the unified
  runtime-construction model.
- `rw/findings/STATUS.md` — manifest of all findings.
- `tools/frida/CODE_STANDARDS.md` — Frida script conventions (followed by all four
  mods shipped this session).
- `rw/docs/wishlist.md` — open digs including "find global per-instance entity
  registry" and "extend SpawnCapture across chapter-load window."
