[← Back to findings](README.md)

# Chapter map binding and boss-spawn architecture

**Status:** in-progress
**Created:** 2026-05-04

## Sources

- `Ravenswatch.exe` (Ghidra MCP — string scan, byte-pattern xrefs, decompile of `chapter_end_work`, `publish_map_name_event`, `session_on_boss_fighting`, `BossTimer_update`)
- `rw/findings/chapter-boss-portal-trigger.md` — the upstream trigger event (`0x17d8d901`) and field map for the `BossTimer` instance
- `rw/findings/multiplayer-host-authority.md` — context on `forceBossSpawn` exercising arrival path from the host side
- In-game observation by user, 2026-05-04: all four chapter boss arenas reuse the same arena assets; only the post-fight epilogue differs per chapter

## Goal / scope

Initial-research dig to scope a future "boss-rush mod" — fight all four chapter bosses back-to-back in one chapter without the normal map-transition flow. The dig was boss-centric but surfaced several engine-flow facts not previously captured in this repo (chapter-map binding, level state machine, randomized next-chapter selection, named-event subscriber substrate). This document captures both the boss-relevant material and the broader engine context discovered en route, so future digs aren't redundant.

Status `in-progress` because the actual boss-spawn mechanism (the working hypothesis at the bottom) is not yet verified and the mod itself isn't designed yet.

## What's confirmed

### 1. Four chapter maps, name-bound by table

A static table at `0x140eea480` lists the four chapter map names and parallel stat hashes used by `publish_map_name_event @ 0x140291560`.

| Index | Map name | Per-map stat hash |
|---|---|---|
| 0 | `Dark_Hills` | `0x193495c2` |
| 1 | `Storm_Island` | `0x193495c4` |
| 2 | `Avalon` | `0x1a597765` |
| 3 | `Baba_Yaga_Map` | `0x1b677eca` |

Strings live at `0x140eedbc0..0x140eedbf0`; the parallel hash array is at `0x140eea740`. The lookup is by string-compare on the current map's runtime name (no chapter-index path through this table); the matched index then selects a stat hash that gets written via `FUN_140204e30(scene, 0x193495b8, hash_value)` for analytics or progression bookkeeping.

The table size is fixed at 4 entries — checked by the loop's hardcoded upper bound `0x140eea4bf`. There is no fifth chapter slot in the binary's static data.

### 2. Each chapter is a `.level.ot` scene loaded by `LevelGs`

The level state machine (string blob at `0x140ef6e10..0x140ef7390`) drives load through:

```
StateLoadingResource → StateDownloading → StateResourceLoaded
   → StateWaitAllPeerLoaded → StateSpawnUiIn → StateSpawnUiTransition
   → StateInGame → StateDespawnUiIn → StateSpawnUiOut → StateDespawnUiOut
   → _Unload
```

Per-load steps logged include `MapDefinition loading`, `Generate enemy camps`, `Generate rewards`, `LoadAndGetRandomHeroEntity`, `Rebuild navmesh`, `Rebuild terrain`, `AddMasterLevel`, `Register game objects to sectorization`. There is no separate "boss load" step — boss entities arrive with the map.

The four chapter map names from §1 are *not* hardcoded as `.level.ot` paths in `Ravenswatch.exe`; only UI-level paths appear hardcoded (`Hero_Photo_Cabin.level.ot`, `MainMenu.level.ot`, `Common_Settings.level.ot`). Chapter map paths are resolved via the data-driven asset system (`oCDtMapDefinition`).

`oCGameLevelDatabase` distinguishes **Master levels** from **Streamed levels** (strings `Mater level {0}`, `Master levels count`, `Streamed level {0}`, `Streamed levels count`, `Remove Level`, the load step `Level load - AddMasterLevel`). The engine supports holding multiple levels active simultaneously — relevant to mod-design alternatives.

### 3. Chapter-end flow is randomized next-map selection

`chapter_end_work @ 0x1402907e0`:

- Reads current chapter index from `session+0xa0` (also exposed via `GameModeDefault_copy_chapter_index @ 0x14031bc40` which copies a 32-bit value at struct offset `+0x40`).
- Calls `set_chapter_counter_publish_event(session, chapter_index + 1)` to advance the counter.
- Calls `lookup_run_state_by_index(GameModeDefault.factory, chapter_index)` and caches the run-state pointer at `session->slot+0x1a0`.
- Maps chapter-index → difficulty score: `1→3, 2→6, 3→9`, written at `g_game_profile_data_manager+0x230`. (No mapping for index 4 — implies Baba Yaga / chapter-4 is handled differently or is treated as a special endgame slot.)
- Calls `update_difficulty_high_water_mark(session)`.
- **Picks the next chapter map at random** from a hashmap-backed pool stored at `scene_manager+0x738`. The selection is `tls_random_modulo` over an SSE-vectorized iteration (16-byte stride; pool entries are `(key, map_handle, _)` triplets at 0x18 each in a deeper structure).
- Reads modifier-stat values at hashes `0x1ab183ab` and `0x1ab58780` as gates that toggle which selection branch runs (likely "is end of chapter" vs "is end of run"), then publishes an `oCGameNamedEvent` to the encyclopedia subscribers via `publish_event_to_subscribers @ 0x140652b60`.

Implication: chapter slot does **not** deterministically map to a single map. The map pool is per-context and pre-built; this matches in-game behavior where consecutive runs visit different second/third chapter maps.

### 4. Session-side boss state machine — bookkeeping only

`session_on_boss_fighting @ 0x140282df0` runs *after* the boss is spawned and combat starts (it is not the spawn path). It:

- Reads four boss-progress floats from the global-entity-value scene context: `0x1cdf6e90`, `0x1cc8c666`, `0x1cd7923b`, `0x20220b3c`. Computes `progress = clamp(boss_a / (boss_b - boss_c), 0, K)` and writes it at `g_game_profile_data_manager+0x240`.
- Sets `g_game_profile_data_manager+0x23c = 1` (one-shot "ratio cached" gate).
- Zeros five session state-bag flags (`0x181d17fe`, `0x181d17ff`, `0x181d1800`, `0x181d180d`, `0x181d1801`) and sets `0xf122efd2 = 1` via `FUN_140204ca0(scene, hash, value)`.
- Sets `session+0x1a9 = 1` ("in boss fight").
- Triggers another named event `0x25c606ac` and writes `"boss.fighting"` to the property bag.

None of this loads or selects the boss prefab. It's pure transition bookkeeping on the engine state-bag.

### 5. Named-event substrate — subscribers cannot be enumerated statically

The boss-arrival event `0x17d8d901` ("Boss time start", string at `0x140ef2048`) is fired by `BossTimer_update` via `fire_named_event @ 0x14067dea0`. A byte-pattern search for the hash bytes `01 d9 d8 17` finds **only** `BossTimer_update` and `BossTimer_register_stats_and_events` — no third site.

Subscribers register through the substrate's runtime API (`register_named_event @ 0x14067daa0`), keyed by hash. The hash is computed at registration time from the event-name string read out of level data (asset definitions). The hash never appears as a static constant in subscriber code, so static analysis cannot enumerate listeners.

To enumerate subscribers in practice: hook `register_named_event` from Frida and filter on hash `0x17d8d901` during chapter level load. The substrate vtable family includes `oCGameNamedEvent::vftable` (used by `publish_event_to_subscribers @ 0x140652b60`) and class `oCDtNamedEventLevelUp` (string at `0x140effd70`) for level-up named-event subclassing.

### 6. Boss arenas — shared scenery, per-chapter tile + spawner entity

User-observed 2026-05-04: the four chapter boss arenas look visually identical; only the post-fight epilogue cinematic differs per chapter.

Asset-tree inspection (`rw/ref/tree-deciphered.txt`) refines this: the arenas share *scenery and props* but each chapter has its own boss-arena `.level.ot` tile and its own boss-spawner entity definition. The shared layer is in `_Cooking/3D/Scenery/Common!Boss_*` (claws, ground rim, transitions), `_Cooking/3D/Mechas/BossShrine!*` (the central shrine, with per-chapter material variants), and `_Cooking/3D/Mechas/BossClawTerrain!*` (the animated arena-floor breakup). The per-chapter layer is:

| Chapter | Map | Boss-arena tile | Boss-spawner entity |
|---|---|---|---|
| 1 | DarkHills | `Tiles!40x40_Boss_Shrine_WhiteLady.level.ot` | `Map_Boss_Spawner_Dark_Hills.entity.ot` |
| 2 | Storm_Island | `Tiles!40x40_Jinn_Boss_Shrine_Arena.level.ot` | `Map_Boss_Spawner_Storm_Island.entity.ot` |
| 3 | Avalon | `Tiles!40x40_Witch_Boss_Shrine.level.ot` | `Map_Boss_Spawner_Avalon.entity.ot` |
| 4 | Baba_Yaga_Map | (separate Outside/Interior arena, see below) | `Baba_Yaga_Boss_State_Listener_Model.entity.ot` |

The `Map_Boss_Spawner_Model.entity.ot` is the shared base entity (likely carries the `0x17d8d901` subscriber graph); the three per-chapter variants override per-chapter properties (which boss prefab, arena binding, etc.). Sibling files in the same family:

- `Map_Boss_Spawner_Cinematic_Awakening.entity.ot` — the awakening cinematic. This is the most likely actual subscriber to `0x17d8d901`.
- `Map_Boss_Spawner_Cinematic_Dying.entity.ot` — base "boss dying" cinematic.
- `Map_Boss_Spawner_Cinematic_Dying_Chapter3_Model.entity.ot`, `_To_BabaYaga.entity.ot`, `_To_Score.entity.ot` — chapter-3 branching: after the chapter-3 kill, route to Baba Yaga (chapter 4) or to score screen.
- `Map_Boss_Spawner_Claw_Model.entity.ot`, `Map_Boss_Spawner_Claw_Storm_Island.entity.ot` — boss-claw arena transformation; Storm Island has a custom variant.

Baba Yaga deviates from the per-chapter `Map_Boss_Spawner_*` pattern: it has `Baba_Yaga_Boss_State_Listener_Model.entity.ot` and a separate Outside/Interior arena structure (`Baba_Yaga_Outside_Arena_Barrier.entity.ot`, `Yone_Render_Setting_Baba_Yaga_House_Arena.entity.ot`, `Yone_Render_Setting_Baba_Yaga_Interior_Arena.entity.ot`). Consistent with chapter 4 being treated as endgame in the `chapter_end_work` difficulty mapping (which only covers chapters 1-3).

The four chapter boss assets:

| Chapter | Boss codename | Per-chapter enemy entity prefix |
|---|---|---|
| 1 (DarkHills) | "WhiteLady" | (asset prefix not yet enumerated) |
| 2 (Storm_Island) | "Jinn" | `_Cooking/3D/Characters/Enemies!Jinns!Animations!JinnsBoss_*` |
| 3 (Avalon) | "Witch" (Morgana) | (asset prefix not yet enumerated) |
| 4 (Baba_Yaga_Map) | "BabaYaga" | `_Cooking/EntitySettings/Enemies/Baba_Yaga_Boss!*` (multiple sub-entities — minigun eye, summoned eye, summoned tentacle, hot soup wave, skull projectiles) |

Mini-bosses also exist as separate tiles (`Crab_Mini_Boss_Den_Entrance` on Storm_Island, `Boss_Ghoul_Den_Entrance` on DarkHills, `Avalon_Wolf_Boss_Den_Entrance` on Avalon). These are world-map encounters, not chapter bosses — distinct progression role.

## Working hypothesis (unverified)

If reading (b) holds, the most likely chapter→boss resolution mechanism is **`EntitySwitchSelectorToSpawnEntityCpnt`** (RTTI at `0x141367dd8`, settings type `EntitySwitchSelectorToSpawnEntityCpntSettings`). This is a generic engine component that picks one of N entities to spawn based on a switch input. A boss-arena that uses this with chapter-index as the switch would cleanly explain the shared-arena observation: same arena scene, four spawner entries, current chapter selects which one fires when `0x17d8d901` arrives.

If this is the path:

- A "boss-rush" mod could stay in one chapter's arena, override the switch selector's chosen index after each boss death, reset the BossTimer state, and re-fire `0x17d8d901`.
- The mod also needs to suppress chapter-end on each kill except the last (post-kill flow eventually routes through `chapter_end_work` and the run-state advance).

If reading (a) holds instead, the four bosses are independent prefabs embedded in their own maps, and the mod must additionally either (i) load the relevant boss prefab into the active scene at runtime, or (ii) layer the other chapters' arena sub-levels via `AddMasterLevel`. Both are heavier than (b).

## What changes for a boss-rush mod

Independent of which reading is correct, the live mod needs:

1. **Boss-prefab override** — the route differs by reading: switch-selector index forcing (b) vs entity injection (a).
2. **Chapter-end suppression on each non-final kill** — prevent the normal post-boss flow from ending the chapter and triggering the next-map-selection in `chapter_end_work`. The kill itself fires the chain that eventually calls `session_on_abandoned_dispatch` / `session_on_saved_dispatch`; intercepting before chapter-end is more surgical than after.
3. **BossTimer reset between fights** — set `is_boss_awaken (+0x148) = 0`, `boss_just_awoke (+0x14a) = 0`, restore `elapsed (+0x12c)` below `boss_time (+0x144)`, then `forceBossSpawn` again. (`is_in_overtime (+0x149)` may also need clearing.) Field map already documented in `chapter-boss-portal-trigger.md`.
4. **Session boss-state flags reset** — clear `session+0x1a9` and the state-bag flags written by `session_on_boss_fighting` (`0x181d17fe..0x181d1801`, `0x181d180d`, `0xf122efd2`) before the next fight, or the second fight will start in a degenerate state.

(3) and (4) only matter if the underlying mechanism is (b). Under (a), each "next boss" requires a full level-stream load, which carries its own initialization.

## Cinematic-as-load-cover (boss arrival)

User-corrected understanding 2026-05-04: "Animation screens before you encounter them" — the boss-arrival cinematic IS the load cover. The engine sync-loads boss-arena assets during the cinematic's playback duration; the player perceives the cinematic, the engine streams.

Asset evidence: `Map_Boss_Spawner_Cinematic_Awakening.entity.ot` is a peer of the per-chapter `Map_Boss_Spawner_<Chapter>.entity.ot` files. Likely flow: subscriber on `Map_Boss_Spawner_<Chapter>` (inherited from `Map_Boss_Spawner_Model`) listens for `0x17d8d901`; on fire, starts the awakening cinematic; CineBlocs inside the cinematic load + activate + spawn the boss.

Engine-side scripting API (the `Sc_*` script-binding family at strings `0x140f...`):

| API string | Method ID | Implementation | Semantics |
|---|---|---|---|
| `Sc_RequestSyncLoadData` | `0x228a` | `0x1408605d0` | Refcounted sync-load. `++[this+0x124]`; if was 0, jump-tail to actual load at `0x140860410`. Otherwise return — already loaded. |
| `Sc_RequestSyncUnloadData` | `0x228b` | `0x1408605f0` | Refcounted unload. `--[this+0x124]`; calls actual unload at `0x1408604e0` only when refcount transitions 1→0. |
| `Sc_Spawn` | `0x1faa` | `0x1406ef7c0` | Multi-step entity-spawn (sets flags at `+0x168/+0x169`, tail-calls activator at `0x1406ef5c0`). |
| `Sc_Despawn` / `Sc_IsSpawned` / `Sc_Activate` / `Sc_Deactivate` / `Sc_Apply` / `Sc_Unapply` | various | (registrations not yet decoded) | Symmetric per-entity controls. |

These bindings live in registration tables consumed by the script-method-binding system at `0x140865da0`. The `Sc_*` family is the canonical entry point for cinematic CineBlocs to load assets and spawn entities — meaning CineBlocs inside `Cinematic_Awakening` call these directly.

**Implication for the boss-rush mod**: load is refcount-based, so calling `Sc_RequestSyncLoadData` on an arbitrary boss/arena/cinematic resource handle from Frida won't conflict with the engine's own ref-tracking. The natural mod flow:

1. Frida-resolve resource handles for the next chapter's boss prefab + arena tile + cinematic.
2. Call `Sc_RequestSyncLoadData` on each (engine streams; UI cover comes from our own faded cinematic, or the existing chapter's awakening cinematic re-fired).
3. Call `Sc_Spawn` to instantiate the new boss in the current arena.
4. After kill, `Sc_Despawn` + `Sc_RequestSyncUnloadData` to release; loop to next.

Caveats not yet resolved:

- The `Sc_RequestSyncLoadData` implementation at `0x1408605d0` operates on `[this+0x124]` — i.e., it's a method on a **resource-handle object**, not on the entity that owns the handle. Frida-callers need to resolve the actual handle pointer (typically a child of the spawner-entity's component graph), not just the spawner pointer.
- `Sc_Spawn` (`0x1406ef7c0`) is per-entity-class — different classes register different implementations. Its signature on the entity classes that matter (boss prefab, spawner) needs decompilation before Frida-calling.
- Cross-chapter asset-bundle resolvability still unverified (whether chapter-1's running session can resolve chapter-2's boss asset handle).

## Engine scripting API — Sc_* family (Frida-callable surface)

The `Sc_*` family is the engine's script-method-binding system: methods registered through a binding helper at `0x140471ab0..0x140471d60` (multiple variant registrars) into a method-id-keyed dispatch. Each registration encodes `(name_string, param_descriptors, return_descriptor, method_id, implementation_ptr)` and the implementation is a normal C function the engine calls when script invokes the method by ID. Because registration happens at static init in the retail build, all listed implementations are present in the shipping binary and Frida-callable given the right `this` pointer.

The implementations decoded so far:

| API | Method ID | Impl | Behavior |
|---|---|---|---|
| `Sc_FindGo(level*, char* name) → entity*` | `0x171124` | wrapper `0x140462d90` → `0x140463210` | **Linear search by name in a level.** Walks `level+0x80` (entity ptr array) of count `level+0x88`; compares each `entity+0x50` (name) against `name`. Returns first match or 0. Pure, no side effects. |
| `Sc_FindNearestGoContaining` | `0x25b6a69` | (registration at `0x1404636c0`) | Substring search — nearest match. Multi-param signature with level, links, dummy fallbacks. |
| `Sc_FindAllGoContaining` | (TBD) | (sibling of above) | Substring search — all matches. Returns a collection. |
| `Sc_FindObject(host, char* name) → object_ref` | `0x1563fdb` | `0x14045ad50` | **Larger named-object registry**. Walks `host+0x688` (16-byte entries: name ptr + value pair) of count `host+0x6a0`. Different host class than `Sc_FindGo` — possibly `oCGameLevelDatabase` or similar global registry. |
| `Sc_GetLevel(this) → level*` | `0x299b035` | `0x14045f870` | **Entity → level back-pointer.** Returns `(*this+0x28).vftable[0]()` and `*this+0x28`. Any entity has its level at `+0x28`; this just dereferences and returns. |
| `Sc_RequestSyncLoadData(this) → void` | `0x228a` | `0x1408605d0` | Refcounted load: `++[this+0x124]`; if was 0, jump-tail to actual load at `0x140860410`. |
| `Sc_RequestSyncUnloadData(this) → void` | `0x228b` | `0x1408605f0` | Refcounted unload: `--[this+0x124]`; on 1→0 transition, calls actual unload at `0x1408604e0`. |
| `Sc_Spawn(entity)` | `0x1faa` | `0x1406ef7c0` | Multi-step spawn: sets flags at `+0x168/+0x169`, tail-calls activator at `0x1406ef5c0`. |
| `Sc_AddPicture` (UI) | `0x2a13de4` | `0x140537e30` | UI primitive — adds a picture element. Not yet decompiled but registration confirmed. |

UI Sc_* primitives also include `Sc_AddLabel`, `Sc_SetTitle`, `Sc_SetTextColor`, `Sc_SetFont`, `Sc_SetPosition`, `Sc_SetSize`, `Sc_Hide`, `Sc_Show`, `Sc_HideElement`, `Sc_Delete`, `Sc_GetWidth`, `Sc_GetHeight` — a complete element-graph manipulation API. Frida-callable given a UI host reference. **Implication**: a Frida mod could draw arbitrary debug overlays into the game's own UI subsystem, without injecting a separate renderer.

## Cinematic and selector share an entity-component base

`oCEntityCpntCinematic` (RTTI `0x14136bdb8`) and `oIEntitySelectorToSpawnEntityCpnt` (RTTI `0x141349638`) share several vtable slots verbatim:

- `vtable[4] = FUN_1406f5ee0`
- `vtable[9] = FUN_1406f6030`
- `vtable[11] = FUN_1406f6210`
- `vtable[19] = FUN_1406f6230`

Same function addresses, same slot indices. They inherit from a common entity-component interface (likely `oIEntityCpnt`-something). **The cinematic IS just another entity component** — same lifecycle methods, same activation model, same parent-entity binding. So a CineBloc activating a different entity-component is mechanically the same operation as one component sending a message to its peer.

This unifies the boss-arrival picture:

```
BossTimer_update fires named event 0x17d8d901
  └─> entity-component subscriber on Map_Boss_Spawner_<Chapter>
       (registered via the named-event substrate at level-load)
       └─> starts the Map_Boss_Spawner_Cinematic_Awakening cinematic
            (cinematic is itself an entity component; activation = same as any other)
            └─> CineBlocs inside the cinematic execute in sequence:
                 - Picture fade-in (oCPictureCineBlocFadeIn) — load cover
                 - Sc_RequestSyncLoadData on the boss/arena bundle (refcounted)
                 - Sc_Spawn + Sc_Activate (oCActivateEntityCpntCineBloc) — wake the boss
                 - Animations, audio cues
                 - oCEntityNamedEventSenderCineBloc — fire downstream events
                 - Picture fade-out
```

For a boss-rush mod the moving parts collapse to:

1. `Sc_FindAllGoContaining(level, "Map_Boss_Spawner")` — find the active spawner (and any siblings).
2. Read the spawner's bound boss-prefab handle (offset TBD — needs the spawner's component layout).
3. `Sc_RequestSyncLoadData` on the next chapter's boss bundle (refcount-safe, won't conflict with engine).
4. Rewrite the bound prefab handle to the next boss's resource.
5. Re-fire `0x17d8d901` (already proven — `forceBossSpawn` does this).
6. Awakening cinematic plays again; subscriber re-spawns; new boss appears.

Suppression of chapter-end on intermediate kills remains a separate concern (see §"What changes for a boss-rush mod" earlier).

## Engine architecture — entity components, resource refs, and the global prefab catalog

The deeper dig revealed the full shape of the entity / resource system, well beyond the boss-specific path.

### Entity components inherit from `oIEntityCpnt`

`oIEntitySelectorToSpawnEntityCpnt` and `oCEntityCpntCinematic` share four vtable slots verbatim — they have a common base (`oIEntityCpnt`-something). The shared base defines:

| Vtable slot | Function | Role |
|---|---|---|
| `[+0x20]` `vtable[4]` | `oIEntityCpnt_onAttach_commitToParent` (`0x1406f5ee0`) | Finalizes attach to parent entity. `[this+0x10]` = parent, `[this+0x8]` = transient. |
| `[+0x38]` `vtable[7]` | `oIEntityCpnt_persistenceAttach` (`0x1406f5f20`) | Binds component to per-entity persistence record (cross-session state). Calls `find_persistent_data_for_entity`. |
| `[+0x40]` `vtable[8]` | `oIEntityCpnt_persistenceDetach` (`0x1406f5fc0`) | Symmetric unbind. |
| `[+0x58]` `vtable[11]` | `oIEntityCpnt_getMemberByHash_baseImpl` (`0x1406f6210`) | **Hash-keyed data accessor.** Two known: `0xfd2832a → this+0x18`, `0xfd2833c → this+0x38`. |
| `[+0x98]` `vtable[19]` | `oIEntityCpnt_getMethodHandleByHash_baseImpl` (`0x1406f6230`) | **Hash-keyed method dispatcher.** Returns a `(this, method_thunk)` callable handle. Two known: `0x1a5453c0 → LAB_1406fb940`, `0x1a5453c1 → LAB_14035fa60`. |

**Implication**: data-driven entity composition (the `.entity.ot` files) wires components together by hash. A spawner can be told via data: "when event X fires, call method-with-hash-Y on the cinematic component." The engine resolves at runtime via vtable[19]. Subclasses override these to expose more hashes.

### Spawner has multiple inheritance — `oCEntitySpawner` is a sub-object

Confirmed via `oCDtEntityCpntHeroSpawner_ctor @ 0x1402ccf20`:

```c
HeroSpawner_ctor(this, dtor_flag) {
    *this              = oCDtEntityCpntHeroSpawner::vftable;   // primary base
    this[+0x68]        = oCEntitySpawner::vftable;              // secondary base sub-object
    ...
}
```

`oCEntitySpawner` is the spawn-tracking machinery: a doubly-linked list of spawned entities. Confirmed by:

- `oCEntitySpawner_addSpawnedEntity @ 0x1406db390` (vtable[3]) — appends a node to the list at `[spawner+0x20]..[spawner+0x28]`, sets the entity-node's back-pointers at `node[+0x38]` and `node[+0x50]`, increments the count at `[spawner+0x18]`.
- `oCEntitySpawner_removeSpawnedEntity @ 0x140678b80` (vtable[4]) — symmetric removal, decrements count.

So `oCEntitySpawner` answers "how many entities have I spawned and which are they?" — but the **prefab they're instances of** is held elsewhere.

### `oCEntitySpawnData` is transform, not prefab

`oCEntitySpawnData::vtable[3] @ 0x1406c9490` is the deserializer. It reads three 4-byte fields at `+0x10/+0x14/+0x18`, then a 4-dword block at `+0x1c` (Quaternion via `FUN_140125740`), then a 3-dword block at `+0x2c` (Vec3 via `FUN_1401257c0`). That's a (Vec3, Quat, Vec3) — position, rotation, scale. Not the prefab handle.

### **The prefab catalog: `oCTLibrary<oCEntitySettingsResource>`**

This is the biggest architectural find of the dig. The engine has a templated library type instantiated as `oCTLibrary<oCEntitySettingsResource>` (RTTI at `0x141367b70`). It's the **global registry of every loadable entity prefab** — every `.entity.ot.EntitySettingsResource.gen` file in the asset tree is an entry in this library.

Adjacent types:

| Type | Role |
|---|---|
| `oCEntitySettingsResource` | Runtime form of an `.entity.ot` file. 27 vfuncs — full lifecycle (load, ref, query, unload). |
| `oCEntitySettings` | The data class for an entity definition. |
| `oCEntitySettingsRootRef` | Small ref wrapper (8 vfuncs) — likely the type stored in spawner fields as the bound prefab handle. |
| `oCEntitySettingsRootPtr` | Pointer wrapper variant. |
| `oCGlobalEntitySettingsRef` | Global ref to entity settings. |
| `oCTGlobalResourceRef<oCEntitySettingsResource>` | Templated global resource reference. RTTI at `0x141332850`. |
| `oCTResourceWeakRef<oCEntitySettingsResource>` | Weak templated ref. |
| `oCTLibrary<oCEntitySettingsResource>` | **The global catalog. Single source of truth for all entity prefabs across all chapters.** |

**Cross-chapter handle resolvability is now answered**: yes, in principle. The catalog is global and content-addressable — Storm Island's `Map_Boss_Spawner_Storm_Island` is in the same library Dark Hills's `Map_Boss_Spawner_Dark_Hills` is in. Any chapter's session can resolve any prefab by its catalog key, regardless of which chapter is currently active. Whether the *contents* of an alien-chapter prefab can be loaded successfully depends on whether its dependencies (boss character assets, animation sets, audio) are also catalogued globally. The streaming-on-demand model (`Sc_RequestSyncLoadData` triggers actual disk read via `data_resource_actual_load_impl @ 0x140860410`) suggests they are — assets are demand-loaded, not pre-bundled with the active chapter.

### **The bound-prefab pattern — universal across components**

`oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20` (formerly `FUN_140314e20`) is called by HeroSpawner_spawnHero and at least 5 other call sites — it's the engine's universal "fetch one of my bound child prefabs" function. It reveals the per-entity layout:

| Parent-entity offset | Field |
|---|---|
| `+0x8C0` (= `parent[0x118]` in u64-indexing) | Pointer to array of settings-entries |
| `+0x8C8` (= `parent[0x119]`) | Count of entries |

Each settings entry has:

| Entry offset | Field |
|---|---|
| `+0x1c0` | Path string A (folder/category) |
| `+0x1d0` | Path string B (filename/resource) |
| `+0x1e0` | Optional loader-class ref (null = use global) |
| `+0x1e8` | Resolution flag (0 = path needs resolve, 1 = pre-resolved) |
| `+0x1f0` | **The bound resource handle (refcounted)** ← the prefab pointer |

When `+0x1e8 == 0`, the resolver walks the **global type registry** at `g_global_type_registry_root @ DAT_141446f38` (array at `+0x30`, count at `+0x38`), finds the class with id `0x53b64d`, and calls its `vtable[+0x18]` with the path strings to load by name.

**Implication**: this is the universal pattern. Every entity component that needs a bound prefab — HeroSpawner, Map_Boss_Spawner, cinematic spawners, enemy-camp definitions, anything — uses the same `parent[+0x8C0]` settings-array structure. The boss prefab on a `Map_Boss_Spawner_<Chapter>` entity instance lives at `parent[+0x8C0][i]+0x1f0` for some small `i` (typically 0 if the spawner has only one bound prefab).

**For the boss-rush mod, this resolves all three previously-unknown lookups**:

1. ✅ Global library instance: `g_global_type_registry_root @ 0x141446f38` (loader catalog) plus per-entity bound-prefabs at `parent[+0x8C0]` (spawner-side bindings).
2. ✅ Library lookup function: `oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20` — Frida-callable.
3. ✅ Spawner's prefab-handle field offset: `entries[i]+0x1f0` within the array at `parent[+0x8C0]`. Universal pattern, not Map_Boss_Spawner-specific.

## The Encyclopedia — runtime test results 2026-05-05

> **CORRECTION over the prior architectural assumptions in this section.** The runtime test on 2026-05-05 invalidated the central premise that `findEntitySettings("Map_Boss_Spawner_<Chapter>")` would resolve the per-chapter boss spawner prefab. It does not. The encyclopedia holds **abstract spawner classes keyed by display name** (e.g. `[Entity spawner] Boss Spawner`), not asset-path-style names. The chapter-specific boss data lives at instance-level on the live `Boss Spawner` entity in the loaded chapter, NOT in this encyclopedia. The original prose below is preserved for historical context; the **"Verified runtime layout"** subsection below records the actual structure discovered live.

### What was verified end-to-end (Frida, 2026-05-05)

- `_oCTSameTypeTester<oCEntitySettingsEncyclopediaSceneContext>::vftable @ 0x140f536d0` resolves correctly.
- `scene_manager_find_context_by_type @ 0x140653f80` returns a non-null encyclopedia given a captured scene_manager (captured via `Interceptor.attach` on the function itself, first natural caller).
- The hashmap layout at encyclopedia `+0x28..+0x48` matches the static decode (control-bytes ptr, entries ptr, count, capacity-mask).
- The hashmap **key (entry +0x00..+0x10) is NOT `(begin_ptr, end_ptr)` of name strings** as previously assumed — dereferencing those qwords produces ACCESS VIOLATION. They are precomputed hash qwords (the engine pre-hashes the name once at registration and stores the fingerprint, not the string identity). So a Frida-side hashmap lookup keyed by a freshly-allocated buffer cannot match — must walk entries instead.
- The entry value (entry `+0x10`) points to a sub-object inside `oCEntitySettingsResource` at `resource+0x98`, with this layout:
  ```
  +0x00: vtable
  +0x08: char* name
  +0x10: u32 length
  +0x18: vtable / function ptr
  +0x20: self-pointer
  ```
  Reading `value+0x08` as a `char*` and `value+0x10` as the length yields the prefab's display name.

### Verified runtime layout — what's actually in the encyclopedia

In a chapter-1 (Dark_Hills) live session, the encyclopedia contained **21 entries, all entity-spawner classes**, keyed by display name:

```
[Entity spawner] Enemy Camp 01
[Entity spawner] Boss Spawner          ← single generic class, not per-chapter
[Entity spawner] Hog Enemy Camp Wandering
[Entity spawner] Teleporter
[Entity spawner] Entrance
[Entity spawner] Den Entrance
[Entity spawner] Cauldron
... (15 more spawner-class entries)
```

`forceBossSpawn()` does NOT trigger new prefab registrations into this encyclopedia — count stays at 21 before and after the boss arrival event. The chapter-specific Boss Spawner prefab (the engine-side analog of `Map_Boss_Spawner_Dark_Hills.entity.ot`) is loaded by a different mechanism. The asset-tree files `Map_Boss_Spawner_<Chapter>.entity.ot` exist but their data does not surface as encyclopedia keys.

### What this implies for the boss-rush mod

The "swap a bound prefab in the encyclopedia and re-fire `0x17d8d901`" plan is invalidated. The boss configuration lives at **instance-level on the live `Boss Spawner` entity in the current chapter**, accessed via the `parent[+0x8C0][i]+0x1f0` universal pattern (per the `oIEntity_resolveBoundPrefab_byIndex` decode below). The right next step is **live-entity enumeration**: query a different scene-context (likely `oCEntitySceneContext` or similar) to walk active entities, locate the Boss Spawner instance, then read/swap its bound prefab there.

### Path-based loader — discovered 2026-05-05 dig (static)

To "swap to chapter-2's boss while in chapter 1" the mod needs a way to load a prefab by path string at runtime. Initial assumption was `Sc_RequestSyncLoadData` could do this — **invalidated**: that function takes a single `this` (resource handle) arg, increments its refcount, and triggers a deferred load only if the resource was already constructed with its path baked in. It's exposed only as a *script binding* (`"Sc_RequestSyncLoadData"`, registered at `0x14085fe20` with `arg_count=1`) and is not the engine's own path-based load API.

The actual path-based loader is reachable through the prefab-loader class registered in `g_global_type_registry_root` under type-id `0x53b64d`. From `oIEntity_resolveBoundPrefab_byIndex`'s decompile:

```c
// Find the prefab loader class in g_global_type_registry_root
plVar7 = *(longlong **)(g_global_type_registry_root + 0x30);  // entries array
count   = *(uint *)(g_global_type_registry_root + 0x38);       // entry count
for (i = 0; i < count; i++) {
    classPtr = *plVar7;
    if (*(int *)(classPtr + 8) == 0x53b64d) break;             // match by type-id
    plVar7++;
}
loaderInstance = *(undefined8 *)(classPtr + 16);               // class struct +0x10 = instance
// Call vtable[3] (offset 0x18) — the load-by-path call
(*(code *)(*loaderInstance + 0x18))(
    loaderInstance,
    &pathStruct,           // 16-byte { char* begin; char* end; } — the path
    _DAT_1412c7590,        // 0x1412c7590 — static config blob (default loader options)
    &outHandle,             // out: oCEntitySettingsResource* (refcounted)
    0                       // flags / ?
);
```

Settings-entry layout on the parent entity's `[+0x8C0]` array (each entry per-slot):

| Offset | Field |
|---|---|
| `+0x1c0` | path string (16-byte `{ begin, end }`) — the asset path |
| `+0x1d0` | secondary string (probably variant/qualifier path) |
| `+0x1e0` | optional loader-class override; null → use the `0x53b64d` default loader |
| `+0x1e8` | resolved flag — when 1, loader is skipped (already resolved) |
| `+0x1f0` | bound resource handle (refcounted; `+0x08` is the refcount field) |

So the boss-rush PoC path is:

1. Frida-walk `g_global_type_registry_root` (`0x141446f38`) to find the prefab-loader instance with type-id `0x53b64d`. Wrap its vtable[3] in a `NativeFunction`.
2. Hook `oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20` during a `forceBossSpawn` window — capture the parent entity ptr, the slot index, and the settings entry's `+0x1c0` path string. Confirms the path *format* the engine expects.
3. Construct chapter-2's analogous path string (e.g. `"Map_Boss_Spawner_Storm_Island"` or whatever format step 2 reveals) and call the loader from step 1 directly. If it returns a non-null handle without crashing, cross-chapter loading works.
4. Either write the new handle into the live entity's `entry[+0x1f0]` and clear `entry[+0x1e8]`, or rewrite `entry[+0x1c0]`'s path bytes and clear `entry[+0x1e8]` — the engine reresolves on next access. Re-fire `0x17d8d901`.

Step 3 is the binary gating test — does the path-based loader load assets that aren't in the current chapter's level data? Unknown until tested.

### Working Frida primitive (read-only) — for reference

The Frida code that produced the above lives at `tools/frida/mods/boss_rush.js` v0.4.0-walk-by-name. It exposes:
- `findEncyclopedia()` → encyclopedia pointer
- `dumpEncyclopedia(limit?)` → array of `{name, value}`
- `findEntitySettings(name)` → exact-display-name match against the dumped list

This primitive is correct for the encyclopedia it accesses — it just doesn't yield Map_Boss_Spawner_<X> because that data isn't there.

---

## The Encyclopedia — original prose (pre-runtime test)

> Preserved for context; superseded by the runtime test results above.

The `oCEntitySettingsEncyclopediaSceneContext` is a scene-context that holds a **hashmap of every entity-settings prefab loaded in the current session**, keyed by name string.

**Layout** (verified from `EntitySettingsEncyclopedia_registerByName` and `_unregisterByName`):

| Offset | Field |
|---|---|
| `+0x28` | Hashmap base (the entries array; stride/format internal to `hashmap_find_string_keyed_node`) |
| `+0x38` | Entry count |
| `+0x40` | Hashmap mask / capacity bits |

Each hashmap node has:

| Offset | Field |
|---|---|
| `+0x10` | The stored entity-settings pointer (`oCEntitySettingsResource*`) |

The two operations on the encyclopedia:

| Function | RVA | Behavior |
|---|---|---|
| `EntitySettingsEncyclopedia_registerByName` | `0x1406eb7e0` | Insert (name → settings ptr). Emits `"already registered"` / `"Cannot register entity settings, {} is already registered with this ID"` on collision. |
| `EntitySettingsEncyclopedia_unregisterByName` | `0x1406ebfb0` | Remove (name). Emits `"not registered to encyclopedia"` on miss. |

Both call:

| Function | RVA | Behavior |
|---|---|---|
| `fnv_string_hash_64` | `0x140507510` | Hashes a `{ptr, end}` byte range. Uses constant `0xde5fb9d2630458e9` for fold (FNV-style mix). |
| `hashmap_find_string_keyed_node` | `0x1406a0680` | Find by `(name_ptr, hash)`. Returns a node ptr; node `+0x10` holds the value. |
| `hashmap_insert_string_keyed_node` | `0x14069b640` | Insert. New node's `+0x10` is filled by caller with the value. |

**Reaching the encyclopedia from Frida**:

The encyclopedia is a SCENE CONTEXT. Same access pattern as other contexts in this engine:

```c
scene_manager_find_context_by_type(scene_manager, &EncyclopediaTypeTester_vftable)
```

The type-tester vtables exist statically (as RTTI helpers). The engine has two families: `_oCTSameTypeTester<X, oIGameSceneContext>` (exact-type match) and `_oCTKindOfTypeTester<X, oIGameSceneContext>` (subtype/kind-of match). The chapter encyclopedia path uses a `KindOf` tester for `oCDtEncyclopediaSceneContext`; the entity-settings encyclopedia path uses a `Same` tester for `oCEntitySettingsEncyclopediaSceneContext`.

Resolved addresses (verified 2026-05-05 via RTTI walk: type descriptor at `0x141369540` → CHD at `0x141010180` → COL at `0x1410104a8` → vftable at `vftable-8`):

- `_oCTSameTypeTester<oCEntitySettingsEncyclopediaSceneContext, oIGameSceneContext>::vftable @ 0x140f536d0` — used by `EntitySettings_onLoad_registerToEncyclopedia @ 0x140703920` (and by two sibling sites at `0x140703a2e/0x1407184ad`)
- `scene_manager_find_context_by_type @ 0x140653f80` — confirmed from the `CALL` site at `0x14070398f`

The scene_manager itself is at `session->[+0x20]->[+0x18]` (verified earlier in `chapter_end_work` and other functions).

**Frida lookup primitive (skeleton)**:

```javascript
const ENC_TYPETESTER_VFTABLE = base.add(0xf536d0);   // _oCTSameTypeTester<oCEntitySettingsEncyclopediaSceneContext>::vftable
const SCENE_MANAGER_FIND_CONTEXT = base.add(0x653f80);
const FNV_STRING_HASH_64        = base.add(0x507510);
const HASHMAP_FIND              = base.add(0x6a0680);

function findEntitySettings(name) {
    const sceneManager = session.add(0x20).readPointer().add(0x18).readPointer();
    const encyclopedia = sceneManagerFindContextByType(sceneManager, ENC_TYPETESTER_VFTABLE);
    if (encyclopedia.isNull()) return null;

    const buf = Memory.allocUtf8String(name);
    const end = buf.add(name.length);
    const hash = fnvStringHash64(buf, end);

    const out = Memory.alloc(0x20);
    hashmapFind(encyclopedia.add(0x28), out, buf, hash);
    const node = out.readPointer();
    return node.isNull() ? null : node.add(0x10).readPointer();
}
```

**Implication (INVALIDATED 2026-05-05 — see correction above):** ~~with this single primitive, Frida can resolve `findEntitySettings("Map_Boss_Spawner_Storm_Island")`, etc.~~ — runtime test showed asset-path-style names are NOT registered in this encyclopedia. The encyclopedia holds 21 abstract spawner classes keyed by display name (e.g. `[Entity spawner] Boss Spawner`), not per-chapter prefabs.

The pseudocode below also doesn't work as written, because the hashmap key is a precomputed hash pair (not interned begin/end pointers) and a freshly-allocated Frida buffer can't match. Walk entries instead — see the working primitive in `tools/frida/mods/boss_rush.js` v0.4.

## Trigger surface — engine event/method primitives

The engine exposes four orthogonal trigger surfaces, each with a Frida-callable entry point:

### 1. Named events (scene-context broadcast)

```c
fire_named_event(scene_context, hash_id, payload_ptr);
```

- `0x14067dea0` (already named).
- `payload_ptr` points to an `oCCustomFlagList` struct (in-stack works fine — see `BossTimer_update`: `oCCustomFlagList::vftable` + a single-float payload `0x3f800000` = 1.0f).
- Subscribers register via `register_named_event @ 0x14067daa0` keyed by hash.
- Used for: chapter-end, boss-arrival (`0x17d8d901`), boss-warning (`0x17d8d900`), boss-overtime (`0x1cd7928b`), and many more named events.

### 2. Hash-keyed method invocation on entity components

Every entity component supports `getMethodHandleByHash` at `vtable[19]` (base impl `oIEntityCpnt_getMethodHandleByHash_baseImpl @ 0x1406f6230`):

```c
struct CallableHandle {
    void*  this_ptr;     // [+0x0] = entity
    void*  unused;        // [+0x8]
    void*  method_ptr;    // [+0x10] = thunk address
};

cpnt->vtable[19](cpnt, &out_handle, hash);
if (out_handle.method_ptr != null) {
    out_handle.method_ptr(out_handle.this_ptr, args...);
}
```

Two known hashes on the base: `0x1a5453c0 → LAB_1406fb940`, `0x1a5453c1 → LAB_14035fa60`. Subclasses override to expose more.

### 3. Hash-keyed member-data access on entity components

Same pattern but for fields, at `vtable[11]` (base impl `oIEntityCpnt_getMemberByHash_baseImpl @ 0x1406f6210`):

```c
void* member_ptr = cpnt->vtable[11](cpnt, hash);
```

Two known: `0xfd2832a → cpnt+0x18`, `0xfd2833c → cpnt+0x38`. Subclasses override.

### 4. Script-method API (`Sc_*`)

Already mapped in §"Engine scripting API". These are method-id keyed rather than hash-keyed:

- `Sc_FindGo`, `Sc_FindObject`, `Sc_FindNearestGoContaining`, `Sc_FindAllGoContaining` — discovery
- `Sc_GetLevel`, `Sc_Spawn`, `Sc_Despawn`, `Sc_Activate`, `Sc_Deactivate` — entity ops
- `Sc_RequestSyncLoadData`, `Sc_RequestSyncUnloadData` — resource ops
- `Sc_AddLabel`, `Sc_AddPicture`, `Sc_SetTitle`, etc. — UI ops

Each `Sc_*` has a known implementation function in the binary, callable directly with the appropriate `this` pointer.

### Unified Frida trigger primitive

```javascript
const FIRE_NAMED_EVENT  = base.add(0x67dea0);
const REGISTER_NAMED_EVENT = base.add(0x67daa0);

const fire_named_event = new NativeFunction(
    FIRE_NAMED_EVENT, 'void', ['pointer', 'uint32', 'pointer']);

function fireNamedEvent(sceneContext, hashId, floatValue) {
    // Build oCCustomFlagList on a tiny scratch buffer
    // Layout: { vtable, count, capacity, data_ptr, payload[N] }
    const buf = Memory.alloc(0x40);
    buf.writePointer(oCCustomFlagList_vftable);  // vtable resolved at session start
    // ... seed a single-float payload — full layout in BossTimer_update reference
    fire_named_event(sceneContext, hashId, buf);
}

function callMethodByHash(cpnt, methodHash, ...args) {
    // Read vtable[19] thunk
    const vtable     = cpnt.readPointer();
    const fn_addr    = vtable.add(0x98).readPointer();
    const out_handle = Memory.alloc(0x18);

    const get_method = new NativeFunction(fn_addr, 'pointer', ['pointer', 'pointer', 'uint32']);
    get_method(cpnt, out_handle, methodHash);

    const this_ptr   = out_handle.add(0x0).readPointer();
    const method_ptr = out_handle.add(0x10).readPointer();
    if (method_ptr.isNull()) return null;

    const method = new NativeFunction(method_ptr, 'pointer', ['pointer', ...]);
    return method(this_ptr, ...args);
}
```

## Master picture — pseudocode for the boss-rush mod

```javascript
// Setup at chapter load (once)
const session = findGameSession();           // walk from a known root
const sceneContext = session.add(0x20).readPointer();
const sceneManager = sceneContext.add(0x18).readPointer();
const level = sceneManager.add(...).readPointer();   // exact offset TBD
const entityLibrary = findGlobalEntityLibrary();      // oCTLibrary<oCEntitySettingsResource>; offset TBD

// Find the active map-boss spawner
const spawnerEntity = sc.FindGo(level, "Map_Boss_Spawner_Dark_Hills");
const spawner = spawnerEntity;                         // entity ptr

// Per fight, after each kill (except the final one):
function fightNextBoss(nextChapterTag) {
  // 1. Resolve next boss's prefab from the global catalog
  const nextPrefabRef = libraryFindByKey(entityLibrary, `Map_Boss_Spawner_${nextChapterTag}`);

  // 2. Refcount-safe sync-load (cinematic will use the cached load)
  sc.RequestSyncLoadData(nextPrefabRef);

  // 3. Rewrite the spawner's bound prefab handle
  // Field offset TBD — likely in the oCEntitySpawner sub-object or a sibling component
  spawner.add(SPAWNER_PREFAB_HANDLE_OFFSET).writePointer(nextPrefabRef);

  // 4. Reset BossTimer state (already mapped — see chapter-boss-portal-trigger.md)
  bossTimer.add(0x148).writeU8(0);    // is_boss_awaken = 0
  bossTimer.add(0x14a).writeU8(0);    // boss_just_awoke = 0
  bossTimer.add(0x12c).writeFloat(0); // elapsed = 0
  // (then forceBossSpawn() will set elapsed = boss_time on next frame)

  // 5. Reset session boss-state flags written by session_on_boss_fighting
  resetSessionBossFlags(session);

  // 6. Re-fire the arrival event — cinematic plays again, new boss spawns
  forceBossSpawn();   // already implemented: writes elapsed = boss_time
}
```

## Open questions / next dig

The 2026-05-05 runtime test reshaped this list — what was integration-level is now partly architectural again. New priority order:

1. ~~**Resolve the encyclopedia type-tester vtable address.**~~ **Resolved 2026-05-05.** `_oCTSameTypeTester<oCEntitySettingsEncyclopediaSceneContext, oIGameSceneContext>::vftable @ 0x140f536d0` via RTTI walk. `scene_manager_find_context_by_type @ 0x140653f80` resolved as a side-product. End-to-end Frida access verified — see `tools/frida/mods/boss_rush.js` v0.4.

2. ~~**Encyclopedia name-key dump tool.**~~ **Resolved 2026-05-05.** Hash-keyed lookup from outside doesn't work — entry `+0x00..+0x10` is a precomputed hash pair, not interned begin/end pointers. Walker iterates Swiss-Table entries, derefs `entry+0x10 → value`, reads `value+0x08` (char*) + `value+0x10` (u32 length). Implemented in `boss_rush.js` v0.4.

3. ~~**Verify `oCTString` representation.**~~ **Resolved 2026-05-05.** The name field on the encyclopedia value is a plain `char*` at `value+0x08` with a length u32 at `value+0x10`. No vtable prefix or extra deref needed.

4. **Find live Boss Spawner instance in the active level (cheapest path identified).** Hook `oIEntity_resolveBoundPrefab_byIndex @ 0x140314e20` during a `forceBossSpawn` window — captures `(parent_entity, slot_index, settings_entry_ptr)` for every bound-prefab resolution. Filter to the boss-spawn one (likely happens during the awakening cinematic) to get the live spawner instance pointer + the entry whose `+0x1c0` path is the chapter-1 boss spawner path.

5. ~~**Locate where `Map_Boss_Spawner_<Chapter>.entity.ot` data lives at runtime.**~~ **Reframed 2026-05-05.** Discovered the path-based loader API (see "Path-based loader" section above): `vtable[3]` of the class registered at `g_global_type_registry_root` type-id `0x53b64d`. Calling it with a path string returns an `oCEntitySettingsResource*` handle. The remaining open question is whether this loader can pull cross-chapter assets while the wrong chapter's level is active (binary in-game test).

6. **Verify the bound-prefab field offset on the live Boss Spawner instance** (depends on #4). Universal pattern is `parent[+0x8C0][i]+0x1f0` per `oIEntity_resolveBoundPrefab_byIndex`, but the specific index `i` and whether multiple slots are populated needs runtime confirmation against the live instance.

7. **Boss-kill / chapter-end suppression hook.** Trace caller chain from boss-death to `chapter_end_work @ 0x1402907e0`. The mod must intercept at the right level — early enough to skip chapter advance, late enough to keep kill credit and rewards. Unchanged.

8. **Identify subscribers to `0x17d8d901` at level-load time** via Frida hook on `register_named_event @ 0x14067daa0` filtered to that hash. Confirms which entity-component does the actual spawn. Likely depends on #4 findings to know which entity-component to look at.

## Annotations applied 2026-05-05 (coordinated three-agent session)

Read-only multi-agent dig (Agents A/B/C — spawning logic, player position API, camps/placement). All renames proposed at end-of-session and applied as a single `batch_rename` after user approval, to avoid cross-agent identity drift. 22 proposed; 21 applied (one no-op — `0x140314e20` was already named from the prior session below). Topic-focused detail in `spawn-at-coord-recipe.md`.

Function renames (19):

| RVA | New name |
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
| `0x1402b72e0` | `global_value_publish_vec3` |
| `0x1401c6790` | `global_value_find_bucket_by_hash` |
| `0x14038e260` | `HC_per_frame_update` (confirmed; was already partially named) |

Data renames (3):

| RVA | New name |
|---|---|
| `0x141447dc0` | `g_typeDesc_oITransform3dAccess` |
| `0x141447448` | `g_typeDesc_Vec3_direct` |
| `0x1412c09d8` | `g_eventHash_GenerateEnemyCamps` |

Headline finding from this session: there is a confirmed callable spawn-at-position path. The placement primitive is the universal `vtable[+0x1a0]` setter on `oITransform3dAccess`-implementing entities, exposed to scripts as `Sc_ForcePosition`. Combined with `Sc_Spawn`, this gives an end-to-end "spawn an entity, then place it at a chosen coord" recipe. See `spawn-at-coord-recipe.md` for the full contract, recipe, and unresolved questions.

## Annotations applied 2026-05-04 (initial dig)

All committed via `mcp__ghidra__rename_symbol`. Function renames (29):

| RVA | New name |
|---|---|
| `0x140462d90` | `Sc_FindGo_glue` |
| `0x140463210` | `oCGameLevel_findGoByName` |
| `0x14045f870` | `oIEntity_Sc_GetLevel_impl` |
| `0x14045ad50` | `Sc_FindObject_impl` |
| `0x14034b780` | `oIEntitySelectorToSpawn_onBindToParent` |
| `0x1406f5ee0` | `oIEntityCpnt_onAttach_commitToParent` |
| `0x1406f5f20` | `oIEntityCpnt_persistenceAttach` |
| `0x1406f5fc0` | `oIEntityCpnt_persistenceDetach` |
| `0x1406f6210` | `oIEntityCpnt_getMemberByHash_baseImpl` |
| `0x1406f6230` | `oIEntityCpnt_getMethodHandleByHash_baseImpl` |
| `0x1402ccf20` | `oCDtEntityCpntHeroSpawner_ctor` |
| `0x1402cd370` | `oCDtEntityCpntHeroSpawner_spawnHero` |
| `0x1402cd320` | `oCDtEntityCpntHeroSpawner_persistenceDetach` |
| `0x1402cd2f0` | `oCDtEntityCpntHeroSpawner_persistenceAttach` |
| `0x1402cd800` | `oCDtEntityCpntHeroSpawner_broadcastToTypedChildren_at_0x88` |
| `0x1406db390` | `oCEntitySpawner_addSpawnedEntity` |
| `0x140678b80` | `oCEntitySpawner_removeSpawnedEntity` |
| `0x140678250` | `oCSpawnablePool_allocateNode` |
| `0x140314e20` | `oIEntity_resolveBoundPrefab_byIndex` |
| `0x1406ebfb0` | `EntitySettingsEncyclopedia_unregisterByName` |
| `0x1406eb7e0` | `EntitySettingsEncyclopedia_registerByName` |
| `0x1406a0680` | `hashmap_find_string_keyed_node` |
| `0x14069b640` | `hashmap_insert_string_keyed_node` |
| `0x140507510` | `fnv_string_hash_64` |
| `0x140703920` | `EntitySettings_onLoad_registerToEncyclopedia` |
| `0x14048ea80` | `oCEntitySettingsResource_onLoad_registerToParent` |

Data renames (4):

| RVA | New name |
|---|---|
| `0x140eea480` | `g_chapter_map_name_to_hash_table` |
| `0x140eea740` | `g_chapter_map_stat_hash_array` |
| `0x141446f38` | `g_global_type_registry_root` |
| `0x141447c18` | `g_typeId_oCEntitySettingsEncyclopediaSceneContext` |

Plate comments added at:

- `0x140eea480` — entry layout (`(name_ptr, type_tag)` × 4), the four map names, parallel hash array reference, consumer (`publish_map_name_event`).
- `0x1402907e0` — appended cross-ref to this finding from the existing `chapter_end_work` plate.

No struct/type definitions added — would be premature without runtime verification of the bound-prefab indexing.

## Locating these symbols on a new build

Per project doc convention (see `rw/docs/README.md` §"Locating <thing>"). All RVAs listed elsewhere in this finding will shift on any recompile of `Ravenswatch.exe`. To re-anchor on a new build, use the strategies below — each tied to a stable artifact (string, RTTI, or content-derived hash).

### Strategy 1 — Strings (most reliable)

Search for the literal string in Ghidra, walk the single xref site, identify the containing function. Used for symbols whose behavior emits a known fixed message:

| Find symbol | Anchor string | Found via |
|---|---|---|
| `g_chapter_map_name_to_hash_table` | `"Dark_Hills"`, `"Storm_Island"`, `"Avalon"`, `"Baba_Yaga_Map"` (4 strings, table is the contiguous pointer set above) | Strings end at `0x14...edbc0..edbf0` region; table is in `.rdata` referencing them. |
| `publish_map_name_event` | `"map.name"` (analytics property key) | Single xref. Walks the table above. |
| `BossTimer_update` | Already anchored in `chapter-boss-portal-trigger.md` via `"Boss time start"` registration. |
| `BossTimer_register_stats_and_events` | Same — registers `"Boss warning start"`, `"Boss time start"`, `"Boss overtime start"` strings to event hashes. |
| `EntitySettingsEncyclopedia_registerByName` | `"Entity Settings {} already registered to encyclopedia."` and `"Cannot register entity settings, {} is already registered with this ID"` (one xref each). |
| `EntitySettingsEncyclopedia_unregisterByName` | `"Entity Settings {} not registered to encyclopedia."` (one xref). |
| `Sc_FindGo` / `Sc_FindObject` / `Sc_GetLevel` / `Sc_RequestSyncLoadData` / `Sc_Spawn` (and any `Sc_*`) | The literal `"Sc_*"` string, registered with the script-binding system. The registration site is two `LEA` instructions: one to the name string, one to the implementation function pointer. The implementation is usually within a few hundred bytes. |
| `chapter_end_work` | Already named — anchor is the `1→3, 2→6, 3→9` difficulty mapping (a unique three-cmp/three-store sequence) plus xrefs to the chapter-map name table. |

### Strategy 2 — RTTI symbols (very reliable)

Search Ghidra for the class name as a string (`.?AVoCFoo@@` form). The associated vtable lives nearby in `.rdata`. Walk vtable slots to recover member methods.

| Class | RTTI string |
|---|---|
| `oCEntitySettingsResource` | `.?AVoCEntitySettingsResource@@` at `0x141367a10` |
| `oCEntitySettingsEncyclopediaSceneContext` | `.?AVoCEntitySettingsEncyclopediaSceneContext@@` at `0x141346298` |
| `oCDtEntityCpntHeroSpawner` | `.?AVoCDtEntityCpntHeroSpawner@@` at `0x14134eb68` (RTTI type descriptor); the class also has the human string `"Dt Hero Spawner"` for non-RTTI reference. |
| `oCEntitySpawner` | `.?AVoCEntitySpawner@@` at `0x14130f300` |
| `oCSpawnable` / `oCSpawnablePool` | `.?AVoCSpawnable@@` at `0x141365988`, `.?AVoCSpawnablePool@@` at `0x1413655e8`. |
| `oIEntitySelectorToSpawnEntityCpnt` | `.?AVoIEntitySelectorToSpawnEntityCpnt@@` (interface base for selector family). |
| `oCEntityCpntCinematic` | `.?AVoCEntityCpntCinematic@@` at `0x14136bdb8`. |
| `oCEntitySpawnData` | `.?AVoCEntitySpawnData@@` at `0x14134b0e8` (transform data for spawns). |
| `_oCTSameTypeTester<oCEntitySettingsEncyclopediaSceneContext, oIGameSceneContext>` | RTTI name string `.?AV?$_oCTSameTypeTester@VoCEntitySettingsEncyclopediaSceneContext@@VoIGameSceneContext@@@@` at `0x141369550` (descriptor begins 16 bytes earlier at `0x141369540`). To locate the vftable: walk descriptor xrefs to the BCD; from BCD walk to the CHD (`pCHD` field); search for the COL by the CHD-RVA-as-bytes; vftable sits at `COL+0x28` (or equivalently 8 bytes after the COL address). Resolved this build: COL `0x1410104a8`, vftable `0x140f536d0`. |

### Strategy 3 — Content-derived hashes

These are FNV-style hashes of asset/property names. They survive recompiles because they're computed at build time from string assets. They only change if the asset name is renamed at the source.

| Hash | Meaning | Verification path |
|---|---|---|
| `0x17d8d901` | Named event "Boss time start" | Verify in `BossTimer_register_stats_and_events` (registers the name → hash mapping). |
| `0x17d8d900` | Named event "Boss warning start" | Same. |
| `0x1cd7928b` | Named event "Boss overtime start" | Same. |
| `0x193495c2` / `0x193495c4` / `0x1a597765` / `0x1b677eca` | Per-map analytics stat hashes (Dark_Hills / Storm_Island / Avalon / Baba_Yaga_Map) | Embedded in `g_chapter_map_stat_hash_array`; see Strategy 1. |
| `0xfd2832a`, `0xfd2833c` | `oIEntityCpnt::getMemberByHash` base — fields at `+0x18`, `+0x38` | Confirmed by decompile of `oIEntityCpnt_getMemberByHash_baseImpl @ vtable[11]` on any entity-component class. |
| `0x1a5453c0`, `0x1a5453c1` | `oIEntityCpnt::getMethodHandleByHash` base — methods returning `LAB_1406fb940` and `LAB_14035fa60` | Confirmed by decompile of `oIEntityCpnt_getMethodHandleByHash_baseImpl @ vtable[19]`. |
| `0x53b64d` | Class id used in `oIEntity_resolveBoundPrefab_byIndex` lookup against `g_global_type_registry_root` | Confirmed in the function decompile. |
| `0x1ab183ab` / `0x1ab58780` | Modifier-stat gate hashes in `chapter_end_work` | Embedded in the function. |

### Strategy 4 — Byte-pattern search for hash constants

When a hash appears as a literal `MOV EDX, <hash>` constant in code, byte-pattern search re-locates every fire/register site immediately. Example: pattern `01 d9 d8 17` (little-endian `0x17d8d901`) found exactly two sites — `BossTimer_update` and `BossTimer_register_stats_and_events` — confirming the static-fire path.

### Strategy 5 — Vtable indices and struct offsets

Stable across patch builds, can shift on major engine updates. Re-verify when a major version lands:

| Anchor | Offset / index | Use |
|---|---|---|
| `oIEntityCpnt` vtable[4] | `+0x20` | `oIEntityCpnt_onAttach_commitToParent` |
| `oIEntityCpnt` vtable[7] | `+0x38` | `oIEntityCpnt_persistenceAttach` |
| `oIEntityCpnt` vtable[8] | `+0x40` | `oIEntityCpnt_persistenceDetach` |
| `oIEntityCpnt` vtable[11] | `+0x58` | `getMemberByHash` |
| `oIEntityCpnt` vtable[19] | `+0x98` | `getMethodHandleByHash` |
| `oCEntitySettingsEncyclopediaSceneContext` | `+0x28..+0x40` | hashmap (control / entries / count / capmask) |
| Hashmap entry | `+0x10` | stored value (`oCEntitySettingsResource*`) |
| Entity-component (any) | `+0x10` | parent entity ptr |
| Entity (any) | `+0x28` | back-pointer to level (used by `Sc_GetLevel`) |
| Settings holder | `+0x108` | start of bound-prefab array (in HeroSpawner-style classes) |
| Settings entry | `+0x1f0` | bound resource handle (universal) |
| Parent entity (universal) | `+0x8C0` (= `entity[0x118]` u64-indexed) | array-of-settings-entries pointer |
| Parent entity (universal) | `+0x8C8` | settings-entries count |
| Resource handle | `+0x110` / `+0x118` | bundle string-list ptr / count |
| Resource handle | `+0x124` | refcount (used by `Sc_RequestSyncLoadData`) |
| BossTimer instance | `+0x12c`, `+0x144`, `+0x148`, etc. | full field map in `chapter-boss-portal-trigger.md`. |

If a major engine update shifts any of these, the anchoring functions (decompiled and named here) still execute the same logic — re-decompiling reveals the new offsets immediately.

### Re-anchoring quick recipe

For a new `Ravenswatch.exe` build, the cheapest path to recover this finding's symbols:

1. Open the new exe in Ghidra; let auto-analysis complete.
2. For each function symbol: pick its strongest anchor from Strategy 1 or 2 above. String-anchored symbols are usually 30-second look-ups.
3. For each data symbol: walk from the function that uses it (e.g. `g_global_type_registry_root` is used by `oIEntity_resolveBoundPrefab_byIndex`).
4. For struct offsets: re-decompile the same function and read the new offset. The semantic field doesn't change; only its byte position can.
5. Validate the encyclopedia primitive end-to-end with a known-good name (`"Map_Boss_Spawner_Storm_Island"`); if it returns non-null, the chain is intact.

## Notes on methodology

The `0x17d8d901` subscriber question consumed disproportionate effort before pivoting. The lesson: when an engine uses runtime-string-keyed dispatch, **don't expect static analysis to enumerate listeners** — the static dispatcher fingerprint is in the *fire* path, not the *subscribe* path. Switch to runtime hooks earlier next time. Same lesson would apply to any property-bag listener investigation.

The `active_boss` string (`0x140ef27b8`) was a red herring — it appears in only one function (`0x1401f4f10`, an analytics-event payload builder) where it's a telemetry field key, not a runtime entity reference. Worth recording so future digs don't re-chase it.
