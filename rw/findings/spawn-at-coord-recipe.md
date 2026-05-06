[← Back to findings](README.md)

# Entity world position — read/write contract and spawn-at-coord recipe

**Status:** in-progress (player teleport — confirmed; spawn step + cross-chapter loading — open)
**Created:** 2026-05-05
**Last updated:** 2026-05-06 — player teleport primitive verified live

> **Runtime test layer added 2026-05-05 (later session).** The body below was written from static decompile by three triangulating Ghidra agents (read-only). A subsequent Frida-driven runtime session tested the recipe end-to-end and discovered constraints not visible from static analysis alone — most importantly that `vtable[+0x1a0]` on `oCEntity` (the class actually accessed via `HC[+0x08]`) is a stub, NOT `setWorldPosition`. The "Runtime verification 2026-05-05" section below records what was confirmed live, what failed, and what call shapes still need solving. Read that section together with the static body — it constrains and corrects several claims.

> **2026-05-06 update — PLAYER TELEPORT VERIFIED.** The "+0x1a0 stub" finding was a false alarm from looking at the wrong vtable contract. **`oCEntity_setPosition` lives at `vtable[+0x50]` (RVA `0x6ca7f0`) for the player's `oCEntity` class** (vtable RVA `0xf4cc40`). Calling it with a Vec3 visibly teleports the player. Recipe + working Frida mod live in `tools/frida/mods/teleport.js`. The "+0x1a0 contract" applies to a DIFFERENT class hierarchy (`oITransform3dAccess`-derived classes like `oCPosRotGo`), not `oCEntity`. See "Player teleport — verified" section below.

## Sources

- `Ravenswatch.exe` (Ghidra MCP — three coordinated read-only agents on 2026-05-05; decompile of `Sc_ForcePosition_impl`, `Sc_MoveTowards_impl`, `Sc_TranslatePosition_impl`, `Sc_Spawn_impl`, `oCEntitySpawner_spawnEntityFromBoundTransform`, `HC_per_frame_update`, `oCDtEntityCpntHeroSpawner_spawnHero`, `level_load_orchestrator`)
- `rw/findings/chapter-map-and-boss-spawn-architecture.md` — prior pass on the boss-spawn architecture, settings-entry layout (`parent[+0x8C0][i]+0x1f0`), path-based loader, and the `oCEntitySpawner` sub-object pattern
- `rw/findings/multiplayer-host-authority.md` — context on host-authority and replication; relevant to whether `vtable[+0x1a0]` writes propagate to peers

## Player teleport — verified 2026-05-06

**Working primitive (verified live, multiple successful teleports):**

```c
// Resolve player parent entity
HC_array_header* hdr   = HC_per_frame_update::param_2;       // hooked once, captures hdr
oCEntity*        hc    = hdr->arr[0];                        // first HC
oCEntity*        player= *(oCEntity**)((uint8_t*)hc + 0x08); // HC[+0x08] = parent

// Teleport
Vec3 newPos = { x, y, z };
typedef void (*setPos_t)(oCEntity*, Vec3*);
((setPos_t*)player->vtable)[10 /* +0x50 */](player, &newPos);
```

**Frida one-liner (paths work after `loadMod("teleport")`):**

```js
RW.tp.refresh();         // arm hook
// (game ticks one frame — captures player address)
RW.tp.set(125, 0, -200); // chapter-1 spawn-area coords
RW.tp.shift(10, 0);      // relative +10 X, preserves Y
RW.tp.spawn();           // recover to known-safe (125, 0, -200)
```

Mod source: `tools/frida/mods/teleport.js`.

### What was tested live

- **Small deltas (+3, +5 X)** — write went through to `+0x324`, but visual change was imperceptible to the user. Either the character controller animated the small jump smoothly, or the visual delta was below the user's perception threshold.
- **Larger deltas (+15, +20, +50 X)** — visible teleport. Player snapped to new position.
- **Long-distance teleport (-200 X, +75 Z)** — works. Player landed in different chapter terrain (with real altitude — the user noticed elevation differences at the destination).
- **Off-map teleport** — works at the position level. Player ends up in pure black void with the map still visible to the side. **The character then free-falls indefinitely** (Y decreased from 0 → -28 → -138 → -161 across a few seconds), which means there's no collision floor outside the playable area.
- **Recovery** — `tp.spawn()` to `(125, 0, -200)` restores the player to a confirmed-on-map position.

### What does NOT happen on teleport

- **Fog-of-war does NOT auto-reveal.** Teleporting to undiscovered map territory (verified) leaves the minimap fog intact. Reveal is movement-bound, not position-bound — the engine probably ties reveal to either the natural movement events (`oCEntity::_VelocityUpdate`) or to a per-frame proximity check that doesn't fire on a clean position write. **Implication:** any future "exploration" or "reveal whole map" mod cannot just teleport; it would need to either (a) trigger the reveal events directly, or (b) animate the player through the unrevealed area at high speed.
- **Camera does follow** the teleport — when the player jumps, the camera frames them at the new location. Pan vs snap behavior was not pinned but the user didn't report a delay.
- **Engine-managed prev/target fields** at `+0x3d8..+0x3ef` (used by `oCEntity::_VelocityUpdate_loop` for NPCs, not the player) are NOT required and NOT useful — the engine resets them to zero within ~3 seconds of any manual write. The player's natural movement does NOT route through those fields (the player setPosition caller is different from `_VelocityUpdate_loop`; that loop drives NPC movement).

### Why the previous session thought `vtable[+0x1a0]` was the answer

The agent triangulation that produced this document analyzed `Sc_ForcePosition_impl` and saw it dispatch through `param_1->vtable[+0x1a0]`. They concluded "+0x1a0 = setWorldPosition" for any entity that passes the `isKindOf(oITransform3dAccess)` test. That conclusion is correct for `oITransform3dAccess`-derived classes (e.g. `oCPosRotGo`, the spawn-point class registered under `g_typeDesc_oITransform3dAccess` at `0x141447a08`).

But the player's `HC[+0x08]` is a plain `oCEntity` (RTTI `.?AVoCEntity@@`, vtable RVA `0xf4cc40`), and `oCEntity` does NOT implement `oITransform3dAccess`. Its `vtable[+0x1a0]` is the stub `oIEntityCpnt_getMemberByHash_baseImpl` (returns 0 unless the hash matches a known member). Calling that with a Vec3 just no-ops.

`oCEntity`'s setPosition is at `vtable[+0x50]`, with separate getters at `+0x48` (position), `+0x58` (rotation), `+0x68` (scale). The position field is embedded at `oCEntity+0x324` (three contiguous floats). `Sc_ForcePosition_impl` does NOT work on `oCEntity` instances — only on classes that pass the `oITransform3dAccess` kind-test.

### oCEntity transform layout (verified runtime)

| Offset | Size | Field |
|---|---|---|
| `+0x270` | qword | dirty-broadcast gate (must be non-null for the dirty path to fire) |
| `+0x288` | byte  | dirty flag (0 = clean, 1 = dirty); `oCEntity_setPosition` sets to 1 if previously 0 and gate is non-null |
| `+0x28c` | u32   | dirty-handler mode (1 = use `+0x270`, 2 = use `+0x280`, other = skip refresh) |
| `+0x308` | 16 B  | rotation (Quat, 4 floats) — getter at `vtable[+0x58]` returns `+0x308` |
| `+0x318` | 12 B  | scale (Vec3) — getter at `vtable[+0x68]` returns `+0x318` |
| `+0x324` | 12 B  | **position (Vec3)** — getter at `vtable[+0x48]` returns `+0x324`; setter at `vtable[+0x50]` writes to it |
| `+0x3a8` | qword | head of broadcast handler list (renderer/camera/etc subscribers); written via `broadcast_to_handler_list` after a position change |
| `+0x3d8..+0x3ef` | 24 B | engine-managed prev/target Vec3s used by `oCEntity_VelocityUpdate_loop` (NPC movement). Manual writes are reset to zero within seconds; not useful for player teleport |

**Annotations applied to Ghidra this session:**

- `0x1406ca7f0` → `oCEntity_setPosition`
- `0x1406c3ca0` → `oCEntity_getPosition`
- `0x1406c3cb0` → `oCEntity_getRotation`
- `0x1406cce40` → `oCEntity_VelocityUpdate_loop`

## Runtime verification 2026-05-05 (subsequent session)

### What was verified live

- **Player position retrieval via global-value bus** (§4) **WORKS.** Hooking `global_value_publish_vec3 @ 0x1402b72e0`, filtering for hash `0x15c82040`, captures the player Vec3 every frame. Sample reading from chapter-1 arena: `(-13.31, 2.64, 11.00)` — sane in-world coords. GVSC pointer also captured for free as the function's first arg (cached at `0x1efcadab500` in that session — heap address, ASLR-randomized, not stable across launches).
- **HC array access shape**: `HC_per_frame_update`'s `param_2` is `uint *`. Length is at `+0x00` (u32). **Array pointer is at `+0x08`** (per `(uint *)param_2 + 2` = byte offset 8), NOT `+0x10`. `arrPtr[i]` is a pointer to an HC instance. `HC[+0x08]` is the parent entity ("smaller data class"). One reading in chapter 1: `len=1`, single HC.
- **HC[+0x08] is `oCEntity`.** RTTI-walked via vtable - 8 → COL → type descriptor: name string `.?AVoCEntity@@`. Vtable RVA `0xf4cc40`. `vtable[+0x48]` correctly returns a `Vec3*` to the player's current position.
- **Encyclopedia walker** (`oCEntitySettingsEncyclopediaSceneContext`) works end-to-end. 21 entries in lobby, 2041 in chapter 1. Cache-key format definitively: `lowercase(typeTag) + lowercase(path) + ASCII(config_digit)` — e.g., `entitysettingsobjects\map_boss_spawner\map_boss_spawner_dark_hills.entity.ot1`. The `!` in the deciphered asset tree (`Obzects/Map_Boss_Spawner!Map_Boss_Spawner_*.entity.ot`) is the cooker's serialization of a path separator; the runtime path uses `\`. Entries are 24-byte structs: `{char* path, u32 len, u32 cap, void* value}`. Hashmap key is a precomputed hash pair (entry first 16 bytes), NOT interned `(begin, end)` — dereferencing it produces ACCESS VIOLATION; walk Swiss-Table entries directly. See working primitive in `tools/frida/mods/boss_rush.js` v0.7.2.
- **Six chapter-1 boss-spawner variants confirmed cached in chapter 1**: `map_boss_spawner_model`, `_dark_hills`, `_cinematic_awakening`, `_claw_model`, `_cinematic_dying`, `_graph_model`. **None of the chapter-2/3/4 variants** (`_storm_island`, `_avalon`, Baba_Yaga's separate path) are cached while in chapter 1. Confirms the engine doesn't preload other chapters' assets — the path-based loader gating question (§A) is functionally answered for the cached path: chapter-1's cache only contains chapter-1's assets.
- **`forceBossSpawn` records the chapter-boss kill in the stats page.** Verified live. Side-boss (key/quest) recording behavior unknown (would require an analogous force primitive for those; not yet mapped).

### What FAILED runtime — claims requiring revision

- **`vtable[+0x1a0]` on `oCEntity` (player primary class) is a STUB.** `*(player.vtable + 0x1a0)` resolves to `FUN_1404f4640` which is `return &DAT_1412c7a70;` — returns a constant pointer, ignores its arg. **Calling it with a target Vec3 is a no-op.** Tested live: read player pos `(-25.80, 2.86, 2.20)`, called `vtable[+0x1a0](player, &(pos+(3,0,0)))`, re-read pos: unchanged. No crash, no teleport, no movement.
- **`Sc_ForcePosition_impl @ 0x14045fd70` therefore does NOT teleport the player either.** Sc_ForcePosition's body unconditionally dispatches to `param_1->vtable[+0x1a0](param_1, &Vec3)` after building the Vec3. The kind-of test is on the *source* (param_2) only, not on the destination. So when `param_1` is the player's `oCEntity` instance, the call hits the same stub and silently no-ops.
- **The "universal contract" on `+0x198/+0x1a0/+0x1a8` therefore is NOT universal across all entity classes accessible from a Frida session.** It applies to classes that pass `isKindOf(g_typeDesc_oITransform3dAccess)` — but the player's `oCEntity` instance reachable from `HC[+0x08]` does not. The `oITransform3dAccess`-implementing object on the player must be a sub-object or a separate component we haven't located. Embedded image-range pointers at player+0x48, +0x58, +0x60, +0x68, +0xc8, +0xd0 turned out to be *function pointers / data pointers*, not sub-object vtables (verified by checking each: vtable+0x1a0 reads produced garbage / instruction bytes).
- **Path-based loader `vtable[3]` (= `thunk_FUN_14048be40` at `0x14030c6d0` → `FUN_14048be40`) CANNOT be called cold from Frida.** Crashes at access-violation on `0x20`. The function does substantial setup (constructs `oCResourceRequestInfoFeed` stack object, takes critical sections at `+0x118`, modifies global `DAT_141415af8/b00`, traverses linked lists) — engine-side level-load orchestrator state is required and cannot be replicated from outside. Tested with both candidate path forms (with `!` literal and with `\` separator) and known-cached path "`Heroes\\Hero_Merlin\\Hero_Merlin.entity.ot`" — all crash at the same offset.
- **`oCEntitySpawner_spawnIfNotCached @ 0x1406ef5c0` direct call CRASHES at `0x1`** when bypassing `Sc_Spawn_impl`'s preconditions. Captured spawner sub-object `+0x18` was `0x1` (a small flag, not a pointer); the function expected a pointer there. Conclusion: this function also needs setup state from its callers.
- **`Sc_Spawn_impl @ 0x1406ef7c0` returned OK on captured enemy-spawner sub-objects but did NOT visibly spawn.** Inspected fields showed `+0x160 != 0` on every captured spawner (active state already populated), so the function took its early-return branch. Forcing `+0x160 = 0` and calling again could be tested but risks orphaning live entities — not attempted.
- **`FUN_14048b600` cache-lookup helper returned 0 for every Frida-side call**, including for known-cached paths (Hero_Merlin, chapter-1 boss spawner). `FUN_14048ae70` (the key-construction helper called inside) was hooked and the constructed key was inspected raw — bytes did NOT match the expected `entitysettings + path + 1` form. Conclusion: the call ABI my probe used had the input string struct layout subtly wrong, OR the keyBuilder requires SSO-mode handling we didn't replicate. The cache walk works (read-only iteration); the cache-keyed lookup call does not.

### What's now KNOWN to need a different approach

- ~~**To teleport the player:** `vtable[+0x1a0]` on `oCEntity` is the wrong primitive.~~ **RESOLVED 2026-05-06.** The player teleport primitive is `vtable[+0x50]` (= `oCEntity_setPosition` @ RVA `0x6ca7f0`), NOT `+0x1a0`. See "Player teleport — verified" section below. The `+0x1a0` contract from the agent triangulation applies to a different class hierarchy (`oITransform3dAccess`-derived, e.g. `oCPosRotGo`), which is not what `HC[+0x08]` returns.
- **To teleport an enemy:** capture the enemy's actual entity address (not just its spawner sub-object). The cleanest hook target untested this session is `oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20`'s `param_1` (the parent entity) during chapter-load resolutions, OR `vtable[+0x48]` on enemy entities (the position-getter that fires every frame on every visible enemy). Either captures live entity addresses for placement-primitive testing on a *non-player* class — which may or may not have valid `vtable[+0x1a0]`.
- **To load chapter-2's spawner from chapter 1:** the path-based loader gates on engine-internal load-context state. Three viable fallbacks: (1) trigger a chapter transition and capture chapter-2 assets, (2) find a different load entry point (perhaps via a higher-level orchestrator that sets up the context), (3) accept scope-shrink to single-chapter boss-rush.

### Frida loop established autonomously from WSL

The runtime session ran probes from WSL via the Windows-side `frida.exe`:

```bash
FRIDA=/mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe
( sleep N; echo exit ) | "$FRIDA" -n Ravenswatch.exe -l "$(wslpath -w /tmp/rw-probe/<probe>.js)"
```

Multiple Frida sessions to the same target are independent (separate JS contexts, hooks, etc.) and don't disturb the user's interactive REPL. Probes lived at `/tmp/rw-probe/p_*.js` (ephemeral). The full PowerShell-side launch path with `$env:FRIDA` via `$PROFILE` is documented in `tools/frida/README.md` Option D.

### Day/night cycle naming correction

`rw_lab.js`'s "BossTimer" naming is misleading. The instance at the `BossTimer_update` callsite (RVA `0x1e9d50`) is actually `oe::dt::DayNightCycleSceneContext` (RTTI-confirmed via vtable RVA `0xee52b8`). Its "boss_time" field is the day+night cycle threshold for boss arrival. `forceBossSpawn` is the right *behavior* but lives on the day/night cycle, not a "BossTimer" class.

## Confirmed Findings

### 1. Universal entity transform vtable contract

Three independent decompiles converged on the same three vtable slots on `oCEntity`-derived classes that pass the `oITransform3dAccess` kind-test:

| Vtable offset | Method | Returns / takes |
|---|---|---|
| `+0x198` | `getWorldPosition()` | `Vec3*` (engine-internal pointer to 3 contiguous float32; do not free, do not write through) |
| `+0x1a0` | `setWorldPosition(Vec3*)` | void; **the placement primitive — teleports the entity** |
| `+0x1a8` | refresh / poll | called immediately before `+0x198` when sourcing position from another entity; presumed `refreshTransform()` or `getWorldPosition` (vs local). Not always called. |

The kind-gate is `entity->isKindOf(g_typeDesc_oITransform3dAccess @ 0x141447dc0)`. Anything passing this test exposes the contract; non-3D entities have null or different slots. Confirmed identical use in `Sc_ForcePosition_impl`, `Sc_MoveTowards_impl`, `Sc_TranslatePosition_impl`, `Sc_GetDistanceTo` handler, `Sc_GetProximity` handler, and `oCDtEntityCpntHeroSpawner_spawnHero`.

`Vec3` layout: 3 contiguous float32, no padding, 12 bytes total — confirmed by consecutive 4-byte stack slots in `HC_per_frame_update` and `pfVar5[0]/[1]/[2]` indexing in the distance/proximity handlers.

### 2. Script-binding entry points (Frida-callable)

Four `Sc_*` bindings expose the placement contract to scripts. All four were renamed in Ghidra this session.

| Binding | Impl RVA | Method-id | Behavior |
|---|---|---|---|
| `Sc_ForcePosition` | `0x14045fd70` | `0x031bf6d7` | Reads Vec3 from a `(value_ptr, type_tag)` arg pair. When type-tag is `g_typeDesc_Vec3_direct @ 0x141447448`, reads 3 floats from `value_ptr`; when type-tag is `g_typeDesc_oITransform3dAccess`, reads from a target entity via `+0x198`/`+0x1a8`. Calls `entity->vtable[+0x1a0](&Vec3)` — the canonical placement primitive. |
| `Sc_MoveTowards` | `0x14045fc70` | `0x02997809` | Move toward target with speed; same vtable contract underneath. |
| `Sc_TranslatePosition` | `0x14045fe20` | `0x02997b1c` | Relative move along direction vector. |
| `Sc_Spawn` | `0x1406ef7c0` | `0x1faa` | Multi-step spawn: gates on `+0x168/+0x169`, tail-calls `oCEntitySpawner_spawnIfNotCached @ 0x1406ef5c0` → `oCEntitySpawner_spawnEntityFromBoundTransform @ 0x1406eef40`. Position used by the worker comes from `vtable[+0x178]` on the parent spawner — i.e., this binding alone does NOT take a position arg. |

`Sc_SetPosition` is **not** a world-position setter despite the name — confirmed UI primitive that writes `+0x2c8/+0x2cc` (UI element X/Y in pixels). Skip when looking for entity placement.

### 3. Spawn dispatch trunk

Every entity spawn in the engine flows through `oCEntitySpawner::vftable[0x18]`, dispatched with an `oCEntitySpawnData` and a pre-allocated pool node:

```c
oCEntitySpawnData spawn_data;
spawn_data.vtable   = oCEntitySpawnData::vftable;
spawn_data.position = chosen_or_sourced_vec3;     // +0x10
spawn_data.rotation = chosen_or_sourced_quat;     // +0x1c
spawn_data.scale    = (Vec3){1,1,1};              // +0x2c
node = oCSpawnablePool_allocateNode(prefab_resource + 0xb0);
spawner_subobj->vtable[0x18](spawner_subobj, node, &spawn_data);
```

Two static call-sites confirm the shape: `oCDtEntityCpntHeroSpawner_spawnHero @ 0x1402cd370` and `oCEntitySpawner_spawnEntityFromBoundTransform @ 0x1406eef40`. Both build the `oCEntitySpawnData` on stack from a getter (`+0x178` on the spawner) before calling `vtable[0x18]`. The position is supplied by the caller — i.e., the dispatch primitive itself accepts an arbitrary chosen Vec3.

`oCEntitySpawner_spawnEntityFromBoundTransform` is the single-entity worker; `FUN_1406f2c50` (renamed `oCTileSpawner_spawnAllTransforms`) is a batch variant that iterates a 0x40-byte transform array at `parent[+0x98]/+0xa0`, multiplies each by the parent's world matrix, and dispatches `vtable[0x18]` per entry — the likely TileSpawner / EnemyCamp multi-instance path.

### 4. Player position publish — global-value bus

`HC_per_frame_update @ 0x14038e260` reads the player's parent-entity Vec3 every frame via `parent->vtable[+0x48]` (a smaller data-class vtable, not the full `oCEntity` slot list) and publishes it to the global-value scene-context under hash `0x15c82040` ("Local player position"):

```c
plVar4   = *(longlong **)(HC + 8);                              // HC body+0x8 = parent entity
puVar10  = (undefined4 *)(**(code **)(*plVar4 + 0x48))(plVar4); // vtable[9] -> Vec3*
local_98 = *puVar10; local_94 = puVar10[1]; local_90 = puVar10[2];
global_value_publish_vec3(scene_ctx, 0x15c82040, &local_98);    // 0x1402b72e0
```

The Vec3 is wrapped in an `oCEntityValueUnion` envelope (kind=10 for Vec3, inline storage at `+0x10`). To read the published position from Frida without hooking the per-frame tick:

```
1. Find oCGlobalEntityValueSceneContext via scene_manager_find_context_by_type
   (or hook global_value_publish_vec3 once and capture param_1).
2. bucket = global_value_find_bucket_by_hash(global_value_ctx, 0x15c82040);   // 0x1401c6790
3. Vec3 = bucket + 0x10;                                                       // inline storage
```

Sibling hash: `0x18294f69` ("Player watching position").

### 5. End-to-end spawn-at-coord recipe

```
1. Resolve a prefab handle by path string (cross-chapter resolvability TBD; see Unresolved §A):
   - Walk g_global_type_registry_root @ 0x141446f38 for class with type-id 0x53b64d.
   - Call its vtable[3] with { begin, end } path strings.
   - Receive an oCEntitySettingsResource* handle (refcounted; refcount at +0x124).
   - Pre-existing recipe — see chapter-map-and-boss-spawn-architecture.md "Path-based loader."

2. Spawn the entity:
   - Locate an oCEntitySpawner instance bound to the desired prefab
     (Sc_FindGo / Sc_FindNearestGoContaining / Sc_FindAllGoContaining).
   - Call Sc_Spawn_impl @ 0x1406ef7c0 — entity instantiated at the spawner's bound transform.

3. Place at chosen coordinates:
   - Direct vtable call (cheaper):
       (*entity->vtable[+0x1a0])(entity, &(float[3]){x, y, z});
   - OR via Sc_ForcePosition_impl @ 0x14045fd70 with a (value_ptr, g_typeDesc_Vec3_direct) arg pair.

4. (Optional) Register to spatial partitioning:
   - register_entity_to_sectorization @ 0x1406efa70 (state 12 of level_load_orchestrator).
   - Sc_Spawn may already do this; calling again may double-register or no-op. Untested.
```

For reading the player's current position to use as the spawn target, see §4 — the global-value bus path is the cheapest.

**Confidence:** Steps 2–4 are confirmed by static decompile. Step 1's *cross-chapter* viability is the gating empirical question — a Frida test of `loadPrefabByPath("Map_Boss_Spawner_Storm_Island")` while in Dark Hills (per `tools/frida/mods/boss_rush.js` v0.5) is queued and answers it directly.

### 6. Camp generation is event-driven, not function-driven

State 11 of `level_load_orchestrator @ 0x140289b30` ("Generate enemy camps") publishes a named event via `publish_event_to_subscribers((sceneCtx)+0x340, &eventObj)` using event hash held at `g_eventHash_GenerateEnemyCamps @ 0x1412c09d8` (runtime-initialized; currently zero in the image). Pre-placed `oCDtEnemyCampEntitySelectorToSpawnEntityCpnt` instances subscribed to this event own the actual placement decision; each spawns its bound enemy prefab *at its own static position* via `oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20`.

There is **no high-level "place a camp at (x,y,z)" function**. To force a camp at a chosen location, the candidate paths are:

- **(a) Move an existing pre-placed selector before triggering.** Find the camp-selector entity, write its position via `vtable[+0x1a0]`, re-fire the camp-gen event. Cheapest. Untested.
- **(b) Construct a new selector at runtime.** Heavier; requires deep struct knowledge.
- **(c) Skip the selector entirely** — resolve an enemy prefab via the `0x53b64d` loader, `Sc_Spawn`, then `Sc_ForcePosition`. Bypasses camp semantics (no tier, no selector logic) but works at the per-enemy level. This is the recipe in §5.

## Unresolved

### A. Cross-chapter prefab resolvability via the path-based loader

The `0x53b64d` loader's vtable[3] takes a path string and returns an `oCEntitySettingsResource*` handle. Static analysis cannot determine whether the loader gates on the active chapter — i.e., whether `loadPrefabByPath("Map_Boss_Spawner_Storm_Island")` succeeds while Dark Hills is the loaded chapter. The boss-rush PoC test queued at `tools/frida/mods/boss_rush.js` v0.5 answers this directly:

- **Success** (non-null pointer, no crash) → cross-chapter loading works; boss-rush mod scope is full and the spawn-at-coord recipe step 1 is empirically validated for arbitrary paths.
- **Failure** (null or throw) → loader gates on active chapter; recipe step 1 is bounded to the current chapter's catalog.

### B. Replication behavior of `vtable[+0x1a0]` writes in MP

Per `multiplayer-host-authority.md`, host-authoritative state writes propagate via ReplicaManager3 if the field is replicated. Position is a strong candidate for being replicated, but verification requires running the test. Specifically:

- Does a host-side `setWorldPosition` on a hero entity propagate to peers automatically, or does it need a separate broadcast?
- For non-hero entities (camp enemies, boss spawners) — same question.

### C. `+0x178` (spawner-side getter) vs `+0x198` (entity-side getter) discrepancy

Agent A's decompile of `oCEntitySpawner_spawnEntityFromBoundTransform` reads the spawn transform via `parent->vtable[+0x178]`; Agents B and C confirmed `+0x198` as the entity-side getter used by the four script handlers. These are likely two different vtables (the spawner sub-object's vtable vs the entity's vtable), not contradictory observations — but a vtable-dump confirmation would close the question.

### D. Vtable[+0x1a8] semantics

Called immediately before `+0x198` in script handlers when sourcing position from another entity, but *not* when supplying a literal Vec3. Hypothesis: `refreshWorldTransform()` (force the cached transform to update before reading). Resolve by decompiling the implementation in `oCEntityCpnt3dNode::vftable`.

### E. Quat layout

`oCDtEntityCpntHeroSpawner_spawnHero` reads 4 floats from `vtable[+0x58]` (data-class vtable). Order (`{w,x,y,z}` vs `{x,y,z,w}`) not pinned. Verify by patching a known-orientation hero and inspecting the return.

### F. Local-hero entity acquisition

`HC_per_frame_update` reaches the parent-entity via `HC+8`, but the runtime path from a fresh Frida session to "the local hero entity" was not pinned in this session. Two candidate paths:

- From `oCDtEntityCpntHeroSpawner_spawnHero @ 0x1402cd370`, find where `param_1+0x68` (the spawner sub-object) caches the spawned-entity result.
- Hook `oCEntitySpawner_addSpawnedEntity @ 0x1406db390` and filter for hero-class spawns; the second arg is the new entity pointer.

### G. `Sc_Spawn` per-class signature

Per the prior, `Sc_Spawn` may be per-class — different entity classes register different implementations. The signature on the enemy/creature classes that matter for the recipe needs decompilation before Frida-calling.

## Notes

### Mode used during this session

All three Ghidra agents ran in read-only mode by design — no `rename_symbol`, `batch_rename`, `comments`, `create_function`, `create_data_var`, `patch_bytes`, `assemble_code`, or struct/type creation during analysis. Renames were proposed in the agents' final reports and applied as a single `batch_rename` at end-of-session after user approval. This avoided cross-agent identity drift during concurrent investigation.

### Annotations applied 2026-05-05 (this session)

22 renames proposed; 21 applied (one was a no-op — `0x140314e20` was already named `oIEntity_resolveBoundPrefab_byIndex` from prior work). Full list in `chapter-map-and-boss-spawn-architecture.md` §"Annotations applied 2026-05-05" (cross-referenced from there to keep this doc topic-focused).

Highlights specific to this finding:

| RVA | Name |
|---|---|
| `0x14045fd70` | `Sc_ForcePosition_impl` |
| `0x14045fc70` | `Sc_MoveTowards_impl` |
| `0x14045fe20` | `Sc_TranslatePosition_impl` |
| `0x1406ef7c0` | `Sc_Spawn_impl` |
| `0x1406ef5c0` | `oCEntitySpawner_spawnIfNotCached` |
| `0x1406eef40` | `oCEntitySpawner_spawnEntityFromBoundTransform` |
| `0x1406ef6c0` | `oCEntitySpawner_despawnAndUnregister` |
| `0x1406ef300` | `oCEntitySpawner_recomputeActivationGate` |
| `0x1406ef3a0` | `oCEntitySpawner_setActiveFlag` |
| `0x1406efcc0` | `oCEntitySpawner_clearAsyncIoVector` |
| `0x1406f2c50` | `oCTileSpawner_spawnAllTransforms` |
| `0x140289b30` | `level_load_orchestrator` |
| `0x140235940` | `register_oCDtEnemyCampEntitySelectorToSpawnEntityCpnt_class` |
| `0x1407fd1e0` | `Entity3dNodeLocator_transform_update_loop` |
| `0x140700ee0` | `Entity_teleport_profile_zone_enter` |
| `0x1406efa70` | `register_entity_to_sectorization` |
| `0x14038e260` | `HC_per_frame_update` (already partially named — confirmed) |
| `0x1402b72e0` | `global_value_publish_vec3` |
| `0x1401c6790` | `global_value_find_bucket_by_hash` |
| `0x141447dc0` | `g_typeDesc_oITransform3dAccess` |
| `0x141447448` | `g_typeDesc_Vec3_direct` |
| `0x1412c09d8` | `g_eventHash_GenerateEnemyCamps` |

### Recommended next analysis pass

1. **Frida sanity test of the spawn-at-coord recipe.** Pick a known-active spawner via `Sc_FindNearestGoContaining`, call `Sc_Spawn`, then `Sc_ForcePosition` with a chosen Vec3. Confirms §5 end-to-end. Highest leverage, smallest risk.
2. **Hook `oCEntitySpawner_addSpawnedEntity @ 0x1406db390`** for one chapter to capture every `(spawner, node, spawn_data)` triple. Exhaustive live spawn graph in one session.
3. **Hook `register_named_event @ 0x14067daa0`** during the `"Generate enemy camps"` profile-zone window to capture the camp-gen event hash and full subscriber list. Resolves the runtime-initialized `g_eventHash_GenerateEnemyCamps` and unblocks candidate path (a) in §6.
4. **Dump `oCEntitySpawner::vftable`** (RTTI string `0x14130f300`) and enumerate per-subclass overrides of slots `[3]` and `[18]`. Resolves §C.
5. **Verify position-write replication in MP** by hooking `vtable[+0x1a0]` on host and peer simultaneously. Resolves §B.
6. **Locate the level-load enemy-camp generator** by walking xrefs from `oCDtEnemyCampEntitySelectorToSpawnEntityCpntSettings` constructors and `oCDtEnemyTribeDefinition` library lookups. Cross-reference against the level-load `"Generate enemy camps"` log site.
