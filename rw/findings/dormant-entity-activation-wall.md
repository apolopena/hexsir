[← Back to findings](README.md)

# Dormant-entity activation — the streaming-grid wall

**Status:** confirmed
**Created:** 2026-05-10

Why "summon a dormant enemy from anywhere" doesn't work end-to-end without dynamic tracing. Four attempted approaches all hit walls; the surfaced walls are documented here so a future session knows what's a dead end vs what's still unexplored. Includes corrections to `entity-spawner-mechanism.md`, the entity factory's runtime contract, and a list of Ghidra rename proposals staged for a parallel-mode batch.

## Sources

- `Ravenswatch.exe` Ghidra reads, 2026-05-10 — decompiles of `oCEntitySpawner_fireSpawnWithBroadcast` (RVA `0x6f62b0`), `oCEntitySpawner_dispatchSpawn` (RVA `0x713520`), `oCEntitySpawner_allocateAndRegisterChild` (RVA `0x714350`), `oCSpawner_createEntityFromSettings` (RVA `0x6db260`), `oCSpawner_getChapterContext` (RVA `0x713c30`), `oCEntitySpawner_setActiveFlag` (RVA `0x6ef3a0`), `oCEntitySpawner_enableAndSpawn` (RVA `0x6f04b0`), `oCEntityCpntEntitySpawner_ctor` (RVA `0x2d0ee0`), `oCDtEntityCpntMagicalObjectsDrop` class methods (RVAs `0x277960`/`0x2d2f60`/`0x2d3970`/`0x2d4480`), `chapter_distribute_rewards_inline_pcg_at_offset_0x84` (RVA `0x1e6030`)
- Live Frida-driven testing, chapter 1 (Dark Hills), 2026-05-10
- `tools/frida/mods/poc_warp_enemy.js` (this session) — captures every `oCEntity::ctor` with deferred name resolution; warp + scan + diff + restore APIs
- `tools/frida/mods/poc_ghoul_spawn.js` (this session, archived header) — direct-factory call attempts; documents the universal entity factory pipeline
- `tools/frida/mods/poc_summon_enemy.js` (this session, archived header) — broadcast worker / enableAndSpawn attempts on dormant spawners
- Prior context: `rw/findings/entity-spawner-mechanism.md` (parent doc; field-map correction proposed below)

## TL;DR

- **Goal:** call a Frida function and have an enemy appear at the player's position, fully wired (rendering, AI, collision). Useful for testing, soak runs, debug puppeteering.
- **Result:** the warp mechanism is mechanically correct (position writes stick), but **rendering, collision, and AI/leash logic are gated by multiple engine subsystems that don't follow `+0x324` position writes.** Moving a dormant entity to the player produces an invisible, immobile, non-engaging entity. Each subsystem has its own registration tied to streaming-grid cell membership at chapter-init time.
- **Honest call:** completing this from outside the engine, with the tools we have on hand, is genuinely WinDbg-tier work. We can see the renderer/AI/collision wiring is split across multiple subsystems, but we don't have a map of any single one of them, and inferring them from static analysis is high-effort and low-confidence.
- **Bonus deliverables**: the dig surfaced enough Ghidra-symbol identification to propose 18 renames + 4 plate comments + a doc correction. The `poc_warp_enemy.js` mod works correctly for visible entities (e.g., scene props, lights) — it's the dormant-rendering case that doesn't.

## Confirmed Findings

### 1. Four approaches tried; four walls

| # | Approach | Wall hit |
|---|---|---|
| 1 | Direct call to `oCSpawner_createEntityFromSettings` with a hand-built `oCEntitySpawnData` | Access violations at multiple unmapped uninitialized fields (sentinel `0xff..ff` reads, NULL dereferences). Required state we couldn't fully populate. |
| 2 | Broadcast-worker fire (`oCEntitySpawner_fireSpawnWithBroadcast`) on a dormant streaming-grid spawner | `0xff..ff` access — the spawner's sub-object `+0x68` is sentinel-init at chapter ctor and only populated by streaming-grid activation. |
| 3 | `oCEntitySpawner_enableAndSpawn` + manual flag set on dormant spawners | Same sentinel-state crash + corruption from byte-writes (`0x100000167` from an incorrectly-interpreted ptr read). |
| 4 | Warp pre-existing (chapter-init-ctored) entities to player, also moving camp anchors | Visual move works, but rendering geometry, collision, AI, and leash logic stay wired to original chapter-init cell. Entities are invisible, immobile, and either leash away or freeze. |

### 2. The activation pipeline involves at least four subsystems

From the warp-existing-entity experiments:

| Subsystem | Wiring | Reaction to `setPosition(+0x324)` |
|---|---|---|
| **Renderer** | Mesh is registered to a streaming-grid cell at chapter init | Doesn't follow `+0x324`; entity stays invisible to player even when at player's coords |
| **Collision** | Tile-attached collision: tile-parent (`oCDtEntityCpntTileSpawner`) spawns child `oCEntityCpntCollisionVolume` (and related) sub-entities at chapter init via `oCTileSpawner_spawnAllTransforms` (RVA `0x6f2c50`). Bullet-backed (`btCollisionShapeData`). | Drags with the moved tile parent (matrix-relative spawn coords carry over partially) but the Bullet body's "CollisionVolume Transform update" is a separate per-frame dirty-driven event — it doesn't re-emit on raw `+0x324` writes → leaves "ghost" collision in safe zone |
| **AI** | EnemyController component, behavior tree | Goes inert: retreat behavior fires, no engagement |
| **Leash** | Anchored to some original-cell reference (not just `+0x2e0`) | Entity tries to pathfind back to original camp coords |

We confirmed `+0x2e0` holds a position copy (matches `+0x324` for active entities), but writing it on warp didn't defeat the leash. There's at least one more anchor reference (likely a pointer to the camp entity, or a cell-id stored on the controller component).

### 3. Universal entity factory — verified pipeline (static)

The clean call chain for arbitrary entity spawn (if all state were satisfiable):

```
oCEntitySpawner_fireSpawnWithBroadcast (RVA 0x6f62b0)
  ├─ pre-broadcast (PTR_DAT_1412d2348 subscriber list)
  ├─ ValueSignal flag updates (+0x20/+0x40)
  ├─ vtable[28] = oCEntitySpawner_dispatchSpawn (RVA 0x713520)
  │    ├─ pool selection: settings.+0x1a8+0x98 OR owner.vtable[+0xf0]()
  │    ├─ job allocator (FUN_140717a00) → job record
  │    └─ oCEntitySpawner_allocateAndRegisterChild (RVA 0x714350)
  │         ├─ chapter sub-object via oCSpawner_getChapterContext(spawner)
  │         └─ oCSpawner_createEntityFromSettings (RVA 0x6db260)
  │              ├─ oCSpawnablePool_allocateNode(settings + 0x18) → new oCEntity slab
  │              └─ subobj.vtable[3] = oCSpawner_addEntityIntoWorld
  │                   ├─ adds entity to spawner's child list (+0x18/+0x20/+0x28)
  │                   ├─ installs death-listener thunks at child[+0x38, +0x48, +0x50, +0x60]
  │                   └─ entity.vtable[5] = entity_init_from_config_block(entity, spawnData)
  ├─ post-broadcast (PTR_DAT_1412d23b8 subscriber list)
  └─ consumed-bit set on +0x64
```

Where the broadcast worker drops the new child: **`spawner.+0x210`** (ptr array, count `u32 +0x218`) — NOT `+0x160` as the prior doc claimed. The `+0x160` cached-output is only used by the dormant streaming-grid passive path (`spawnIfNotCached`).

### 4. `oCEntitySpawnData` layout — corrections

From disassembly of `hero_inventory_create_magical_object` (RVA `0x39dee0`):

| Offset | Type | Field | Notes |
|---|---|---|---|
| `+0x00` | ptr | `oCEntitySpawnData::vftable` | Address: `0x140ef6400` (RVA `0xef6400`). Final vtable after multi-inheritance ctor chain. |
| `+0x08` | ptr | owner/settings ref | NULL OK |
| `+0x10` | 3×float | position xyz | The renderer/AI position |
| `+0x1c..+0x2b` | 4×float | rotation quaternion (x, y, z, w) | **Corrects prior "Euler XYZ at +0x1c" annotation.** Identity = (0, 0, 0, 1). w at +0x28 = 1.0 required — zero quat is degenerate, downstream code that normalizes it gets NaN. |
| `+0x2c..+0x37` | 3×float | scale xyz | (1, 1, 1) for unscaled |
| `+0x38` | ptr | parent entity ref | NULL OK |
| `+0x40` | 4×u32 | IDs/flags | zero OK |
| `+0x50` | 24 B | listener block | zero OK |

Total struct size: 0x68 bytes.

### 5. `oCEntityCpntEntitySpawner` field-map correction

Verified via the ctor decompile (`oCEntityCpntEntitySpawner_ctor`, RVA `0x2d0ee0`) and the working `Hourglass.js` code:

| Offset | Role |
|---|---|
| `+0x00` | primary vtable (`oCEntityCpntEntitySpawner::vftable` @ `0x140f00650`) |
| `+0x08` | parent `oCEntity*` |
| `+0x10` | **settings binding (`oCEntityCpntEntitySpawnerSettings*`) ★** (corrects prior doc which said `+0x18`) |
| `+0x18`..`+0x30` | embedded `EntityCpntValueSignal<bool>` (active signal) |
| `+0x38`..`+0x50` | embedded `EntityCpntValueSignal<bool>` (idle signal) |
| `+0x64` | flag byte — bit 1 = firing, bit 3 = consumed |
| `+0x68`..`+0xb8` | embedded `oCSpawner` sub-object (sentinel-init `0xff..ff` until streaming-grid activates) |
| `+0xc8` | owner override (pool from `+0xc8.vtable[+0xf0]()` if non-null) |
| `+0x108` | sentinel-init `0xff..ff`; broadcast-worker path doesn't use; prior "I/O queue" interpretation incomplete |
| `+0x160` | cached-output entity — `spawnIfNotCached` path only |
| `+0x168` / `+0x169` | active flag / enable flag (DO NOT write directly — corrupts adjacent state; see #6) |
| `+0x1c0` / `+0x1c8` | spawn-job array head / count |
| `+0x210` / `+0x218` | **spawned-child-entity array head / count (broadcast-worker path)** ★ |
| `+0x230` | last chapter-state-check result |

### 6. Why direct flag-writes on dormant spawners corrupt state

The `+0x168` / `+0x169` activation bytes are part of a wider state field that the engine reads as a unit. Writing them as bytes corrupts subsequent ptr reads (we saw a crash at `0x100000167` after our flag writes — the engine read a struct field that combined our byte writes with adjacent uninitialized state, interpreted it as a pointer, dereferenced it).

**Practical takeaway:** flag-writes on dormant spawners are not a safe path. Activation goes through specific functions (`setActiveFlag`, `enableAndSpawn`) which handle the wider field correctly, but those functions themselves crash on dormant spawners because of other uninitialized state (`+0x68` sub-object sentinel).

### 7. The leash anchor isn't a single byte

Byte-diff between active Fisherman #3 (in player's cell, AI-on, rendering-on) and dormant-bound Fisherman #0 (in a different camp, AI-off, rendering-off) revealed 116 ranges of differences across the first 0x600 bytes:

- 11 instances of "component-init pair" pattern: `(+N+0x00 = 0x01, +N+0x08 = 0x08)` on active, zeros on dormant. These look like 11 separate components' "attached" flags.
- `+0x270` (qword): A=*real ptr*, B=NULL — the "dirty-broadcast gate" per the parent doc.
- `+0x28a..+0x28c`: dirty flag (byte) + handler mode (u32 = 1 vs -1 sentinel). Per the parent doc: "+0x28c u32 — dirty-handler mode (1 = use +0x270, 2 = use +0x280, **other = skip refresh**)."
- `+0x2e0`: 3-float position copy matching the entity's anchor position. Looked like the leash reference but writing it on a warped entity didn't defeat the leash.

The activation isn't a single flag — it's an entire pipeline that the streaming grid runs at cell activation. Replaying it requires populating 11+ component-attach states, the dirty-broadcast gate (which requires a valid handler list pointer), and likely registering with the renderer / collision / AI subsystems.

### 8. `poc_warp_enemy.js` — what works, what doesn't

The mod (`tools/frida/mods/poc_warp_enemy.js` v0.11.1) ships with:

- **Deferred-name-resolution ctor capture.** Buffers `(entity, settings)` ptrs in `onEnter`, runs a 500ms resolver tick that reads names lazily. Mirrors `Registry.js`'s pattern. Catches 30k+ ctors per chapter init (vs. ~15 the original immediate-read version caught).
- **Spawner-component capture** (RVA `0x2d0ee0`) — used for the `summon` flow's camp-anchor lookup.
- **Warp APIs** — `warpToPlayer`, `warpMeTo`, `summon`, `scanActive`, `warpScannedToPlayer`, `diff`, `restoreCamp`, `restoreScanned`, `clear`.
- **Confirmed working** — visible entities (lights, props, the hourglass parent) warp cleanly and stay where placed.
- **Confirmed NOT working** — dormant enemies (Festering_Ghoul, Standard_Undead_Hog_*) warp at the byte level but don't render/engage. Pool-stub entities at `(0, 0, 0)` are mostly inert allocations and warping them produces nothing visible.

## Unresolved

### A. Renderer's per-cell registration

Where the mesh is registered for an entity to actually draw. Different from `+0x324`. Likely a streaming-grid cell membership list keyed by entity ptr. Until we find this, moving an entity in memory won't move its rendered mesh.

### B. AI / leash reference

`+0x2e0` is a position copy but not the leash anchor. The leash probably reads from a pointer field — most likely a reference to a camp entity (or to the entity's own controller's spawn-record). Need to find this field to defeat leash.

### C. Collision-mesh follow-on (refined 2026-05-11)

The "tile collision baked into a cell" symptom is more concrete than initially documented. **Tiles are not single entities** — a tile is `oCDtEntityCpntTileSpawner` (IS-A `oCEntitySpawner` IS-A `oCSpawner` IS-A `oIEntityCpnt`), a procedural building block that spawns N child sub-entities at chapter init. `oCTileSpawner_spawnAllTransforms` (RVA `0x6f2c50`) walks a transform array at `parent[+0x98]` (count `+0xa0`, stride `0x40`), multiplies each entry by the parent's world matrix at `+0x140..+0x180`, builds an `oCEntitySpawnData`, and dispatches a spawn per entry. The "invisible mesh" the player gets stuck in is one of these child sub-entities — specifically a pure-collision sub-entity.

Collision-component classes identified (engine string table):

| Class | Purpose (hypothesized) |
|---|---|
| `oCEntityCpntCollisionVolume` | Pure-collision volume — blocks movement, no render. The primary "invisible mesh" candidate. |
| `oCEntityCpntCollisionVolumeDetector` | Overlap trigger (non-blocking). |
| `oCEntityCpntCollisionVolumeExtraction` | "Extract" on overlap — likely loot pickup regions or contents-extract triggers. |
| `oCEntityCpntCollisionGpn` | Gameplay-network collision — per-entity dynamic body (the enemy/player body itself). |
| `oCEntityCpntCollisionAttack` | Melee-hit volume. |
| `oCEntityCpntCollisionRaycast` / `oCEntityCpntCollisionEntityRaycast` | Raycast emitters. |
| `oCCollisionMesh` | Shape resource (own `oCTLibrary<>` catalog) — the raw mesh asset a CollisionVolume references. |

All Bullet-backed (`btCollisionShapeData`, `btCollisionObjectFloatData` at `0x140f8e958` / `0x140f8e980`). Navmesh is Detour multi-tile (`oCDetourNavMeshByTiles`), rebuilt at level load (`Level load - Rebuild navmesh` event).

There is a named per-frame handler `"oCEntityCpntCollisionVolum - CollisionVolume Transform update"` (string literal at `0x140f64550`); the installer fragment is at `0x1407cfca0`. The fact that transform updates are an explicit named per-frame event suggests volume → Bullet-body re-emit is **queue-driven (dirty-flag style), not implicit on `setPosition`**. That's the most likely reason warping a tile parent leaves "ghost" collision: the parent's matrix moves, the per-volume dirty event hasn't fired, the Bullet body sits half-updated.

**Practical purpose of the invisible volumes:** they form the world-geometry boundaries inside procedural tiles — invisible walls, blocked corridors, cliff edges, building footprints, gap-fillers between visible scenery. Cheaper than full mesh colliders for places where the visible art doesn't naturally enclose the play area.

**Still unknown:**
- Which event/flag fires the volume's dirty bit, and whether it can be poked from Frida to force a re-emit after a parent-warp.
- Whether collision volumes are scene-graph-parented to the tile anchor (and therefore should follow a parent-matrix update) or carry independent world transforms baked at spawn.
- The settings-asset offset that lists a tile's child-transform array's collision-type entries (so we can identify which children are volumes vs props vs scenery).

### D. Pool-stub vs. bound-entity distinction

Many captured enemy entities are at `(0, 0, 0)` — pool stubs the engine pre-allocates for fast spawn-on-demand. Others are bound to specific camps with real coords. The difference between them isn't visible from name alone. There may be a single field that distinguishes (e.g., "is this entity assigned to a camp" flag).

### E. The full activation function

`oCEntitySpawner_enableAndSpawn` (RVA `0x6f04b0`) is what streaming-grid registration calls when activating a cell. It internally invokes `setActiveFlag(true)` then `spawnIfNotCached`. The reason it crashed for us is the spawner's own `+0x68` sub-object was sentinel-init — but when called natively in the engine's natural flow, that sub-object has already been wired up by some other code path we haven't identified. Tracing that population in WinDbg would unlock direct activation.

## Notes

### Methodology

- All Ghidra reads were read-only. Renames are proposed for a parallel-mode batch in §"Ghidra annotation proposals" below.
- Static analysis hit diminishing returns ~midway through the session. Each "next layer" revealed another subsystem rather than a single answer. The honest pivot point would have been recognizing this earlier.

### Recommended next step

**WinDbg trace of natural cell activation.** Walk into a real camp with breakpoints set on:
- `oCEntitySpawner_enableAndSpawn` — to capture what state the spawner has at the moment activation is requested (vs. the sentinel-init dormant state).
- The renderer-registration call inside that path — likely callable as a public function once we identify it.
- The first write to the entity that establishes its "in-cell" status.

That gives us the full activation pipeline as a sequence of arg-state snapshots. From there, replaying it for a warped entity is mechanical.

### Ghidra annotation proposals (parallel-mode batch)

**Renames (11):**

| Current | Proposed | RVA |
|---|---|---|
| `FUN_1406f62b0` | `oCEntitySpawner_fireSpawnWithBroadcast` | `0x6f62b0` |
| `FUN_140713520` | `oCEntitySpawner_dispatchSpawn` | `0x713520` |
| `FUN_140714350` | `oCEntitySpawner_allocateAndRegisterChild` | `0x714350` |
| `FUN_140717a00` | `oCEntitySpawner_allocateJobRecord` | `0x717a00` |
| `FUN_140717f90` | `oCEntitySpawner_jobRecordCleanup` | `0x717f90` |
| `FUN_140713c30` | `oCSpawner_getChapterContext` | `0x713c30` |
| `FUN_140254280` | `MagicalObject_spawnAllObjectsAtChapterLoad` | `0x254280` |
| `FUN_140277960` | `oCDtEntityCpntMagicalObjectsDrop_typedesc_init` | `0x277960` |
| `FUN_1402d2f60` | `oCDtEntityCpntMagicalObjectsDrop_loadFromSettings` | `0x2d2f60` |
| `FUN_1402d3970` | `oCDtEntityCpntMagicalObjectsDrop_fireDropAndAddToInventory` | `0x2d3970` |
| `FUN_1402d4480` | `oCDtEntityCpntMagicalObjectsDrop_addOneAndRemoveFromRegistry` | `0x2d4480` |

**Generic helpers surfaced:**

| Current | Proposed | RVA |
|---|---|---|
| `FUN_1406ca380` | `oCEntity_findComponentByTypeDesc` | `0x6ca380` |
| `FUN_140216210` | `entity_listener_node_alloc` | `0x216210` |
| `FUN_140503df0` | `entity_listener_node_bind` | `0x503df0` |
| `FUN_14070ae70` | `chapter_state_can_spawn_check` | `0x70ae70` |
| `FUN_140253e30` | `oCDtEntityCpntMagicalObjectsDrop_getClassHash` | `0x253e30` |
| `FUN_1402d3130` | `oCDtEntityCpntMagicalObjectsDrop_clearState` | `0x2d3130` |
| `FUN_1402d32d0` | `oCDtEntityCpntMagicalObjectsDrop_onAttachToParent` | `0x2d32d0` |
| `FUN_1402d3320` | `oCDtEntityCpntMagicalObjectsDrop_onDetach` | `0x2d3320` |

**Global data label:**

| Current | Proposed | Address |
|---|---|---|
| `DAT_14140de00` | `g_magicalObjectsDrop_registry` | `0x14140de00` |

**Data label:**

| Current | Proposed | Address |
|---|---|---|
| (none) | `oCEntitySpawnData::vftable` | `0x140ef6400` |

**Plate comments (4):**

- `oCEntitySpawner_fireSpawnWithBroadcast @ 0x1406f62b0` — Pre-broadcast (PTR_DAT_1412d2348), vtable[28] dispatch, post-broadcast (PTR_DAT_1412d23b8), consumed-bit. Writes child to `+0x210`/`+0x218`, NOT `+0x160`. `+0x160` is for `spawnIfNotCached` only.
- `oCEntitySpawner_dispatchSpawn @ 0x140713520` — Pool selection: `(spawner.+0xc8 == NULL) ? settings.+0x1a8+0x98 : owner.vtable[+0xf0]()`. Job array `+0x1c0`/`+0x1c8`, child array `+0x210`/`+0x218`.
- `oCEntitySpawner_allocateAndRegisterChild @ 0x140714350` — Calls `oCSpawner_createEntityFromSettings` and pushes result into `spawner.+0x210`. Frida code firing via `fireSpawnWithBroadcast` should read the new-child pointer from here.
- `oCSpawner_getChapterContext @ 0x140713c30` — Takes a spawner-component (param_1). Returns either the chapter scene's spawner sub-object (`scene + 0xa0`) OR the spawner's own `+0x68` if settings flags at `+0x35`/`+0x1bc`/`+0x19f0` route to fallback. The fallback case is what crashes when called on dormant spawners — `+0x68` is sentinel-init.

### Tile / collision-volume renames (staged 2026-05-11)

**Renames (3):** already-named functions surface from the `oCDtEntityCpntTileSpawner` family — listed here for completeness of the staged batch:

| Current | Status | RVA |
|---|---|---|
| `oCTileSpawner_spawnAllTransforms` | already named | `0x6f2c50` |
| `oCDtEntityCpntTileSpawner_ctor` | already named | `0x1e3760` |
| `oCDtEntityCpntTileSpawner_typedesc_init` | already named | `0x2379b0` |

**Plate comments (1) — additional:**

- `oCTileSpawner_spawnAllTransforms @ 0x1406f2c50` — Walks transform array at `parent[+0x98]` (count `+0xa0`, stride `0x40`); multiplies each entry by parent world matrix at `+0x140..+0x180`; builds `oCEntitySpawnData` (vftable `0x140ef6400`); calls `oCSpawnablePool_allocateNode(spawner.+0x18)`; dispatches via `*(*spawner+0x30)+0x18`. This is how a single tile-anchor instantiates all its scenery + collision-volume children at chapter init.

**EOL comments on string labels (3, advisory — display names for CampType enum):**

- `0x140eee8d0` — `Standard camp` (CampType enum-name)
- `0x140eee8e8` — `Sandman` (CampType enum-name)
- `0x140eee8f0` — `Wandering camp` (CampType enum-name)

The three sit in a tight enum-display block at `0x140eee8d0..0x140eee900` with `None` between them. No direct xref (string-pool-indexed access), so attribution rests on layout adjacency.

### Field-map correction to apply

`rw/findings/entity-spawner-mechanism.md` §"Field map on `oCEntityCpntEntitySpawner`" says `+0x18 ptr — settings binding`. Wrong — settings binding is at `+0x10`. `+0x18` is the start of an embedded `EntityCpntValueSignal<bool>` sub-object (verified via the ctor decompile and the working `Hourglass.js` code at line 49 which reads name from `+0x10`).

### Cross-references

- `rw/findings/entity-spawner-mechanism.md` — parent doc; field-map correction proposed above
- `rw/findings/enemy-spawn-architecture.md` — `+0x570` listener-array architecture, `+0x5e8` component hashmap
- `rw/findings/on-demand-spawn-pipeline.md` — sibling pipeline doc
- `tools/frida/mods/poc_warp_enemy.js` — the working mod that catches the wall
- `tools/frida/mods/poc_ghoul_spawn.js` (archived header) — direct-factory call attempts
- `tools/frida/mods/poc_summon_enemy.js` (archived header) — broadcast-worker attempts
