[← Back to findings](README.md)

# Save: subsystem architecture and live-trigger map

How Ravenswatch saves are written to disk: the threading model, function call chain, key globals, and the addresses needed to trigger an on-demand save from a live game.

**Status:** confirmed
**Status notes:** Architecture mapped 2026-04-29 / extended 2026-04-30. Save subsystem trigger pipeline confirmed: Frida invocation of `save_request_sync` successfully causes the worker thread to write `Profile_1.ob` to disk. **However, the produced file is incomplete:** `save_request_sync` only enqueues a write of bytes already prepared at `job+0x30`. A separate **prep / serializer function** (location TBD) is responsible for walking the live run-state and serializing it into that buffer before the natural game save. We bypassed that step. The 2026-04-30 Ghidra pass mapped the full chapter-end event chain (see "Chapter-end save chain — verified call topology" below) but the exact instruction that writes `*(data_source + 0x1958)` is not yet pinpointed; suspected to be inside `chapter_end_work` (image+0x2907e0) or a vtable[0xd0] call from `session_finalize_and_save`. The 2026-04-30 effort also empirically identified a WinDbg anti-debug tripwire at boss-spawn and boss-kill transitions — see "Empirical: WinDbg anti-debug behavior" below.

**Created:** 2026-04-29 · **Extended:** 2026-04-30

## TL;DR

Saves are written by a dedicated **worker thread** that pulls jobs from a queue. The natural trigger (chapter completion → game UI → **prep step (TBD)** → enqueue save → worker writes) is async; you can't make the main thread block on a save call.

**The prep step is the missing piece.** `save_request_sync` does not introspect the run state — it just queues a write of bytes at `job+0x30`. The natural save flow has a serializer that walks live state and populates that buffer before triggering. Calling `save_request_sync` directly (as our current Frida script does) writes whatever was previously in the buffer (typically catalog + hero header + last talents) — a partial save the engine does NOT recognize as a continuable run.

Three paths to force a save on-demand, in order of simplicity:

1. **Public sync API call.** `save_request_sync(NULL, job_ptr)` (= `image_base + 0x6797b0`). Bumps seq, enqueues, signals worker, busy-waits until done. Cleanest single-call path.
2. **Public async API call.** `save_request_async(NULL, job_ptr)` (= `image_base + 0x679760`). Same enqueue+signal but returns immediately; caller polls `job_ptr+0x80` for completion.
3. **Direct orchestrator call.** `save_atomic_orchestrator(manager, job)` (= `image_base + 0x678f30`). Bypasses the queue and runs the save inline. Requires also passing the manager pointer.

Both require knowing one address at runtime: the saves-manager instance pointer. **Resolved:** the singleton is stored at `g_saves_manager_singleton` (= `Ravenswatch+0x12cbe50`). At runtime:
```c
manager = *(uintptr_t *)(image_base + 0x12cbe50);
```
Set by either `saves_manager_init_with_path` (0x14067a360) or `saves_manager_init_default` (0x140679660) at engine init — both write the freshly-constructed manager to that slot before launching the worker thread.

## Sources

- Ravenswatch.exe (Ghidra project `Ravensmith.rep`, image base 0x140000000) — all addresses below are absolute (subtract `0x140000000` for RVA).
- `/mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save/` — observed save folder layout (`Profile_1.ob`, `Profile_1_Temp.ob`, `GameSettings.ini`, `GameSettings_Temp.ini`, `steam_autocloud.vdf`).
- Strings: `_Save\` (`0x140f8da98`), `_Temp` (`0x140f3ddf8`), `.ob` (`0x140f1909c`), `.ini` (`0x140f1d948`), `Saved` (`0x140ef73e0`), `Game save` (`0x140f19478`), `Applying savegame` (`0x140f19498`), `oCBinarySaver`/`oCPcSavesManager` RTTI tags.

## Architecture diagram

```
[main thread: chapter-completion dispatcher FUN_14028f140]
   ↓ phase==3 (win)
[FUN_140291350]                           ← also broadcasts "Saved" event
   ├─ FUN_1402907e0 (chapter-end work)
   └─ <save job enqueued somewhere along this path>
                              ↓ enqueue
[ring queue at DAT_14143ffc0] ← signaled by [semaphore DAT_14143ff98]
                              ↓ wakes
[worker thread: saves_manager_worker_thread (0x140679150)]
   ↓ reads opcode at job+0xc
   ├ opcode=0  → LOAD   FUN_140679810(job, DAT_14140e9c8)
   ├ opcode=1  → SAVE   save_atomic_orchestrator(manager, job)
   └ opcode=2  → DELETE (*DAT_14140e9e0)(job, &name)

[save_atomic_orchestrator (0x140678f30)]
   EnterCriticalSection(manager+0x20)
   FUN_14064b2f0(job)                                  ← pre-save state setup
   (*DAT_14140e9d0)(local_res8)                        ← TRIVIAL STUB on PC — always returns 1
   *(job + 0x79) = 1                                   ← TEMP filename mode ON
   FUN_140679810(job, DAT_14140e9c0)                   ← write Profile_1_Temp.ob
   FUN_140679810(job)                                  ← second write
   *(job + 0x79) = 0                                   ← TEMP filename mode OFF
   FUN_1405229b0(temp_path, real_path)                 ← CopyFileW(temp, real, overwrite) — temp persists as backup
   LeaveCriticalSection
```

The `oCFileBinaryStream` class is the actual byte-level serializer. Its vtable[1] is the WRITE method, called inside `save_write_binary_stream` (0x140679b90).

## Function map (renamed and plate-commented in Ghidra)

| Address | Name | Role |
|---|---|---|
| `0x140679150` | `saves_manager_worker_thread` | Thread loop. Reads jobs, dispatches by opcode. Entry point of the save thread. |
| `0x140678f30` | `save_atomic_orchestrator` | Performs one save: write to Temp file, atomic rename. Call this for save-on-demand. |
| `0x140679b90` | `save_write_binary_stream` | Opens `oCFileBinaryStream` for write, calls vtable[1] to serialize `(*(param_1+0x30))[0..*(param_1+0x38)]`. |
| `0x1406798d0` | `save_read_binary_stream` | Opens stream for read, calls reader. Mirror of write. |
| `0x140679f80` | `save_delete_file` | Resolves path, calls `FUN_140522790` (Win32 DeleteFileW wrapper). |
| `0x140678e40` | `resolve_save_full_path` | Concatenates `_Save\` root (from global `DAT_14140ddb8`) + `build_save_filename` output. |
| `0x14064b140` | `build_save_filename` | Builds basename + optional `_Temp` + extension. Used for `Profile_1.ob` and `GameSettings.ini`. |
| `0x140679810` | `FUN_140679810` (unrenamed; generic IO dispatcher) | `(*param_2)(param_1, &filename, ...)`. Called by orchestrator with write/read fn-ptr. Stores result code at `param_1+0x84`. |
| `0x14067a160` | `saves_manager_global_init` | Constructs the static manager struct, registers all IO function-pointer globals. |
| `0x14067a360` | `saves_manager_init_with_path` | Path-aware init wrapper; sets singleton ptr and starts the worker thread. |
| `0x140679660` | `saves_manager_init_default` | Default-path init wrapper (same shape, no path arg). |
| `0x1406818a0` | `saves_queue_enqueue` | Pushes a 16-byte entry into the ring queue. **Caller signals semaphore separately.** |
| `0x140680760` | `saves_queue_init` | Allocates initial bucket(s) for the ring queue. |
| `0x1405229b0` | (unrenamed; `CopyFileW` wrapper) | Path-normalized `CopyFileW(src, dst, FAIL_IF_EXISTS=0)`. Used for the Temp→real step. |
| `0x14067a590` | (unrenamed; pre-save guard stub) | 3-instruction stub: `*RCX=0; return 1`. PC-only no-op. |

Adjacent and named earlier in this session:

| Address | Name | Role |
|---|---|---|
| `0x140380360` | `serde_hero_owned_mo_persistent_data` | Inner item-record serde (16-byte GUID via `vtable[0x90]` u32 path, counter via `vtable[0xa8]`). |
| `0x1403b4550` | `serde_vec_hero_owned_mo_persistent_data` | Vector-of-records serde (unified read/write). |
| `0x140380490` | `serde_hero_controller_persistent_data` | Hero-level persistent-data serde (parent of the above). |
| `0x140212f90` | `serde_guid_as_4xu32` | Generic 16-byte GUID serializer (treats as 4× u32 via stream `vtable[0x90]`). |
| `0x14025b9e0` | `initial_loading_orchestrator` | InitialLoading phase machine; calls Nacon-OS init. |
| `0x14025e8d0` | `profile_slot_path_load` | Builds `"Profile_{slot}"` path string (no extension). |
| `0x14044e8c0` | `applying_savegame_orchestrator_LOAD` | Load-side orchestrator — emits `"Applying savegame"`. |
| `0x14044e6b0` | (unrenamed; `"Game save"` log emitter) | Logger thunk for save-side messages. |

## Job struct layout (partial, inferred)

The ring-queue entries are 16-byte records pointing to job structs:

```
job+0x00: longlong  ptr to data buffer (passed as param_1 of save_write_binary_stream)
job+0x0c: int       opcode (0=LOAD, 1=SAVE, 2=DELETE)
job+0x30: longlong  serialize-source pointer (data to write — passed to oCFileBinaryStream::Serialize)
job+0x38: int       serialize size (bytes)
job+0x48: longlong  extension flag — non-zero → ".ob", zero → ".ini"
job+0x79: byte      _Temp suffix flag — temporarily set to 1 by save_atomic_orchestrator during the temp-write
job+0x84: byte      result code (0 = success, 2/3/4/5/7 = various errors)
job+0xa0: ...       state struct (FUN_1401ff840 copies into here pre-save)
job+0xd0: ...       completion event/handle (FUN_1402b6970 signals)
```

Field offsets confirmed by `save_atomic_orchestrator`, `saves_manager_worker_thread`, and `save_write_binary_stream` decompiles. Full struct probably ≥ 0x100 bytes; not all fields decoded.

## Key globals

| Global | Likely role |
|---|---|
| **`g_saves_manager_struct`** (`0x14143fcd0`) | **Saves manager singleton (statically allocated).** Address itself is the manager pointer. Pass as `param_1` to `save_atomic_orchestrator`. |
| `g_saves_manager_singleton` (`0x1412cbe50`) | Holds pointer to the manager (= `&g_saves_manager_struct`). One indirection. |
| `g_saves_manager_worker_fn` (`0x1412cbe48`) | Worker thread function pointer (= `saves_manager_worker_thread`). |
| `g_saves_manager_thread_handle` (`0x141444b90`) | `HANDLE` from `CreateThread`. |
| `g_saves_manager_active` (`0x141444514`) | Worker active flag (worker thread's outer `while`). Setting to 0 stops the worker; non-zero keeps it alive. |
| **`g_saves_queue_semaphore`** (`0x14143ff98`) | Worker semaphore. `ReleaseSemaphore(g_saves_queue_semaphore, 1, NULL)` wakes the worker after enqueuing a job. |
| **`g_saves_queue_head_bucket`** (`0x14143ffc0`) | Pointer to head bucket (dequeue side). Worker reads from here. |
| **`g_saves_queue_tail_bucket`** (`0x141440000`) | Pointer to tail bucket (enqueue side). `saves_queue_enqueue` writes here. |
| `g_saves_queue_bucket_capacity` (`0x141440008`) | Per-bucket capacity, default `0x200`, doubles on growth, capped at `0x200`. |
| `DAT_141444b98` | Last QPC counter at save trigger time — drives the 1000ms vs INFINITE wait choice. |
| `DAT_14140e9b0` | Pre-save guard fn-ptr — must return non-zero for load to proceed (else error code 1). |
| `DAT_14140e9b8` | Post-save callback fn-ptr (load path). |
| `DAT_14140e9c0` | **Save-write file IO fn-ptr** (passed as `param_2` to `FUN_140679810` from `save_atomic_orchestrator`). |
| `DAT_14140e9c8` | **Save-load file IO fn-ptr.** |
| `DAT_14140e9d0` | Pre-write guard fn-ptr — must return non-zero for save to proceed (else error code 6 in `FUN_140678f30`, code 8 for delete). |
| `DAT_14140e9d8` | Post-IO completion callback fn-ptr (called after both write and delete). |
| `DAT_14140e9e0` | Delete file IO fn-ptr. |
| `DAT_14140ddb8` | Save-folder root path (oCString-shaped at +0x08, length+flags at +0x10). Concatenated with `build_save_filename` output by `resolve_save_full_path`. |

The `(*DAT_14140e9d0)(local_res8)` pre-write guard at the top of `save_atomic_orchestrator` is interesting: if this returns 0, the save short-circuits with error code 6 and never writes. Likely candidates for what this guards: Steam Cloud lock acquisition, write-permission re-check, or a flag set by a "save in progress" debounce. Worth tracing if forcing a save fails.

## Triggering a save on demand

### Path 1 — direct call

Pseudo-C:
```c
uintptr_t image_base = /* from `lm m Ravenswatch` */;
typedef int (*save_atomic_t)(void *manager, void *job);
save_atomic_t save_atomic = (save_atomic_t)(image_base + 0x678f30);
void *manager = (void *)(image_base + 0x143fcd0);   // g_saves_manager_struct (static)
save_atomic(manager, job_ptr);
```

Requirements:
- `manager`: just take the address of the statically allocated `g_saves_manager_struct` at `image_base + 0x143fcd0`. Or equivalently `*(void**)(image_base + 0x12cbe50)`. **Resolved.**
- `job_ptr`: a save-job struct. Easiest: capture one from a live game by breakpointing `save_atomic_orchestrator` at chapter completion and recording RDX. Reuse that pointer for subsequent forced saves (game keeps the job buffer alive across saves).
- The pre-save guard `(*DAT_14140e9d0)` is a 3-instruction stub that always returns 1 on PC, so nothing in `save_atomic_orchestrator` can refuse the call.

### Path 2 — queue injection

Push a synthesized 16-byte entry onto the ring queue, then signal the worker thread's semaphore. Cleaner because the worker handles all the locking/state correctly.

Pseudo-C:
```c
struct queue_entry { void *job_ptr; uint32_t opcode; uint32_t aux; } entry;
entry.job_ptr = job_ptr;          // pointer to a save-job struct (e.g., captured at chapter end)
entry.opcode  = 1;                // SAVE
entry.aux     = 0;                // any value; gets stored at job_ptr+0x80 after dispatch

// Enqueue (image_base + 0x6818a0)
typedef int (*enqueue_t)(void *unused, void *entry);
((enqueue_t)(image_base + 0x6818a0))(0, &entry);

// Wake the worker
ReleaseSemaphore(*(HANDLE *)(image_base + 0x143ff98), 1, NULL);
```

The enqueue function (`saves_queue_enqueue` at `0x1406818a0`) walks the linked-list of ring buckets (head `g_saves_queue_head_bucket`, tail `g_saves_queue_tail_bucket`), allocates a new bucket if all are full, and writes the 16-byte entry to the next slot. Bucket layout:

```
bucket+0x00 : u64 head index (next dequeue slot)
bucket+0x40 : u64 tail index (next enqueue slot)
bucket+0x48 : u64 cached head
bucket+0x80 : u64 ptr to next bucket (linked list)
bucket+0x88 : u64 ptr to data buffer (array of 16-byte entries)
bucket+0x90 : u64 capacity_mask (= capacity - 1; ring wrap)
bucket+0x98 : u64 original malloc base (for free)
```

Default bucket capacity is `0x200` entries, doubling on growth.

Path 1 is simpler if you only need one save-on-demand and have a captured job pointer; Path 2 is more correct if you want to issue many saves or interact with normal game-driven saves without bypassing the queue.

## Empty-save discovery (2026-04-29 evening)

After the Frida pipeline triggered a successful `save_request_sync` end-to-end (`Profile_1.ob` mtime updated, CRC valid), the resulting file was **NOT recognized as a continuable save** by the engine: relaunching the game showed only "New Game", no "Continue" option.

Analysis of the file (`rw/saves/proofs/geppetto/chapter1/frida-trigger-1/Profile_1.ob`):

| Field | Frida-saved | Chapter 2 (working) |
|---|---|---|
| Size | 71,644 | 74,239 |
| CRC | valid | valid |
| Catalog records (114, immutable) | 114 | 114 |
| Real `tag=0x1a` item records | **0** | 21 |
| Hero GUID prefix in run-state body | matches | matches |
| Talent GUID present in run-state body | yes (1 talent) | yes (5+) |
| run-state body+0x59 (chapter-2 items count) | 0 | 21 |
| Engine treats as resumable? | **no** | yes |

The save retains the persistent items that don't change per save (catalog records, hero GUID, the player's currently-picked talent which is held in some always-populated buffer). It DOES NOT retain run-progress data (item records, run state markers). This is the signature of "writer dumped the buffer, but no one prepared the buffer with current state."

The `save_atomic_orchestrator` decompile reveals the writer reads `*(job+0x30)` (data buffer pointer) and `*(job+0x38)` (size) and serializes those bytes via `oCFileBinaryStream::vtable[1]`. Neither `save_request_sync` nor the worker thread populates these fields. The 2026-04-30 Ghidra pass eliminated the original prep candidates (`FUN_140678780` is `io_request_list_clear` — a list teardown; `FUN_1406ce030` is `swap_subscribed_pointer` — a state-pointer swap; neither writes the save buffer). The actual prep is somewhere in the chapter-end chain (see next section), most likely inside `chapter_end_work` or one of its sub-calls, OR via the vtable[0xd0] call inside `session_finalize_and_save`:

```c
// from session_finalize_and_save (image+0x28d6a0), early in the function
(**(code **)(**(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x20) + 0x18) + 0x230) + 0xd0))();
// chain: scene_manager -> +0x18 -> +0x230 -> vtable[0xd0]
```

That vtable[0xd0] call is the most likely "serialize-self-to-buffer" entry point. Identifying it requires resolving the runtime vtable address of whatever object lives at `(scene_manager+0x18)+0x230`. Pending.

## Chapter-end event bus findings (2026-04-29)

Static analysis of the save-or-continue modal path shows the engine uses hashed/interned event IDs at runtime, not raw event-name strings.

For `GAME_END_SUCCESS`:

- String literal: `0x140ef16c8`.
- Runtime event ID storage: `DAT_1412bfca0`.
- Initializer write: `0x14002e537`.
- Runtime reads: `0x140280574` and `0x140281832`.
- The string initializer hashes the literal with the CRC table, calls `FUN_140506950(0, crc)`, and stores the returned ID in `DAT_1412bfca0`.

In `FUN_14027fde0`, event subscription has a consistent shape:

1. Load an event ID.
2. `FUN_14023d6e0(event_map, out_pair, &event_id)` finds or creates the event bucket.
3. `FUN_140216210()` allocates a callback node.
4. `FUN_140503df0(callback_node, closure)` installs the callback closure.
5. The callback node is appended to the bucket list/vector and saved on the session for cleanup.

Important confirmed wires:

| Event | ID storage | Subscribe site | Callback thunk | Handler |
|---|---|---:|---|---|
| `GAME_END_SUCCESS` | `DAT_1412bfca0` | `0x140280574` | `LAB_1402c85c0` | `FUN_140282df0` |
| `GAME_END_SUCCESS_SKIP_NEXT` | `DAT_1412c02a0` | `0x140280644` | `LAB_1402c85e0` | `FUN_140282b50` |
| `GAME_CHRONO_START` | `DAT_1412c00a8` | publish at `0x140280e8f`/`0x140280eb5` | n/a | n/a |

`FUN_14027fde0` loads the save-or-continue modal resource (`GameUis\\Modal\\Modal_Save_Or_Quit.entity.ot`), stores the modal handle at `session+0xf8`, then constructs and publishes `GAME_CHRONO_START`:

```text
0x140280e8f: lea rdx, [DAT_1412c00a8]   ; GAME_CHRONO_START descriptor/ID
0x140280e9d: call FUN_140652960         ; construct oCGameNamedEvent
0x140280eb5: call FUN_140652b60         ; dispatch/publish event
```

Implication: `FUN_14027fde0` is both a subscriber-registration function for `GAME_END_*` events and the modal setup/publish path for `GAME_CHRONO_START`. The upstream question is now where `GAME_END_SUCCESS` is published; that publish site is the likely natural entry into the chapter-end save dialog path.

## Recommended next steps for live trigger

1. ✅ **Decode singleton location.** Resolved — `g_saves_manager_struct @ image_base + 0x143fcd0`.
2. ✅ **Confirm rename step.** Resolved — `FUN_1405229b0` is a `CopyFileW` wrapper (overwrite copy, not rename). Temp file persists as backup.
3. ✅ **Verify `(*DAT_14140e9d0)` guard.** Resolved — 3-instruction stub at `0x14067a590` that always returns 1 on PC. Nothing blocks the orchestrator.
4. ✅ **Decode enqueue ABI and public APIs.** `saves_queue_enqueue` (0x1406818a0), `save_request_sync` (0x1406797b0), `save_request_async` (0x140679760).
5. **Find the run-state job pointer.** ⚠️ Job lives at `data_source + 0x1928`. Profile-saves use `*(void**)(image_base + 0x140dd70) + 8`. Run-state save uses a heap-allocated `data_source` not directly globally rooted. Strong candidate root: statically-allocated struct at `image_base + 0x140ecf0` (vtable at `0x140f2d680`, address held by `DAT_14140ddc0` and also `DAT_14140e390`) — likely the main game app/world singleton, traversal from here to the run state needed.

## Public save APIs (decoded)

| Function | Address | Signature |
|---|---|---|
| `save_request_sync` | `image_base + 0x6797b0` | `void(void *unused, void *job)` — blocks until save complete |
| `save_request_async` | `image_base + 0x679760` | `uint32_t(void *unused, void *job)` — returns seq; poll `job+0x80` for completion |
| `save_atomic_orchestrator` | `image_base + 0x678f30` | `void(void *manager, void *job)` — direct call, bypasses queue |

The first arg of the public APIs is **unused** by the queue path (the worker thread provides the manager from `g_saves_manager_struct` automatically). Pass NULL.

Job struct fields confirmed:
- `+0x30`: `void *` data buffer to serialize
- `+0x38`: `uint32_t` data buffer size (bytes)
- `+0x48`: `uint64_t` extension flag — non-zero → `.ob`, zero → `.ini`
- `+0x79`: `byte` _Temp suffix flag (toggled by orchestrator during atomic write)
- `+0x7c`: `uint32_t` pending request seq (incremented by `save_request_*`)
- `+0x80`: `uint32_t` completed seq (set by worker after dispatch)
- `+0x84`: `byte` result code (0=success, 2/3/4/5/7=various errors)

For the run-state save (full game state), the job is embedded inside a heap-allocated `data_source` struct at offset `+0x1928`. The `data_source` struct also has:
- `vtable[0]()` returns the type tag `DAT_1414475a0` (used to identify it in linked-list walks)
- `+0x1ef4`: byte "saves disabled" flag — game checks this before triggering; bypassable by calling `save_atomic_orchestrator` directly

## Path to a deterministic injector

### Profile save (account-level data — talents, achievements)

Fully static-rooted, no scan needed:

```c
void *profile_save_struct = *(void **)(image_base + 0x140dd70);
void *profile_job = (char *)profile_save_struct + 8;
((save_now_t)(image_base + 0x6797b0))(NULL, profile_job);
```

### Run-state save (chapter data — items, inventory, run progress)

Data source is the heap-allocated `oCDtRootGs` instance (root game state). Signature-match it on heap:

```c
// Step 1: resolve the type descriptor pointer (static, ASLR-stable)
uintptr_t expected_typedesc = *(uintptr_t *)(image_base + 0x1414475a0);

// Step 2: scan readable heap regions for an instance whose vtable[0]() returns the typedesc
void *data_source = NULL;
MEMORY_BASIC_INFORMATION mbi;
uintptr_t addr = 0;
while (VirtualQuery((LPCVOID)addr, &mbi, sizeof(mbi))) {
    if (mbi.State == MEM_COMMIT &&
        (mbi.Protect & PAGE_READWRITE) &&
        mbi.Type == MEM_PRIVATE) {
        // Walk pointer-aligned addresses within this region.
        // Filter: first qword is a readable RX address (vtable in Ravenswatch.exe);
        //         first vtable entry is a small function returning the typedesc.
        for (uintptr_t p = (uintptr_t)mbi.BaseAddress;
             p + 0x2000 < (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
             p += 8) {
            void **maybe_vtbl = *(void ***)p;
            if (!is_in_image(maybe_vtbl)) continue;
            __try {
                uintptr_t (*get_type)(void *) = (uintptr_t (*)(void *))maybe_vtbl[0];
                if (get_type((void *)p) == expected_typedesc) {
                    data_source = (void *)p;
                    goto done;
                }
            } __except(EXCEPTION_EXECUTE_HANDLER) { continue; }
        }
    }
    addr = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
}
done:
// Cache data_source for the rest of the session.
```

```c
// Step 3: trigger save (any time after Step 2)
void *run_job = (char *)data_source + 0x1928;
((save_now_t)(image_base + 0x6797b0))(NULL, run_job);
// Returns when save is complete. Profile_1.ob updated.
```

The signature scan is standard mod/cheat technique. Completes in well under a second on startup. The cached `data_source` pointer remains valid for the entire session; re-scan on session restart.

### Required statics (image_base-relative offsets)

| Offset from image_base | Symbol | Use |
|---|---|---|
| `0x6797b0` | `save_request_sync` | Save trigger (synchronous) |
| `0x679760` | `save_request_async` | Save trigger (async, returns seq number) |
| `0x6818a0` | `saves_queue_enqueue` | Direct queue push (advanced) |
| `0x143fcd0` | `g_saves_manager_struct` | Saves manager (statically allocated) |
| `0x1414475a0` | `g_oCDtRootGs_typedesc` | Type descriptor for data_source class — used as the scan key |
| `0x140dd70` | `g_profile_save_struct_ptr` | Pointer-to-profile-save (account-level saves) |
| `0x143ff98` | `g_saves_queue_semaphore` | Worker thread wakeup |
| `0x143ffc0` | `g_saves_queue_head_bucket` | Queue head (for advanced manipulation) |

### Why this beats a static pointer chain

- **Static-pointer-chain approach**: would require finding a chain like `g_oe_engine → field+0xN → child → field+0xM → data_source`. Each hop needs decompile work; chain might break across game patches.
- **Signature scan approach**: uses the type-descriptor singleton as a fixed identifier. Resilient to layout changes between game patches as long as the class's vtable structure is preserved.

The injector needs no debugger, no breakpoints, and no captured pointers. It runs in-process on game startup, finds the data source, and exposes a hotkey or IPC to trigger saves on demand.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. This finding cites ~170 RVAs spanning the save subsystem. They shift on every recompile of `Ravenswatch.exe`. Re-anchor by tier:

### Tier 1 — Class anchors (most reliable, RTTI-based)

The save subsystem is a class hierarchy. Recover any class via RTTI string `.?AVoCFoo@@`, then walk vtables for member functions.

| Class | RTTI | Members anchored from this |
|---|---|---|
| `oCDtRootGs` | `.?AVoCDtRootGs@@` | `oCDtRootGs_constructor`. Sub-object layout (`+0x18`, `+0x1948`, `+0x1958`) recoverable from constructor decompile. |
| `oCDtGameProfile` | `.?AVoCDtGameProfile@@` | `oCDtGameProfile_constructor`. Inherits `oIGameProfile`. |
| `oIGameProfile` | `.?AVoIGameProfile@@` | `oIGameProfile_base_constructor` (parent class). |
| `oCMemoryBinaryStream` | `.?AVoCMemoryBinaryStream@@` | `Write` is `vtable[?]`; the only call inside Write that mallocs is `oCMemoryBinaryStream_grow_buffer`. |
| `GameSessionGs` | `.?AVGameSessionGs@@` | `session_finalize_and_save` is at `vftable[6]`. |
| `oCBinarySaver` | `.?AVoCBinarySaver@@` | Profile-save wrapper — wraps `oCFileBinaryStream` internally. Not used for run-state. |
| `GameModeDefault` | `.?AV?$GameModeDefault@dt@oe@@` | `GameModeDefault_copy_chapter_index = vtable[0x40]` (one-line `*(p1+0x40) = *(p2+0x40)`). The factory at `+0x38` holds the runtime serializer/allocator. |

### Tier 2 — Function anchors (string and structure-based)

| Symbol | Strongest anchor |
|---|---|
| `chapter_end_work` | Hardcoded difficulty mapping `chapter==1 → 3`, `chapter==2 → 6`, `chapter==3 → 9` (three-cmp-three-store sequence). Plus `tls_random_modulo` over `scene_manager+0x738` map pool. |
| `save_request_sync` | **Only** caller in the binary is `session_finalize_and_save`. Single-xref guarantee. |
| `save_request_async` | Four callers, all writing chapter/profile state. Function itself is uniquely the "request" name. |
| `session_finalize_and_save` | Two anchors: GameSessionGs `vftable[6]`, AND it's the only function that calls `save_request_sync`. |
| `profile_mark_chapter_complete_save` | Sets `profile_data->[0x18c] = 1` then enqueues `save_request_async` — distinctive single-byte-write + async-call pair. |
| `chapter_end_analytics_emit`, `publish_chapter_end_if_in_chapter`, `set_chapter_counter_publish_event` | Strings `"chapter_end"`, `"map.chapter"`, `"map.name"`. See `chapter-map-and-boss-spawn-architecture.md` for cross-anchors. |
| `oCMemoryBinaryStream_grow_buffer` | Only function called from inside `oCMemoryBinaryStream::Write`'s grow path; only place with `_malloc_base`/`_realloc_base` for the buffer at `+0x30`. |
| `global_save_modal_init_dispatcher`, `global_save_dispatcher_chapter_state` | Names retain "global save"-related strings; xrefs from any of the four `save_request_async` call sites. |

### Tier 3 — Globals and statics

| Symbol | Anchor |
|---|---|
| `g_global_save_dispatcher` | xrefs from any of the four `save_request_async` callers — they share a global dispatcher pointer. |
| `g_game_profile_data_manager_ptr` | Pervasive. Re-derive via `chapter_end_work`'s difficulty-mapping block — three writes to `*(g_game_profile_data_manager_ptr+0x20)+0x230`. |
| `oCDtRootGs::vftable` | RTTI for `oCDtRootGs`. |
| `GameSessionGs::vftable` | RTTI for GameSessionGs (slot 6 = `session_finalize_and_save`). |

### Tier 4 — Struct offsets (within `oCDtRootGs` / `data_source`)

Stable across patch builds, can shift on major engine updates. Re-derive from constructors decompiled here:

| Offset | Field | Re-derivation source |
|---|---|---|
| `+0x18` | `oCDtGameProfile` sub-object | `oCDtRootGs_constructor` writes `*(this+0x18) = ...` |
| `+0x18c` | Chapter-complete byte | `profile_mark_chapter_complete_save` writes 1 here |
| `+0x1928` | `oCMemoryBinaryStream` job slot | `oCDtRootGs_constructor` |
| `+0x1948` | Stream's vtable slot (`save_io_job_init_oCMemoryBinaryStream` writes vftable here) | the init function |
| `+0x1958` | Stream's buffer ptr | `oCMemoryBinaryStream_grow_buffer` writes its result to `*param_1` |
| `+0x230` | Difficulty score (1→3 / 2→6 / 3→9) | `chapter_end_work`'s mapping block |

### Tier 5 — Vtable slots

| Slot | Class | Purpose |
|---|---|---|
| `GameSessionGs::vftable[6]` | GameSessionGs | `session_finalize_and_save` |
| `GameModeDefault::vftable[0x40]` | GameModeDefault | `copy_chapter_index` |
| `factory.vtable[0xf8]` | factory at `GameModeDefault+0x38` | `factory_alloc_GameModeDefault_thunk` (2-instruction MOV/JMP) |
| `oCMemoryBinaryStream::Write` | the stream class | The `Write` virtual; identifiable by the only impl that grows the buffer |

### Assumptions and known failure modes

- Assumes the OEngine `Gs`-family class hierarchy (`oCDtRootGs`, `GameSessionGs`, `oCDtGameProfile`) remains the save root structure. Major engine version changes could rewrite this.
- Assumes the chapter→difficulty mapping stays hardcoded. If devs add a chapter or change difficulty curves, this anchor breaks for `chapter_end_work` only (the rest stand).
- Assumes RTTI is preserved. Ravenswatch shipped with full RTTI; if a future build strips it, fall back to byte-pattern signatures.
- `+0x1958` is the most likely struct offset to shift on a major engine bump. `oCMemoryBinaryStream_grow_buffer` is the canonical re-derivation source.

### Cross-finding anchoring

This finding is the foundational save-subsystem reference. Multiple findings cross-anchor against it: `frida-pipeline-hardware-breakpoint.md`, `chapter-boss-portal-trigger.md`, `save-edit-pipeline.md`, `chapter-map-and-boss-spawn-architecture.md`. Re-anchor this doc first on a binary update; others follow.

## Open questions

| Question | Status |
|---|---|
| Where is the saves-manager singleton stored? | Static refs identified (3 sites); not yet decoded. |
| Is `DAT_14140e9d0` a Steam-Cloud guard or just a thread-mutex? | Untested. |
| Does `save_atomic_orchestrator` support a "save slot N" parameter? | The job struct has a slot field but path 1 may need `profile_slot_path_load(slot)` instead. Untested. |
| Can the chapter-completion-only restriction be lifted purely by triggering this directly mid-run, or does the game state need to be in a serializable state first? | The natural call site only fires at phase==3 after `FUN_14028f140`'s state checks. Forcing a save mid-run will write whatever state is in memory — likely valid, but mid-room state may have transient pointers that confuse load. |
| What does `FUN_14064b2f0` do (called before `(*DAT_14140e9d0)` in the orchestrator)? | Pre-save state setup, partially decoded. |

## Notes for live debugging

- All addresses listed are at image base `0x140000000` (the value Ghidra uses). At runtime, Ravenswatch.exe is ASLR-randomized; you can either compute the actual base from `WinDbg` `lm` output and add the RVA, or break on a known string LEA (e.g., `LEA RAX, [Saved]` near `0x14029140d`) to find the runtime base.
- The save thread is alive whenever the game is running, regardless of menu/in-game state. So the worker can be prodded any time after engine init.
- `_Save\Profile_1_Temp.ob` is left on disk only if the orchestrator crashed mid-write. Its presence after a clean shutdown indicates a failed save.

## Non-triggering events (the chapter-boss kill is the only natural save event)

Empirically observed events that do **not** produce a `Profile_1.ob` write:

- Quicksave / autosave (no such systems)
- Save-on-quit (clean exit from main menu or alt-F4)
- Save-on-death
- **Save-on-crash** — process crash mid-run does not flush a save (observed 2026-05-04 in a multiplayer host run that crashed without producing a clean proof). Save state is held in the in-memory buffer until `save_request_sync` is called; an unwinding crash never reaches that call site.
- Multiplayer (any role: host or peer) — see `multiplayer-host-authority.md`

## Cross-references

- `rw/findings/save-binary-format.md` — the format being written.
- `rw/findings/save-account-binding.md` — Steam Cloud vs file portability.
- `rw/findings/magical-objects.md` — record format inside the saved file.
- `rw/findings/items-add-primitive-cap.md` — open: chapter-completion test of counter durability is in progress (BM Mirror probe currently swapped into active save).
- `.ai/scratch/rw-parallel-findings.md` — ancillary discoveries from the 2026-04-30 Ghidra pass (anti-debug, false-lead candidates, event-bus internals).

---

## Chapter-end save chain — verified call topology (2026-04-30)

Static decompile in Ghidra mapped the full chain from boss death to disk write. All
function names in this section have been renamed in the Ghidra database for
persistence. Addresses are absolute; subtract `0x140000000` for RVA.

### Save-call topology (single sync, multiple async)

`save_request_sync` (image+0x6797b0) has **exactly one** caller in the entire binary:
`session_finalize_and_save` (image+0x28d6a0). That call writes the GameSessionGs root
job at `data_source + 0x1928`. There is exactly one sync save.

`save_request_async` (image+0x679760) has **four** callers, all writing to the
same global save manager target `*(DAT_14140dd70) + 8`:

| Caller | RVA | Trigger condition |
|---|---|---|
| `global_save_modal_init_dispatcher` | image+0x25db45 (inside FUN @ +0x25d3b0) | First-time profile init / global save manager bootstrap |
| `global_save_dispatcher_chapter_state` | image+0x262f33 (inside FUN @ +0x261ca0) | Chapter-state delta detected, primary path |
| `global_save_dispatcher_chapter_state` | image+0x26308d (inside FUN @ +0x261ca0) | Chapter-state delta detected, alternate path (when `*(scene+0x13de) != 0`) |
| `profile_mark_chapter_complete_save` | image+0x26c781 (inside FUN @ +0x26c700) | Chapter-win marker write (`profile_data->[0x18c] = 1`) |

So the empirically observed "three-save" model is **1 sync + N async** to the same
global manager. All async calls target one global save buffer (`DAT_14140dd70+8`).
There is no separate `profile+0x50` job; that was a misidentification in earlier
notes — the only profile-touch on chapter end is via `profile_mark_chapter_complete_save`,
which still uses the `DAT_14140dd70+8` queue.

### Chapter-end event chain

Chapter setup (runs when chapter loads):

```
session_subscribe_chapter_end_events   image+0x27fde0
  ├─ Subscribes to ~17 named events (chapter-end, scene transitions, etc.)
  │  Notable: GAME_END_SUCCESS at DAT_1412bfca0, callback thunk LAB_1402c85c0
  ├─ Loads Modal_Save_Or_Quit.entity.ot (resource at DAT_141410b38), stores at session+0xf8
  ├─ Loads sub-resource at DAT_141410558, stores at session+0xa8
  └─ Publishes GAME_CHRONO_START via construct_named_event + publish_event_to_subscribers
```

Chapter-end fires (boss death → engine publishes GAME_END_SUCCESS):

```
GAME_END_SUCCESS publishes
  ↓ event-bus dispatches to subscribers
LAB_1402c85c0 (vtable adjustor thunk; subscriber registered by session_subscribe_chapter_end_events)
  ↓ tail-jumps via *(0x140ef9a88) = 0x1402835f0
0x1402835f0 (XOR EDX, EDX; JMP 0x140283520)
  ↓
on_game_end_event_handler (image+0x283520)
  ├─ Guards on session+0x1ab (one-shot flag)
  ├─ Looks up oCDtP2PSessionSceneContext, calls vtable[0xd8] for some predicate
  ├─ Calls walk_session_for_typedesc (image+0x2b7280) to find some object
  ├─ Calls game_end_should_show_modal (image+0x2918b0) — returns 0 or 1
  └─ Routes:
     ├─ if !game_end_should_show_modal && param_2 == 0:
     │    game_end_no_modal_path (image+0x285080)  ← straight to next chapter, no dialog
     └─ else: publish_named_event_game_end (image+0x285710, with arg=2)
          ↓ constructs oe::dt::NamedEventGameEnd, publishes via lVar3+0x340
on_named_event_game_end_handler (image+0x28f140) ← subscriber for NamedEventGameEnd, vtable-dispatched
  ├─ Updates profile_data fields (chapter completion stats, +0x234 +0x240 +0x246)
  ├─ Difficulty score → profile+0x230 based on event params
  ├─ Routes by inner state at param_2+0x60:
  │  ├─ state == 3 (chapter WIN): ────────────► session_on_saved_dispatch
  │  ├─ state == 2 (in-progress?):
  │  │  └─ if !game_end_should_show_modal && param_2+0x6e==0: chapter_end_work directly
  │  │     else: chapter_end_encyclopedia_and_stats_update
  │  └─ states 0/1: chapter_end_encyclopedia_and_stats_update
  └─ if scene type doesn't match 0x1945ba26: session_on_abandoned_dispatch
session_on_saved_dispatch (image+0x291350)
  ├─ Sets phase = 3 (win) at session+0x150
  ├─ Calls chapter_end_work(session)         ← LIKELY HOST OF PREP FUNCTION
  ├─ Sets saves-enabled flag session+0xa5 = 1
  ├─ Constructs "Saved" oCCustomFlagList, publishes via FUN_14067dea0(GameEventScene, 0x17cde816)
  ├─ Updates profile_data->[0x244] (chapter counter)
  └─ Sets session+0x30 = 1 (committed flag)
```

Then user clicks "Save and quit" on the modal, which (mechanism TBD — vtable on the
modal callback) eventually invokes `session_finalize_and_save`:

```
session_finalize_and_save (image+0x28d6a0)
  ├─ Vtable at image+0xefa120 slot[0] holds this function (no other refs)
  ├─ Pre-save calls (param_1 = session):
  │  ├─ FUN_14026f750 / FUN_14026f620 — list/state plumbing on session+0x38, +0x80
  │  ├─ vtable[0xd0] call on (((session+0x20)->+0x18)->+0x230) ← ★ likely prep entry
  │  ├─ scene-context iteration writes to session+0x138/+0x140/+0x148 via FUN_1401c5d50
  │  ├─ io_request_list_clear(session+0xd8)
  │  ├─ FUN_1406e7320(session+0x130->+0x1a8, session+0xd8)
  │  ├─ swap_subscribed_pointer(session+0xa8, NULL) — clear modal state
  │  ├─ profile_data manager call chain
  ├─ Walks linked list at session+8 looking for puVar3 such that vtable[0]()
  │  returns g_oCDtRootGs_typedesc (the data_source instance discriminator)
  ├─ Checks *(data_source + 0x1ef4) == 0 (saves-enabled flag)
  └─ Calls save_request_sync(NULL, data_source + 0x1928)
     ↓ enqueues to ring-queue, signals semaphore
saves_manager_worker_thread → save_atomic_orchestrator → oCFileBinaryStream write
     ↓
Profile_1.ob updated on disk
```

### Where the prep most likely happens — REFRAMED 2026-04-30 LATE

Subsequent Ghidra walk this session revealed the **architectural reality**:

**The job IS an `oCMemoryBinaryStream`**, embedded at offset +0x20 within the
save_io_job (which is at +0x50 within oCDtGameProfile, which is at +0x18d8 within
oCDtRootGs = +0x1948 absolute on data_source). Its constructor
(`save_io_job_init_oCMemoryBinaryStream`, image+0x64ac60) initializes:

| stream offset | absolute (in data_source) | field | initial value |
|---|---|---|---|
| +0x10 | +0x1958 (= job+0x30) | buffer pointer | **NULL** |
| +0x18 | +0x1960 (= job+0x38) | capacity | 0 |
| +0x24 | +0x196c (= job+0x44) | used size | 0 |

**The buffer is NULL at construction.** It is allocated and grown lazily by
`oCMemoryBinaryStream::Write` (image+0x5257d0) on each call — `_malloc_base` /
`_realloc_base` happen INSIDE the Write method's grow path
(`oCMemoryBinaryStream_grow_buffer` at image+0x24e700).

So **there is no single "allocate buffer + assign" call to find**. The "prep" is
the engine making many `Write` calls into the embedded stream during chapter-end
serialization, each of which appends bytes and grows the buffer dynamically.

The Write method's only direct callers are 2 stack-local stream usages
(`load_object_via_memory_stream`, `load_object_array_via_memory_stream`) — these
are LOAD-side helpers using transient memory streams, NOT the chapter-end save
path. The chapter-end Write calls go through **vtable dispatch** on the embedded
stream and don't appear in static xref graphs.

#### Implications for finding the actual prep entry

- Static-only analysis of Write callers is exhausted. No vtable-dispatched
  callers are visible.
- The cleanest path forward is a **hardware data breakpoint on
  `*(data_source + 0x1958)`** during a real chapter-end run. The instruction
  that writes the first non-NULL pointer to that slot IS the first Write call.
  Its call stack reveals the SerializeArchive entry — which is the prep.
- Alternative: hardware watchpoint on `*(data_source + 0x196c)` (used_size).
  Each increment is a Write call. Capturing several gives us the full list of
  Serialize call sites.

### oCBinarySaver does NOT serve the run-state save

The `oCBinarySaver` class (vtable at `0x140f235e0`, constructor at
image+0x4e8ca0) is wired to `oCFileBinaryStream` internally — it writes directly
to `.ini` / `.ob` files. It is used for SETTINGS save and the LOAD path, not for
the chapter-end run-state save (which uses the embedded memory stream).

Save format magic markers discovered in `FUN_1404e9350`
(serialize_object_with_name):

- `0xAABB1111` at `DAT_140eb3ae8` — class registry section marker
- `0xAABB2222` at `DAT_140eb3aec` — object section marker

These framing bytes appear inside saved files (settings AND profile saves).
Worth cross-referencing against actual save-file bytes for format work.

### Class hierarchy resolved

```
oCDtRootGs (= data_source, size 0x21d0)
  inherits oCConsolesRootGs
  inherits oIGameState
  constructor: oCDtRootGs_constructor (image+0x258c00)
  vtable: 0x140ef49d8

  embeds oCDtGameProfile at +0x18d8 (size 0x3b8)
    constructor: oCDtGameProfile_constructor (image+0xc9340)
    inherits oIGameProfile (base init at oIGameProfile_base_constructor, image+0xc8cb0)

    embeds save_io_job at +0x50 (= data_source +0x1928)
      constructor: save_io_job_init_oCMemoryBinaryStream (image+0x64ac60)

      embeds oCMemoryBinaryStream at +0x20 (= job+0x20 = data_source +0x1948)
        write-side vtable: 0x140f28d80
        read-side vtable:  0x140f28d48
        Write method: oCMemoryBinaryStream_Write (image+0x5257d0)
        grow helper: oCMemoryBinaryStream_grow_buffer (image+0x24e700)

    embeds oCDtPlayerProfileData at +0x178 (within oCDtGameProfile)
```

### Renamed functions (Ghidra database, 2026-04-30)

The following functions are now named in the Ghidra project. Old `FUN_xxxxxxxx`
references in older notes can be cross-walked here:

| Address | New name | Old name | Role |
|---|---|---|---|
| `0x14028d6a0` | `session_finalize_and_save` | FUN_14028d6a0 | Walks data_source list, calls save_request_sync (only sync caller) |
| `0x140291350` | `session_on_saved_dispatch` | FUN_140291350 | Phase=3, chapter_end_work, "Saved" event publish |
| `0x140291190` | `session_on_abandoned_dispatch` | FUN_140291190 | Phase=1, "Abandon" event — abandon path, sister to Saved |
| `0x1402907e0` | `chapter_end_work` | FUN_1402907e0 | Massive chapter-end orchestrator; LIKELY HOST OF PREP |
| `0x14028f140` | `on_named_event_game_end_handler` | FUN_14028f140 | NamedEventGameEnd subscriber; routes by state to Saved/Abandon/encyclopedia |
| `0x14028f660` | `chapter_end_encyclopedia_and_stats_update` | FUN_14028f660 | Stat tracking + encyclopedia mark on chapter end |
| `0x140283520` | `on_game_end_event_handler` | FUN_140283520 | Real GAME_END_SUCCESS handler (after thunk indirection) |
| `0x140285710` | `publish_named_event_game_end` | FUN_140285710 | Constructs and publishes `oe::dt::NamedEventGameEnd` |
| `0x140285080` | `game_end_no_modal_path` | FUN_140285080 | Alternative chapter-end path that skips the modal |
| `0x1402918b0` | `game_end_should_show_modal` | FUN_1402918b0 | Predicate: returns 1 if modal should show |
| `0x14027fde0` | `session_subscribe_chapter_end_events` | FUN_14027fde0 | Chapter-start setup; subscribes ~17 events, loads modal entity, publishes GAME_CHRONO_START |
| `0x1402b7280` | `walk_session_for_typedesc` | FUN_1402b7280 | Linked-list walker on session+8 looking for typedesc match |
| `0x140260410` | `data_source_modal_state_init_or_teardown` | FUN_140260410 | param_2=1 setup, param_2=0 teardown for modal-related state on data_source |
| `0x140678780` | `io_request_list_clear` | FUN_140678780 | List teardown — NOT save prep (was suspected) |
| `0x1406ce030` | `swap_subscribed_pointer` | FUN_1406ce030 | Generic refcounted state-pointer swap with subscriber re-registration — NOT save prep |
| `0x140282df0` | `session_on_boss_fighting` | FUN_140282df0 | Boss-fight setup; publishes "boss.fighting" event (NOT GAME_END subscriber as earlier note suggested) |
| `0x140652960` | `construct_named_event` | FUN_140652960 | Universal event-publish primitive (constructs event obj) |
| `0x140652b60` | `publish_event_to_subscribers` | FUN_140652b60 | Universal event-publish primitive (fans to subscribers) |
| `0x14026c700` | `profile_mark_chapter_complete_save` | FUN_14026c700 | Sets profile+0x18c, fires async save (one of three async callers) |
| `0x140261ca0` | `global_save_dispatcher_chapter_state` | FUN_140261ca0 | Global save dispatcher; 2 async-save call sites for chapter-state delta |
| `0x14025d3b0` | `global_save_modal_init_dispatcher` | FUN_14025d3b0 | First-time global save manager bootstrap with async save |
| `0x14026ccd0` | `session_register_data_source_callback` | FUN_14026ccd0 | Registers a callback on data_source+0xd8->0x158 |
| `0x140291560` | `publish_map_name_event` | FUN_140291560 | Looks up map name from list, publishes stat event with index |
| `0x1402916d0` | `update_difficulty_high_water_mark` | FUN_1402916d0 | Updates profile difficulty progression flag |

Additional renames (2026-04-30 late):

| Address | New name | Old name | Role |
|---|---|---|---|
| `0x140258c00` | `oCDtRootGs_constructor` | FUN_140258c00 | Constructor for the data_source class (size 0x21d0) |
| `0x1400c8cb0` | `oIGameProfile_base_constructor` | FUN_1400c8cb0 | Base init for oCDtGameProfile; calls save_io_job_init |
| `0x1400c9340` | `oCDtGameProfile_constructor` | FUN_1400c9340 | Constructor for sub-object at data_source+0x18d8 (size 0x3b8) |
| `0x1400c93b0` | `oCDtGameProfile_destructor` | FUN_1400c93b0 | Destructor for oCDtGameProfile |
| `0x14064ac60` | `save_io_job_init_oCMemoryBinaryStream` | FUN_14064ac60 | Initializes the save_io_job; embeds oCMemoryBinaryStream at +0x20; **leaves buffer ptr at +0x30 NULL** |
| `0x1405257d0` | `oCMemoryBinaryStream_Write` | FUN_1405257d0 | Appends bytes to the in-memory buffer; grows on demand |
| `0x14024e700` | `oCMemoryBinaryStream_grow_buffer` | FUN_14024e700 | Internal: grows the stream buffer via _malloc/_realloc |
| `0x1404e8ca0` | `oCBinarySaver_constructor_with_file_stream` | FUN_1404e8ca0 | Constructs oCBinarySaver; embeds oCFileBinaryStream (file backing only) |
| `0x1404e5100` | `save_object_to_file_via_oCBinarySaver` | FUN_1404e5100 | Top-level "save object to file" via oCBinarySaver |
| `0x1404e5a90` | `load_object_array_via_memory_stream` | FUN_1404e5a90 | Load helper using stack-local oCMemoryBinaryStream (0x400 byte transient) |
| `0x1404e5f60` | `load_object_via_memory_stream` | FUN_1404e5f60 | Single-object load helper, similar transient pattern |
| `0x14064b5a0` | `settings_post_load_processing` | FUN_14064b5a0 | Mirror of settings_serialize_load_or_save_ini for load direction |
| `0x1403e4130` | `subscriber_lists_cleanup_destructor` | FUN_1403e4130 | Destructor that clears multiple subscriber lists at offsets +0x118..+0x830 |
| `0x1404ef070` | `alloc_zeroed_0x710_with_array` | FUN_1404ef070 | Allocator that produces a 0x710-byte zeroed struct with an array of 0x1e × 0x38-byte elements |
| `0x1402bc100` | `hashmap_find_entry` | FUN_1402bc100 | SwissTable / SSE2 hashmap lookup |
| `0x14030e7a0` | `global_hashmap_emplace` | FUN_14030e7a0 | SwissTable insert/find on a process-wide hashmap (with FNV-1a hash) |
| `0x140216cf0` | `fnv1a_u64_hash` | FUN_140216cf0 | FNV-1a hash of a u64 value |
| `0x1404ffbe0` | `tls_random_modulo` | FUN_1404ffbe0 | Thread-local PRNG, returns rand % param_1 |
| `0x14048bc50` | `linked_list_filter_remove` | FUN_14048bc50 | Iterates linked list, removes entries matching vtable[0x80] predicate |
| `0x1404e9350` | (unrenamed; ‘serialize_object_with_name’) | FUN_1404e9350 | Top-level serializer: writes class registry + object section markers (0xAABB1111 / 0xAABB2222) |

## Empirical: WinDbg anti-debug behavior at game-state transitions (2026-04-29)

**Confirmed via two independent crashes** during a debugging session 2026-04-29
evening: with WinDbg attached to `Ravenswatch.exe`, the process self-terminates
with `STATUS_BREAKPOINT` (0x80000003) on certain game-state transitions:

- **Boss-spawn** (chapter-1 boss arrival): observed once
- **Boss-kill** (chapter-1 boss defeat): observed once

The tripwire fires only when WinDbg is **already attached** at the moment of the
transition. No breakpoints needed to be set or hit; merely having a debugger
present is sufficient. WinDbg's `.lastevent` shows `Exit process, code 80000003`
with no preceding BP hit markers in the session log.

Mechanism: presumed `__debugbreak()` / `IsDebuggerPresent()` check in code that
runs at the transition moment. The game ships an unhandled `INT3` to the
debugger, which Windows interprets as a crash, terminating the process.

**Confirmed safe:** WinDbg attached to `Ravenswatch.exe` on the main menu, with
both `bu` (software) and `ba e1` (hardware) BPs armed on `save_atomic_orchestrator`,
firing on settings-save (volume-slider change) — no crash, BP fires cleanly.

**Implication for live-debug capture of the chapter-end save chain:**

- Don't attach WinDbg before boss-spawn or boss-kill.
- Viable window: **after** boss-kill, **during** the post-boss-die animation
  (~5 seconds) but before the Save-and-quit dialog dispatches the actual save.
  Both anti-debug checks have already fired by this point and seen no debugger;
  attaching after they passed lets the rest of the save chain proceed unmolested.
- Frida is unaffected by this tripwire (Frida hooks via inline trampolines, does
  not register as a Windows debugger; `IsDebuggerPresent()` returns false).

This was costly to discover empirically. Two chapter-1 runs (~40 minutes of play)
were lost before the pattern was identified. The corrected operational flow is
in `rw/docs/ghidra-windbg-mcp-for-wsl.md` "Live debugging session" + "Known
limitations" sections.

---

## Prep-chain dig — narrowed to factory+serialize on GameModeDefault (2026-04-30 night)

### Headline

The `vtable[0xd0]` call inside `session_finalize_and_save` was investigated and
**ruled out as the prep**. It resolves to a P2P/network shutdown method on
`oCDtP2PSessionSceneContext`. The actual prep candidate is the next block in
the same function: a **factory + serialize pair** running on a runtime-installed
subsystem hung off `oe::dt::GameModeDefault+0x38`.

### vtable[0xd0] resolution

`scene_manager+0x230` is a **cached pointer to `oCDtP2PSessionSceneContext`**.
Confirmed via sibling caller `FUN_1401df9d0` which uses the same `+0x230` deref
to call `vtable[0xd8]` — the same slot that `on_game_end_event_handler` calls
on the result of `scene_manager_find_context_by_type(scene_manager,
&TKindOfTypeTester<oCDtP2PSessionSceneContext>)`. The `+0x230` field caches
the lookup so subsequent calls don't re-walk the scene-context list.

`oCDtP2PSessionSceneContext::vtable[0xd0]` = `oCDtP2PSession_shutdown_raknet`
(image+0x2a3680). It clears a network buffer, calls `vtable[0x70]/[0x78]` on
the network manager (param_1+0x210), `Sleep`s, logs `"RakNet Shutdown"`, resets
state from a global, calls `FUN_14083ce50(this, 6)`. **This is session
shutdown — not save prep.** Makes sense given session_finalize_and_save is the
"Save and quit" handler: shut down P2P first, then save.

### Real prep candidate (saves-enabled branch)

The next block of `session_finalize_and_save` (gated on `session+0xa5 != 0`,
the saves-enabled flag) does:

```c
R14 = *(scene_manager + 0x708);          // = oe::dt::GameModeDefault* (size 0x48)
RCX = *(R14 + 0x38);                     // = serializer-factory subsystem
serializer = RCX->vtable[0xf8]();        // factory.create_serializer()
serializer->vtable[0x40](R14);           // serializer.serialize(GameMode)
profile_data_manager+0x1e0 = serializer; // cache result on profile manager
```

This is a textbook factory + serialize pattern, runs **just before**
`save_request_sync`, and the serializer's `vtable[0x40]` is the only call
plausibly responsible for populating the embedded `oCMemoryBinaryStream` at
`data_source+0x1948`.

### GameMode+0x38 is runtime-installed via name registry

`oe::dt::GameMode::ctor` (image+0x31b950) initializes `+0x38 = NULL`, then
performs a registry lookup using the universal module-registration magic
`0x53b64d`:

```c
// inside oe_dt_GameMode_constructor:
param_1[7] = 0;  // +0x38 = NULL
// search registry at *(DAT_141447698 + 0x30) for entry with (entry+0x8) == 0x53b64d
(**(code **)(*(longlong*)*entry + 0x18))(*entry, name_string,
                                         _DAT_1412c7590, &param_1[7], 0);
//                                       ^ name string    ^ OUT: writes to +0x38
```

`module_registry_init_with_magic_0x53b64d` (image+0x442bb0) populates the
registry by iterating the global module list (`DAT_141414090`) and inserting
one entry per module tagged `0x53b64d`. The handler at the matched entry's
`+0x10` slot resolves the `name_string` (e.g., `"GameModeDefault"`) into a
concrete subsystem instance.

**Implication: the concrete class at `GameMode+0x38` is selected at runtime by
GameMode name.** Different GameModes (Default, Tutorial, etc.) install
different subsystems sharing the same vtable[0xf8]/[0x40] interface.
**Static analysis cannot pin a single class** for the prep — but it has
narrowed the field from "anywhere in the codebase" to "whatever is at
GameMode+0x38 right now".

### session class identified: GameSessionGs

The runtime `session` parameter passed to `session_finalize_and_save` is an
instance of `GameSessionGs` (size `0x198`, typedesc init at
`oCDtP2PSessionSceneContext_typedesc_init`-style helper at
`FUN_14027a820`, registers class string `"GameSessionGs"`). The vtable
starts at `0x140efa0f0` and `session_finalize_and_save` occupies slot[6]
(offset `0x30` into the vtable). The vtable has zero static xrefs — it is
reached via a runtime mechanism (likely an interface upcast within the
class hierarchy).

### Two new sync-style save sites discovered

`FUN_1403db6c0` and `FUN_1403db790` are previously-undocumented save trigger
functions. They:

1. Pause/unpause two controllers at `[param_1+0x230]` and `[param_1+0x238]`
   via `FUN_140539170` (a state-toggle / event-publisher with subscriber
   list at `*(this+0x290) + 0x328`).
2. **Inline** the `save_request_sync` enqueue + semaphore + busy-wait logic
   directly (rather than calling `save_request_sync`).
3. Target the global profile save manager (`DAT_14140dd70+0x240` →
   `+0x84/+0x88` for pending/completed seq).

Both are vtable-dispatched (no static callers) and reside in `0x14148xxxx` data
sections. Augments the topology to **1 sync (`save_request_sync`) + 4 async
(`save_request_async`) + 2 inlined-sync (`FUN_1403db6c0/790`)**.

### oCGameStream class characterized

`oCGameStream` (vtable `0x140f19e48`, ctor `0x140466400`) is a heap-pooled
stream wrapper that **embeds an `oCMemoryBinaryStream`** at offset `+0x78`.
Its pool acquire (`oCGameStreamPool_acquire` at `0x14046ebe0`) uses critical-
section-guarded freelist allocation. Despite embedding a memstream, this class
is NOT used for the chapter-end run-state save (which uses the embedded
memstream at `data_source+0x1948` directly, not via oCGameStream).

### New renames (this dig)

| Address | New name | Role |
|---|---|---|
| `0x140466400` | `oCGameStream_constructor` | Heap-pooled stream wrapper ctor |
| `0x14046ebe0` | `oCGameStreamPool_acquire` | Pool allocator (CRITICAL_SECTION + freelist) |
| `0x140653f80` | `scene_manager_find_context_by_type` | Scans scene_manager+0x58/+0x68 lists |
| `0x1402a31f0` | `oCDtP2PSessionSceneContext_constructor` | Class ctor (size 0x330, vtable 0x140ef9470) |
| `0x14022b050` | `oCDtP2PSessionSceneContext_typedesc_init` | Registers class with name `"oCDtP2PSessionSceneContext"` |
| `0x1402a3680` | `oCDtP2PSession_shutdown_raknet` | vtable[0xd0] — RakNet teardown, NOT prep |
| `0x1401909d0` | `GameModeDefault_typedesc_init` | Registers `"GameModeDefault"` (size 0x48) |
| `0x1401ab3d0` | `oe_dt_GameModeDefault_constructor` | Final-class ctor; vtable 0x140edf420 |
| `0x14031b950` | `oe_dt_GameMode_constructor` | Parent class ctor; sets up name registry hook for +0x38 |
| `0x140442bb0` | `module_registry_init_with_magic_0x53b64d` | Registers all modules under tag 0x53b64d |
| `0x141446cc0` (data) | `g_GameModeDefault_typedesc` | typedesc for `"GameModeDefault"` |
| `0x141447ef0` (data) | `g_oCDtP2PSessionSceneContext_typedesc` | typedesc for P2P scene context |

### Class-address quick reference

| Symbol | Address | Notes |
|---|---|---|
| `GameSessionGs::vftable` | `0x140efa0f0` | session_finalize_and_save at slot[6] |
| `oCDtP2PSessionSceneContext::vftable` | `0x140ef9470` | size 0x330 |
| `oe::dt::GameModeDefault::vftable` | `0x140edf420` | size 0x48 |
| `oe::dt::GameMode::vftable` | `0x140edb8f8` | parent of GameModeDefault |
| `oCGameStream::vftable` | `0x140f19e48` | embeds memstream at +0x78 |
| `oISerializable::vftable` | `0x140edd7c8` | universal base |
| `oIResource::vftable` | `0x140f1e7d0` | resource base |

### Net move on the prep question

We started believing the prep was a single hidden function discoverable by
walking xrefs. We end with the architectural shape: it's a
**registry-resolved, name-keyed factory + serialize pair** anchored at
`GameModeDefault+0x38`. The static walk had to fail because the concrete
class is determined at runtime by GameMode name. **The hardware-watchpoint
plan in the handoff is still the right path** — and now sharpened: watch
`*(GameModeDefault+0x38)` (or `*(scene_manager+0x708) + 0x38`) **before** the
buffer slot. The first non-NULL write to that field IS the registry handler's
`vtable[0x18]` storing the concrete subsystem — its call stack reveals the
class that owns the prep methods.

### Live-capture path (2026-05-03)

The WinDbg hardware-watchpoint plan above is **retired** — see "Empirical:
WinDbg anti-debug behavior at game-state transitions" below. Boss-spawn and
boss-kill self-terminate the moment a Windows debugger is attached, which
makes the watchpoint pipeline unreliable. Replacement is a pure-Frida hook:
`probeForBossKillSave()` in `tools/frida/rw_lab.js` attaches
`session_finalize_and_save` (image+0x28d6a0), walks the verified chain
(`*(*(session+0x20)+0x18)+0x708 = GameModeDefault`, `+0x38 = factory`)
to locate the factory subsystem, then chains one-shot `Interceptor.attach`s
on `factoryVT[0xf8]`.onLeave and `result.vtable[0x40]`.onEnter. Frida is
unaffected by the anti-debug tripwire. Operational doc lives in
`rw/findings/frida-pipeline-hardware-breakpoint.md` §"Next task: probe
capture via `probeForBossKillSave()`".

### CORRECTION (2026-05-04): the "factory + serialize" pair is NOT the save-buffer prep

The hypothesis above stated that `factory.vtable[0xf8] = create_serializer` and
the returned object's `vtable[0x40] = serialize(GameMode)` is the function that
populates the embedded `oCMemoryBinaryStream` at `data_source+0x1948`. **Wrong.**

Decompile-confirmed (2026-05-04):

- `factory.vtable[0xf8]` = `factory_alloc_GameModeDefault_thunk` (image+0xc6ea0) — a
  2-instruction thunk (`MOV RDX,RCX; JMP allocate_GameModeDefault_with_kind`)
  that allocates a fresh `GameModeDefault` instance (sizeof 0x48). NOT a
  serializer factory.
- `GameModeDefault.vtable[0x40]` = `GameModeDefault_copy_chapter_index`
  (image+0x31bc40) — one-line: `*(p1+0x40) = *(p2+0x40)`. NOT a serializer;
  copies one u32 (chapter index) between two GameModeDefault instances.

What the prep block actually does: allocate a fresh GameModeDefault, copy
the chapter index from the running GameModeDefault, cache the new instance
at `*(profile_data_manager + 0x1e0)`. **Chapter-snapshot bookkeeping**, not
save-buffer serialization. The actual buffer-population call site remains
unidentified; the doc's "registry-resolved factory + serialize pair" framing
should be treated as misleading.

`save_request_sync` only enqueues bytes already at IO_job+0x30 — it does not
serialize. So the question "what writes to `data_source+0x1948`?" is still
open and is **not** answered by the chain documented above.

Plausible next directions:

1. Frida `Interceptor.attach` on `oCMemoryBinaryStream::Write` (image+0x5257d0)
   filtered to `this == data_source+0x1948`, run during a real save event.
2. Trace readers of `profile_data_manager+0x1e0` — whatever consumes the
   cached GameModeDefault snapshot is downstream of the prep, and likely
   sits between this and the actual buffer write.

Plate comment on `0x14028d6a0` in Ghidra records the corrected interpretation.

**Stronger hypothesis (requires empirical verification): incremental serialization model.**
There may not be a single prep function. The save buffer is populated by many
small oCMemoryBinaryStream::Write calls distributed across the gameplay code,
each emitting one record when the corresponding state changes. Save-and-Quit
just flushes. Chapter-boss-kill saves work because by then all expected
records have been emitted. **Mid-run Frida triggers cannot produce a
complete save** in this model — the buffer is incomplete by design until
specific events occur. Static evidence supporting this: oCMemoryBinaryStream
::Write has only a handful of xrefs (all DATA/COMPUTED_CALL on local
streams), oCDtRootGs::vftable (0x140ef49d8, ~26 slots) has no
serialize-entire-state-shaped slot, session_finalize_and_save calls no
serializer between scene-context cleanup and `save_request_sync`. Cheap
verification: extend `probeForBossKillSave()` to log buffer size at
checkpoints (chapter start, mid-chapter, pre-save, post-save) and watch
for monotonic growth tied to game events. Full discussion in
`rw/findings/frida-pipeline-hardware-breakpoint.md`.

---

## Modal_Save_Or_Quit.entity.ot decoded (2026-04-30 night)

### Where it lives, and how to harvest

| Attribute | Value |
|---|---|
| Game-engine path | `GameUis\Modal\Modal_Save_Or_Quit.entity.ot` |
| Cooked filename | `Hrtgl!Hrtgl_Fgkq_Ou_Pwdi.qzidis.ri.MzidisFqiidzyvLqvrwubq.yqz` |
| Cooked dir | `DarkTalesResources/_Cooking/MzidisFqiidzyv/KgxqJdv/` (`EntitySettings/GameUis/`) |
| Decoded resource type | `oCEntitySettingsResource` (`.gen` extension) |
| Size | 2,856 bytes |

A copy of the file lives at
`rw/dumps/modal_save_or_quit/Modal_Save_Or_Quit.entity.ot.EntitySettingsResource.gen`.

### Cipher correction (cipher.py)

`tools/rerw-src/lib/cipher.py` lists position 40 (uppercase `O`) as `#`
(unknown). Empirically, `O` enciphers to `O` (identity): `Modal_Save_Or_Quit`
encodes as `Hrtgl_Fgkq_Ou_Pwdi`. Update suggested:

```python
# Change CIPHER position 40 from '#' to 'O' (identity).
```

### File format (entity.ot cooked .gen)

This is the same `Cooked` format used for hero-definition files (cf.
`rw/dumps/geppetto/herodef_analysis.txt`).

**Header (16 bytes):**

| Offset | Size | Value | Field |
|---|---|---|---|
| 0x00 | u32 | 16 (`0x10`) | header size |
| 0x04 | u32 | 1 | (count) |
| 0x08 | u32 | 6 | string length |
| 0x0C | 6 bytes | `"Cooked"` | format identifier |

After the header: a u32 count, a u8 (0x31), then the framing markers begin.

**Section markers (matches `FUN_1404e9350` discovery):**
- `0xAABB1111` = section start
- `0xAABB2222` = section end

**Class registry:** `0xAABB1111` → u32 class_count → per class:
- u32 name_length, name bytes, u32 id, u32 vmaj, u32 parent_id (16 bytes metadata after name)
- (exact field meaning of the 4 u32s after the name is unverified; matches
  `FUN_1404e9350` save-side intent)

Class registry of `Modal_Save_Or_Quit` (14 entries):
1. `oCEntitySettingsResource`
2. `oIResource`
3. `oISerializable`
4. `oCEntitySettings`
5. `oCSpawnableSettings`
6. `oCEntityCpntLabelUiSettings`
7. `oCEntityCpntWindowUiSettings`
8. `oIEntityCpntSettings`
9. `oCEntityCpntValueSettings`
10. `oCEntityCpntPicker`
11. `oCEntityCpntValuePicker`
12. `oCEntityValueUnion`
13. `oCWindowIdentifierPicker`
14. `oIUniqueObjectPicker`

**Object section:** `0xAABB1111` → object body (class index + 16-byte GUID + class-specific fields) → `0xAABB2222`. Multiple objects can be nested; each gets its own start/end pair.

### Modal contents

The modal extends `GameUis\Modal\Modal_Model.entity.ot` (referenced as a
picker; the parent template likely defines the actual button-class wiring).
Visible content of `Modal_Save_Or_Quit`:

| Field | Localization key | Source |
|---|---|---|
| Title | `Message_Save_And_Quit_Title` | `Common~GAM.xls` |
| Description | `Message_Save_And_Quit_Description` | `Common~GAM.xls` |
| Cancel button label | `Message_Save_And_Quit` | `Common~GAM.xls` |
| Validate button label | `Message_Continue` | `Common~GAM.xls` |

**Counter-intuitive UI mapping (semantically flipped):**

- **Cancel button = "Save and Quit"** (the user-facing destructive secondary action)
- **Validate button = "Continue"** (the user-facing primary action — just keeps playing)

This means a **click on the modal's Cancel button is what triggers save-and-quit**
in the C++ code — not Validate.

### Where the callback wiring is (and isn't)

There is **no callback function pointer or event ID stored in the .gen file
itself**. The buttons carry only their label-loc keys. Wiring is C++-bound:
the modal's host class (loaded via `oCEntityCpntWindowUiSettings`) implements
`OnCancel`/`OnValidate` virtual methods (or equivalent), and `OnCancel` is
what eventually calls `session_finalize_and_save`.

The static path-traced wire (still partial):
1. At chapter-start, `session_subscribe_chapter_end_events` calls
   `FUN_14048be40(&DAT_141441b60, &DAT_141410b38, _DAT_1412c7590, &local_540, 0)`
   to load the modal, then `FUN_14010b260(session+0xf8, &local_540)` to install
   the modal handle on the session.
2. The modal's button widget components publish a named event on click.
3. **One of the ~17 events subscribed in `session_subscribe_chapter_end_events`**
   is the modal-cancel event. The corresponding thunk
   (`LAB_1402c85xx` family at image+0x2c8500..0x2c86e0) leads to a handler that
   eventually calls `session->vtable[6]()` = `session_finalize_and_save`.
4. The vtable for the GameSessionGs class lives at `0x140efa0f0` with no static
   xrefs — runtime-only access.

### Practical Frida path the decode unblocks

Even without resolving (3)/(4) statically, knowing that:
- `Modal_Save_Or_Quit.entity.ot` is reachable via the global at `0x141410b30`,
- the buttons are pure label widgets with C++ vtable callbacks,
- the modal handle is cached at `session+0xf8`,

makes a Frida-side approach plausible: locate the modal entity by signature,
walk to its window component, and either (a) find its OnCancel vtable slot and
call it directly, or (b) replay whatever named-event the cancel publishes. Both
are runtime operations that don't need new static work.

### Reusable decoder

The format above (Cooked header → `0xAABB1111` class registry → `0xAABB1111`
object section → `0xAABB2222` end) is **shared by all entity.ot, herodef.ot,
itemdef.ot, etc.** — one decoder handles all `.gen` files. Implementation
target: `tools/rerw-src/lib/cooked.py` (per dig task #21). Test corpus:
`Modal_Save_Or_Quit` (small, 2.8 KB), Geppetto `herodef.ot` (large, 18.9 KB).

### Cross-references

- File copy: `rw/dumps/modal_save_or_quit/Modal_Save_Or_Quit.entity.ot.EntitySettingsResource.gen`
- Geppetto reference (same format): `rw/dumps/geppetto/herodef_analysis.txt`
- Cooked-name cipher: `tools/rerw-src/lib/cipher.py` (note: position 40 fix needed)
