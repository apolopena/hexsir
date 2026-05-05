[← Back to findings](README.md)

# Frida save-trigger pipeline — prep-chain capture task

**Status:** in-progress
**Status notes:** Mechanical save trigger works (Frida invocation of `save_request_sync` causes the worker thread to write `Profile_1.ob`); however, the produced file is incomplete — the engine does not show "Continue" on relaunch. The buffer at `data_source+0x1928+0x30` is populated lazily by `oCMemoryBinaryStream::Write` calls dispatched through vtables that don't appear in static xref graphs. **The original WinDbg hardware-breakpoint plan is retired** — boss-spawn and boss-kill trip a `STATUS_BREAKPOINT` anti-debug self-terminate the moment a Windows debugger is attached (`rw/findings/save-subsystem.md` §"Empirical: WinDbg anti-debug behavior"). Replacement path: `probeForBossKillSave()` in `tools/frida/rw_lab.js` — a pure-Frida hook on `session_finalize_and_save` that walks the prep chain narrowed in the 2026-04-30 dig (`save-subsystem.md` §"Prep-chain dig — narrowed to factory+serialize on GameModeDefault") and logs the `create_serializer` and `serialize` RVAs in one chapter-end run. Frida is unaffected by the anti-debug tripwire.
**Created:** 2026-04-29 (originally `tools/frida/HANDOFF.md`; folded into findings under PRP-6 docs overhaul). Path retargeted 2026-05-03.

## Sources

- `tools/frida/rw_lab.js` — current Frida hub script. Hosts `probeForBossKillSave()` and the existing talent-picker harness. Header comment is the canonical REPL reference.
- `tools/frida/save_now.js`, `tools/frida/repl.js`, `tools/frida/trace_save_dialog.js` — the original mechanical pipeline scripts that proved `save_request_sync` end-to-end.
- `rw/findings/save-subsystem.md` — full architecture: chapter-end call topology, prep-chain dig identifying GameModeDefault+0x38 factory+serialize, anti-debug observations, oCDtRootGs layout.
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

Originally: hardware data breakpoint on `*(data_source + 0x1958)` during a real chapter-end run, capture the call stack on the first non-NULL write. **Retired** — see "Why the WinDbg hardware-breakpoint path is retired" below.

The 2026-04-30 prep-chain dig narrowed the target without WinDbg by following the call graph inside `session_finalize_and_save` (image+0x28d6a0) — see `save-subsystem.md` §"Prep-chain dig — narrowed to factory+serialize on GameModeDefault". The remaining unknowns (concrete RVAs of `create_serializer` and `serialize`) are runtime-resolved via the GameModeDefault+0x38 registry handler and so can't be pinned by static xrefs. They CAN be captured by a passive Frida hook during one normal chapter-end save.

**Decompile re-verification (2026-05-04).** The full `session_finalize_and_save` decompile was re-checked against the probe code. Confirmed structural offsets: `session+0xa5` (saves-enabled gate, char), `session+0x20 → +0x18` (= scene_manager — single chain, NOT two candidates), `+0x708` (GameModeDefault), `+0x38` (factory subsystem), factory `vtable[0xf8]`, GameModeDefault `vtable[0x40]`. The earlier "two candidate roots" approach was speculative; the decompile shows scene_manager is unambiguously `*(*(session+0x20)+0x18)`. The probe was simplified to walk only this verified chain. Plate comment recording the offsets has been added to `0x14028d6a0` in Ghidra.

**MAJOR CORRECTION (2026-05-04, same session).** The "factory + serialize → populates save buffer" hypothesis from the 2026-04-30 prep-chain dig is **wrong**:

- `factory.vtable[0xf8]` = `factory_alloc_GameModeDefault_thunk` (image+0xc6ea0) — a 2-instruction thunk (`MOV RDX,RCX; JMP allocate_GameModeDefault_with_kind`) that allocates a fresh `GameModeDefault` instance (sizeof 0x48). It is NOT a "create serializer".
- `GameModeDefault.vtable[0x40]` = `GameModeDefault_copy_chapter_index` (image+0x31bc40) — one-line: `*(p1+0x40) = *(p2+0x40)`. It is NOT a "serialize". It just copies a single u32 (the chapter index, written by `chapter_end_work` at image+0x28f578) from the running GameModeDefault into the new one.
- The new instance is cached at `*(profile_data_manager + 0x1e0)`. This is **chapter-snapshot bookkeeping**, not save-buffer serialization. The cached snapshot is presumably consumed downstream by an actual serializer that walks the profile data, but the buffer-population call is invisible from `session_finalize_and_save`.

`save_request_sync` only enqueues bytes already at IO_job+0x30 — it does not serialize. So the chain we set out to capture (`create_serializer` + `serialize`) does not exist in the form the doc proposed. **Capturing those two RVAs via `probeForBossKillSave()` would yield `0xc6ea0` and `0x31bc40`, neither of which solves the partial-save problem.**

**Reframing.** The actual question "what populates `data_source+0x1948` (the embedded `oCMemoryBinaryStream`)?" is not answered by following `session_finalize_and_save`'s call graph. The doc's earlier hypothesis that "the prep is a single hidden function discoverable by walking xrefs" was right that the answer is hidden — but it's not in the GameMode factory chain.

**New hypothesis (2026-05-04, requires empirical verification): the save buffer is populated incrementally during normal gameplay, not by a single prep function.** Static evidence supporting this:

- `session_finalize_and_save` does NOT call any serialize-shaped function before `save_request_sync`. The only functions it calls between scene-context cleanup and the data_source walk are: the chapter-snapshot bookkeeping (the misidentified "prep block"), `io_request_list_clear`, `unregister_callback_remove_from_list`, `swap_subscribed_pointer`. None of these write to the embedded oCMemoryBinaryStream.
- `oCMemoryBinaryStream::Write` (image+0x5257d0) has only a handful of static xrefs, all DATA (vtable slots) or COMPUTED_CALL on local stream objects. There is no static call site that writes to a specific oCDtRootGs's `+0x1948` slot.
- `oCDtRootGs::vftable` (0x140ef49d8) has ~26 slots, none with a shape suggesting "serialize entire state" (most are short helpers, no slots take a stream parameter).
- The doc has long observed "the buffer is populated lazily by oCMemoryBinaryStream::Write calls dispatched through vtables that don't appear in static xref graphs."

**Implication if true:** there are MANY small serialization sites across the gameplay code, each writing one record to the oCDtRootGs's stream when the corresponding state changes. Save-and-Quit is just a "flush" trigger. Chapter-boss-kill saves work because by that point the engine has emitted all records the loader expects. **Mid-run Frida triggers cannot produce a complete save**, because the buffer is incomplete by design until specific end-of-chapter writes occur. The proof-artifact `frida-trigger-1.ob` (captured chapter-1 mid-run) lacks "Continue" not because we missed a prep step, but because it was a snapshot of an in-progress stream.

**Hypothesis verification — diagnostic shipped (2026-05-04).** Step-by-step runbook for the experiment lives in [`frida-buffer-diagnostic-runbook.md`](frida-buffer-diagnostic-runbook.md) (keep open during the test). `tools/frida/rw_lab.js` now has the buffer-state diagnostic wired in:

- `findSaveBuffer()` — one-shot heap scan for the live `oCDtRootGs`, caches the pointer (~10–80s scan, mirrors `tools/frida/save_now.js` heap-scan approach which is empirically validated)
- `logSaveBuffer("label")` — reads the cached buffer state (ptr / size / capacity / pend / done / result / silencer flag) and logs one labeled line. Call at gameplay checkpoints
- The probe also walks the data_source linked list at `session_finalize_and_save` entry, auto-caches, and logs buffer state as `[PROBE/sfas/buffer]`

**Field offsets used (verified, NOT speculative):**
- `data_source + 0x1958` = buffer ptr (qword) — confirmed by `oCMemoryBinaryStream_grow_buffer` decompile (image+0x24e700) showing `*param_1` is buffer ptr; matches save_atomic_orchestrator's read of `*(job+0x30)` per the doc
- `data_source + 0x1960` = current size (u32) — same decompile, `param_1[1]` is size
- `data_source + 0x1964` = capacity (u32) — `(longlong)param_1+0xc`
- `+0x19a4`/`+0x19a8`/`+0x19ac`/`+0x1ef4` — sequence/result/silencer fields, validated empirically via `save_now.js`

**Usage protocol (one ~20-min chapter run):**

1. Launch game, attach Frida with `rw_lab.js`. Reach the run-start menu and start a chapter-1 run.
2. As soon as you have control: `findSaveBuffer()`. Wait for cache-hit log line.
3. `logSaveBuffer("chapter1-start")`
4. Clear room 1 → `logSaveBuffer("chapter1-room1-clear")`
5. Mid-chapter (a few rooms in) → `logSaveBuffer("chapter1-mid")`
6. Right before boss room → `logSaveBuffer("chapter1-pre-boss")`
7. Right after boss-kill, BEFORE clicking save → `logSaveBuffer("chapter1-post-boss")`
8. `probeForBossKillSave()` → click Save and Quit (probe auto-logs `[PROBE/sfas/buffer]`)
9. Read `C:\Users\KidSqid\AppData\Local\Temp\frida_seed_diag.log`

**Interpretation:**

| Pattern in the `size` field across `[BUFFER/...]` lines | Model | Implication |
|---|---|---|
| Grows monotonically: small→bigger→bigger→big→biggest | Incremental | Mid-run Frida saves are fundamentally impossible. Pivot Frida focus to runtime patches that influence naturally-triggered saves. |
| Near-zero or constant until probe fires, then large | Single serializer | A single big serialize call exists. Hook the call site (visible via `oCMemoryBinaryStream::Write` xrefs filtered to this `data_source`) and build `saveNow()`. |
| Mostly flat with a big jump at "post-boss" only | Hybrid | Final serializer triggered by boss-kill. Hooking THAT serializer enables chapter-end Frida saves (which is when you'd want them anyway). |

After the run, paste the `[BUFFER/...]` lines into a new "Captured size series" subsection here and update Status accordingly.

**Practical consequences if confirmed:**

- "Frida `saveNow()` at arbitrary game state" is not achievable without replicating all the engine's per-event Write calls — a much larger undertaking than expected.
- The save-edit pipeline (modify a chapter-boss-kill proof, swap into `_Save`, replay) remains the only viable path for arbitrary state injection.
- `probeForBossKillSave()` should still run for the structural-chain confirmation, but expectations should be lowered: it captures `0xc6ea0` and `0x31bc40` (now known to be chapter-snapshot bookkeeping, not buffer writers).

**Less-likely alternative directions if the incremental-write model proves wrong:**

1. Frida `Interceptor.attach` on `oCMemoryBinaryStream::Write` (image+0x5257d0) at chapter-end with a `this`-filter on `data_source+0x1948`. If a single function dominates the writes, that function is the missing prep we couldn't find statically.
2. Trace from `profile_data_manager+0x1e0`'s readers (the cached GameModeDefault snapshot) — possibly indicates a downstream serializer.

## Why the WinDbg hardware-breakpoint path is retired

Boss-spawn and boss-kill trigger a process self-terminate with `STATUS_BREAKPOINT` (0x80000003) the instant a Windows debugger is attached (no breakpoints needed; mere debugger presence is sufficient). Confirmed empirically 2026-04-29 via two independent crashes; cost two ~20-min chapter-1 runs to identify. Full evidence in `save-subsystem.md` §"Empirical: WinDbg anti-debug behavior at game-state transitions". The only safe WinDbg attach window is the post-boss-die animation (~5 s) before the Save-and-Quit dispatch — too narrow and fragile for a reliable capture pipeline.

Frida is explicitly noted as unaffected (Frida hooks via inline trampolines, no `IsDebuggerPresent()` signal). All future capture work in this chain should use Frida.

## Next task: probe capture via `probeForBossKillSave()`

The replacement workflow uses a permanent, inert-when-unarmed hook on `session_finalize_and_save` (`GameSessionGs::vftable[6]`, image+0x28d6a0) installed by `tools/frida/rw_lab.js`. Design and chain rationale are in `save-subsystem.md` §"Prep-chain dig"; REPL command and phase breakdown are in the `rw_lab.js` header §"SAVE-WRITE PREP-CHAIN PROBE".

### Operational steps

1. Reach a chapter end (any chapter; the GameModeDefault factory chain fires regardless of chapter index). The picker work and the silencer fix are both compatible — running with the production mint pipeline avoids the silencer per `save-silencer-mechanism.md`.
2. Launch the game, then attach Frida with `rw_lab.js` per the WSL → Windows interop workflow in CLAUDE.md "Frida: WSL → Windows interop workflow".
3. Before clicking "Save and Quit" on the boss-kill modal, in the Frida REPL: `probeForBossKillSave()`.
4. Click "Save and Quit". The probe fires once, dumps the chain, and disarms.
5. Read the log at `C:\Users\KidSqid\AppData\Local\Temp\frida_seed_diag.log` and copy the captured RVAs into the "Captured RVAs" subsection below.

### Expected log output

A successful capture writes lines tagged `[PROBE/sfas]` at three phases:

```
[T+...s] [PROBE/sfas] enter session=0x...
[T+...s] [PROBE/sfas] session+0xa5 (saves-enabled gate) = 0x1
[T+...s] [PROBE/sfas] *(session+0x20)        = 0x...
[T+...s] [PROBE/sfas] scene_manager          = 0x...
[T+...s] [PROBE/sfas] GameModeDefault        = 0x... vt=0x... (RVA +0x...)
[T+...s] [PROBE/sfas] factory_vtable=0x... (RVA +0x...) create_serializer=0x... (RVA +0x...)     <-- ★ first target RVA
[T+...s] [PROBE/sfas] phase2 create_serializer returned 0x...
[T+...s] [PROBE/sfas] phase2 serializer_vtable=0x... (RVA +0x...) serialize=0x... (RVA +0x...)   <-- ★ second target RVA
[T+...s] [PROBE/sfas] phase3 serialize enter rcx=0x... rdx=0x...
[T+...s] [PROBE/sfas] phase3 backtrace: 0x... (img+0x...) | 0x... (img+0x...) | ...
```

The two RVAs marked ★ are the deliverables. Cross-check that the phase3 backtrace's top frames land inside `session_finalize_and_save` (image+0x28d6a0..) — that confirms the call site is the prep block, not some unrelated serializer.

### Failure modes and how to read them

- **`session+0xa5 (saves-enabled gate) = 0x0`** — the engine will skip the prep block. Phase 2/3 won't fire. Phase 1 still captures the structural offsets, which is partial progress, but you won't get the create/serialize RVAs from this run. Investigate why saves are disabled (silencer tripped on a stale edited save? cold profile?). Re-run after fixing.
- **Chain bails at one of the structural derefs** (`*(session+0x20)` / `+0x18` / `+0x708` / `+0x38`) — the runtime structure shifted from the decompile-verified offsets. The probe logs at which step it failed and the last good pointer. Re-decompile `session_finalize_and_save` (image+0x28d6a0) in Ghidra to find the new offsets.
- **`GameModeDefault vt NOT in image`** — the +0x708 deref produced a non-vtable. Either the chain shifted, or this session is using a different GameMode (Tutorial, P2P-client, etc.) where +0x708 lives elsewhere. Inspect the live pointer manually.
- **`create_serializer not in image`** (factory `vtable[0xf8]` failed) — vtable index moved. Dump a wider range of the factory vtable and compare to the documented signature (`vtable[0xf8] = create_serializer`).
- **Phase 2 fires but serializer's `vtable[0x40]` not in image** — same issue at the serializer level. Dump the serializer vtable.
- **Phase 3 fires but backtrace top frame is NOT inside session_finalize_and_save** — the captured `serialize` is being called from somewhere else first (e.g., a sibling save path runs the same chain). The RVA is still likely correct, but verify by re-running and watching for a second phase 3 event from the actual save block.

### Captured RVAs

| Symbol | RVA | Captured | Source run |
|---|---|---|---|
| `create_serializer` (factory vtable[0xf8]) | TBD | — | — |
| `serialize` (serializer vtable[0x40]) | TBD | — | — |

Fill in after the first successful probe run. Once both rows are filled, this finding flips Status to `confirmed`.

### Post-capture follow-ups

Once the two RVAs are recorded:

1. **Annotate in Ghidra** per CLAUDE.md "Ghidra: annotate findings on the spot": rename the two functions (e.g., `GameModeDefault_serializer_factory_create` and `GameModeDefault_serialize_to_save_buffer`), document the GameMode→buffer flow.
2. **Build `saveNow()` in `rw_lab.js`** — a REPL command that, given a live game state, calls factory.create_serializer() then serializer.serialize(GameMode) then `save_request_sync`, reproducing the in-engine sequence on demand. This is the "collapse the test cycle from 20 min to 5 sec" payoff stated in this finding's Goal.
3. **Update this finding** — flip Status to `confirmed`, move the operational notes into a "How it works" section, retire the "Failure modes" troubleshooting (or move to an addendum).
4. **Cross-check the silencer interaction** — verify that calling `saveNow()` when `+0x1ef4` is non-zero behaves the way `save-silencer-mechanism.md` predicts (silently no-ops at the `save_request_sync` gate). If so, document; if not, that's a new lead.

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

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. The bulk of this finding's RVAs are foundational save-subsystem symbols that are anchored in `save-subsystem.md` §"Locating these symbols on a new build". Re-anchor that finding first; this doc inherits.

### Symbols specific to this finding

| Symbol | Anchor |
|---|---|
| `save_request_sync` (image+0x6797b0) | Single-xref guarantee from `session_finalize_and_save` (GameSessionGs `vftable[6]`). |
| `save_request_async` (image+0x679760) | Adjacent to `save_request_sync` in code; four call sites all dispatch to global save state. |
| `saves_queue_enqueue` (image+0x6818a0) | Called from both save_request_*; lower-level enqueue. |
| `g_saves_manager_struct` (image+0x143fcd0) | Static, referenced by all enqueue paths. xrefs from save_request_async. |
| `g_oCDtRootGs_typedesc` (image+0x14475a0) | Type-descriptor storage; the typedesc-getter at `image+0x1c6830` writes it on first call. |
| `oCDtRootGs` typedesc-getter (image+0x1c6830) | RTTI: it's `oCDtRootGs::vftable[0]`. The `oCDtRootGs::vftable` is the static recovery anchor. |
| `oCMemoryBinaryStream::Write` (image+0x5257d0) | RTTI: vtable slot on `oCMemoryBinaryStream`. The only impl that grows the buffer at `+0x30`. |
| `session_finalize_and_save` (image+0x28d6a0) | GameSessionGs `vftable[6]`. |
| `chapter_end_work` (image+0x2907e0) | See `chapter-map-and-boss-spawn-architecture.md` and `save-subsystem.md` for the difficulty-mapping anchor. |

### Struct offsets (within `oCDtRootGs`)

The complete `oCDtRootGs` field map is in §"Field offsets within `oCDtRootGs`" above; re-derivation paths:

| Offset | Re-derivation |
|---|---|
| `+0x1928` | Constructor of `oCDtRootGs` initializes embedded `oCMemoryBinaryStream` job here |
| `+0x1928 + 0x7c..0x84` | The `save_atomic_orchestrator` reads/writes these on each request — re-derive by decompiling that function |
| `+0x1ef4` | The saves-disabled gate — checked at the top of the orchestrator's queue function |

### Discovery primitive (heap scan for `oCDtRootGs` instance)

The runtime discovery technique itself is version-resilient *if* the RTTI-based vtable matching is intact:

1. Find `oCDtRootGs::vftable` in `.rdata` via RTTI (`.?AVoCDtRootGs@@`).
2. The vtable slot 0 is the typedesc-getter; its address (here `image+0x1c6830`) is the discriminator.
3. Scan process heap for qwords equal to `image_base + <vtable_offset>`. Each match is an `oCDtRootGs` instance.
4. The chapter-end instance is the one whose `+0x1ef4` saves-disabled flag is `0`.

This procedure does not depend on any specific RVA; only on RTTI being preserved. Should work across patches.

### Cross-finding anchoring

This finding heavily inherits from `save-subsystem.md`. If a binary update lands, re-anchor `save-subsystem.md` first using its Tier 1 (RTTI) and Tier 2 (string) anchors, then propagate updated RVAs to this finding's tables.

## Possible future improvements (after prep is solved)

- **Speed up the heap scan.** Currently ~80 seconds dominated by per-pointer reads. Options: reduce ranges scanned (skip very small ones, target the heap arenas where instances live based on prior observation, e.g. the `0x2ba_xxxxxxxx` range). Or use `Memory.scanSync` more cleverly with the exact 8-byte vtable pattern.
- **Cache `data_source` pointer across invocations within a session.** Same game session, same heap state — once found, reuse. Would need an out-of-process cache (e.g. a temp file) since Frida sessions don't persist.
- **Auto-detect when scan is unneeded.** If the user just saved 30 seconds ago and the game hasn't reloaded a profile, the cached pointer is still valid. Check via signature on the cached address before re-scanning.
- **Make a CLI wrapper.** `rerw save-now` that takes care of the frida invocation, copies the script, parses output, returns success/failure with the new file's md5. Hides the Frida details from the user's normal workflow.
