# Save: subsystem architecture and live-trigger map

How Ravenswatch saves are written to disk: the threading model, function call chain, key globals, and the addresses needed to trigger an on-demand save from a live game.

**Status:** Architecture mapped 2026-04-29. Save subsystem trigger pipeline confirmed: Frida invocation of `save_request_sync` successfully causes the worker thread to write `Profile_1.ob` to disk. **However, the produced file is incomplete:** `save_request_sync` only enqueues a write of bytes already prepared at `job+0x30`. A separate **prep / serializer function** (location TBD) is responsible for walking the live run-state and serializing it into that buffer before the natural game save. We bypassed that step. **Next gap:** identify and call the prep function from Frida so the buffer reflects current state. See `tools/frida/HANDOFF.md` "Prep function search" section.
**Created:** 2026-04-29

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

The `save_atomic_orchestrator` decompile reveals the writer reads `*(job+0x30)` (data buffer pointer) and `*(job+0x38)` (size) and serializes those bytes via `oCFileBinaryStream::vtable[1]`. Neither `save_request_sync` nor the worker thread populates these fields. The natural game save chain (chapter-end UI → `FUN_14028d6a0` orchestrator → `save_request_sync`) populates them somewhere upstream. Possibly via:

- `FUN_140678780(data_source + 0xd8)` — pre-save state setup
- `FUN_1406ce030(data_source + 0xa8, ...)` — operates on the records vector
- A vtable call: `(**(code **)(*plVar7 + 0x40))(plVar7, ...)` — likely a "serialize self to buffer" virtual method

One of these (or a chain of them) is the prep function. Identifying it via static analysis is the next blocker for save-anytime functionality. See `tools/frida/HANDOFF.md` "Prep function search" section.

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

## Cross-references

- `rw/key-findings/save-binary-format.md` — the format being written.
- `rw/key-findings/save-account-binding.md` — Steam Cloud vs file portability.
- `rw/key-findings/magical-objects.md` — record format inside the saved file.
- `rw/triage/items-add-primitive-cap.md` — open: chapter-completion test of counter durability is in progress (BM Mirror probe currently swapped into active save).
