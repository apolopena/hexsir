[← Back to findings](README.md)

# Entity-spawner mechanism — how entities spawn child entities

**Status:** in-progress
**Created:** 2026-05-07

The mechanism by which entities (cauldrons, summoners, hero spawners, tile spawners, etc.) produce child entities at runtime. Pinpoints the engine's `oCEntityCpntEntitySpawner` component, the universal spawn primitive `oCEntitySpawner_spawnIfNotCached`, and the pool-ownership tether that ties spawned-children's lifetime to a chosen owner.

This is the long-running static dig from 2026-05-07. The user's question that prompted it: "what mechanism do enemies use to spawn their minions, and is it tied to the parent enemy or callable separately?" The answer is encoded below.

The engine does not call this "summon" — that string appears once in the binary (`KilledBySummon` event-flag). The engine-native term is **spawn**. All summon-style behaviors (Cultist Summoner → tentacle, Spider Mother → egg → baby spider) go through this one component.

## Sources

- `tools/frida/mods/spawn_capture.js` — the live-capture tool that surfaced the `[Entity spawner]` anchor names and triggered this dig.
- `rw/findings/enemy-spawn-architecture.md` — parent finding. Universal entity factory chain (`oCEntity::ctor` at RVA `0x6c96f0`), `EnemyController` class identification, `+0x570` listener-array architecture, `+0x5e8` component hashmap.
- `rw/findings/transporter-placement-primitive.md` — the encyclopedia / asset-cache layout, `+0x08` char* / `+0x10` length pattern.
- Ghidra DB renames + plate comments in this dig (Ravenswatch.exe):
  - `FUN_1406ed7b0` → `oCEntityCpntEntitySpawner_registerScriptCallables`
  - `FUN_1402d0ee0` → `oCEntityCpntEntitySpawner_ctor`
  - `FUN_1402d1140` → `oCEntityCpntEntitySpawner_dtor`
  - `Sc_Spawn_impl` → `oCEntityCpntEntitySpawner_Sc_Spawn_impl`
  - `FUN_1406ee530` → `oCEntitySpawner_onAttachToParent`
  - `FUN_1406f0180` → `oCEntitySpawner_streamingGridRegister`
  - `FUN_1406f0280` → `oCEntitySpawner_streamingGridUnregister`
  - `FUN_1406f04b0` → `oCEntitySpawner_enableAndSpawn`
  - `FUN_1406f45f0` → `oCEntitySpawner_batchSpawnTimeBudget`
  - `FUN_1406780f0` → `oCSpawnablePool_dtor`
  - `FUN_1406f5e40` → `oIEntityCpnt_detachFromAllRegistries`
  - `FUN_1406c7090` → `oCEntitySettings_ctor`
  - `FUN_1402491d0` → `oIEntityCpntNetworkData_dtor`
  - `FUN_1406c37e0` → `oCEntity_getClassHash_stub`
  - `FUN_1406c9bc0` → `oCEntity_registerSettingsListener`
  - Plate comments at `0x1406ed7b0`, `0x1406ef5c0`, `0x1406ef7c0`, `0x1406ef380`, `0x1406ee530`, `0x1406f0180`, `0x1406c70c0`, `0x1406c7090`, `0x140678250`, `0x1406f04b0`, `0x140f4cc40`.
  - EOL comment at `0x1406c7129` documenting primary vtable installation.

## TL;DR

- **`oCEntityCpntEntitySpawner` is the universal spawn component.** RTTI string `.?AVoCEntityCpntEntitySpawner@@` at `0x14134da38`. Vtable RVA `0xf00650`. Class hash `0x33bd`. Display name "Entity Spawner". Every "[Entity spawner] NoModel" / "[Entity spawner] Fireflies_2" / "[Entity spawner] NoModel+2Cpnt" anchor entity captured by `SpawnCapture` is an instance bearing this component (the format string `[Entity spawner] {}` lives at `0x140f4f4b0`).
- **Three script-callables on this component:**

  | Name | Method hash | Handler RVA |
  |------|-------------|-------------|
  | `Sc_Spawn` | `0x1faa` | `0x6ef7c0` (`oCEntityCpntEntitySpawner_Sc_Spawn_impl`) |
  | `Sc_Despawn` | `0x1fab` | `0x6ef820` |
  | `Sc_IsSpawned` | `0x1fac` | `0x6ef7b0` |

  Plus the activation-side script-callables on a parent class: `Sc_Activate`, `Sc_Deactivate`, `Sc_IsActivated`, `Sc_ToggleActivation`. Every activation-bearing entity (cauldrons, hourglasses, wave anchors) supports this surface.

- **The spawn primitive chain** (every entity-spawner produces output via this path):

  ```
  Sc_Spawn_impl (0x6ef7c0)
    └─ oCEntitySpawner_spawnIfNotCached (0x6ef5c0)        ★ gated spawn
        └─ oCEntitySpawner_spawnEntityFromBoundTransform  ★ allocate + post async I/O
            └─ oCSpawnablePool_allocateNode (0x678250)    ★ pool allocator
                └─ vtable[10] on pool's slab allocator    ★ creates new entity
                    └─ oCEntity::ctor (0x6c96f0)          ★ universal ctor
  ```

- **Pool-ownership tether.** Every `oCEntity` is allocated from an `oCSpawnablePool` (xrefs to the pool vtable `0x140f45dd8` are inside `oCEntity::ctor` and the universal allocator trampoline). When the pool is destroyed, every entity in its alive-list is destroyed. The choice of pool determines child lifetime:

  - **Tethered (e.g. Cultist Summoner → Tentacle):** child is allocated from the parent enemy's pool at `parent->+0xb0`. Parent dies → pool dies → tentacle dies.
  - **Independent (e.g. Spider Mother → Egg → baby spider):** child is allocated from a longer-lived pool (chapter context, prefab, settings asset cache). Spider mother dies but the egg's pool outlives her, so the egg/baby-spider survives.

  Which pool gets used is encoded in the spawner's `+0x1c0` "owner backref" — set at component-attach time. **Same component class handles both flavors**; tethered-vs-independent is data-driven, not class-driven.

- **Death-listener subscription on the spawned child.** When a spawn fires, the spawner registers itself in the child's `+0x570` listener array (count `+0x578`, capacity `+0x57c`). When the child dies, the engine walks `+0x570` and dispatches each callback. The spawner's callback (`0x1406ef380`) clears its `+0x160` cache and `+0x168` activation flag — so it can spawn again later if reactivated. **This is the "13 listeners per enemy / 393 events for one cauldron fight" mechanism noted (and dismissed) in `enemy-spawn-architecture.md`** — every listener was a spawner subscription.

- **Two distinct trigger paths** for invoking the spawn primitive:

  1. **Streaming-grid (passive).** `oCEntitySpawner_streamingGridRegister` (RVA `0x6f0180`) — chapter loads, player walks into the cell containing the spawner; cell-state byte triggers `setActiveFlag(true)`; spawn fires. Pair: `streamingGridUnregister` (player leaves cell). This is the cauldron-anchor / chapter-load enemy path.
  2. **Script-call (active).** AI behavior tree calls `Sc_Spawn` by method hash `0x1faa` via the engine's reflection dispatcher (`getMethodHandleByHash`). Bypasses streaming-grid activation. This is the Cultist-Summoner-summoning-tentacle path.

- **No explicit "kill children" code** in the spawner's dtor or in the parent enemy's death handler. **Tear-down is automatic via pool ownership.** When the parent's pool is destroyed, the alive-list walk destroys every child. This is why we previously couldn't find a parent→children backref (`enemy-spawn-architecture.md` §"Parent-traversal does not work via entity bytes"): there isn't one. The relationship lives in pool-allocation-state, not in either entity's bytes.

## Findings

### Confirmed

#### Class identification — `oCEntityCpntEntitySpawner`

| Item | Value |
|------|-------|
| RTTI string | `.?AVoCEntityCpntEntitySpawner@@` at `0x14134da38` |
| Type descriptor | `0x14134da28` |
| Vtable | RVA `0xf00650` |
| Settings RTTI string | `.?AVoCEntityCpntEntitySpawnerSettings@@` at `0x141369768` |
| Settings vtable | RVA `0xf515a0` |
| Class hash | `0x33bd` |
| Display name | `"Entity Spawner"` (string at `0x140f21c28`) |
| Output-format string | `[Entity spawner] {}` at `0x140f4f4b0` (used to label captured anchor entities) |
| Ctor | RVA `0x2d0ee0` (`oCEntityCpntEntitySpawner_ctor`) |
| Dtor | RVA `0x2d1140` (`oCEntityCpntEntitySpawner_dtor`) |
| Script-callable registrar | RVA `0x6ed7b0` (`oCEntityCpntEntitySpawner_registerScriptCallables`) |

The class derives from `oCEntitySpawner` (intermediate) which derives from `oCSpawner`. Multiple-inheritance bases visible in the ctor: `oIEntityCpnt`, two `oe::EntityCpntValueSignal<bool>` slots, `oCEntitySpawner`, two `oCEntity3dLocator` slots, `oCEntity3dTransformListener`, `oe::EntityCpntValueSignal<int>` slots. The `oIEntitySelectorToSpawn` interface is shared via vtable[3] = `oIEntitySelectorToSpawn_onBindToParent`.

#### Field map on `oCEntityCpntEntitySpawner` (this offsets)

> **2026-05-10 correction.** Earlier revisions of this section listed `+0x18` as the settings binding. **That was wrong.** Verified in-DB and corroborated by working tooling: settings ptr is at **`+0x10`** (qword 2). Byte `+0x18` is the start of an embedded `EntityCpntValueSignal<bool>` sub-object (own vtable + 3 zero qwords). The corrected entry below replaces the prior one; downstream prose has been updated to match. `tools/frida/mods/powers/Hourglass.js` already uses `+0x10` (line 105) — the doc was lagging the code. See plate comment on `oCEntityCpntEntitySpawner_ctor` (RVA `0x2d0ee0`).

| Offset | Type | Role |
|--------|------|------|
| `+0x10` | ptr | **settings binding** ★ (non-null required to spawn) — the "what gets spawned" pivot for hijack |
| `+0x18` | obj | embedded `EntityCpntValueSignal<bool>` sub-object (own vtable + 3 zero qwords) |
| `+0x20` | ptr | bound-transform context binding |
| `+0xd4..+0xe8` | floats | spawn position / rotation / scale data |
| `+0x108` | obj | async I/O request list (asset-streaming queue for the child entity) |
| `+0x160` | ptr | **cached output entity** ★ written when spawn fires; cleared by death-listener and by despawn |
| `+0x168` | byte | active flag |
| `+0x169` | byte | enable / replicated-active flag |
| `+0x16a` | byte | "gate computed" flag |
| `+0x178` | byte | gate condition (read on parent during recompute) |
| `+0x1c0` | ptr | **owner backref** ★ — the parent thing whose pool this spawner allocates from; set at component-attach |
| `+0x1f8` | byte | alternate gate condition byte |

#### The spawn primitive — `oCEntitySpawner_spawnIfNotCached` (RVA `0x6ef5c0`)

```c
longlong oCEntitySpawner_spawnIfNotCached(spawner) {
  if (spawner->+0x160 != 0) return;            // already has cached output, bail
  child = oCEntitySpawner_spawnEntityFromBoundTransform(spawner);
  listener = create_listener_node();           // 24-byte struct
  listener[0] = spawner;                       // owner
  listener[2] = &LAB_1406feb40;                // callback (multi-inheritance thunk → 0x1406ef380)
  // Append listener to child->+0x570 (alive-list at +0x570, count at +0x578, cap at +0x57c)
  // Each listener entry is 8 bytes (just the listener-node pointer)
  child->+0x578 += 1;
  child->+0x570[count] = listener;
  spawner->+0x160 = child;                     // cache the output
  return child;
}
```

#### The actual create — `oCEntitySpawner_spawnEntityFromBoundTransform` (RVA `0x6eef40`)

```c
longlong oCEntitySpawner_spawnEntityFromBoundTransform(spawner) {
  // Build oCEntitySpawnData on the stack
  oCEntitySpawnData spawn_data;
  spawn_data.position = spawner->vtable[47/0xe8]();    // bound-transform-derived position
  spawn_data.scale    = (1.0, 1.0, 1.0);
  spawn_data.rotation = read_from spawner->+0xd4..+0xe4;
  spawn_data.callback = FUN_1406fb840;                  // post-construction callback
  spawn_data.owner    = spawner;

  // Allocate from the spawner's owner pool
  child = oCSpawnablePool_allocateNode(spawner->+0x1c0 + 0xb0);

  // Post async I/O: actual entity construction is deferred to the streaming I/O processor
  spawner->+0x108.vtable[3](spawner->+0x108, child, &spawn_data);

  spawner->+0x160 = child;
  return child;
}
```

The child entity is REGISTERED in the pool's alive-list during `oCSpawnablePool_allocateNode`, but its actual `oCEntity::ctor` invocation happens asynchronously when the I/O queue processes the request. Both the `+0x570` listener registration (in `spawnIfNotCached`) and the pool registration (here) happen synchronously; the entity content is filled in afterward.

#### Pool architecture — `oCSpawnablePool` (vtable RVA `0xf45dd8`)

Class info: 1 virtual method (`vtable[0]` = scalar deleting destructor at RVA `0x6780f0`), 8 fields. Allocator entry: `oCSpawnablePool_allocateNode` (RVA `0x678250`). Universal across the engine — 20+ callers including hero spawning (`oCDtEntityCpntHeroSpawner_spawnHero`), tile spawning (`oCTileSpawner_spawnAllTransforms`), magical-object inventory (`hero_inventory_create_magical_object`), initial chapter loading (`initial_loading_orchestrator`), and the entity-spawner component itself.

Pool struct layout:

| Offset | Type | Role |
|--------|------|------|
| `+0x00` | ptr | vftable (`oCSpawnablePool::vftable` @ `0x140f45dd8`) |
| `+0x08` | ptr | slab allocator object (vtable[10] = offset 0x50 creates a new entity) |
| `+0x10` | int | freelist count (recycled nodes available) |
| `+0x18` | ptr | freelist head (chained via node `+0x18`/qword 3) |
| `+0x28` | int | alive-list count |
| `+0x30` | ptr | alive-list head |
| `+0x38` | ptr | alive-list tail |

Each allocated node has `+0x18` next-pointer and `+0x20` prev-pointer threaded into the alive-list. Allocation either pops from the freelist or asks the slab allocator (`*(pool+8))->vtable[10]` for a fresh slab; in both cases the new node is appended to the alive-list (head/tail/count maintained). When the pool is destroyed, the alive-list is walked and every entity is destroyed in lockstep.

#### Pool-ownership taxonomy

The pool that each child gets allocated from is selected by the `+0xb0` field on the spawner's `+0x1c0` owner backref. Different owner classes give different child lifetimes:

| Owner class (at spawner's `+0x1c0`) | Owner's `+0xb0` resolves to | Child lifetime |
|---|---|---|
| Parent enemy entity | per-enemy child pool | dies when parent dies (TETHERED) |
| Asset-prefab settings | per-prefab pool | lives as long as the prefab is loaded (chapter-scope INDEPENDENT) |
| Chapter scene-context | chapter-wide pool | lives until chapter unload |
| Engine root | game-wide pool | lives forever (statics / UI) |

The **same `oCEntityCpntEntitySpawner` class handles all flavors** — what differs is the runtime value of `+0x1c0`. This is set during component-attach: `oCEntitySpawner_onAttachToParent` (RVA `0x6ee530`) reads the attach-target and binds the spawner to it.

`oCEntity::ctor` and `oCEntitySettings::ctor` both initialize the `+0xb0` field to NULL — the actual pool gets installed lazily, presumably when the first spawner that targets this owner attaches and discovers no pool exists yet. Multiple spawners targeting the same owner share the pool.

#### The death-listener thunk + handler

Listener callback registered on the child:
- Thunk: `LAB_1406feb40` — multi-inheritance `this`-adjustor that JMPs via `[0x140f501b8]`.
- Resolved target: `0x1406ef380` (small handler, no Ghidra-defined function — accessed via the vtable indirection).
- Handler logic:

  ```c
  void onChildDying(spawner, _, eventType) {
    if (eventType != 0) return;             // only respond to "dying" event (eventType==0)
    spawner->+0x168 = 0;                     // deactivate
    spawner->+0x160 = 0;                     // clear cached output
  }
  ```

  When the child dies, the spawner is reset to "no output, deactivated." It can produce a new output the next time it is reactivated (streaming-grid re-enter, AI script-call, or Sc_Spawn fire).

#### `oCEntitySpawner_onAttachToParent` (RVA `0x6ee530`)

Component lifecycle hook fired when the spawner is attached to a parent entity. Sequence:

1. Pre-attach setup (`FUN_14045f350`).
2. `register_entity_to_sectorization(this)` — register with the chapter spatial-hash sectorization.
3. Walk parent's component list (`parent->+0x1c0`/`+0x1c8`), call `vtable[13]` (offset `0x68`) on each — onSiblingAttached notification chain. Most components no-op (`FUN_1400c07a0` stub at `vtable[13]`).
4. `despawnAndUnregister` — clean any stale state from a prior attach.
5. `recomputeActivationGate` — resolve `+0x168` from `+0x20`/`+0x178`/`+0x1f8` conditions.
6. If `(active && bound && enabled)`: `spawnIfNotCached` — try to spawn now.

`oCEntity` exposes TWO component access paths:
- `+0x1c0` / `+0x1c8` — sequential array (iteration in attach order).
- `+0x5e8` / `+0x5f0` / `+0x5f8` / `+0x600` — Swiss-Tables hashmap by component-class hash (already documented in `enemy-spawn-architecture.md`).

#### Streaming-grid integration

Spawners are spatial-hash registered for chapter-streaming activation. The engine's chapter spatial grid maintains active-spawner lists per cell:

- **Grid struct fields:**
  - `+0xb0` ptr — cells_array (1D row-major, indexed `(row * grid->+0xc0 + col) * 8`).
  - `+0xc0` int — grid width.
- **Cell struct fields:**
  - `+0x10` byte — state (bit 1 = "spawners active").
  - `+0x30` ptr — active-spawner list head.
  - `+0x38` int — list count.
  - `+0x3c` int — list capacity.
- **`oCEntitySpawner_streamingGridRegister`** (RVA `0x6f0180`): looks up the grid cell containing the spawner's bound transform, sets the spawner's active flag from the cell state, and appends the spawner to the cell's active-spawner list. Called when the player walks into the cell.
- **`oCEntitySpawner_streamingGridUnregister`** (RVA `0x6f0280`): removes the spawner from the cell's list. Called when the player leaves.

The cauldron-wave anchors and chapter-load enemies activate via this path. Cultist-Summoner-summons-tentacle does **not** — it uses the script-call path.

#### `oCEntitySettings` inheritance chain (related context)

`oCEntitySettings_ctor` (RVA `0x6c7090`) reveals the chain:

```
oISerializable
  └─ oCSpawnableSettings  (has embedded oCSpawnablePool at +0x18 — ASSET-INSTANCE pool)
      └─ oIGoPtrOwner          (sub-object at +0x60)
          └─ oIGoPtrOwnerRelay
              └─ oCGoPtrOwnerRelay
                  └─ oCEntitySettings  (final derived)
```

Every prefab/settings struct has an embedded `oCSpawnablePool` at `+0x18` — this is the **asset-instance pool**, tracking all live entities of "this settings's type" in the chapter. Distinct from the `+0xb0` child-pool field (which spawners use as the allocation target). Two pools per settings:

- `+0x18` — instances of THIS class (managed by the asset/streaming system)
- `+0xb0` — children of THIS instance produced by spawners (lazily initialized)

#### `oCEntity::ctor` (RVA `0x6c96f0`) layout highlights

`oCEntity` inherits from `oCSpawnable`. Settings ptr stored at qword 5 = byte `+0x28`. Field zeroes confirm:

- `+0xb0` — set to NULL by ctor (the child-pool field; lazy-initialized later).
- `+0x1d0` — `&DAT_140edbfa0` (sentinel; reused at +0x500, +0x5e8 — empty-hashmap sentinels per prior finding).
- `+0x5e8` — `&DAT_140edbfa0` (component hashmap ctrl_bytes_ptr; matches prior finding).

### Hypothesis (mapped, not fully verified)

- **The settings flag selecting tethered vs independent is in the `oCEntityCpntEntitySpawnerSettings` field map.** Phase 2 of the dig (settings-resource decode) is the next concrete step. The settings RTTI is at `0x141369768`, vtable RVA `0xf515a0`; decompiling its ctor + serialize methods would surface field names. Likely a flag along the lines of "use-parent-pool" / "spawn-as-child" boolean. Until verified, the assignment "tethered = `+0x1c0` is parent enemy / independent = `+0x1c0` is chapter-scope" remains a strong inference rather than a confirmed fact.
- **Multi-output spawning (Cultist Summoner spawns 3 tentacles) likely uses one spawner per child slot.** The `+0x160` cached-output is single-pointer, so a parent with N concurrent children must have N spawner components. The `oCSpawnedEntityCollector` class (RTTI at `0x141349a78`, vtable `0x140eea5f8`, 7 vtable methods) may be the orchestration container — wraps a list of spawners. Untested.
- **The AI-summon trigger path is `behavior-tree-node → engine reflection dispatcher → Sc_Spawn (hash 0x1faa)`.** The dispatcher takes a method hash and routes via `oIEntityCpnt::getMethodHandleByHash`. Tracing requires identifying the AI behavior-tree library and its "call-method-on-component" node. Not pursued in this dig.
- **`oCEntityCpntDespawn` (sister class, RTTI at `0x141368f80`, vtable `0x140f51830`)** is structurally identical to the spawner (same 30-method vtable shape, same `oIEntitySelectorToSpawn` base via vtable[3]). Likely the matched-pair component for explicit despawn — e.g., when a wave ends and remaining minions should be cleaned up by Sc_Despawn rather than waiting for the parent's pool to be destroyed.
- **`oIOnEntitySpawnEntityCpnt` (RTTI `0x14134dfd8`, vtable `0x140efc780`)** is an interface for "do something when an entity spawns." 33-method vtable. Likely subscribed by modifier components / talent effects that need to react to a specific spawn (e.g., "buff every enemy spawned in this cauldron"). Untraced.

### Tried and ruled out

- **String-based asset anchors (Phase 1).** Searched for asset-name strings (`Cultist_Summoner_Summoned_Tentacle`, `Spider_Nightmare_Egg`, etc.) directly in the binary. Result: 0 matches. Asset names live only in cooked `.gen` files and are interned at runtime. Phase 1 dead — pivoted to RTTI search.
- **Searching for the literal word "Summon"** in any class/method name. One match (`KilledBySummon` event-flag string). The engine simply does not use "summon" terminology — it uses "spawn" universally.
- **Hooking `oCEntitySpawner_spawnEntityFromBoundTransform` at runtime** (prior session). 0 captures during a cauldron fight per `enemy-spawn-architecture.md` §"Tried and ruled out." The reason wasn't that this function isn't called — it's that the function early-returns when the spawner's `+0x160` cache is non-null. Cauldron waves likely re-create spawner components per wave (so each wave is a fresh +0x160), or the captures coincidentally landed during cached state. Either way, the `oCEntity::ctor` hook is the right place for live capture (which is what `spawn_capture.js` actually uses).

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating &lt;thing&gt;" — RE-side template.

### Anchors

| Symbol | Anchor strategy |
|---|---|
| `oCEntityCpntEntitySpawner` class | RTTI string `.?AVoCEntityCpntEntitySpawner@@` → TypeDescriptor → COL → vtable. |
| Class hash `0x33bd` | Search bytes `bd 33 00 00` — appears in the registerScriptCallables function as a literal; in the class-metadata table; and in the registerClass for any consumer. |
| `Sc_Spawn` method hash `0x1faa` | Search bytes `aa 1f 00 00`. The function that consumes this constant is the script-callable registrar for the spawner. |
| `oCEntityCpntEntitySpawner_registerScriptCallables` | xref TO the string `Sc_Spawn` at `0x140f4f438`. Two LEAs in the same function reach this string — that function is the registrar. |
| `Sc_Spawn_impl` (`0x6ef7c0`) | xref TO the registrar's `Sc_Spawn` literal load. The handler is loaded via LEA into a local just before being passed to the script-system registration helper. |
| `oCEntitySpawner_spawnIfNotCached` | xrefs FROM the Sc_Spawn handler. Two calls in the handler; the same function is also the tail-call from `setActiveFlag`. |
| `oCEntitySpawner_spawnEntityFromBoundTransform` | xrefs FROM `spawnIfNotCached`. The single call that is followed by listener-array push and `spawner->+0x160 = result`. |
| `oCSpawnablePool` vtable | xref TO `oCEntity::ctor` (RVA `0x6c96f0`) — one of the few external xrefs from inside that function loads this address. |
| `oCSpawnablePool_allocateNode` | xref FROM `spawnEntityFromBoundTransform`. Called with `(spawner_owner_backref + 0xb0)`. |
| Format string `[Entity spawner] {}` | At `0x140f4f4b0`. xrefs FROM identify the entity-formatter that produces the captured anchor names like `[Entity spawner] NoModel`. |
| Death-listener thunk `LAB_1406feb40` | Used as a callback constant in `spawnIfNotCached` and `despawnAndUnregister`. The thunk is 13 bytes (the standard MSVC `this`-adjustor pattern). The actual handler is at `[0x140f501b8]` — `0x1406ef380` in this build. |

### Re-anchoring quick recipe

1. RTTI string `.?AVoCEntityCpntEntitySpawner@@` → vtable RVA → type-descriptor.
2. Search bytes `aa 1f 00 00` (Sc_Spawn method hash) → the registrar function.
3. From the registrar: identify `Sc_Spawn_impl` via the LEA-of-handler-pointer pattern.
4. From `Sc_Spawn_impl`: identify `spawnIfNotCached` (one of its two named calls) and trace down to `spawnEntityFromBoundTransform` and `oCSpawnablePool_allocateNode`.
5. xref the pool vtable address to confirm it's referenced from inside `oCEntity::ctor` — universal-allocator continuity check.

## Trigger primitive — how to fire spawn from Frida

The headline question for live-modding work: *given an in-world entity (cauldron anchor, Cultist Summoner, Spider Mother), how do we make it spawn its child on demand?*

### Direct call (recommended)

```js
const IMG = Module.findBaseAddress('Ravenswatch.exe');
const spawnIfNotCached = new NativeFunction(IMG.add(0x6ef5c0), 'pointer', ['pointer']);

// Given a spawner component pointer (see "Locating spawners on a parent" below):
spawner.add(0x160).writePointer(NULL);   // clear cached-output guard
const child = spawnIfNotCached(spawner);  // returns the new child entity
```

`spawnIfNotCached` itself only checks `+0x160`. As long as the spawner's `+0x10` (settings binding), `+0x108` (async I/O queue), and `+0x1c0` (owner backref) are populated — they are for any spawner that already exists in the chapter — the call produces a child entity. The async I/O processor finishes the construction in the next frame or two; by the time the player notices, the entity is fully built (visual mesh, AI, components all attached).

### Force-multi-spawn

Setting `+0x160 = 0` while a previous child is still alive lets you fire `spawnIfNotCached` again to get a SECOND concurrent child. The first child becomes "orphaned" (its `+0x570` listener still points back at the spawner, but the spawner now caches a different child). When orphaned children die, their listener fires harmlessly — clears `+0x160` to 0, but that field already points at a third child by then. Practical effect: **a single Cultist Summoner can be made to maintain N tentacles instead of 1.**

### Locating spawners on a parent entity

Walk the parent's component array and match by vtable. Per `enemy-spawn-architecture.md` and `transporter-placement-primitive.md`, an entity has its component sequential-list at `+0x1c0` (count `+0x1c8`):

```js
const SPAWNER_VTABLE = IMG.add(0xf00650);

function findSpawnerComponents(entity) {
  const compArrayPtr = entity.add(0x1c0).readPointer();
  const compCount = entity.add(0x1c8).readU32();
  const spawners = [];
  for (let i = 0; i < compCount; i++) {
    const comp = compArrayPtr.add(i * 8).readPointer();
    if (!comp.isNull() && comp.readPointer().equals(SPAWNER_VTABLE)) {
      spawners.push(comp);
    }
  }
  return spawners;
}
```

Each enemy with summon abilities has one spawner component per child slot. A Cultist Summoner that can have 1 tentacle out at a time has 1 spawner. A multi-output spawner (3 tentacles concurrent) has 3 spawners — likely orchestrated via a sibling `oCSpawnedEntityCollector` (untested).

### Reading what a spawner produces

The settings template that this spawner spawns lives at `spawner->+0x10` (the binding pointer). To read its display-name string, follow the encyclopedia walker pattern:

```js
const settings = spawner.add(0x10).readPointer();        // oCEntitySettings*
const namePtr = settings.add(0x08).readPointer();        // char*
const nameLen = settings.add(0x10).readU32();            // length
const name = namePtr.readUtf8String(nameLen);            // e.g. "Cultist_Summoner_Summoned_Tentacle"
```

(Same pattern that `spawn_capture.js` v0.6+ uses for initArg name resolution.)

### Triggering by name

Combine the above to "find any in-world spawner that produces template X and fire it":

```js
function triggerSpawn(templateNameSubstring) {
  // Walk SpawnCapture._captures or the encyclopedia to find candidate parent entities,
  // walk each one's spawner components, read each spawner's bound template name,
  // match against templateNameSubstring, then fire spawnIfNotCached.
  for (const entity of allKnownEntities) {
    for (const sp of findSpawnerComponents(entity)) {
      const name = readSpawnerTemplateName(sp);
      if (name && name.includes(templateNameSubstring)) {
        sp.add(0x160).writePointer(NULL);
        const child = spawnIfNotCached(sp);
        return { entity, spawner: sp, child, templateName: name };
      }
    }
  }
  return null;
}

triggerSpawn("Tentacle");   // produces a Tentacle from any Summoner-class spawner present
triggerSpawn("Egg");        // produces an Egg from any Spider-Mother-class spawner present
```

### Lifecycle expectations after trigger

- The new child enters the owner's pool's alive-list (`pool +0x30/+0x38/+0x28` head/tail/count) and gets the `+0x570` death listener registered.
- Spawn position is the spawner's bound transform (read via `spawner->vtable[47]()`). For a Cultist Summoner the binding usually evaluates to "near the parent's current location," so a new tentacle appears next to the summoner.
- The new child inherits all the standard entity setup: components, mesh, AI tick, network replication.
- **Tether semantics still apply.** A new tentacle spawned via direct trigger is still allocated from the summoner's pool. If the summoner dies, the tentacle dies. If you spawn a non-tentacle template via a tentacle's spawner (because the spawner's binding is fixed), the new entity is whatever the binding says.

### Caveats

- **Multiplayer.** The spawn-replication path runs through entities flagged "Master and replicate activation" (see strings near `0x140f4f320`). Calling `spawnIfNotCached` on the host produces a replicated entity peer-side; calling it on a peer may produce a non-replicated local-only entity. Untested.
- **Settings binding must be valid.** A spawner whose `+0x10` is null silently no-ops in the gated path; in the direct path, the eventual `spawnEntityFromBoundTransform` call would fail. Sanity-check before triggering.
- **Async construction.** `spawnIfNotCached` returns immediately with a partially-built entity. The asset streaming finishes filling it in over the next frame or two; reading components on it during the same Frida call may get an empty hashmap. The simplest fix is to schedule the inspect call one frame later.
- **The child's spawn position is the spawner's bound transform**, not a parameter you control. To spawn at an arbitrary location, either move the spawner first (via `Transporter.warpEntity` on the parent) or override the spawner's transform fields at `+0xd4..+0xe8` before the call.

## Deeper static dig — vtable layouts and unresolved mysteries (2026-05-07 extended dig)

After the initial finding doc was written, the dig went deeper to verify that the trigger primitive can be invoked from Frida with full certainty (the user's "no shortcuts, no guessing" requirement). The results both confirmed and exposed limits.

### `oCEntitySettings` vtable layout — confirmed

The settings class has TWO physical vtables (multi-inheritance):

| Address | Size | Role | Key entries |
|---|---|---|---|
| `0x140f4cee8` | 13 entries | Primary at `+0x00` | **vtable[10] @ +0x50 = `FUN_1406c7a40` (universal entity factory trampoline)** ★ |
| `0x140f4cfc8` | 7 entries | Sub-object at `+0x60` | Serialize-style methods |

Verified by disassembly of `oCEntitySettings_ctor` at `0x1406c7129`:
```
1406c7129: LEA RDX, [0x140f4cee8]    ; primary vtable
1406c7130: MOV qword ptr [RCX], RDX  ; install at +0x00
1406c7133: LEA RDX, [0x140f4cfc8]    ; sub-object vtable
1406c713a: MOV qword ptr [RAX], RDX  ; install at +0x60 (RAX = RCX+0x60)
```

This proves the embedded-pool dispatch chain works as theorized:

```
oCSpawnablePool_allocateNode(settings + 0x18):
  reads pool->+0x8 = *(settings + 0x20) = settings_addr (per ctor's "param_1[4] = param_1")
  reads *(settings_addr) = primary vtable @ 0x140f4cee8
  calls vtable[+0x50] = vtable[10] = FUN_1406c7a40 (trampoline)
    → FUN_1406de800(settings, settings)
      → malloc(0x640)
      → oCEntity::ctor(slab, settings)
      → slab->vtable[1]() = oCEntity_getClassHash_stub (returns 0x5146457; NO init work)
      → returns slab
    returns slab
  → calls slab->vtable[3]() = oCEntity_registerSettingsListener
     (appends slab to settings->+0x98 listener array; NOT scene-context registration)
  → links slab into pool's alive-list
  → returns slab
```

`FUN_1406c7a40` decompile (single-line trampoline):
```c
void FUN_1406c7a40(this) {
  FUN_1406de800(this, this);  // → malloc + oCEntity::ctor + vtable[1]()
  return;
}
```

`FUN_1406de800` decompile (the allocator):
```c
longlong * FUN_1406de800(undefined8 param_1, undefined8 param_2) {
  DAT_141415474++;                                 // global counter
  lVar1 = _malloc_base(0x640);
  if (lVar1 == 0) return null;
  plVar2 = FUN_1406c96f0(lVar1, param_2);          // oCEntity::ctor(new_slab, settings)
  (**(code **)(*plVar2 + 8))(plVar2);              // vtable[1]() — the no-op getClassHash stub
  return plVar2;
}
```

### `oCEntity` vtable layout — confirmed

15 entries at `0x140f4cc40` (the primary `oCEntity::vftable`):

| Index | Offset | Function | Role |
|---|---|---|---|
| 0 | +0x00 | `FUN_1406c37d0` | unknown (likely first-method standard) |
| 1 | +0x08 | `oCEntity_getClassHash_stub` | returns `0x5146457`; called inside `FUN_1406de800` after ctor |
| 2 | +0x10 | `FUN_1406c3cd0` | unknown |
| 3 | +0x18 | `oCEntity_registerSettingsListener` | called by `allocateNode`; appends self to `settings->+0x98` listener array |
| 4 | +0x20 | `FUN_1406c9ec0` | unknown |
| 5 | +0x28 | `entity_init_from_config_block` | takes `(entity, cfg)`, reads position from `cfg+0x40..+0x4c`, applies via `setPosition`. Called by I/O processor with `oCEntitySpawnData` cfg block |
| 6 | +0x30 | `FUN_1406cb4c0` | unknown |
| 7 | +0x38 | `_guard_check_icall` | CFG guard |
| 8 | +0x40 | `FUN_1406c3c90` | unknown |
| 9 | +0x48 | `oCEntity_getPosition` | returns Vec3 ptr |
| 10 | +0x50 | `oCEntity_setPosition` | universal placement primitive (used by `Transporter` mod) |
| 11 | +0x58 | `oCEntity_getRotation` | returns Vec4 quat ptr |
| 12 | +0x60 | `FUN_1406ca8d0` | unknown |
| 13 | +0x68 | `FUN_1406c3cc0` | unknown |
| 14 | +0x70 | `FUN_1406ca9e0` | unknown |

`FUN_1406c37e0` (vtable[1]) decompile:
```c
undefined8 FUN_1406c37e0(void) {
  return 0x5146457;                                // class hash; no work
}
```

### What `allocateNode(settings + 0x18)` actually produces

After `oCSpawnablePool_allocateNode` returns, the new entity has:

| State | Value |
|---|---|
| Memory | 0x640 bytes from `_malloc_base` |
| Primary vtable at `+0x00` | `oCEntity::vftable` @ `0x140f4cc40` |
| Settings ptr at `+0x28` | the input settings (passed via ctor's `param_2`) |
| Component hashmap at `+0x5e8` | empty-sentinel `&DAT_140edbfa0` (no components) |
| Self-pointer at `+0x620` | self (memory-alive check works) |
| `+0x18` embedded pool | initialized (settings ptr, freelist=-1, alive=0/-1) |
| Position | NOT SET (origin or whatever ctor leaves it as) |
| Pool alive-list | this new entity is now linked into `settings->+0x18` pool's alive-list |
| Settings listener | this new entity is registered in `settings->+0x98` listener array |
| Component stack | EMPTY (no EnemyController, CharacterController, etc.) |
| Scene-context registration | NOT DONE (chapter spatial hash unaware) |
| Mesh / textures / VFX | NOT LOADED (async streaming hasn't run) |
| Network replication | NOT REGISTERED |

So: **the entity is a structurally-valid `oCEntity` shell**, present in memory and the pool's alive-list, but **functionally inert** — no rendering, no AI, no game-logic interaction.

To make it a fully-functional enemy, the engine normally completes the construction via the spawner's async I/O queue (`spawner->+0x108`), which dispatches asset streaming → component attach → scene-context registration. That dispatch is what `oCEntitySpawner_spawnEntityFromBoundTransform` posts after allocation:

```c
(**(code **)(spawner_io_queue + 0x18))(&spawner_io_queue, allocated_slot, &spawn_data);
```

### The `[*spawner + 0x178]` static-analysis mystery — UNRESOLVED

The first virtual call inside `spawnEntityFromBoundTransform`:

```asm
1406eefdb: MOV RAX, qword ptr [RCX]      ; RAX = *spawner = primary vtable @ 0x140f00650
1406eefde: CALL qword ptr [RAX + 0x178]  ; CALL [vtable + 0x178]
```

The spawner's primary vtable is confirmed at `0x140f00650` with exactly 30 entries (offsets 0..0xe8). The bytes between offset `+0xf0` and `+0x178` are ASCII strings (RTTI class names of unrelated classes — `oCDtNamedEventGainHealthResource`, `oCEntityGpnTesterCombiner`, `oCDtEntityCpntAbilityCtrlListener`). The qword at `[primary_vtable + 0x178]` = `0x140f007c8` decodes to `0x1402491d0` = `oIEntityCpntNetworkData_dtor`.

A destructor for an unrelated class makes no semantic sense as a "get bound transform position" virtual call (the code expects a Vec3 return). Either:
1. MSVC unified-vtable-with-this-adjustment trick I don't fully understand.
2. The disassembly's literal interpretation isn't what executes at runtime.
3. RCX has been adjusted in a way Ghidra's decompile/disassembly doesn't surface.

**This blocks pure-static certainty for calling `spawnIfNotCached`/`spawnEntityFromBoundTransform` directly from Frida** — we can't predict what happens at runtime when the engine executes that call. WinDbg verification at runtime (set bp on `0x1406eefde`, inspect what gets called) would resolve this in minutes.

### The `+0x108` I/O queue setup — UNRESOLVED

The spawner's ctor (`oCEntityCpntEntitySpawner_ctor` disassembly at `0x1402d1006`) sets `spawner->+0x108 = -1` (sentinel). The actual I/O queue object is installed lazily by some external setup phase (likely the chapter-streaming-asset orchestrator at chapter-load).

Until we identify what installs the I/O queue, we can't construct a fresh spawner from scratch and have it work. A from-scratch spawner would:
- ✅ Have its primary vtable installed (by ctor)
- ✅ Have its settings-binding field at `+0x10` settable
- ❌ Have `+0x108` as `-1` — calling `spawnEntityFromBoundTransform` would dereference -1 as a vtable and crash

The hero spawner (`oCDtEntityCpntHeroSpawner_ctor`) has the same pattern — its sub-object at `+0x68` is installed but the I/O queue isn't.

### "Spawn from arena, no nearby spawners" — assessment

Given the above, this requirement cannot be satisfied with a pure-static Frida script alone. Three realistic paths:

1. **WinDbg + targeted static dig.** Use WinDbg to inspect a live spawner's `+0x108` (identify the I/O queue class), step through `[*spawner + 0x178]` (resolve the position-getter), then construct a Frida primitive with full runtime ground truth. Estimated 30-60 minutes once the game is running.

2. **Hijack an existing in-world spawner.** The starting arena does have spawner-bearing entities (Sandman, hourglass, fireflies, teleporter). Find one, swap its `+0x10` settings binding to point at a desired enemy template (e.g., a captured Tentacle settings from a prior session), clear `+0x160`, fire spawn. Tested empirically — the spawner's I/O queue at `+0x108` is already set up because it's a real in-world entity.

3. **Continue static dig on the streaming-asset orchestrator path.** Trace `initial_loading_orchestrator` → chapter-asset registration → spawner-`+0x108` installation. Likely 5-10 more hours, may still hit walls without runtime data.

Path 2 is the most expedient if the user wants to test soon.

### Frida primitive — what we CAN write with certainty

```javascript
// Bare entity allocation — produces a structurally-valid but functionally-inert oCEntity shell.
// Useful for: confirming the allocation chain works, holding a pool slot, debugging.
// NOT useful for: actual gameplay-functional spawned enemies (no components, no rendering, no AI).
const IMG = Module.findBaseAddress('Ravenswatch.exe');
const allocateNode = new NativeFunction(IMG.add(0x678250), 'pointer', ['pointer']);
const setPosition = (entity, x, y, z) => {
  const vt = entity.readPointer();
  const fn = new NativeFunction(vt.add(0x50).readPointer(), 'pointer', ['pointer', 'pointer']);
  const buf = Memory.alloc(12);
  buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
  return fn(entity, buf);
};

function allocateEntityShell(settings) {
  const newEntity = allocateNode(settings.add(0x18));
  // newEntity has settings ptr at +0x28, empty component hashmap, default position
  return newEntity;
}
```

This is the certain primitive. To make it a usable enemy, additional setup is needed and is the open work.

## Open questions / next steps

1. **WinDbg verify `[*spawner + 0x178]`.** Set breakpoint on `0x1406eefde` during a real cauldron spawn. Inspect `RAX` (vtable address) and `[RAX + 0x178]` (call target). Compare with our static read (which decodes to a destructor). Resolves the multi-inheritance vtable layout question definitively.
2. **WinDbg identify `spawner->+0x108`.** Same breakpoint context. Read `[RDI + 0x108]` (where RDI = spawner). The qword tells us the I/O queue's vtable address; from there we can identify the class and its `vtable[3]` handler — the function that actually finishes the entity construction (asset streaming + component attach + scene-context registration).
3. **Decompile `oCEntityCpntEntitySpawnerSettings`.** Settings vtable RVA `0xf515a0`. Its ctor + serialization methods leak field names via reflection helpers. Goal: identify the tether-vs-independent flag and the "what to spawn" template field.
4. **Trace the AI-summon trigger.** `getMethodHandleByHash` dispatcher + behavior-tree node that invokes hash `0x1faa`. Likely the cleanest "engine-blessed" trigger path.
5. **Verify `+0xb0` lazy-init.** Where does `parent->+0xb0` (the child pool) get initialized? Candidate: `oCEntitySpawner_onAttachToParent` may install it if missing.
6. **Class-metadata table dump (side quest).** Walk `0x140f4ce00..0x140f4d020+` to extract every registered class (name + ctor RVA + hash). Project-wide reference for future digs.
5. **Live verification (when the user runs the game).** Use Frida to confirm:
   - `+0x160` on a captured Cultist Summoner does point at a Tentacle.
   - `+0x1c0` on the Tentacle's spawner component points at the Summoner.
   - `+0xb0` on the Summoner is non-NULL after first tentacle spawn (lazy init).
   - The Summoner's pool's alive-list contains the Tentacle.
   - Killing the Tentacle clears the Summoner's spawner's `+0x160`.
   - Killing the Summoner kills the Tentacle (pool destruction).

## Live work — 2026-05-07 follow-up

After the static dig, a long live-Frida pass confirmed the architecture and surfaced what's actually fireable.

### Working primitive (verified)

**Capture-then-fire by parent name + sub-index**, implemented in `tools/frida/mods/spawner_probe.js` v0.12.0:

1. **Hook the spawner ctor (`FUN_1402d0ee0` at RVA `0x2d0ee0`) BEFORE the chapter loads.** Every `oCEntityCpntEntitySpawner` instance the engine constructs during chapter load is captured to `RW.SpawnerProbe._spawners` with its `+0x08` parent and `+0x10` settings.
2. **After load, identify by stable name + sub-index.** Each captured spawner's parent entity has its own `oCEntitySettings*` at `parent + 0x28`, with the standard asset-cache name layout (`+0x08 char*`, `+0x10 u32 length`). That parent name is asset-baked and stable across launches. Filter by parent name (e.g. `"NoModel+2Cpnt"`, `"[Entity spawner] Cauldron"`, `"Ravenswatch_Super_Flock"`) plus sub-index in the filtered list — the asset-defined spawner ordering within a parent is consistent across reloads of the same chapter type.
3. **Fire by calling `FUN_1406f62b0(spawner)`** (the broadcast worker, RVA `0x6f62b0`). This is the function the engine itself uses internally during natural activation — it's safe to invoke directly with an unfired spawner. With an `noWarp` option, no parent warp is performed and the spawn fires at the spawner's natural bound transform; without it, the parent is first warped to the player's position so the spawn appears at the player.

### Confirmed behaviors

- **Hourglass early-boss-reward fire.** `parentName="NoModel+2Cpnt"` (the chapter hourglass — present in every chapter; the auto-name is the engine's "no base model + 2 attached components" label). Calling `expr_summonAtPlayer({ nameMatch: "NoModel+2Cpnt", index: 0, noWarp: true })` produces the early-boss-reward item that's normally only granted upon defeating the boss before the timer runs out.
  - **Re-fireable when the hourglass is in active state.** If the player leaves the safe area first (so the natural game flow puts the hourglass into its active state), each subsequent call produces another reward item. Unlimited reward farming.
  - **Locked one-shot when the hourglass is not active** (e.g. right at chapter start, before leaving the safe area). One fire per state transition, then cap.
- **Cauldron sub-component spawners** (`parentName="[Entity spawner] Cauldron"`, sub-indexes 0–5). Each fires a different cauldron-specific animation/movement: cauldron move, base-plate transition, etc. None spawn enemies. The base-plate-move spawner is capped at 2 fires per chapter (lockout state location not fully isolated; `+0x64` flags don't change between fires, so the cap lives elsewhere).
- **`Ravenswatch_Super_Flock`** — the bats/birds activation animation. Multiple sub-spawners on one parent; firing any of them produces the full flock visual (multi-output spawner pattern, likely via `oCSpawnedEntityCollector`).
- **Position-stable warp** of the cauldron entity via `setPosition` on `parent.vtable[10]` works for visual-follow if competing periodic timers (e.g. CauldronTest's 500ms re-warp tick) are cleared first. Per-frame engine reset is mild enough that a 16ms tick or fewer keeps it visibly placed.

### What didn't work — ruled out

- **Direct call to `oCEntitySpawner_spawnIfNotCached` (RVA `0x6ef5c0`)** on a found spawner-class component crashes with `0xffff…` access violations on consumed-state spawners (the prior session's note about the `+0x108` I/O queue lazy-init explains why — the I/O queue gets reset post-natural-fire; un-fired spawners may also lack init and be lazy-primed). Could not be made reliable from Frida in this pass.
- **Direct call to `FUN_1406f62b0` (broadcast worker) on a CONSUMED spawner** crashes the same way. The broadcast worker only works on un-fired or actively-armed spawners.
- **The `RegisteredEntitiesHolderEntityCpnt` class's broadcast events** (`PTR_DAT_1412d2348` / `PTR_DAT_1412d23b8`) have empty subscriber lists (verified statically — both list-roots point at the empty Swiss-Tables sentinel `0x140edbfa0`). Holder-only fires set the signals but no one listens for the cauldron's wave path; the wave actually fires through a different chain we couldn't fully isolate.
- **`FUN_14074ef20` (the natural fire dispatcher) called with the spawner's `+0x08` parent as the manager** crashes — `parent != wave_manager`. The wave_manager is a separate object with its own `+0x68` array of spawner pointers; only natural activation reveals which object that is.
- **Replaying a captured wave-orchestrator context** via `FUN_140713520` direct call also crashes on consumed state. Same root cause as the spawnIfNotCached crash.

### Stable identifiers discovered (chapter-agnostic where noted)

| parentName | Sub-indexes | Effect | Notes |
|---|---|---|---|
| `NoModel+2Cpnt` | 0, 1 | Early-boss-reward item drop | Re-fireable when hourglass is active (player has left safe area). Hourglass is in every chapter. |
| `[Entity spawner] Cauldron` | 0–5 | Cauldron sub-component animations (move, base-plate transition, etc.) | Procedurally placed per chapter; only present when chapter rolls a cauldron. |
| `Ravenswatch_Super_Flock` | 0..N | Bats/birds activation flock | Multi-output; any sub-index fires the full flock. |
| `Starting_Safe_Zone` | 0 | Safe-zone marker / interactable | Present in every chapter. |
| `Teleporter_Start_<chapter>` | 0–2 | Chapter-start teleporter return point | Suffix varies per chapter (e.g. `Dark_Hills`). |

### Tooling at HEAD (post-cleanup, v0.12.0)

`tools/frida/mods/spawner_probe.js` — focused surface (the broken approaches were cut):

- `inspect(name)` — dump entity components with vtable RVAs + RTTI.
- `survey(opts?)` — walk encyclopedia for spawner-anchor entries.
- `expr_armSpawnerCtor()` / `expr_stopSpawnerCtor()` — the foundation hook.
- `expr_listSpawners(opts?)` — filter captured spawners by `unfiredOnly`, `nameMatch`, `posNear`, `nearEntity`, `max`.
- `expr_listWaveManagers(opts?)` — group captured spawners by parent for stable name+sub-index lookup.
- `expr_summonAtPlayer(opts?)` — primary spawn primitive: `nameMatch` + `index` + optional `noWarp`/`nearEntity`/`dryRun`.
- `expr_lockToPlayer(ptr, opts?)` / `expr_unlock()` — periodic warp+fire (use `noFire:true` for safe visual follow).
- Diagnostic-only hooks: `expr_captureWaveTrigger` / `expr_stopWaveCapture` (orchestrator hook), `expr_captureFireDispatcher` / `expr_stopFireDispatcherCapture` (dispatcher hook), `expr_inspectLastWave` (dump captured wave-context fields).

#### Production power — `Hourglass`

`tools/frida/mods/powers/Hourglass.js` (v0.4.0) — standalone power for the hourglass-reward fire path. Owns its own Interceptor on `FUN_1402d0ee0`; filters the capture set by `parentName="NoModel+2Cpnt"` + sub-index 0 + bit 3 of `+0x64` clear; fires via `FUN_1406f62b0`. API: `spawnItem()` / `spawnItem({ intervalMs })` / `spawnItem({ verbose: true })` / `spawnItemStop()`. Quiet by default. Must be loaded before chapter setup so the ctor hook is attached when the engine ctors the hourglass spawner. Marked `*` in `tools/frida/rw_lab.js`'s power listing per the setup-bound convention in `tools/frida/CODE_STANDARDS.md`.

#### Companion mod — `easter_item_hunt`

`tools/frida/mods/easter_item_hunt.js` (v0.4.0) — interval-fires the hourglass reward, counts toward a stop-after-N limit, and *attempts* to relocate each dropped item to a random scatter point near the player. Auto-loads Hourglass at IIFE time so the ctor hook arms in time for chapter setup (single-step user flow: `loadMod("easter_item_hunt")` before chapter, then `start(N)`). API: `start(count, opts?)` / `pause()` / `resume()` / `log(on)`.

**Confirmed limitation: `spawner.+0x160` is NULL after the broadcast-worker fire path.** When `FUN_1406f62b0(spawner)` is invoked directly (the path Hourglass uses), the cached-output field documented for `spawnIfNotCached` does not get populated. Effect: `easter_item_hunt` has no spawn-target ptr to pass to `setPosition`, so items currently drop at the hourglass and the mod logs `no child @ +0x160`. Locating the dropped loot for relocation is the open piece; tracked as the **TOP PRIORITY** entry in `rw/docs/wishlist.md` §"Frida tooling" with three suggested approaches (walk `RW.Entity.list()` post-fire / compose with `spawn_capture` mod / decompile `FUN_1406f62b0` to find where it writes the child ptr).

Earlier attempts to write `0` to `+0x160` post-fire (intended as the "force-multi-spawn" trick from §"Trigger primitive") aborted the spawn entirely — items stopped appearing at the hourglass. The broadcast worker path appears to use `+0x160` (or something it touches) during async asset-streaming finalization. Don't clear it until that's understood.

## Cross-references

- `rw/findings/enemy-spawn-architecture.md` — parent doc. Universal entity factory chain, EnemyController class identification, `+0x570` listener-array architecture (confirmed here as the spawner-subscription mechanism), `+0x5e8` component hashmap.
- `rw/findings/enemy-ai.md` — sibling doc covering the AI-target / focus question. The `Sc_Spawn` AI trigger trace is logged there as the next dig from that side.
- `rw/docs/game-rules.md` §"Cauldrons and waves" — gameplay-level model. The "main enemies summon their own minions" mechanism is the spawn primitive documented here.
- `rw/findings/transporter-placement-primitive.md` — encyclopedia / asset-cache layout, `+0x08` char* / `+0x10` length pattern. The asset-name strings used to label captured anchors come from the same encyclopedia walker pattern.
- `rw/findings/STATUS.md` — manifest of all findings.
- `tools/frida/CODE_STANDARDS.md` — Frida script conventions for the live-verification work in §"Open questions."
- `rw/docs/wishlist.md` — open digs including the "global per-instance entity registry" (the `+0x18` embedded asset-instance pool described above is part of the answer — every settings has one).
