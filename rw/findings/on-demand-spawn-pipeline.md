# On-demand entity spawn pipeline (encyclopedia + factory)

**Status:** in-progress
**Created:** 2026-05-08

## Sources

- `Ravenswatch.exe` (Ghidra static analysis)
- `rw/findings/telemetry-surface-and-warden.md` (prior session — adjacent context only)
- `rw/findings/entity-spawner-mechanism.md` (parallel agent — adjacent; not consulted directly)

## Confirmed Findings

### Two distinct spawn paths exist; SOLO must use the factory path

The engine has two entity-spawn entry points that look superficially similar but are NOT
interchangeable:

| Path | Entry function | Use case | Notes |
|---|---|---|---|
| **Factory (SOLO/canonical)** | `oCSpawner_createEntityFromSettings` @ `0x1406db260` | Level-load Bark spawn, `oCEntitySpawner_dispatchSpawn`, 7 other call sites | Calls the world-binder which fully wires the entity into the scene |
| Replication (multiplayer-only) | `oCEntityReplicaFactory_spawnByName_remote` @ `0x1407088f0` | Network deserializer | Allocates + parent-list-binds, but **does NOT call the world-binder** — entity is inert without further bookkeeping |

The replication path is invoked only by `oCEntityReplicaFactory_serializeOrSpawn` @ `0x140703b40`,
which then calls `oCEntityReplicaFactory_registerSpawnRecord` @ `0x1406ec330` to track the spawn
for peer replication. Neither call is meaningful in solo play.

### Factory signature (the SOLO path)

```c
oCEntity* oCSpawner_createEntityFromSettings(
    oCSpawner*         spawnerSubobj,    // embedded sub-object; oCDtRootGs+0x248 is the master scene's
    oCEntitySettings*  settings,         // template/prefab pointer
    oCEntitySpawnData* spawnData,        // 0x68-byte transform/parent block
    void*              parentRef         // NULL OK (Bark spawn passes 0)
);
```

Internal flow:
1. `lVar4 = oCSpawnablePool_allocateNode(settings + 0x18)` — slab-allocates a fresh `oCEntity`. `oCEntitySettings` has its embedded `oCSpawnablePool` at `+0x18`.
2. If `parentRef != NULL`, register a death-listener at `entity+0x588`.
3. `(*spawnerSubobj->vt[3])(spawnerSubobj, entity, spawnData)` — the world-binder.

### oCSpawner is a sub-object class, embedded at multiple sites

Found via triangulating the 9 callers of the factory:

- `oCDtRootGs+0x248` — master scene's spawner (used by level-load Bark)
- `oCEntityCpntEntitySpawner+0x68` — game-object spawner's sub-spawner (overwritten with `oCEntitySpawner::vftable`)
- Other containers embed it at varying offsets

The base class `oCSpawner` (RTTI `0x141332740`, vftable `0x140eb15c0`) has `vt[3]` =
`oCSpawner_addEntityIntoWorld` @ `0x140678ab0` — the world-binder. The derived
`oCEntitySpawner` (vftable `0x140ee0e60`) overrides this with
`oCEntitySpawner_addSpawnedEntity` @ `0x1406db390`, which differs only by a "default-owner if
NULL" optimization at the top.

### oCSpawner::vt[3] (world-binder) body

```c
void oCSpawner_addEntityIntoWorld(oCSpawner* spawner, oCEntity* entity, oCEntitySpawnData* spawnData) {
    // 1. Add entity to spawner's child list
    //    count @ spawner+0x18, tail @ +0x20, head @ +0x28
    //    entity->prev = old tail; old tail->next = entity (or head if first)

    // 2. Install death-listener thunks on entity
    //    entity[+0x38] = spawner   entity[+0x48] = LAB_140681be0
    //    entity[+0x50] = spawner   entity[+0x60] = LAB_140681c00

    // 3. ★ Call entity->vt[5] = entity_init_from_config_block — consumes spawnData
    (*entity->vt[5])(entity, spawnData);
}
```

### oCEntitySpawnData layout (0x68 bytes — confirmed via consumer)

The consumer is `entity_init_from_config_block` @ `0x1406cb380` (= `oCEntity::vt[5]`).

| offset | size | field | required? |
|---|---|---|---|
| `+0x00` | 8 | vftable (`oCEntitySpawnData::vftable`) | yes (header) |
| `+0x08` | 8 | owner/settings ref | NULL OK (Bark uses 0) |
| `+0x10` | 12 | **position** (3 floats) | required |
| `+0x1c` | 12 | **rotation Euler XYZ** (3 floats) | required (`(0,0,0)` for identity) |
| `+0x2c` | 12 | **scale** (3 floats) | required (`(1,1,1)` for unscaled) |
| `+0x38` | 8 | parent entity ref | NULL OK (`oCEntity_setParent_or_clearIfNull` has explicit NULL branch at `0x1406cb1d0`) |
| `+0x40` | 16 | 4 dwords (IDs/flags) | zero OK |
| `+0x50` | ~16 | listener block | zero OK |

The level-load Bark spawn confirms zero-position / zero-rotation / unit-scale / NULL parent works
in production.

### Encyclopedia name lookup primitive

`oCEntitySettingsEncyclopediaSceneContext` (RTTI `0x141346298`) holds a Swiss-style hashmap of
`name → settings_ptr`. Reachable via `scene_manager_find_context_by_type`.

Hashmap layout at `encyc + 0x28`:

| offset | content |
|---|---|
| `encyc+0x28` | control bytes pointer |
| `encyc+0x30` | slots pointer (each slot 0x18 bytes: `[+0x00]=key.data`, `[+0x08]=key.size`, `[+0x10]=settings_ptr`) |
| `encyc+0x40` | capacity / sentinel offset |

Lookup recipe (from `oCEntityReplicaFactory_spawnByName_remote`, reusable for solo):

```c
hash = fnv_string_hash_64(name.data, name.data + name.size);  // @ 0x140507510
hashmap_find_string_keyed_node(encyc + 0x28, &iter, &name, hash);  // @ 0x1406a0680

if (iter[0] == *(encyc + 0x28) + *(encyc + 0x40)) return null;  // not found sentinel
if (iter[1] + 0x10 == 0) return null;
settings = *(iter[1] + 0x10);
```

The encyclopedia is populated by `EntitySettings_onLoad_registerToEncyclopedia` @ `0x140703920`
when an entity-settings asset is loaded. **Naturally enforces "Chapter 1 assets only":** if an
asset isn't loaded for the current chapter, its name returns null.

### Reverse lookup (settings → name)

Each `oCEntitySettings` stores its registry name at `*(*(settings + 0x1c0) + 0x250)` (a
`std::string`). So any in-world entity can be inspected for its prefab name via its
`+0x28` settings pointer.

### Entity layout (0x640 bytes, fully decoded)

`oCEntity_ctor` @ `0x1406c96f0` zeros the full structure and installs `oCEntity::vftable`
@ `0x140f4cc40`. Selected fields documented in the ctor's plate comment in Ghidra. Key offsets:

| offset | meaning |
|---|---|
| `+0x00` | vtable |
| `+0x28` | settings ptr |
| `+0x38, +0x48, +0x50, +0x60` | death-listener slots (filled by world-binder) |
| `+0xb8` | parent-listener-context (multiplayer-only; not cleared on freelist pop) |
| `+0x158/+0x160/+0x170` | component hashmap (zero on fresh entity → empty) |
| `+0x208` | settings-listener block (registered by `vt[3]`) |
| `+0x240..+0x24c` | 4 dwords from `spawnData+0x40` |
| `+0x324..+0x32c` | position xyz (writable via `oCEntity_setPosition` / `vt[10]`) |
| `+0x3a8` | broadcast handler list (movement events) |
| `+0x570..+0x57c` | death-listener array head/count/cap |
| `+0x5d8/+0x5e0` | parent list head/count |
| `+0x600` | component-hashmap control bytes (used by replica path) |

### oCEntity vtable slots

`oCEntity::vftable` @ `0x140f4cc40`:

| slot | offset | function | purpose |
|---|---|---|---|
| 1 | `+0x08` | `oCEntity_getClassHash_stub` (`0x1406c37e0`) | returns `0x5146457`; no-op (called by deep allocator) |
| 3 | `+0x18` | `oCEntity_registerSettingsListener` (`0x1406c9bc0`) | called once on fresh alloc; registers settings-change listener |
| 5 | `+0x28` | `entity_init_from_config_block` (`0x1406cb380`) | consumes `oCEntitySpawnData` |
| 10 | `+0x50` | `oCEntity_setPosition` (`0x1406ca7f0`) | writes xyz at `+0x324` |
| 12 | `+0x60` | setRotation (`0x1406ca8d0`) | consumes Euler XYZ at `spawnData+0x1c` |
| 14 | `+0x70` | setScale (`0x1406ca9e0`) | consumes vec3 at `spawnData+0x2c` |

### Freelist staleness is NOT a concern for the factory path

`oCSpawnablePool_allocateNode` does NOT call `vt[3]` for freelist-popped entities (only for fresh
allocations). This means `entity+0xb8` (parent-listener-context) and the settings-listener
registration can be stale on freelist pops. Verified safe for the factory path because:

- The pool is per-settings (embedded in `settings+0x18`), so freelist pops always come back to
  the same settings type — registered listeners are still valid.
- `entity+0xb8` is only read by the multiplayer-only `oCEntityComponent_setReplicaParent` and
  `oCEntity_initSubsystemBindings_perComponent` (which has a NULL guard). Neither is on our path.
- The world-binder resets all 4 death-listener slots (`+0x38, +0x48, +0x50, +0x60`) every spawn.

### Sectorization registration is a separate, opt-in step

`register_entity_to_sectorization` @ `0x1406efa70` is called by level-load AFTER all entity
creation, in a loop gated by a type-test against `DAT_141447bc8` (the
`g_typeId_isSectorizable_filter` global). The function is **always-safe to call** — for entities
whose settings type doesn't carry a sectorization-registrar, it returns silently. For enemy-like
entities, this is what makes them visible to AI nav and spatial queries.

**Recommendation:** call `register_entity_to_sectorization(entity)` after every spawn in the Frida
primitive. No-op on entities that don't need it.

### Enemy registry shape (oCTLibrary<oCDtEnemyDefinition>)

`oCDtEnemyDefinitionLibrary_init` @ `0x140229990` (formerly `FUN_140229990`) constructs the
library at boot:

- Library global root: `DAT_1414479d8`
- All-libraries list head: `DAT_1414475d8` (libraries link via `lib[0xa]/[0xc]`)
- EnemyDef stride: `0x350` bytes (set via `vt[0xd8](lib, 0x350, 8)`)
- Type-id: `0x176debb7`
- Registered under string `"oCDtEnemyDefinition"` via `vt[0x10]`

Each `oCDtEnemyDefinition` carries a settings handle at `[0x57]` (qword `+0x2b8`). Level-load
filters this corpus by tier / boss-flag / chapter custom-flags and pushes survivors as
`oCEntitySettingsRootPtr` nodes onto `scene+0x328` (head) / `+0x330` (tail) / `+0x320` (count).
That post-filter list is the chapter's "legal enemy spawn corpus" — alternative path to the
encyclopedia for enemy-only spawning.

## Unresolved

- **`oCEntitySpawnData::vftable` exact RVA** — referenced from level_load_orchestrator's stack
  builder but not statically extracted. Easy to read at runtime via Frida.
- **`_oCTKindOfTypeTester<oCEntitySettingsEncyclopediaSceneContext>::vftable` exact RVA** —
  same situation; constructed inline as `{vftable, type-id}` struct on stack in
  `EntitySettings_onLoad_registerToEncyclopedia`. RTTI string at `0x141369840`.
- **Asset-streaming kickoff** — strong inference that `vt[3]`'s settings-listener registration IS
  the streaming trigger via the listener pattern. Empirical confirmation pending live test.
- **Whether the entity will tick / render without manual sectorization registration** — unknown;
  `oCEntity_VelocityUpdate_loop` and `Entity3dNodeLocator_transform_update_loop` iterate
  user-provided arrays whose population mechanism wasn't fully traced. Live test will resolve.
- **Cross-chapter asset loading** — out of scope per user direction. Encyclopedia naturally
  enforces "currently-loaded only," which IS the legal-spawn boundary.

## Notes

### Recommended Frida primitive shape

```js
function spawnByName(scene, name, x, y, z) {
    const tester = buildEncyclopediaTypeTester();
    const encyc = scene_manager_find_context_by_type(scene, tester);
    if (!encyc) return null;

    const nameStr = makeStdString(name);
    const hash = fnv_string_hash_64(nameStr, nameStr.add(name.length));
    const iter = Memory.alloc(16);
    hashmap_find_string_keyed_node(encyc.add(0x28), iter, nameStr, hash);

    const ctrlPtr = iter.readPointer();
    const sentinel = encyc.add(0x28).readPointer().add(encyc.add(0x40).readU64());
    if (ctrlPtr.equals(sentinel)) return null;

    const slot = iter.add(8).readPointer();
    const settings = slot.add(0x10).readPointer();
    if (settings.isNull()) return null;

    // Build oCEntitySpawnData (0x68 bytes)
    const spawnData = Memory.alloc(0x68);
    spawnData.writeByteArray(new Uint8Array(0x68));
    spawnData.writePointer(oCEntitySpawnData_vftable);
    spawnData.add(0x10).writeFloat(x);
    spawnData.add(0x14).writeFloat(y);
    spawnData.add(0x18).writeFloat(z);
    // rotation +0x1c..+0x27 = (0,0,0) — already zero
    spawnData.add(0x2c).writeFloat(1.0);
    spawnData.add(0x30).writeFloat(1.0);
    spawnData.add(0x34).writeFloat(1.0);

    const spawner = scene.add(0x248);
    const entity = oCSpawner_createEntityFromSettings(spawner, settings, spawnData, NULL);
    if (entity) register_entity_to_sectorization(entity);
    return entity;
}
```

### Testing approach (proposed)

A non-mutating discovery script first, to plug the two remaining unresolved-vtable-address gaps
without committing to a spawn:

1. Walk the encyclopedia hashmap, log all `(name, settings_ptr)` pairs.
2. Read `*(scene + 0x248)` for the live `oCSpawner` instance, log its vtable.
3. Read `oCEntitySpawnData::vftable` from one of the level-load stack-build sites.
4. Read existing in-world entity layouts to confirm field offsets.

Then a spawn test in Chapter 1 with a known-loaded settings (e.g. picked from the encyclopedia
walk).

### RVA reference table

| Symbol | RVA | Purpose |
|---|---|---|
| `oCSpawner_createEntityFromSettings` | `0x6db260` | The factory (was `FUN_1406db260`) |
| `oCSpawner_addEntityIntoWorld` | `0x678ab0` | `oCSpawner::vt[3]` body (was `FUN_140678ab0`) |
| `oCSpawnablePool_allocateNode` | `0x678250` | Slab allocator |
| `oCEntity_ctor` | `0x6c96f0` | Entity ctor (was `FUN_1406c96f0`) |
| `oCEntity_alloc_ctor_postInit_trampoline` | `0x6de800` | Deep allocator (was `FUN_1406de800`) |
| `oCEntity_setPosition` | `0x6ca7f0` | Position setter |
| `entity_init_from_config_block` | `0x6cb380` | `oCEntity::vt[5]` — spawnData consumer |
| `oCEntity_setParent_or_clearIfNull` | `0x6cb1d0` | Parent setter (was `FUN_1406cb1d0`) |
| `oCEntity_registerSettingsListener` | `0x6c9bc0` | `oCEntity::vt[3]` — fresh-alloc post-init |
| `scene_manager_find_context_by_type` | `0x653f80` | Scene context lookup |
| `hashmap_find_string_keyed_node` | `0x6a0680` | Swiss-table find |
| `fnv_string_hash_64` | `0x507510` | Name hasher |
| `EntitySettings_onLoad_registerToEncyclopedia` | `0x703920` | Encyclopedia populator |
| `EntitySettingsEncyclopedia_registerByName` | `0x6eb7e0` | Encyclopedia register |
| `EntitySettingsEncyclopedia_unregisterByName` | `0x6ebfb0` | Encyclopedia unregister |
| `register_entity_to_sectorization` | `0x6efa70` | Spatial-index register (always-safe) |
| `oCEntityReplicaFactory_spawnByName_remote` | `0x7088f0` | **MULTIPLAYER ONLY — do not use for solo** |
| `oCEntityReplicaFactory_serializeOrSpawn` | `0x703b40` | MP deserialize wrapper |
| `oCEntityReplicaFactory_registerSpawnRecord` | `0x6ec330` | MP spawn-record bookkeeping |
| `oCDtEnemyDefinitionLibrary_init` | `0x229990` | Boot init for enemy registry |
| `oCEntity::vftable` | `0xf4cc40` (data) | Entity vtable |
| `oCSpawner::vftable` | `0xeb15c0` (data) | Spawner sub-object vtable |
| `oCEntitySpawner::vftable` | `0xee0e60` (data) | Derived spawner vtable |

### Globals

| Global | Address | Meaning |
|---|---|---|
| `g_oCDtEnemyDefinitionLibrary` | `0x1414479d8` | EnemyDef registry root |
| `g_oCTLibrary_listHead` | `0x1414475d8` | All-libraries linked-list head |
| `g_emptyVectorOfEnemyDefPtr_default` | `0x141411ae0` | Sentinel returned when registry is empty |
| `g_typeId_isSectorizable_filter` | `0x141447bc8` | Type-id used to gate sectorization registration |
| `g_typeId_replicaParentFilter` | `0x1414477f8` | Type-id used by replica parent setter |
