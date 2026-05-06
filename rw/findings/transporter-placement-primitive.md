# Transporter — placement primitive on encyclopedia map landmarks

**Status:** in-progress
**Date:** 2026-05-06
**Author:** session continuation from `spawn-at-coord-recipe.md` and `chapter-map-and-boss-spawn-architecture.md`

## Sources

- Live Frida probes against `Ravenswatch.exe` (chapter 1, safe arena starting state)
- Ghidra MCP decompile of:
  - `FUN_140186740` — `oCEntitySceneContext` class registrar
  - `FUN_1406e5a40` — `oCEntitySceneContext` constructor (1213 bytes)
  - `FUN_1406ca590` — component-map remove function on `oCEntity`
  - `oIEntityCpnt_onAttach_commitToParent`
  - `FUN_140180820` — `oIGameSceneContext` parent-class registrar
- `boss_rush.js` `dumpEncyclopedia()` walker
- User-driven visual confirmation in-game (Cauldron, Boss Spawner, Teleporter, NoModel+2Cpnt)

## TL;DR

The encyclopedia entry `+0x48` is a back-pointer to ONE live `oCEntity*` per asset. Calling that entity's `vtable[+0x50]` (`oCEntity::setPosition` @ RVA `0x6ca7f0`) writes its position field at `+0x324` and broadcasts to the renderer, camera, and minimap. Combined with a 500ms tick to defeat the engine's per-frame transform reset, this gives **fully functional placement of any cached map landmark** (Cauldron, Teleporter, etc.) at arbitrary world coords. Plus a player-side warp using the same primitive (one-shot, no tick — player movement controller respects single writes).

Shipped as `mods/powers/Transporter.js` with `warpEntity(name, x, y, z, roundtrip?)` and `warpPlayer(x, y, z, roundtrip?)`.

## Confirmed (verified visually with the user in-game)

### oCEntity component hashmap layout

`FUN_1406ca590` is the Swiss-Tables remove function on the entity's component map. Decompile reveals the hashmap fields on `oCEntity`:

```
+0x5e8  ctrl_bytes_ptr   (Swiss-Tables control-byte array)
+0x5f0  values_ptr       (16-byte entries)
+0x5f8  count            (size_t)
+0x600  capacity_mask    (size_t)
+0x618  tombstone_count
```

Each value entry is **16 bytes**: `{ uint32 hash_key; uint32 pad; void* component_ptr }`. Hash uses MurmurHash-style multiplication by `0xde5fb9d2630458e9`.

**Verified live** — walking the player's component map yields 6 named components:

| key (hash) | RTTI |
|---|---|
| `0x1560fd89` | `oCDtEntityCpntCharacterController` |
| `0x1a9a307a` | `RegisteredEntitiesHolderEntityCpnt` |
| `0x15a04b1a` | `oCEntityCpntModifierHolder` |
| `0x170176e5` | `oCDtEntityCpntRemoteDamageOwner` |
| `0x155aac59` | `oCDtEntityCpntHeroController` |
| `0x154fce5c` | `oCEntityCpntNetwork` |

### oCEntitySceneContext is fully decoded

- Class registrar at `FUN_140186740` (image @ `0x140186740`).
- Type ID: `0xe8bb363`. Type-desc storage: `DAT_1414472f8`. Class name string: `"oCEntitySceneContext"`. Registered class size: `0x4f8`. Vtable RVA: `0xf4fa10`.
- Constructor `FUN_1406e5a40` is multi-inherit with embedded sub-objects:
  - `+0x00` primary vtable (`oIGameSceneContext` parent then `oCEntitySceneContext` overrides).
  - `+0xa0` embedded `oCEntitySpawner` (sub-vtable RVA `0xee0e60`).
  - `+0x128, +0x178, +0x1c8, +0x218, +0x268, +0x2b8` six `oCCallScheduleStep` sub-objects.
- Final ctor init: `+0x4e8 (dword) = capacity 0x20`, `+0x4f0 = ptr to 0x20-byte allocation` (Swiss-Tables ctrl bytes for the runtime asset cache).

### Encyclopedia entry → live entity instance

Each `dumpEncyclopedia()` entry is an `oCEntitySettingsResource` at heap addr `value`. Layout:

```
+0x00  vtable
+0x08  char* display_name
+0x10  u32 length
+0x48  oCEntity* (live in-world instance — the placement-primitive target)
+0x50  same oCEntity* (mirror or alternate ref — same value as +0x48 in observed entries)
```

Visiting the in-world instance: `entity->vtable[+0x50]` is `oCEntity::setPosition` (RVA `0x6ca7f0`). Calling it writes `entity+0x324` (the canonical `Vec3` position field) and broadcasts to subscribers.

### Placement primitive — visually confirmed

- **Cauldron** (`[Entity spawner] Cauldron`) — moved from its original `(101, 0, -56)` to within 3 units of the player (-137, 14.5, 90); the cauldron prop visibly relocated. Restored on roundtrip expiry. **First-time setup needed a 500ms tick loop** — single-shot setPosition didn't visibly move the prop (engine resets transform per frame).
- **Boss Spawner** (`[Entity spawner] Boss Spawner` @ `(-382, 0, -198)`) — moved to player; a visible hourglass-shaped prop relocated. **NOT the chapter timer hourglass** (see "Hourglass identity" below); appears to be an arena decoration / sundial at the boss arena.
- **Teleporter** (`[Entity spawner] Teleporter`) — moved to player exact coords; first move only triggered a minimap-discovery (no visible model). After discovery, subsequent moves of the same entity carried the visible portal model. The user clicked the moved teleporter on the minimap and was teleported to its current world position — confirms **the teleporter's destination is its own runtime position**, not a fixed target. Moving the teleporter relocates its endpoint.

### Discovery → visibility state transition

Some entities have visible models that only attach after the proximity-discovery trigger fires. First setPosition near the player triggers discovery (minimap pin appears, model hooks in). Subsequent setPosition calls then visibly relocate the entity. Best documented with the Teleporter; not yet generalized.

### Hourglass identity

`[Entity spawner] NoModel+2Cpnt` IS the chapter hourglass — verified by user observation when moved to the player position. Position varies per run (procgen-placed near Sandman in starting arena, fixed *relative* to other arena features). The display name "NoModel+2Cpnt" is the engine's auto-label for "no base model + 2 attached components" (the hourglass model + day/night cycle logic).

Mechanics the hourglass drives:
- Flips when player leaves the starting arena → time tick begins.
- If player kills the chapter boss before time runs out, the hourglass spawns reward bags (`Hourglass_Drop_Bag_*.entity.ot`) in the next chapter.
- `Day_Night_Cycle_Manager.entity.ot` + `BossTimerPin.entity.ot` are related runtime components.

Moving it via `Transporter.warpEntity` is not blocked, but be aware of these progression side effects before testing.

### Pre-spawned enemies (your hypothesis, confirmed)

Enemies are pre-spawned and exist as live `oCEntity` instances on the heap before the player arrives at a camp. Confirmed by warping the player into a pig camp at `(-0.84, 6, 5.05)` — pigs immediately attacked and killed the player (pre-spawned, AI-active, hostile). No new entries appear in the encyclopedia when the player approaches a camp; the assets were already streamed in.

## Hypothesis (mapped, not fully verified)

- **Visible vs invisible anchors.** "[Entity spawner] X" entries split into two groups: (a) self-rendering (Cauldron, Boss-Spawner-prop, Teleporter, presumably Den Entrance / Entrance) where moving the `+0x48` entity visibly relocates the model; (b) invisible spawn anchors (NoModel, NoModel+2Cpnt, camps) where moving the entity is silent. The visible group has a render component on the same entity; the invisible group's "thing on screen" (pigs, portal swirl) is a separate child entity placed relative to the anchor. Not all classes verified — Den Entrance and Entrance untested.
- **Streaming asset cache, not POI list.** The encyclopedia is keyed by asset path, so multiple physical instances of the same asset (e.g., the 3-4 teleporters per chapter map) share ONE entry. The `+0x48` back-ref points at one specific instance. Other instances exist as separate `oCEntity*` somewhere we haven't located.
- **`RegisteredEntitiesHolderEntityCpnt` is not the global registry.** The component looks like a per-entity registration handle (5 sub-component slots, each linked to per-class-Settings metadata). The actual global "all live entities" registry is still unfound.

## Tried and ruled out

- **`oCEntitySceneContext +0x520` is NOT the live entity registry** (prior session's hypothesis). Walking it yielded `Heroes\Carmilla\animation\carmilla_defensive_default_out.fbx1` and bounding-box-style float data — it's a loaded prefab/animation cache. The prior handoff's priority-1 task was misnamed.
- **Spawner-tree walk from ESC's embedded spawner** — finds 9 unique `oCEntity*` across 11 spawners, but most have 0 components and `(0, 0, 0)` positions (proxy / sentinel slots). 2 entities at `+0xc0/+0xc8` of the root spawner have valid positions but no components — invisible engine bookkeeping. Not the entity registry.
- **Heap scan for `oCEntity` vtable** — `Memory.scanSync` against ranges in the player's heap address space took >2 minutes and crashed the game on the first attempt. Filtered re-runs (size-capped ranges) produced 0 results due to a bad address-range filter. Approach is dangerous; abandoned.
- **Approach-the-camp triggers spawning** — false. Encyclopedia count stayed at 18 entries before/after teleporting the player to a pig camp. Pigs were already there.

## Open questions

- **Where is the global per-instance entity registry?** We can enumerate cached assets but not all instances of those assets. Candidate paths: hook entity creation (e.g., extend `boss_rush.captureResolutions` to capture every `oCEntity*` allocated at chapter load), find a different scene-context that holds live entities, or trace the minimap UI's source data.
- **Do invisible-anchor entities get a visible model after their proximity-discovery fires?** Camps don't seem to (the visible thing is the spawned pigs). But Teleporter does (the portal model attaches post-discovery). Pattern to formalize.
- **Camp anchor + spawn-children mechanic.** If we move a camp anchor near the player, do the spawn-children events fire near the player or at the anchor's original location? Untested. Would let us "summon enemies on demand" if it works.
- **`Boss Spawner` semantics.** Visible hourglass-shaped prop at the boss arena. NOT the chapter-timer hourglass (that's NoModel+2Cpnt at the safe area). What is the Boss Spawner prop, and does moving it affect boss-spawn logic? User declined further testing on it (off-limits along with the hourglass).
- **Den Entrance / Entrance / NoModel / NoModel+2Cpnt-look-alikes** untested for placement-primitive behavior.

## Spawn capture (added later in session)

After Transporter shipped, the user asked: **what does the cauldron actually spawn, and where?** Built `tools/frida/mods/spawn_capture.js` to answer.

### Hook-target dig

Three candidate hook targets investigated via Ghidra:

- **`FUN_1406db390` ("addSpawnedEntity")** — first attempt. Captured 393 events for one cauldron fight; user observed "looks like movement data, not 30 enemies." Decompile revealed the function is actually a **listener-registration helper**: it appends `param_2` to a linked list on `param_1`, wires two callback pairs (`+0x40/+0x48` and `+0x58/+0x60`) with prior-cleanup, then tail-calls `vtable[+0x28]` of the node. So one call = one listener registration, not one entity. ~13 listeners per entity × 30 enemies ≈ 390. Wrong granularity.

- **`oCEntitySpawner_spawnEntityFromBoundTransform` (RVA `0x6eef40`)** — second attempt. Decompile shows it builds an `oCEntitySpawnData` from spawner's bound transform (`+0xd4/+0xdc/+0xe4`), allocates a pool node via `oCSpawnablePool_allocateNode`, calls `vtable[+0x18]` on a sub-object at `param_1[0x21]` to instantiate. Cached at `spawner+0x160`. Hooked it: **0 captures during a cauldron fight**. Cauldron uses a different spawn path (the `+0x160` cache early-returns after the first spawn — incompatible with multi-wave behavior).

- **`oCEntity` constructor (RVA `0x6c96f0`)** — third attempt and the right one. Found via xrefs to `oCEntity` vtable (`0x140f4cc40`). Sets parent `oCSpawnable::vftable` then overrides with `oCEntity::vftable`, initializes ~200 fields. Every `oCEntity` instance creation chains through here exactly once.

### Confirmed (verified live with the user)

- **Hook fires once per entity creation across all subclasses** — captured 283 entities during one cauldron fight.
- **ECS architecture confirmed.** Every entity has the same vtable (`oCEntity`, RVA `0xf4cc40`) — what differentiates a "pig" from a "barrier" from a "shard pickup" is the **components attached**, not the class hierarchy. RTTI alone is uninformative.
- **`oCDtEntityCpntEnemyController` is the enemy marker.** Filtering for it identifies enemy entities. Pattern of components on cauldron-spawned enemies (verified in test):
  - `oCDtEntityCpntEnemyController` (key `0x1561073c`)
  - `oCDtEntityCpntCharacterController` (key `0x1560fd89`)
  - `RegisteredEntitiesHolderEntityCpnt` (key `0x1a9a307a`)
  - `oCDtEntityCpntRemoteDamageOwner` (key `0x170176e5`)
  - `oCEntityCpntModifierHolder` (key `0x15a04b1a`)
  - `oCEntityCpntNetwork` (key `0x154fce5c`)
  Same six components as the player except `EnemyController` swapped for `HeroController`.
- **`initArg` (param_2 of the constructor) groups same-type entities.** Equal `initArg` across multiple captures = same enemy template. Wave structure visible: groups of 4 enemies sharing initArg, in 3 sub-clusters of 4 = textbook cauldron-wave geometry.
- **Empty-hashmap sentinel pattern.** Entities that never had components attached (decorations, particle anchors, etc.) have a synthetic `ctrl_bytes_ptr` pointing at a static read-only sentinel inside the image (verified: `imageBase + 0xedbfa0`), with `vals_ptr = NULL`, `count = 0`, `mask = 0`. Distinguishes "no components ever" from "components removed."

### Open

- **Some test runs catch only non-ECS decorations** even when a cauldron clearly fires. Likely procedural — second `start()` clears the prior run's captures, leaving only ambient activity from the second window. Worth adding a "merge mode" or "snapshot then continue" semantics to `start()` later.

## Frida tooling shipped this session

### Mod (`tools/frida/mods/spawn_capture.js`)

- `SpawnCapture.start()` — arm hook on `oCEntity` constructor (RVA `0x6c96f0`)
- `SpawnCapture.stop()` — detach
- `SpawnCapture.dump()` — print every captured entity grouped by RTTI (raw firehose)
- `SpawnCapture.analyze({ requireComponent? })` — group by initArg template, sort by size, walk each group's first-entity component map. Optional case-insensitive substring filter against component class names — e.g., `analyze({ requireComponent: "EnemyController" })` to drop non-enemy templates.

### Hub helpers (in `tools/frida/rw_lab.js`)

- `RW.Player.entity` — `oCEntity*` for the local hero
- `RW.Player.hc` — HeroController-persistent
- `RW.Player.loc` — `{x, y, z}` getter, re-reads on every access
- `RW.Player.refresh()` — re-arm capture (auto-armed at hub-load)
- `RW.Entity.find(name)` — case-insensitive substring lookup → `{name, value, entity, loc}` or null
- `RW.Entity.list()` — print + return all currently-cached entries

Both `RW.Entity.*` are EXPERIMENTAL-tagged because the underlying encyclopedia is the streaming asset cache, not a full POI list. The encyclopedia walker is **self-contained in `rw_lab.js`** (no dependency on the deprecated `boss_rush` mod). It captures `scene_manager` lazily on first use via a one-shot hook on `scene_manager_find_context_by_type` (RVA `0x653f80`).

### Power (`tools/frida/mods/powers/Transporter.js`)

- `Transporter.warpEntity(name, x, y, z, roundtrip?)` — moves a named entity. Tick-loop locks position every 500ms. Optional auto-restore after `roundtrip` seconds.
- `Transporter.warpPlayer(x, y, z, roundtrip?)` — warps the player. Single-shot setPosition. Optional auto-return.
- `Transporter.clear()` — abort all timers (no position restore).

Refuses to move the hourglass (`NoModel+2Cpnt`).

## Next analysis pass

In priority order:

1. **Test Den Entrance + Entrance** placement-primitive behavior. Quick `Transporter.warpEntity` tests with short roundtrips. Builds the visible-vs-invisible classification table.
2. **Camp-anchor spawn-children test.** Move a non-hostile camp anchor (or the wandering variant) near the player; observe whether spawn events fire near the new anchor position. If yes, "summon enemies" is unlocked.
3. **Find the global per-instance entity registry.** Best path: extend `boss_rush.captureResolutions` to capture every `oCEntity*` allocated during chapter load, then we have a full list at runtime. Alternative: find a different scene-context type via the scene_manager iterator (Ghidra dig at `scene_manager_find_context_by_type @ 0x140653f80`'s caller — the iterator helper).
4. **Cooked `.gen` deserialization** (wishlist item). Static read of `rw/harvested/EntitySettings/` would give us the full design-time POI layout per chapter without needing the game running. Requires RE'ing `oCEntitySettingsResource::deserialize`.
