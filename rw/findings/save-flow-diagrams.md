[← Back to findings](README.md)

# Save flow architecture (Ravenswatch)
**Status:** confirmed


Architecture reference for the save subsystem: chapter-end event chain, threading model,
class hierarchy, memory layout, call topology, and binary framing — derived from static
analysis 2026-04-29 / 2026-04-30. All addresses absolute (subtract `0x140000000` for RVA).
Function names match the Ghidra DB renames; cross-walk in `save-subsystem.md`.

> **Note:** This doc was previously a mermaid-diagram companion. Converted to prose/tables
> 2026-05-06 to remove mermaid maintenance burden — same content, text form.

---

## Sources

- pre-policy — written before the Sources header was mandatory.

## 1. Chapter-end save event chain

End-to-end flow from boss death to `Profile_1.ob` written to disk. Five phases.

### Phase A — Chapter setup (runs at chapter start)

`session_subscribe_chapter_end_events` (image+0x27fde0) does three things:

1. Subscribes ~17 named events including `GAME_END_SUCCESS` at `DAT_1412bfca0`.
2. Loads `Modal_Save_Or_Quit.entity.ot` (`DAT_141410b38`) and stashes it at `session+0xf8`.
3. Publishes `GAME_CHRONO_START` via `construct_named_event` + `publish_event_to_subscribers`.

### Phase B — Boss dies → chapter-end logic

1. Engine publishes `GAME_END_SUCCESS`.
2. `LAB_1402c85c0` (vtable adjustor thunk) →
3. `0x1402835f0` (`XOR EDX, EDX; JMP 0x140283520`) →
4. `on_game_end_event_handler` (image+0x283520).
5. Branches on `game_end_should_show_modal?` (image+0x2918b0):
   - `param_2 == 0` → `game_end_no_modal_path` (image+0x285080), skips dialog → next chapter.
   - otherwise → `publish_named_event_game_end` (image+0x285710, arg=2), which constructs
     `oe::dt::NamedEventGameEnd` and fans to subscribers.

### Phase C — NamedEventGameEnd subscriber

1. Thunk at `0x1402c8750` (`JMP qword[0x140ef9d48]`) →
2. `on_named_event_game_end_handler` (image+0x28f140).
3. Updates profile_data stats at offsets `+0x230 / +0x234 / +0x240 / +0x244`.
4. Branches on state at `param_2+0x60`:
   - `3` (WIN) → `session_on_saved_dispatch` (image+0x291350) — *save path*.
   - `2` → `chapter_end_encyclopedia_and_stats_update` (image+0x28f660).
   - else / type mismatch → `session_on_abandoned_dispatch` (image+0x291190).

### Phase D — Saved dispatcher (WIN path)

`session_on_saved_dispatch` performs:

1. Sets `phase=3` at `session+0x150`.
2. Calls `chapter_end_work` (image+0x2907e0) — likely runs SerializeArchive walks and
   progressively fills `oCMemoryBinaryStream`.
3. Sets the saves-enabled flag at `session+0xa5 = 1`.
4. Publishes `'Saved'` `oCCustomFlagList` event via `FUN_14067dea0` (key `0x17cde816`).
5. Updates `profile_data->[0x244]` (chapter counter).
6. Sets `session+0x30 = 1`.

### Phase E — User clicks Save and quit → file written

1. `Modal_Save_Or_Quit` dialog (cached at `session+0xf8`) is shown.
2. User clicks "Save and quit".
3. Modal callback fires (mechanism still TBD — see *Key unresolved items* §3).
4. Callback invokes `session_finalize_and_save` (image+0x28d6a0).
5. Pre-save plumbing: `FUN_14026f750` / `FUN_14026f620` (scene-context iteration).
6. **Strongest unresolved prep candidate** — `vtable[0xd0]` indirect call:
   `scene_manager+0x708 → +0x38 → vt[0xd0]`. See §9.
7. `io_request_list_clear`, `swap_subscribed_pointer`, `profile_data` manager updates.
8. Walks linked list at `session+8`, finds `oCDtRootGs` by typedesc.
9. Branches on `*data_source+0x1ef4 == 0` (saves-enabled flag):
   - yes → `save_request_sync(NULL, data_source+0x1928)` (image+0x6797b0).
   - no → skip save.
10. `saves_queue_enqueue` (image+0x6818a0) → `ReleaseSemaphore` `g_saves_queue_semaphore`.
11. `saves_manager_worker_thread` (image+0x679150) wakes with `opcode=1=SAVE`.
12. `save_atomic_orchestrator` (image+0x678f30) reads `*(job+0x30)` and `*(job+0x38)`.
13. `oCFileBinaryStream::Write` (vtable[1] at `0x140f28d98`).
14. Writes `Profile_1_Temp.ob`, then `CopyFileW` → `Profile_1.ob`.

**Highlighted hot spots** (formerly red/orange/green nodes):
- `on_named_event_game_end_handler` — the dispatch fan-out (red).
- `chapter_end_work` — the serializer entry that fills the memstream (orange).
- The vtable[0xd0] indirect call — strongest unresolved prep candidate (red).
- `save_request_sync` — confirmed save trigger (green).

---

## 2. Save subsystem threading & queue

The worker-thread side of the save (post-enqueue). Main thread enqueues; worker thread
dequeues and writes.

### Main thread

1. `save_request_sync` (image+0x6797b0).
2. Increment `job+0x7c` (pending counter).
3. `saves_queue_enqueue` (image+0x6818a0).
4. Push 16-byte entry to ring queue at `DAT_14143ffc0`.
5. `ReleaseSemaphore` (`DAT_14143ff98`) — signals the worker.
6. Busy-wait on `job+0x80` (done counter); blocks until worker finishes.

### Worker thread

1. `saves_manager_worker_thread` (image+0x679150).
2. `WaitForSingleObject` on the semaphore.
3. Dequeue 16-byte entry.
4. Branch on opcode at `job+0xc`:
   - `0` (LOAD) → `FUN_140679810(job, DAT_14140e9c8)`.
   - `1` (SAVE) → `save_atomic_orchestrator` (image+0x678f30).
   - `2` (DELETE) → `(*DAT_14140e9e0)(job, &name)`.
5. SAVE path:
   1. `EnterCriticalSection` on `manager+0x20`.
   2. `FUN_14064b2f0` pre-save guard stub (always returns 1 on PC).
   3. `job+0x79 = 1` (TEMP mode on).
   4. `FUN_140679810(job, DAT_14140e9c0)` — writes `Profile_1_Temp.ob`.
   5. `job+0x79 = 0` (TEMP mode off).
   6. `FUN_1405229b0` — `CopyFileW` Temp → real (`Profile_1.ob`).
   7. Increment `job+0x80` (done) and set `job+0x84` (result code).
   8. `LeaveCriticalSection`.
   9. Loop back to step 2.

The semaphore release in main-thread step 5 is what unblocks the worker's
`WaitForSingleObject` in worker-thread step 2. The done-counter increment in worker-thread
step 5.7 is what unblocks the main-thread busy-wait in step 6.

---

## 3. Class hierarchy & data layout (oCDtRootGs)

The `data_source` struct with the embedded `oCMemoryBinaryStream`.

### Inheritance chain

```
oIGameState (interface, has vftable)
  └── oCConsolesRootGs (has vftable)
        └── oCDtRootGs (vftable @ 0x140ef49d8, size 0x21d0)
```

### Class layout summary

| Class | Size | Key fields |
|---|---|---|
| `oCDtRootGs` | `0x21d0` | vftable @ `0x140ef49d8`; `+0x08` linked_list_next; `+0x18d8` `oCDtGameProfile`; `+0x1ef4` saves_disabled_flag; `Serialize()` at vtable[3] = `0x140c01570` |
| `oCDtGameProfile` | `0x3b8` | inherits `oIGameProfile` at `+0x00`; `save_io_job` at `+0x50`; `oCDtPlayerProfileData` at `+0x178` |
| `oIGameProfile` (base) | — | `+0x08` flag; `+0x10` `DAT_140edbfa0`; `+0x50` `save_io_job` |
| `save_io_job` | — | `+0x00` path1_string; `+0x10` path2_string; `+0x20` `oCMemoryBinaryStream`; `+0x7c` pending_seq; `+0x80` completed_seq; `+0x84` result_code |
| `oCMemoryBinaryStream` | — | inherits `oIWriteBinaryStream` + `oIReadBinaryStream`; vftable_write @ `0x140f28d80`; vftable_read @ `0x140f28d48`; `+0x10` buffer_ptr (= `job+0x30`); `+0x18` capacity (= `job+0x38`); `+0x24` used_size (= `job+0x44`); `Write()` at vtable[1] = `0x1405257d0` |

### Containment

- `oCDtRootGs` *embeds* `oCDtGameProfile` at `+0x18d8`.
- `oCDtGameProfile` *embeds* `save_io_job` at `+0x50`.
- `save_io_job` *embeds* `oCMemoryBinaryStream` at `+0x20`.

---

## 4. Memory offsets (data_source absolute layout)

Where the buffer pointer and size live within `data_source`. Numbers are absolute offsets
from the start of the `oCDtRootGs` struct.

| Offset | Field | Notes |
|---|---|---|
| `+0x0000` | vtable | `0x140ef49d8` |
| `+0x0008` | linked_list_next | |
| `+0x18d8` | `oCDtGameProfile` (embedded, 0x3b8 bytes) | start of profile section |
| `+0x18d8` (`+0x00`) | `oIGameProfile` vtable | base-class vtable for the profile |
| `+0x1928` (`+0x18d8 + 0x50`) | `save_io_job` (start) | path1 string |
| `+0x1938` | path2 string | |
| `+0x1948` | `oCMemoryBinaryStream` (write side vtable) | |
| `+0x1950` | `oCMemoryBinaryStream` (read side vtable) | |
| `+0x1958` | **buffer_ptr (u64)** ★ | NULL at construction; grown on Write |
| `+0x1960` | **capacity (u32)** ★ | read by `save_atomic_orchestrator` as 'size' |
| `+0x196c` | used_size (u32) | |
| `+0x19a4` | pending_seq (u32) | |
| `+0x19a8` | completed_seq (u32) | |
| `+0x19ac` | result_code (u8) | |
| `+0x1ef4` | saves_disabled_flag (u8) | bottom-line gate read by `session_finalize_and_save` |

`+0x1958` and `+0x1960` are the two pointer/size slots `save_atomic_orchestrator` reads.
First-write of `+0x1958` is the "★ THE PREP" hot spot — see §9, *Key unresolved items* §1.

---

## 5. Serialization paths (settings save vs run-state save)

Two distinct serializer paths. The settings path uses `oCBinarySaver` + `oCFileBinaryStream`
(direct file). The run-state path uses an embedded `oCMemoryBinaryStream` that grows in
memory, then `save_atomic_orchestrator` copies bytes to disk.

### Settings save path (`GameSettings.ini`, profile data)

1. `settings_serialize_load_or_save_ini` (image+0x64b2f0) →
2. `oCBinarySaver` constructor (image+0x4e8ca0) →
3. `oCBinarySaver` instance (vtable @ `0x140f235e0`) embeds `oCFileBinaryStream` at
   `saver+0x20` (vtable @ `0x140f28d98`).
4. `serialize_object_with_name` (`FUN_1404e9350`) writes class-registry section + object
   section markers (`0xAABB1111`, `0xAABB2222`).
5. Per-object `Serialize` (vtable slot 3 of each object).
6. `oCFileBinaryStream::Write` (image+0x140f28d98 vt[1]) → direct file write to .ini.

### Run-state save path (`Profile_1.ob`, chapter end)

1. `chapter_end_work` (image+0x2907e0) — likely entry. Drives the serializer/archive that
   writes to the embedded stream via vtable dispatch.
2. Embedded `oCMemoryBinaryStream` at `data_source+0x1948`.
3. `oCMemoryBinaryStream::Write` (image+0x5257d0 vt[1]) — grows buffer dynamically.
4. Buffer accumulated at `*(data_source+0x1958)`; size at `*(data_source+0x1960)`.
5. `save_request_sync(NULL, job)` via `session_finalize_and_save`.
6. `saves_manager_worker_thread` →
7. `save_atomic_orchestrator` →
8. Read `*(job+0x30)` + `*(job+0x38)`, write to `Profile_1_Temp.ob` via
   `oCFileBinaryStream::Write`.
9. `CopyFileW` → `Profile_1.ob`.

`oCMemoryBinaryStream` and its `Write` vtable slot are the hot spots — `Write` is what
actually fills the in-memory buffer that the worker thread later flushes to disk.

---

## 6. Save call topology (verified)

Three relevant entry points and their callers.

### `save_request_sync` (image+0x6797b0)

Exactly **one caller**: `session_finalize_and_save` (image+0x28d6a0). This is the *sync*
trigger — caller blocks on the worker. Confirmed save trigger.

### `save_request_async` (image+0x679760)

**Four callers**, all targeting `*(DAT_14140dd70)+8` (the global save manager):

- `global_save_modal_init_dispatcher` (image+0x25d3b0, at +0x25db45)
- `global_save_dispatcher_chapter_state` (image+0x261ca0, at +0x262f33 *and* +0x26308d)
- `profile_mark_chapter_complete_save` (image+0x26c700, at +0x26c781)

### Lower-level entry points (bypass)

- `saves_queue_enqueue` (image+0x6818a0) — direct queue push.
- `save_atomic_orchestrator` (image+0x678f30) — direct call, bypasses the queue.

---

## 7. Save format magic markers (binary save framing)

Discovered in `FUN_1404e9350` (`serialize_object_with_name`).

| Marker | Value | Stored at | Purpose |
|---|---|---|---|
| Class registry section | `0xAABB1111` | `DAT_140eb3ae8` | Frames the class-registry section |
| Object section | `0xAABB2222` | `DAT_140eb3aec` | Frames the object section |

### Per-class entry layout (inside class-registry section)

- `m_sName` (string)
- `m_uId` (u32)
- `m_uVersionMaj` (u16)
- `m_uVersionMin` (u16)
- `m_uParentId` (u32)

### Per-object entry layout (inside object section)

- `uFoundIndex` (u32) — references a class entry by index
- The object's `Serialize()` then writes its fields immediately after.

---

## 8. Anti-debug tripwires (empirical, 2026-04-29)

Trip conditions when WinDbg is attached to the running game.

| Game state | Behavior with debugger attached |
|---|---|
| Main menu / settings save | OK — breakpoints work normally |
| Boss-spawn transition | `__debugbreak()` fires; process exits with `STATUS_BREAKPOINT 0x80000003` |
| Boss-kill transition | `__debugbreak()` fires; process exits with `STATUS_BREAKPOINT 0x80000003` |
| Chapter-end animation (post-boss-die window) | OK — attaching during this window is safe |

Implication: attach window for save-pipeline debugging is between the post-boss-die
animation start and the modal callback firing. Don't attach during boss-spawn or
boss-kill transitions.

---

## 9. Prep chain (refined 2026-04-30 night)

End-to-end chain from `session_finalize_and_save` into the static prep candidate. The
runtime-installed slot's concrete class is selected by `GameMode` name and cannot be
pinned by static analysis alone.

1. `session_finalize_and_save` (image+0x28d6a0) — `GameSessionGs::vtable[6]`.
2. `FUN_14026f750` / `FUN_14026f620` — list/state plumbing.
3. Branch on `session+0xa5` (saves enabled?):
   - **No** → `profile_data_manager+0x198`, `vtable[0x10]` teardown. End.
   - **Yes** → continue:
     1. `R14 = *(scene_manager+0x708)` — points to `oe::dt::GameModeDefault*` (size 0x48).
     2. `RCX = *(R14+0x38)` — **runtime-installed subsystem** (the slot whose concrete
        class is GameMode-dependent; this is the "green node" — known by structure, not
        by name).
     3. `serializer = RCX->vtable[0xf8]()` — factory creates the serializer.
     4. `serializer->vtable[0x40](R14)` — **THE PREP** — populates the memstream
        (red hot-spot; first-writer of `*(data_source+0x1958)`).
     5. `profile_data_manager+0x1e0 = serializer` — cache for later teardown.
4. Walk `session+8` linked list → `data_source`.
5. `save_request_sync(NULL, data_source+0x1928)`.

**Earlier in `session_finalize_and_save` (NOT prep — distractor):**
`scene_manager+0x230` is the cached `oCDtP2PSessionSceneContext`; its `vtable[0xd0]` is
`oCDtP2PSession_shutdown_raknet` (network teardown, not a save prep).

---

## 10. GameModeDefault+0x38 install path (registry by name)

How the prep target gets installed. Static analysis reveals the mechanism but cannot
resolve the concrete class.

### Constructor path

1. `oe_dt_GameMode_constructor` (image+0x31b950).
2. `param_1+0x38 = NULL` (initialize the slot).
3. Scan registry at `*(DAT_141447698+0x30)`:
   - For each entry, check `entry+0x8 == 0x53b64d` (magic).
   - On match: `handler = entry+0x10`.
4. Call `handler->vtable[0x18](handler, name_string, _DAT_1412c7590, &param_1+0x38, 0)`
   — last arg is the OUT pointer; the call writes the concrete subsystem pointer back
   into `param_1+0x38`.
5. `+0x38` now holds a `concrete subsystem*` whose class depends on `name_string`.

### Module-registry init (where the magic-tagged entries come from)

1. `module_registry_init_with_magic_0x53b64d` (image+0x442bb0).
2. Iterates global module list at `DAT_141414090`.
3. Per module: inserts an entry tagged `0x53b64d` into the per-module registry.

So the registry is populated at module-init time; lookups happen at GameMode construction.

---

## 11. Modal_Save_Or_Quit.entity.ot decoded layout

The cooked `.gen` format that defines the chapter-end save dialog.

### File framing

1. **Header** — 16 bytes, `'Cooked'` identifier.
2. **u32 count + u8 marker** — preamble.
3. **`0xAABB1111` — section start** (class registry section).
4. **Class registry** — 14 classes for this modal:
   - `oCEntitySettingsResource`
   - `oCEntityCpntWindowUiSettings`
   - `oCEntityCpntLabelUiSettings` × N buttons
   - `oCEntityCpntPicker` / `oIUniqueObjectPicker` (references `Modal_Model.entity.ot`)
   - (and the rest of the 14, listed in the asset itself)
5. **`0xAABB1111` — object section start** (note: same marker; section disambiguated by
   position).
6. **Object bodies** — each: `class_index (u32)` + 16-byte GUID + class fields.
7. **`0xAABB2222` — section end**.

### Object semantics (the labels you see in-game)

| Object | Localization key | User-facing string |
|---|---|---|
| Title | `Message_Save_And_Quit_Title` (Common~GAM.xls) | (title text) |
| Description | `Message_Save_And_Quit_Description` | (body text) |
| **Cancel button** ★ | `Message_Save_And_Quit` | "Save and Quit" — this is the action |
| Validate button | `Message_Continue` | "Continue" |

### Note — buttons are abstract

There are no callback IDs in the `.gen`. The buttons are abstract `Cancel` / `Validate`
slots. The wiring is C++-bound: the host's `OnCancel` handler is what implements
"Save and Quit." So picking it apart in `.gen` only gives you label + structure, not
behavior.

---

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. This is an architecture
doc; nearly every RVA cited here is anchored elsewhere. **Re-anchor `save-subsystem.md`
first** (its Tier 1-5 anchor tables cover all save-subsystem RVAs in this doc) and the
content here remains valid.

### Symbols specific to this doc

| Symbol class | Anchor |
|---|---|
| Save-format magic markers (§7) | These are byte values in the format itself, not RVAs. They survive recompiles unless save format changes. The magic-byte table in this doc IS the anchor. |
| Anti-debug tripwire RVAs (§8) | Each tripwire's signature: a bare `INT 3` or distinctive timing-check sequence. Re-derive empirically by triggering the corresponding game state with a debugger attached. |
| `Modal_Save_Or_Quit.entity.ot` decoded layout (§11) | This is asset-side, not binary-side. Survives binary recompiles entirely — anchored by the asset file name in `rw/ref/tree-deciphered.txt`. |
| GameModeDefault+0x38 install path (§10) | Anchor: GameModeDefault RTTI (`save-subsystem.md` Tier 1) + walk to `+0x38` at construction. |

### Cross-finding anchoring

This doc is composed almost entirely of cross-references to `save-subsystem.md` and
`frida-pipeline-hardware-breakpoint.md`. Re-anchoring those two findings updates this one
transitively. No locator section unique to this doc beyond what those two provide.

## Key unresolved items

1. **Where exactly is `*(data_source + 0x1958)` first written non-NULL?** Static analysis
   hits a ceiling because the write happens via vtable-dispatched `oCMemoryBinaryStream::Write`
   calls that aren't in the xref graph. The cleanest path forward is a hardware data
   breakpoint on the buffer-pointer slot during a real chapter run. The instruction at the
   fire point IS the prep call.
2. **What is `oCDtRootGs::vtable[3]` (= `0x140c01570`) actually?** Disassembly shows it's
   a code chunk inside a larger function (`FUN_140c01480`) that uses critical sections —
   looks like a thread-safe init/finalizer, not a Serialize method. The `data_source`'s
   actual Serialize entry may be at a different vtable slot or invoked via a different
   mechanism.
3. **Modal callback → `session_finalize_and_save` link.** When the user clicks "Save and
   quit" on the modal, what wires the click to invoke `session_finalize_and_save`? The
   vtable that holds it (at `0x140efa120` slot 0) has no callers in static xrefs.

## Cross-references

- `rw/findings/save-subsystem.md` — full architecture and function map
- `rw/findings/frida-pipeline-hardware-breakpoint.md` — operational doc for Frida save-trigger
- `rw/docs/ghidra-windbg-mcp-for-wsl.md` — debugger setup and known limitations
- `.ai/scratch/rw-parallel-findings.md` — side discoveries (anti-debug, RTTI, false leads)
- `.ai/scratch/rw-context-handoff-20260430-010309.md` — supersedes prior handoffs
