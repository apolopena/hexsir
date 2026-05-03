[← Back to findings](README.md)

# Frida save-trigger pipeline — hardware breakpoint task

**Status:** in-progress
**Status notes:** Mechanical save trigger works (Frida invocation of `save_request_sync` causes the worker thread to write `Profile_1.ob`); however, the produced file is incomplete — the engine does not show "Continue" on relaunch. The buffer at `data_source+0x1928+0x30` is populated lazily by `oCMemoryBinaryStream::Write` calls dispatched through vtables that don't appear in static xref graphs. Hardware data breakpoint on `*(data_source + 0x1958)` during a real chapter-end run is the cleanest path forward.
**Created:** 2026-04-29 (originally `tools/frida/HANDOFF.md`; folded into findings under PRP-6 docs overhaul)

## Sources

- `tools/frida/save_now.js`, `tools/frida/repl.js`, `tools/frida/trace_save_dialog.js` — the Frida pipeline scripts.
- `rw/findings/save-subsystem.md` — full architecture: chapter-end call topology, suspect functions (`FUN_14028f140`, `FUN_140291350`, `FUN_1402907e0`, `FUN_14028d6a0`), oCDtRootGs layout.
- `rw/findings/save-flow-diagrams.md` — mermaid diagrams of the save flow, class hierarchy, data layout.
- `rw/saves/proofs/geppetto/chapter1/frida-trigger-1/Profile_1.ob` — proof artifact from the working (but incomplete) pipeline (md5 `48c24953cc845b7f5304e0268caf23d6`).

## Goal

Build a Frida-driven save trigger for Ravenswatch. The user can edit save bytes externally, then run a single Frida command that makes the running game serialize current in-memory state to `Profile_1.ob` — collapsing the test cycle from ~20 minutes (chapter run) to ~5 seconds.

## What's working

The mechanical pipeline is operational. `tools/frida/save_now.js` exposes `globalThis.go()`:

1. **Read image_base.** `Process.findModuleByName('Ravenswatch.exe').base` — the ASLR-randomized base.
2. **Compute static addresses.** `expectedFn = image_base + 0x1c6830` (typedesc-getter), `saveFn = image_base + 0x6797b0` (`save_request_sync`).
3. **Find vtable addresses in image.** `Memory.scanSync(image_base, image_size, ptrToBytes(expectedFn))` returns each qword equal to `expectedFn`. Each match is a vtable slot 0; typically 2 hits — one is `oCDtRootGs::vftable`, the other a sibling-class vtable.
4. **Scan heap for instances.** Bulk-read each rw- range with `addr.readByteArray(chunkSize)` and JS-loop over qwords. Each qword whose value equals a candidate vtable address is a candidate instance.
5. **Filter to plausible candidates.** Reject any whose `flag` (`+0x1ef4`) is not 0 or 1, whose `done > pend`, or whose `result >= 16` (and not `0xff` sentinel). The right `oCDtRootGs` always passes; sibling-class instances typically fail at least one.
6. **Trigger save.** `((void(*)(void*, void*))saveFn)(NULL, instance + 0x1928)`. Synchronous — busy-waits inside the function until the worker thread completes the file write (~50-200ms). Returns when `Profile_1.ob` is updated.

Run output from a working session:

```
[+] image_base = 0x7ff622cd0000
[+] expected vtable[0] = 0x7ff622e96830
[+] save_request_sync   = 0x7ff6233497b0
[+] 2 aligned vtable address(es) found
[+]   found: 0x2ba502214a0 (82937ms)
[+] selected: 0x2ba502214a0
[+] triggering save: save_request_sync(NULL, 0x2ba50222dc8)
[+]   before: pend=1 done=1
[+]   after:  pend=2 done=2 result=0 (took 8ms)
[+] SAVE COMPLETE.
```

Game UI displays "Now Saving" during the call, confirming the trigger goes through the real in-engine save path rather than being a silent file-write side effect.

## Why the file is incomplete

`save_request_sync` does NOT introspect run state. The worker thread reads `*(job+0x30)` (data buffer ptr) and `*(job+0x38)` (size), then writes those bytes to disk. The Frida-triggered save does produce some new serialized records, so some upstream state/buffer content is current — but the natural-save preparation/finalization that makes the file complete and loadable is bypassed.

Result: file has hero header, catalog (114 immutable records), picked talent, and some newly written records — but lacks the complete resumable-run state the engine expects. On relaunch, the main menu shows only "New Game" rather than "Continue."

## Why static analysis stalls (the reframing)

**Update 2026-04-30 (revised, late):** The "prep function" hunt was reframed.

The job at `data_source+0x1928` IS an `oCMemoryBinaryStream`. The buffer pointer at `job+0x30` (= `data_source+0x1958`) is **NULL at construction** — there is no single "allocate buffer" call to find. The buffer is allocated and grown lazily by `oCMemoryBinaryStream::Write` (image+0x5257d0) inside its grow path (`oCMemoryBinaryStream_grow_buffer` at image+0x24e700). Chapter-end serialization calls Write many times (vtable-dispatched), each appending a record. Static analysis can't see those callers because vtable dispatches don't appear in xref graphs.

The cleanest path forward is a **hardware data breakpoint on `*(data_source + 0x1958)`** during a real chapter-end run: the instruction that writes the first non-NULL pointer there is the FIRST Write call, and its call stack reveals the chapter-end SerializeArchive entry point.

## Next task: hardware-breakpoint capture

The exact recipe lives in [`../docs/workflow/windbg.md`](../docs/workflow/windbg.md) §"Find the chapter-end save buffer writer." Outline:

1. Begin a chapter-2+ run; reach the boss arena.
2. Kill the boss. Do not click "save and exit" yet — the post-kill animation window is ~5-15 s.
3. **Attach WinDbg AFTER boss-kill** during the animation window. Attaching at boss-spawn or boss-kill itself triggers an anti-debug self-termination (confirmed empirically 2026-04-29).
4. Find the live `data_source` via Frida `globalThis.find()` before the WinDbg attach (note the address; it's heap, per-launch).
5. In WinDbg: `ba w8 <data_source+0x1958>`, then `g`, click through the save dialog, capture the call stack with `kb 30` when the breakpoint fires.

The first Write call's call stack tells you which function called it — that's the chapter-end SerializeArchive entry point.

## Field offsets within `oCDtRootGs`

| Offset | Field |
|---|---|
| `+0x00` | vtable pointer (in image) |
| `+0x08` | linked-list next pointer |
| `+0x1928` | embedded IO job struct (passed as `param_2` to `save_request_sync`) |
| `+0x1928 + 0x7c` (= +0x19a4) | u32 pending-save sequence (incremented per request) |
| `+0x1928 + 0x80` (= +0x19a8) | u32 completed-save sequence (set by worker after save) |
| `+0x1928 + 0x84` (= +0x19ac) | u8 result code (0 = success) |
| `+0x1ef4` | u8 saves-disabled flag (0 = enabled) |

The instance is heap-allocated when a profile/run loads — no static address holds it directly. Discovery requires scanning the heap for objects whose first qword equals one of the `oCDtRootGs::vftable` addresses (which we find by scanning the image's `.rdata` for qwords equal to `image_base + 0x1c6830`).

## Critical RVAs

| RVA | Symbol | Use |
|---|---|---|
| `0x6797b0` | `save_request_sync` | The save trigger function. Call as `((void(*)(void*, void*))(image_base + 0x6797b0))(NULL, job_ptr)` |
| `0x679760` | `save_request_async` | Async variant; returns a seq number; poll job+0x80 for completion |
| `0x6818a0` | `saves_queue_enqueue` | Lower-level enqueue (advanced) |
| `0x143fcd0` | `g_saves_manager_struct` | Saves manager singleton (statically allocated) |
| `0x14475a0` | `g_oCDtRootGs_typedesc` storage | Holds a heap pointer to the type descriptor; runtime-set during class registration |
| `0x1c6830` | typedesc-getter function | The unique `vtable[0]` for class `oCDtRootGs`. Discriminator: every `oCDtRootGs` instance's `vtable[0]` equals `image_base + 0x1c6830` |

## Static event-bus finding (2026-04-29)

Investigated to answer whether the chapter-end save dialog path is a publish site or a subscriber.

Event names such as `GAME_END_SUCCESS` are not passed around as raw string pointers in the runtime event calls. The boot/static initializer hashes the string with the engine CRC table, calls `FUN_140506950(0, crc)`, and stores the resulting runtime ID. For `GAME_END_SUCCESS`:

- Literal string: `0x140ef16c8`.
- Runtime event ID storage: `DAT_1412bfca0`.
- Xrefs to the ID storage: write at `0x14002e537`, reads at `0x140280574` and `0x140281832`.

The repeated subscribe shape in `FUN_14027fde0`:

1. Load a hashed event ID into a local.
2. Call `FUN_14023d6e0(event_map, out_pair, &event_id)` to find/create the event bucket.
3. Call `FUN_140216210()` to allocate a callback node.
4. Call `FUN_140503df0(callback_node, closure)` to install `{this, thunk}`.
5. Append the callback node to the bucket list/vector and store the handle on the session object for cleanup.

Confirmed subscriptions in `FUN_14027fde0`:

- `GAME_END_SUCCESS` ID `DAT_1412bfca0`, read at `0x140280574`, installs thunk `LAB_1402c85c0`, which resolves to handler `FUN_140282df0`.
- `GAME_END_SUCCESS_SKIP_NEXT` ID `DAT_1412c02a0`, read at `0x140280644`, installs thunk `LAB_1402c85e0`, which resolves to handler `FUN_140282b50`.

`FUN_14027fde0` also publishes `GAME_CHRONO_START`; it does not merely subscribe to it. Near the modal resource load:

- It loads `GameUis\\Modal\\Modal_Save_Or_Quit.entity.ot` through `FUN_14048be40`, then stores the handle at `session+0xf8` via `FUN_14010b260`.
- It constructs an `oCGameNamedEvent` from `DAT_1412c00a8` (`GAME_CHRONO_START`) with `FUN_140652960`.
- It dispatches/publishes that event with `FUN_140652b60(event_context, event_obj)` at `0x140280eb5`.

Implication: `FUN_14027fde0` is the save-or-continue modal setup path and a `GAME_CHRONO_START` publish site. The actual "chapter complete / show save dialog" trigger is upstream of this function, likely where `GAME_END_SUCCESS` is published and the registered handler chain enters this modal setup.

## Avoid broad recursive Frida heap ref scans

A diagnostic attempt on 2026-04-29 found the live data source and job fields, then started recursive reference scans for owner discovery. The repeated full/near heap scanning was too slow and the game later crashed/closed without a fresh CrashDB dump. Crash signature:

```
SYMBOL_NAME: Ravenswatch+4f2d45
FAILURE_BUCKET_ID: NULL_CLASS_PTR_READ_INVALID_POINTER_READ_c0000005_Ravenswatch.exe!Unknown
```

`Ravenswatch+0x4f2d45` is `0x1404f2d45`; disassembly shows `MOV R8, qword ptr [RAX]` immediately before a virtual call through `[R8+0x138]`, so the crash is a null/invalid object pointer dereference in a virtual-call loop. Treat broad memory/reference diagnostics as suspect unless they are tightly bounded.

Safer Frida owner-discovery path added after the crash:

- `tools/frida/diagnose_save.js` now has `session()`.
- `session()` finds `oCDtRootGs` as before, then scans for exact `oe::dt::GameSessionGs::vftable` at RVA `0xEFA0F8`.
- It verifies candidates by checking whether `candidate+8` linked-list traversal contains the data source.
- Avoids recursive "find all references to all previous nodes" scans. Should be the next Frida diagnostic before trying another live chapter-end run.

While the user is carrying a live run to chapter end, avoid broad heap scans. Use static Ghidra work, passive hooks, or narrow WinDbg breakpoints/watchpoints instead.

## Parallel investigation: what gates the "Continue" dialog?

Independent of the prep-function question: the engine decides whether to show "Continue" vs only "New Game" based on **something** when it reads `Profile_1.ob` at startup. Two possibilities:

1. **Pure file structure** — engine inspects the bytes, finds a valid run-state record with specific fields populated (items count > 0? some "in-progress" flag?), and shows Continue.
2. **External marker** — separate file, registry entry, or in-engine flag set when a save is created that says "this profile has a resumable run."

The save folder layout (`_Save\Profile_1.ob`, `Profile_1_Temp.ob`, `GameSettings.ini`, `steam_autocloud.vdf`) doesn't show an obvious external marker. `steam_autocloud.vdf` is Steam-side, not consulted by the game (see [`save-account-binding.md`](save-account-binding.md)). So the dialog is **likely driven by the file structure itself**.

### Why this matters

If we can identify the exact field/byte that gates Continue, we have two payoffs:

- **Disambiguation.** We can know whether a future fix (prep function found, save written) actually solves the loadability problem, OR if there's a second hidden requirement.
- **Bypass shortcut.** If the gate is just a flag, we could potentially patch our incomplete save to set the flag and see if the engine attempts to load it. The load would likely fail (because run state is missing) but we'd learn what the engine checks for.

### How to find the Continue gate

Static approach (Ghidra):

1. Search for the function that populates the main-menu UI. Strings to start from: `"Continue"` UI string, `"New Game"` UI string, the function reading `Profile_1.ob` at title-screen time (NOT during run-load).
2. The function will read the save file, parse some specific fields, and return a boolean (or set a flag) that the menu UI consumes. That field is the gate.
3. Likely candidates: items count, a specific u32 in the run-state body (could be a "run state" enum), the presence of any `tag=0x12` record, a field in the trailing block.

Empirical approach (faster, but requires Frida prep function first OR a hand-crafted file):

1. Take a known-good chapter-2 save (engine shows Continue).
2. Mutate one field at a time, observe which mutation causes Continue to disappear.
3. The byte(s) that flip the dialog from Continue → New Game ARE the gate.

Empirical testing requires a faster iteration loop than 20-min chapter playthroughs — which loops back to needing the Frida save trigger to actually work. So the prep-function investigation is the higher-priority blocker.

## Possible future improvements (after prep is solved)

- **Speed up the heap scan.** Currently ~80 seconds dominated by per-pointer reads. Options: reduce ranges scanned (skip very small ones, target the heap arenas where instances live based on prior observation, e.g. the `0x2ba_xxxxxxxx` range). Or use `Memory.scanSync` more cleverly with the exact 8-byte vtable pattern.
- **Cache `data_source` pointer across invocations within a session.** Same game session, same heap state — once found, reuse. Would need an out-of-process cache (e.g. a temp file) since Frida sessions don't persist.
- **Auto-detect when scan is unneeded.** If the user just saved 30 seconds ago and the game hasn't reloaded a profile, the cached pointer is still valid. Check via signature on the cached address before re-scanning.
- **Make a CLI wrapper.** `rerw save-now` that takes care of the frida invocation, copies the script, parses output, returns success/failure with the new file's md5. Hides the Frida details from the user's normal workflow.
