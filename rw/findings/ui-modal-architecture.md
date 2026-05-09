[← Back to findings](README.md)

# UI modal architecture — assets, runtime class, push/dismiss API, text-input wiring

**Status:** parked
**Created:** 2026-05-08
**Updated:** 2026-05-08

## Sources

- `Ravenswatch.exe` (Ghidra static analysis)
- `rw/ref/tree-deciphered.txt` — UI asset inventory
- `rw/dumps/modal_analysis/` — decoded modal entity-settings files harvested this session:
  - `Modal__Modal_Model.gen` (33 KB, parent template)
  - `Modal__Modal_Info.gen` / `Modal__Modal_Warning.gen` / `Modal__Modal_Error.gen` / `Modal__Modal_Timed.gen`
  - `Modal__Modal_Multiplayer.gen` (29 KB — the text-input reference)
  - `Common_Ui__Dialog_Ui.gen`, `Common_Ui__Message_Ui.gen`
- `rw/dumps/modal_save_or_quit/Modal_Save_Or_Quit.entity.ot.EntitySettingsResource.gen` (prior dump)
- `rw/findings/save-subsystem.md` § "Modal_Save_Or_Quit.entity.ot decoded" — prior partial decode
- `rw/findings/cooked-format-schemas.md` — schema decoder used to inspect modal `.gen` files
- `rw/findings/on-demand-spawn-pipeline.md` — entity factory primitive (`oCSpawner_createEntityFromSettings`)
- `tools/rerw-src/lib/cooked.py` / `cooked_schemas.py` — runtime decoder

## Verdict — parked under no-game-files constraint

**Research preserved as reference; the original session goal (a pre-chapter-load SeedInputModal) is not viable under the project's no-game-files rule.**

The constraint prohibits `.exe` patching and asset modification. Under that rule, the only remaining Frida-only paths to a "custom" modal are:

- **Hijack an existing modal** (Tier 1 — push the multiplayer text-input modal from Frida and hook its confirm callback to route the typed value to `Seed.set()` instead of EOS join). Mechanically possible but a hack-on-hack: cannot relabel the modal cleanly, repurposes an unrelated UI flow, no benefit over an external Frida REPL command for setting the seed.
- **Forge a custom modal at runtime** (Tier 3). Live capture 2026-05-08 of an active multiplayer modal showed the data-source at `oCEntityModal+0x88` is a polymorphic tree with vftables at six different offsets (+0x00, +0x10, +0x40, +0x98, +0xb0, +0xf8). Forging from scratch is impractical.
- **Asset clone** (Tier 2) — explicitly off-limits per the no-game-files rule.

The full architecture below is preserved as an RE reference. If the no-game-files constraint ever lifts (e.g., a future modding-allowed branch), Tier 2 becomes the cleanest path and the symbol map below is the entry point.

See **Notes → Custom-modal feasibility — three tiers** for the full tier breakdown.

## Confirmed Findings

### Three-layer architecture

| Layer | What it is | Where it lives |
|---|---|---|
| **Asset** | `oCEntitySettingsResource` cooked binaries — declarative UI templates with picker overrides | `EntitySettings/GameUis/Modal!*.entity.ot.EntitySettingsResource.gen` |
| **Static registry** | `oCGlobalEntitySettingsRef` instances — preloaded smart-ptrs to a fixed set of modal assets | 8 known slots in `.data` (e.g. `DAT_141410b30..b88` = Modal_Save_Or_Quit) |
| **Runtime** | `oCEntityModal` (0xf8 bytes, embedded `oCEntitySpawner` at +0x90) pushed onto `oIModalSceneContext` stack | Heap-allocated; managed by `oIModalSceneContext` (modal-stack at `+0xc0`, active at `+0xe0`) |

### Asset layer — template inheritance

`Modal_Model.entity.ot` (33 KB) is the **parent template**. It defines the full visual layout: window, picture, four labels (`Title`, `Description`, `Timer`, `InputDisplay`), three buttons (`Validate`, `Cancel`, `Matchmaking` — last one extra), and a hidden text-input slot consisting of `Edit_Frame` + `Edit_Entry` (using classes `oCUIEditDesc` / `oCUIEditStyle`).

Specialized modals override pickers on the parent. Concrete examples:

| Modal | Size | Override surface |
|---|---:|---|
| `Modal_Warning` | 700 B | Title Color only |
| `Modal_Save_Or_Quit` | 2.8 KB | Title / Description / Cancel label / Validate label (4 loc keys to `Common~GAM.xls`) |
| `Modal_Info` | 9 KB | Picture (`UI_InterrogationPoint`), Title Color, Game Ui |
| `Modal_Error` | 9 KB | Picture (`BackCross`), Title Color, Game Ui |
| `Modal_Timed` | 2.3 KB | Adds `oCEntityCpntTimerSettings` + Timer Label |
| `Modal_Multiplayer` | 29 KB | Reveals `Edit_Frame`/`Edit_Entry`, repurposes Validate as `Join_Button`, adds `Matchmaking_Button`, attaches `MultiplayerModalUiControllerEntityCpntSettings` |

The `Modal_Model` parent is referenced via the `EntitySettingsResource` parent-link at the end of the cooked file (e.g. `EntitySettings#GameUis\Modal\Modal_Model.entity.ot`).

### Static modal registry — 8 hardcoded slots

8 modal entity-settings are preloaded at process start as `oCGlobalEntitySettingsRef` static instances. Class identifier RTTI: `.?AVoCGlobalEntitySettingsRef@@` (`0x1413372c8`). Each slot's struct:

| Field offset | Content |
|---|---|
| `+0x00` | `oCGlobalEntitySettingsRef::vftable` |
| `+0x08` | `std::string` resource_type (always `"EntitySettings"`, hash `0x8000000e`) |
| `+0x10` | `std::string` resource_path (e.g. `"GameUis\Modal\Modal_Save_Or_Quit.entity.ot"`) |
| `+0x30` | linked-list next (in global resource registry at `0x141447140/148/138`) |
| `+0x38` | linked-list prev |
| `+0x50` | smart-ptr to loaded `oCEntitySettingsResource` (filled lazily by `FUN_14048be40`) |

The 8 path-string xref clusters resolve to:

| Slot region | Modal |
|---|---|
| `0x141410b30..b88` | `Modal_Save_Or_Quit` |
| `0x14140fa50..aa8` (+ 5 siblings in `0x14140faXX` range) | `Modal_News_Redirect`, `Modal_MyNacon`, `Modal_Keep_Solo_Run`, `Modal_Load_Run`, `Modal_EULA`, `Modal_Multiplayer` |
| `0x140f0e6XX` | `Modal_Difficulty_Unlocked` |

Each slot is initialized by a static-init function at `0x140024380`+ family (~14 instances), each registering one path and installing an `atexit` destructor (~10 destructor function siblings, e.g. `FUN_140e6e4f0`).

Other modals (`Modal_Info`, `Modal_Warning`, `Modal_Error`, `Modal_Timed`) are NOT in the static registry — they're loaded on-demand via the encyclopedia path or referenced by other modal templates as parents.

### Runtime layer — `oCEntityModal`

**Class:** `oCEntityModal` (RTTI `.?AVoCEntityModal@@` at `0x14134b320`). Concrete struct size **0xf8 bytes**. Derived variant: `oCEntityModalWithSpawnerCpnt`.

**Allocator:** `FUN_140271b90` (proposed: `oCEntityModal_alloc`):

```
LOCK INC DAT_141415474           ; alloc counter
ptr = _malloc_base(0xf8)
FUN_140258280(ptr)               ; ctor
ptr->vt[1](ptr)                  ; init slot 1
return ptr
```

**Constructor:** `FUN_140258280` (proposed: `oCEntityModal_ctor`). Sets:
- `+0x00` = `oCEntityModal::vftable`
- `+0x90` = `oCEntitySpawner::vftable` (the modal HAS an embedded entity-spawner sub-object)
- Other zero-init fields at `+0x88` (data-source ptr), `+0xa0..0xe0`, `+0xe8`, `+0xf0`

**Configure:** `FUN_140258320` (proposed: `oCEntityModal_set_datasource`). Refcounted store:
```c
modal[+0x88] = config_smart_ptr   // with retain/release on previous occupant
```

The data-source struct's exact shape is **NOT yet decoded** — see `## Unresolved`.

### Modal manager — `oIModalSceneContext`

Interface RTTI: `.?AVoIModalSceneContext@@` (`0x141368c28`). Concrete: `oCEntityModalSceneContext` (`0x141368b18`).

**Locating at runtime:**

```c
local_2a0 = DAT_1414476d8;        // type-id
local_2a8 = _oCTKindOfTypeTester<class_oIModalSceneContext, class_oIGameSceneContext>::vftable;
modalCtx = scene_manager_find_context_by_type(sceneMgr, &local_2a8);
```

**Manager struct fields** (offsets verified via `FUN_140685fd0` and `FUN_140686350`):

| Offset | Field |
|---|---|
| `+0xc0` | modal-stack vector data ptr |
| `+0xc8` | stack count |
| `+0xcc` | stack capacity |
| `+0xe0` | active modal pointer (top of stack post-sort) |
| `+0xe8` | input-priority list head (linked list of input-claim records) |

### Push/dismiss API

**Push (proposed name `oIModalSceneContext_pushModal`)**, `FUN_140685fd0(modalCtx, modal)`:

1. Allocate a callback subscriber node, install handler `LAB_1406a0770` with `modalCtx` user-data.
2. Append node to `modal+0x68` (modal's subscriber list, count `+0x70`, cap `+0x74`).
3. Append `modal` pointer to `modalCtx+0xc0` vector.
4. Call `FUN_140ca7390(stack, count, 8, &LAB_140686580)` — sort by comparator (priority).
5. Call `FUN_140686350(modalCtx, new_top)` — switch active modal.

**Switch active (proposed name `oIModalSceneContext_setActiveModal`)**, `FUN_140686350(modalCtx, newTop)`:

1. If `modalCtx[+0xe0]` (current active) != `newTop`:
   - On the previous active modal: clear 4 lifecycle slots at `prev+0x38/+0x50/+0x68/+0x80` (release callback function-pointers and user-data each).
   - Call `prev->vt[7](prev, 0)` — deactivate (vt slot 7 = vtable byte offset `+0x38`).
2. `modalCtx[+0xe0] = newTop`.
3. Call `newTop->vt[7](newTop, 1)` — activate.
4. Wire 4 lifecycle callbacks pointing to `LAB_14043f500`, `LAB_14069ae80`, `LAB_14069aea0`, `LAB_14069aec0` into `newTop+0x38/+0x50/+0x68/+0x80`. Strong guess: onShow / onHide / onValidate / onCancel — **not yet verified**.
5. Walk `modalCtx[+0xe8]` input-priority list, claim a slot for the new active modal.

### Save-modal init dispatcher (representative usage)

`global_save_modal_init_dispatcher` at `0x14025d3b0` is the canonical "spawn a save modal" call site. Pattern:

```c
modal = FUN_140271b90();                        // alloc + ctor + vt[1]
FUN_140258320(modal, &session->config_block);   // configure (config from one of session+0x18a8/b0/c0/d0/d8)
modal->vt[0x18](modal, ...);                    // additional setup
modal->vt[0x28](modal);                         // finalize
modal->vt[0x38](modal, 0);                      // initial flag clear
// subscribe handlers to modal+0x68 (e.g. on_event_19eadad1_request_profile_save)
FUN_140685fd0(modalCtx, modal);                 // push & activate
```

### Text-input runtime — `oCUIEdit`

**Class:** `oCUIEdit` (RTTI `.?AVoCUIEdit@@` at `0x14135d100`). Type-id `0x1689`. Class size **0x380 bytes**.

**Type descriptor location:** `DAT_141448bb8` (used by `FUN_140538b10(component_collection, DAT_141448bb8)` to look up an oCUIEdit instance from a parent's component map).

**Class registry entry:** `FUN_140406bd0` (proposed: `oCUIEdit_class_registry_init`).

**Known field:** `oCUIEdit + 0x374` is a u32 (likely max-input-length or similar; observed read into an input-request struct).

**Sibling classes:**
- `oCUIEditDesc` — type-id `0x15fc934f`, 0x138 bytes, descriptor (registry at `FUN_1404067f0`, type-descriptor at `DAT_141448c10`).
- `oCUIEditStyle` — visual style (RTTI `0x1413547c8`).
- `oCUiEditorControl` — singleton wrapper (RTTI `0x14135c4b0`); not directly hooked this session.
- `oCUISpinner` — type-id `0x168a`, 0x398 bytes (numeric-input widget; potential alt for numeric seeds).

### `oCUIEdit::vt[12]` (offset `+0x60`) = setText

Verified via `FUN_1404251a0` (proposed: `oCUIEdit_apply_input_system_text`):

```c
plVar2 = FUN_140538b10(component_collection, DAT_141448bb8);  // get oCUIEdit*
if (plVar2 && !*(char*)(g_input_system + 0xa9)) {
    // ... set up input-request struct from plVar2[+0x374]
    if (g_input_system->vt[0x118](&request, &out_string)) {
        // ★ vt[12] / +0x60 on oCUIEdit consumes the new text
        plVar2->vt[0x60](plVar2, &out_string);
    }
}
```

This fires per-frame (or per-IME-event) whenever the input system has text for the active edit widget. **This is the per-keystroke entry** — hook target for live-text mirroring on the Frida side.

`getText` was deferred — not strictly needed when `setText` mirrors every state change.

### Multiplayer "Join By Code" path — fully traced

The chain from Validate-click on `Modal_Multiplayer` to network call:

```
[User types code in Edit_Entry, Validate clicked]
         │
         ▼
[MultiplayerModalUiControllerEntityCpnt fires]
   class type-id 0x19bdb17c, struct size 0x138 bytes
   class registry init: FUN_14027b7a0
   schema vftable +0x80: LAB_14027dc50
   type descriptor: DAT_1414481c0
         │
         ▼
[Enqueue command on g_eos_command_queue (DAT_1414431c8) with tag=5,
 payload[0]=typed-code-string]
         │
         ▼
[Per-frame: FUN_14087d860 — eos_event_pump_tick]
   switch(cmd_tag) {
     case 4: EOS_Lobby_CreateLobby   // host
     case 5: EOS_LobbySearch_Find    // ★ join-by-code (uses *uStack_2f0 as lobby ID)
       EOS_Lobby_CreateLobbySearch(...)
       EOS_LobbySearch_SetLobbyId(handle, &{1, *uStack_2f0})
       EOS_LobbySearch_Find(handle, &opts, clientData, FUN_14087ade0)
     case 6, 13, etc.
   }
         │
         ▼
[FUN_14087ade0 — eos_on_lobby_search_complete]
   if (success) EOS_Lobby_JoinLobby(g_eos_lobby_interface, &opts, clientData, FUN_14087ab40)
         │
         ▼
[FUN_14087ab40 — eos_on_lobby_joined]
   transition lobby state
```

**Cleanest hijack point:** inside `FUN_14087d860` case-5, just before `EOS_LobbySearch_Find`. At that moment, `*uStack_2f0` (a `std::string` deref) IS the typed code. Read it, parse as seed, call `Seed.set()`, return early to skip the network call entirely.

Alternative (more decoupled): hook `FUN_1404251a0` for live-text mirror; on any modal dismiss (hook `FUN_140686350` onLeave), if typed text is parseable as a seed, force it.

### EOS global handles

| Address | Handle |
|---|---|
| `DAT_1414431c8` | EOS command-queue head |
| `DAT_141443518` | `g_eos_lobby_interface` |
| `DAT_1414434f0` | `g_eos_platform_handle` |
| `DAT_141443510` | `g_eos_p2p_handle` |
| `DAT_141443528` | `g_eos_rtc_audio_handle` |

## Unresolved

### `oCEntityModal+0x88` data-source struct shape

The smart-pointer set by `FUN_140258320` drives Title/Description/button labels at runtime. Required if you want to construct a fully synthetic modal config in scratch memory (rather than reusing pre-loaded asset settings). Not blocking the seed-modal hijack since we can reuse `Modal_Multiplayer`'s settings as-is.

### 4 modal lifecycle callbacks — names not verified

`LAB_14043f500`, `LAB_14069ae80`, `LAB_14069aea0`, `LAB_14069aec0` are wired into the active modal at `+0x38/+0x50/+0x68/+0x80` by `FUN_140686350`. Strong guess: onShow / onHide / onValidate / onCancel — based on slot count and position in the activation flow. Not directly decompiled this session.

### `oCUIEdit::vt[?]` for getText

Not located. The std::string buffer lives somewhere in the 0x380-byte struct; finding the exact field offset is a 10-minute follow-up (hook setText, log `this`, dump bytes near `*this+0x???`). Skipped because the setText mirror approach makes a separate getText unnecessary.

### Button-click event-hash format

Modal buttons publish a named event when clicked (same pub/sub system used for chapter-end events). Format of the per-button event hash not yet identified — would let us hook `publish_event_to_subscribers` and filter for Validate/Cancel events by hash, the most decoupled hook strategy. Not blocking; the case-5 dispatch hook is sufficient for the seed-modal use case.

### `oCEntityModalSceneContext` for non-system modals

`oIModalSceneContext` traced this session is the **save-action / system-modal stack** (chapter-end Save-or-Quit flow). In-game contextual popups (toasts, notifications, tutorial popups) likely route through the broader `GameUiSceneContext` (`0x14133b600`) — different vtable, different stack semantics. Not investigated this session.

### Adjacent UI surfaces — not yet investigated

- `Common_Ui!Notification_UI_*` — toast/notification popups via `GameUiSceneContext`.
- `Common_Ui!Dialog_Ui` — NPC speech dialog (FMOD-driven, event-state machine via `oCEntityCpntFModDialogUiControllerSettings`). Wholly different from system modals.

## Notes

### Custom-modal feasibility — three tiers

1. **Tier 1 (HIGH):** push an existing modal from Frida by reusing the static `oCGlobalEntitySettingsRef` slot. Implementation chain: `find_oIModalSceneContext` → `FUN_140271b90` (alloc) → `FUN_140258320` (config from existing slot) → `FUN_140685fd0` (push). No asset modification. Fastest to working modal.

2. **Tier 2 (HIGH):** clone a modal asset on disk. Cooked-format encoder/decoder already round-trips byte-equal (`cooked-format-schemas.md`). Override the 4 picker slots on `Modal_Model`, add new loc keys to `Common~GAM.xls`, drop into `_Cooking/`, register as a new `oCGlobalEntitySettingsRef` (or hijack one of the existing 8 hardcoded slots). Requires a game restart per iteration.

3. **Tier 3 (UNCERTAIN):** fully synthetic modal constructed at runtime in heap. Requires understanding of `oCEntityModal+0x88` data-source struct (see Unresolved) AND the encyclopedia's picker-resolution pipeline. Not pursued this session.

### Locating these symbols on a new build

**RE-side anchors** for re-discovering across patches:

- **`oCGlobalEntitySettingsRef` static init pattern:** search for code sequences calling `std_string_assign_realloc` twice with two string-literal pairs followed by `atexit(...)`. Each match is one of the ~14 modal slots.
- **`oCEntityModal::vftable`:** dereference the global written by `FUN_140258280` (the ctor, which itself is reached via the only caller of `_malloc_base(0xf8)` followed by an atomic increment of a counter near `DAT_141415474`).
- **`oIModalSceneContext` type-id:** the 64-bit value at `DAT_1414476d8` (passed as `local_2a0` into `scene_manager_find_context_by_type` along with the `_oCTKindOfTypeTester<class_oIModalSceneContext,...>::vftable`).
- **`oCUIEdit` type descriptor:** the 0x380-byte class registered by the function whose body contains the literal `"oCUIEdit"` and the type-id immediate `0x1689`.
- **`oCUIEdit::vt[12]` (setText):** the function called near the end of `FUN_1404251a0`'s success branch, after the IME extracts text via `g_input_system->vt[0x118]`.
- **EOS join command tag:** `case 5` in the EOS event pump (`FUN_14087d860`), distinguished by adjacent calls to `EOS_LobbySearch_SetLobbyId` and `EOS_LobbySearch_Find`.

### Staged Ghidra annotations — pending approval (parallel-mode rule)

Renames not applied this session because Ghidra was held read-only.

| Address | Proposed name |
|---|---|
| `0x140271b90` | `oCEntityModal_alloc` |
| `0x140258280` | `oCEntityModal_ctor` |
| `0x140258320` | `oCEntityModal_set_datasource` |
| `0x140685fd0` | `oIModalSceneContext_pushModal` |
| `0x140686350` | `oIModalSceneContext_setActiveModal` |
| `0x140271ac0` | `find_oIModalSceneContext` |
| `0x140e6e4f0` (and ~10 siblings) | `oCGlobalEntitySettingsRef_atexit_destructor` |
| `0x1400301a0` (and ~14 siblings) | `oCGlobalEntitySettingsRef_static_init_<modal_name>` |
| `0x141410b30` (and siblings) | `g_GlobalEntitySettingsRef_<modal_name>` |
| `0x1404067f0` | `oCUIEditDesc_class_registry_init` |
| `0x140406bd0` | `oCUIEdit_class_registry_init` |
| `0x14027b7a0` | `MultiplayerModalUiControllerEntityCpnt_class_registry_init` |
| `0x1404251a0` | `oCUIEdit_apply_input_system_text` |
| `0x14087d860` | `eos_event_pump_tick` |
| `0x14087ade0` | `eos_on_lobby_search_complete` |
| `0x14087ab40` | `eos_on_lobby_joined` |
| `DAT_141448bb8` | `g_oCUIEdit_typedesc` |
| `DAT_141448c10` | `g_oCUIEditDesc_typedesc` |
| `DAT_141449968` | `g_oCUISpinner_typedesc` |
| `DAT_1414481c0` | `g_MultiplayerModalUiControllerEntityCpnt_typedesc` |
| `DAT_1414431c8` | `g_eos_command_queue_head` |
| `DAT_141443518` | `g_eos_lobby_interface` |
| `DAT_1414434f0` | `g_eos_platform_handle` |
| `DAT_141443528` | `g_eos_rtc_audio_handle` |
| `DAT_141443510` | `g_eos_p2p_handle` |

Plus plate comments on `0x14025d3b0` (save-modal init dispatcher), `0x140686350` (lifecycle-slot wiring), `0x14087d860` (15-case EOS dispatch), `0x1404251a0` (IME→oCUIEdit setText path).

### Rationale for SeedInputModal feasibility (per session goal)

**Conclusion: not viable under the no-game-files constraint.** See Verdict at top of this doc.

The session's driving question was whether a pre-chapter-load seed-input modal could be built without modifying `Ravenswatch.exe` or its assets. An earlier draft of this section recommended a Tier-1 hijack of the existing multiplayer modal (intercept `EOS_LobbySearch_Find` at case 5 of the EOS event pump in `FUN_14087d860`, route the typed code to `Seed.set()`). That path is mechanically possible but was rejected as a hack-on-hack: it repurposes an unrelated UI flow, can't cleanly relabel the modal, and offers no advantage over an external Frida REPL command for setting the seed.

The follow-up live capture (2026-05-08) of an active modal's data-source struct (see Verdict) further confirms that runtime forging of a fresh modal is impractical — the data-source is a polymorphic tree, not a flat POD struct. A clean SeedInputModal would require Tier-2 asset cloning, which the project rules disallow.
