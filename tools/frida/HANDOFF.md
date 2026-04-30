# Frida save-trigger handoff

Context for an agent picking up this work mid-session.

## Goal

Build a Frida-driven save trigger for Ravenswatch. The user can edit save bytes externally, then run a single Frida command that makes the running game serialize current in-memory state to `Profile_1.ob` — collapsing the test cycle from ~20 minutes (chapter run) to ~5 seconds.

## What's been figured out

All of the static analysis is in `rw/key-findings/save-subsystem.md`. Critical RVAs (relative to Ravenswatch.exe image base, which is 0x140000000 in Ghidra):

| RVA | Symbol | Use |
|---|---|---|
| `0x6797b0` | `save_request_sync` | The save trigger function. Call it as `((void(*)(void*, void*))(image_base + 0x6797b0))(NULL, job_ptr)` |
| `0x679760` | `save_request_async` | Async variant; returns a seq number; poll job+0x80 for completion |
| `0x6818a0` | `saves_queue_enqueue` | Lower-level enqueue (advanced) |
| `0x143fcd0` | `g_saves_manager_struct` | Saves manager singleton (statically allocated; we don't actually need to pass this anywhere) |
| `0x14475a0` | `g_oCDtRootGs_typedesc` storage | Holds a heap pointer to the type descriptor; runtime-set during class registration |
| `0x1c6830` | typedesc-getter function | The unique vtable[0] for class oCDtRootGs. Discriminator: every oCDtRootGs instance's vtable[0] equals image_base + 0x1c6830 |

Field offsets within an `oCDtRootGs` instance:

| Offset | Field |
|---|---|
| `+0x00` | vtable pointer (in image) |
| `+0x08` | linked-list next pointer |
| `+0x1928` | embedded IO job struct (passed as `param_2` to save_request_sync) |
| `+0x1928 + 0x7c` (= +0x19a4) | u32 pending-save sequence (incremented per request) |
| `+0x1928 + 0x80` (= +0x19a8) | u32 completed-save sequence (set by worker after save) |
| `+0x1928 + 0x84` (= +0x19ac) | u8 result code (0 = success) |
| `+0x1ef4` | u8 saves-disabled flag (0 = enabled) |

The instance is heap-allocated when a profile/run loads — no static address holds it directly. Discovery requires scanning the heap for objects whose first qword equals one of the `oCDtRootGs::vftable` addresses (which we find by scanning the image's `.rdata` for qwords equal to `image_base + 0x1c6830`).

## Driving Frida from WSL

Frida is installed on the user's Windows side. From WSL bash, invoke `frida.exe` directly via WSL/Windows interop.

### Frida.exe path

```bash
FRIDA="/mnt/c/Users/<USER>/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe"
```

(Substitute the actual user. The path can be discovered via the Windows-side `where frida` after `frida-tools` is installed.)

### Pattern for one-shot script execution

```bash
# Copy script to a Windows-readable temp path so frida.exe can resolve it.
# (\\wsl.localhost\... paths get backslash-mangled in argv on some setups.)
cp /home/ks73/repos/work/ravensmith/tools/frida/<script>.js \
   /mnt/c/Users/<USER>/AppData/Local/Temp/<script>.js

# Run, piping `exit\n` so frida.exe leaves the REPL after the script loads.
echo "exit" | timeout 60 "$FRIDA" -n Ravenswatch.exe \
   -l 'C:\Users\<USER>\AppData\Local\Temp\<script>.js' 2>&1 | tail -80
```

### Pattern for invoking an interactive function via stdin

If the script defines globals (e.g., `globalThis.find = function() {...}`), call them via stdin:

```bash
printf 'find()\nexit\n' | timeout 300 "$FRIDA" ...
```

### Long-running scripts

Frida CLI has a **30-second script-load timeout**. A script that blocks for >30s during top-level execution will be killed with `Failed to load script: timeout was reached`. Workaround: have the script define functions in `globalThis` (load phase returns instantly), then drive them via stdin commands. Function calls have no timeout.

For very long scans, use `Bash run_in_background: true` plus a Monitor that tails the output file.

## Frida 17.9.3 API gotchas

These cost hours to figure out the first time:

- **`Memory.readByteArray(addr, size)` does NOT exist.** Returns "not a function". Use the NativePointer instance method instead: `addr.readByteArray(size)`.
- **Pattern syntax does NOT support `??` wildcards** in `Memory.scanSync`. Patterns like `?? ?? ?? ?? f6 7f 00 00` throw "invalid match pattern". Only literal hex bytes are accepted, e.g. `f6 7f 00 00`.
- **Memory.scanSync per-call overhead is significant** (~150-200ms per call regardless of range size). Don't call it once per heap range across thousands of ranges; you'll burn the script-load budget. Prefer bulk `addr.readByteArray(size)` + JS DataView loop, or batch ranges.
- **Calling `vtable[0]()` on random pointers is dangerous.** Calling random functions with random pointer args can corrupt state and crash the game. Always pre-filter with strong structural signatures, or use exact byte-pattern matching on known function/vtable addresses.
- **WSL UNC paths get backslashes mangled.** Don't pass `\\wsl.localhost\...` paths directly to frida.exe args. Copy scripts to `/mnt/c/Users/<USER>/AppData/Local/Temp/` and pass the Windows path.

## Scripts in this directory

| Script | Purpose |
|---|---|
| `save_now.js` | The final save trigger. Defines `globalThis.go()` which scans for oCDtRootGs and calls save_request_sync. Drive with `printf 'go()\nexit\n' \| frida -n Ravenswatch.exe -l save_now.js`. Heap scan takes ~60-90 seconds; the function-call path avoids the 30s script-load timeout. |
| `repl.js` | Interactive REPL toolkit. Exposes `scan()`, `dump()`, `field()`, `stats()`, `imageInfo()`, `typedesc()`. Useful for ad-hoc memory inspection. |
| `README.md` | User-facing setup/usage. |
| `HANDOFF.md` | This file — for picking up the work. |

### How `save_now.js` works (the final pipeline)

1. **Read image_base.** `Process.findModuleByName('Ravenswatch.exe').base` — this is the ASLR-randomized base; everything else is image-base relative.
2. **Compute static addresses.** `expectedFn = image_base + 0x1c6830` (typedesc-getter) and `saveFn = image_base + 0x6797b0` (save_request_sync).
3. **Find vtable addresses in image.** `Memory.scanSync(image_base, image_size, ptrToBytes(expectedFn))` scans the image for any qword equal to `expectedFn`. Each match is a vtable that contains `expectedFn` as its first slot. Typically 2 hits — one is the real `oCDtRootGs::vftable`, the other is a related class's vtable. Both are kept as candidates.
4. **Scan heap for instances.** Bulk-read each rw- range with `addr.readByteArray(chunkSize)` and JS-loop over qwords. For each qword whose value equals one of the candidate vtable addresses, the position is a candidate instance. Read structural fields (`+0x19a4` pend, `+0x19a8` done, `+0x19ac` result, `+0x1ef4` flag) for verification.
5. **Filter to plausible candidates.** Reject any whose `flag` is not 0 or 1, whose `done > pend`, or whose `result >= 16` (and not `0xff` sentinel). The right oCDtRootGs always passes; sibling-class instances (the false 2nd vtable) typically fail at least one.
6. **Trigger save.** `((void(*)(void*, void*))saveFn)(NULL, instance + 0x1928)`. Synchronous — busy-waits inside the function until the worker thread completes the actual file write (~50-200ms). Returns when `Profile_1.ob` is updated.

### Known runtime values (current session — will change next launch)

For reference if the scan completes on the user's current session:

- `image_base` = `0x7ff622cd0000`
- `expectedFn` (typedesc-getter) = `0x7ff622e96830`
- vtable candidates in image: `0x7ff623bbc8f0`, `0x7ff623bc49d8`
- data_source instance found at: `0x2ba502214a0` (vtable `0x7ff623bc49d8`)
- job pointer: `0x2ba50222dc8`
- pre-scan field state: `pend=1 done=1 result=0 flag=0` (sane; one prior save completed)

## Reference files

- `rw/key-findings/save-subsystem.md` — full architecture
- `rw/key-findings/save-account-binding.md` — separate finding about Steam Cloud being the cross-account "lock"
- `rw/key-findings/magical-objects.md` — item record format
- `rw/triage/items-add-primitive-cap.md` — engine-validation ceilings
- `tools/frida/README.md` — user-facing setup/usage doc

## Current state

✅ **Pipeline mechanically works** — Frida invocation of `save_request_sync` successfully gets the worker thread to write `Profile_1.ob` (mtime + md5 changed; `result = 0`). The game UI also displays **"Now Saving"**, confirming the trigger goes through the real in-engine save path rather than being only a silent file-write side effect.

❌ **Output file is incomplete** — engine does NOT recognize it as a continuable save (relaunch shows only "New Game"). The triggered save is not a pure no-op/stale dump: new records were verified in the generated file. However, the file still lacks enough run-state data for the main menu/load path to treat it as resumable.

⚠️ **Avoid broad recursive Frida heap ref scans.** A diagnostic attempt on 2026-04-29 found the live data source and job fields, then started recursive reference scans for owner discovery. The repeated full/near heap scanning was too slow and the game later crashed/closed without a fresh CrashDB dump. Prefer targeted Frida reads or WinDbg hardware watchpoints for the next live-session experiment.

Crash signature from that failed diagnostic:

```text
SYMBOL_NAME: Ravenswatch+4f2d45
FAILURE_BUCKET_ID: NULL_CLASS_PTR_READ_INVALID_POINTER_READ_c0000005_Ravenswatch.exe!Unknown
FAILURE_ID_HASH: {4faffeb2-a887-13d3-4d57-7e023de93963}
```

`Ravenswatch+0x4f2d45` is `0x1404f2d45`; disassembly shows `MOV R8, qword ptr [RAX]` immediately before a virtual call through `[R8+0x138]`, so the crash is a null/invalid object pointer dereference in a virtual-call loop. Treat broad memory/reference diagnostics as suspect unless they are tightly bounded.

Safer Frida owner-discovery path added after the crash:

- `tools/frida/diagnose_save.js` now has `session()`.
- `session()` finds `oCDtRootGs` as before, then scans for exact `oe::dt::GameSessionGs::vftable` at RVA `0xEFA0F8`.
- It verifies candidates by checking whether `candidate+8` linked-list traversal contains the data source.
- This avoids recursive “find all references to all previous nodes” scans and should be the next Frida diagnostic before trying another live chapter-end run.

Run output from the working pipeline:

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

Current known-good invocation from WSL:

```bash
FRIDA="/mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe"
cp /home/ks73/repos/work/ravensmith/tools/frida/save_now.js /mnt/c/Users/KidSqid/AppData/Local/Temp/save_now.js
printf 'go()\nexit\n' | "$FRIDA" -n Ravenswatch.exe -l 'C:\Users\KidSqid\AppData\Local\Temp\save_now.js'
```

The save artifact: `rw/saves/proofs/geppetto/chapter1/frida-trigger-1/Profile_1.ob` (md5 `48c24953cc845b7f5304e0268caf23d6`).

Latest live diagnostic observations:

- Paused run state described by user: 38 dream shards, level 2, starting talent, Twin Dummies, Flash of Genius, Excalibur.
- `diag()` found an `oCDtRootGs` data source and showed the job buffer was profile-shaped rather than run-complete:
  - First run: `data=0x172bef61540 size=69459`, `tag12=649`, `tag1a=1`.
  - Rerun after reattach: selected a data source with `job+0x30 = 0`, `job+0x38 = 0`.
- This supports the model that natural chapter-end save does additional state folding/finalization before the job buffer becomes a complete run save.

## Why the file is incomplete

`save_request_sync` does NOT introspect run state. The worker thread reads `*(job+0x30)` (data buffer ptr) and `*(job+0x38)` (size), then writes those bytes to disk. The Frida-triggered save does produce some new serialized records, so some upstream state/buffer content is current. What is still missing is the full natural-save preparation/finalization that makes the file complete and loadable.

We bypassed at least part of the prep/finalizer path. Result: file has hero header, catalog (114 immutable records), picked talent, and some newly written records — but still does not contain the complete resumable-run state the engine expects.

## ⭐ NEXT TASK: Find the prep function

Goal: identify the function that populates `*(data_source+0x1928+0x30)` (= job's data buffer ptr) and `*(data_source+0x1928+0x38)` (= job's data size) from current run state. Once found, our Frida script can call it before `save_request_sync` and produce a complete, loadable save.

### Where to look

The natural save flow:

```
[chapter end UI]
   ↓
FUN_14028f140 (chapter-end dispatcher, routes by phase)
   ↓ phase 3 (win)
FUN_140291350 ("Saved" dispatcher)
   ├─ FUN_1402907e0 (chapter-end work — LIKELY contains the prep call)
   └─ broadcasts "Saved" event
       ↓
[somewhere in the chain]
FUN_14028d6a0 (data-source-walking finalizer that calls save_request_sync)
   ↓
save_request_sync(unused, data_source+0x1928)
   ↓
queue → worker → save_atomic_orchestrator → save_write_binary_stream
   ↓ writes *(job+0x30) bytes
[Profile_1.ob]
```

In `FUN_14028d6a0`, immediately before the `save_request_sync` call, there is a sequence of calls that prepares state. Candidates (decompile not currently in hand — Ghidra MCP was disconnected at end of session):

- **`FUN_140678780(data_source + 0xd8)`** — operates on `+0xd8` of the data source. Plausible "build serialized blob" function.
- **`FUN_1406ce030(data_source + 0xa8, ...)`** — operates on `+0xa8` (the records-vector base). Plausible "serialize records into buffer" function.
- **vtable call**: `(**(code **)(*plVar7 + 0x40))(plVar7, lVar8)` somewhere in the chain — `vtable[0x40]` of some object. Might be a "serialize self" virtual method.

Also look at **`FUN_1402907e0`** which is called from BOTH `FUN_140291350` (chapter-end win path) and `FUN_14028f140` (phase 2). It is the chapter-end work function. It likely contains or invokes the serializer.

### What to extract from each candidate

For each candidate function:

1. **Decompile** it.
2. **Identify writes to `param_1+0x30`, `param_1+0x38`** (where param_1 is the job, OR where the call chain leads to the job). Specifically, look for `*(longlong*)(some_offset_to_job + 0x30) = <pointer to allocated buffer>` and `*(int*)(some_offset + 0x38) = <buffer size>`.
3. **If the function allocates the buffer**, note where (heap allocator? thread-local arena?). The Frida script will need access to that mechanism, OR can pre-allocate and pass in a buffer (preferred).
4. **If the function calls a deeper serialize routine**, follow it. The actual byte-emitter is likely the OEngine archive system (`oCBinarySaver` class — RTTI string we found at `0x14135b650`). Trace from a SerializeArchive() call in the data source down to the byte-write methods.

### What we want at the end

A single function (or a sequence) that, called with `data_source` as input, produces a populated `job+0x30` ready for `save_request_sync`. Ideally:

```c
prepare_save(data_source);                     // populates data_source+0x1928+0x30/0x38
save_request_sync(NULL, data_source+0x1928);   // writes the now-populated buffer
```

If `prepare_save` requires no other args than `data_source` (or simple ones), we can drop it into `tools/frida/save_now.js` immediately.

### Concrete Ghidra steps

1. Re-attach Ghidra MCP server (config in `.mcp.json`: `http://127.0.0.1:8080/mcp`).
2. Decompile `FUN_14028d6a0`. Print the LAST ~30 lines — everything between the linked-list walk that finds the data source and the `save_request_sync` call. That's the prep sequence.
3. For each function called in that prep sequence: decompile, look for writes to fields `+0x30`, `+0x38`, `+0x40` of the job struct (= data_source + 0x1928 + N).
4. Trace any vtable calls back to concrete implementations.
5. Document: the exact function (or chain) to call. Its signature. Its side effects (does it broadcast events? change state? if so, can we no-op those?).
6. Update `tools/frida/save_now.js` to call the prep function before `save_request_sync`.

### Side-effect concerns

The natural save runs at chapter-end and intentionally has side effects (state transition to "after chapter ended"). If the prep function we find is heavily entangled with those side effects, calling it mid-run might leave the game in an unexpected state.

**Mitigation:** if the prep is just a serializer, it should be side-effect-free (just walks state, fills buffer). If it's woven into the chapter-end machinery, we need to find the pure-serialize subroutine and call THAT instead.

`oCBinarySaver` is probably the pure serializer. If we can construct an `oCBinarySaver` instance in WRITE mode, point it at the data source, and call its top-level `SerializeArchive` method, we'd get a buffer of bytes back. That's the cleanest path — no chapter-end ceremony.

## Parallel investigation: what gates the "Continue" dialog?

Independent of the prep-function question: the engine decides whether to show "Continue" vs only "New Game" based on **something** when it reads `Profile_1.ob` at startup. Two possibilities:

1. **Pure file structure** — engine inspects the bytes, finds a valid run-state record with specific fields populated (items count > 0? some "in-progress" flag?), and shows Continue.
2. **External marker** — separate file, registry entry, or in-engine flag set when a save is created that says "this profile has a resumable run."

The save folder layout (`_Save\Profile_1.ob`, `Profile_1_Temp.ob`, `GameSettings.ini`, `steam_autocloud.vdf`) doesn't show an obvious external marker. `steam_autocloud.vdf` is Steam-side, not consulted by the game (see `rw/key-findings/save-account-binding.md`). So the dialog is **likely driven by the file structure itself**.

### Why this matters

If we can identify the exact field/byte that gates Continue, we have two payoffs:

- **Disambiguation.** We can know whether a future fix (prep function found, save written) actually solves the loadability problem, OR if there's a second hidden requirement.
- **Bypass shortcut.** If the gate is just a flag, we could potentially patch our incomplete save to set the flag and see if the engine attempts to load it. The load would likely fail (because run state is missing) but we'd learn what the engine checks for.

### How to find the Continue gate

Static approach (Ghidra):

1. Search for the function that populates the main-menu UI. Strings to start from:
   - `"Continue"` UI string
   - `"New Game"` UI string
   - The function reading `Profile_1.ob` at title-screen time (NOT during run-load — earlier, just to determine menu state).
2. The function will read the save file, parse some specific fields, and return a boolean (or set a flag) that the menu UI consumes. That field is the gate.
3. Likely candidates for the gating field:
   - **Items count** — chapter 2 has 21, our incomplete frida-save has 0. Plausible but feels too narrow (a fresh-start chapter could have 0 items legitimately).
   - **A specific u32 in the run-state body** — could be a "run state" enum where 0=none, 1=in-progress, 2=completed.
   - **The presence of any `tag=0x12` (run-state) record** with body matching certain criteria.
   - **A field in the trailing block** (the variable-length region documented in `magical-objects.md`).

Empirical approach (faster, but requires Frida prep function first OR a hand-crafted file):

1. Take a known-good chapter-2 save (engine shows Continue).
2. Mutate one field at a time, observe which mutation causes Continue to disappear.
3. The byte(s) that flip the dialog from Continue → New Game ARE the gate.
4. Bisect bytes by region: trailing block first, then run-state body offsets.

Empirical testing requires a faster iteration loop than 20-min chapter playthroughs — which loops back to needing the Frida save trigger to actually work. So the prep-function investigation is the higher-priority blocker, but once unblocked, this question becomes cheap to answer.

### What to test once the prep function is found

After Frida produces a complete save matching what the natural game save would write:

1. Save mid-run via Frida.
2. Quit, relaunch, look for "Continue."
3. If Continue appears: the prep function is correct AND mid-run saves are loadable. Pipeline complete.
4. If still only "New Game": there's a second gate (likely a chapter-end-only marker the engine sets in the file). Then run the empirical bisect from a known-good save to find that marker.

## Possible future improvements (after prep is solved)

- **Speed up the heap scan.** Currently ~80 seconds dominated by per-pointer reads. Options: reduce the number of ranges scanned (skip very small ones, target the heap arenas where instances live based on prior observation, e.g., the `0x2ba_xxxxxxxx` range). Or use `Memory.scanSync` more cleverly with the exact 8-byte vtable pattern.
- **Cache data_source pointer across invocations within a session.** Same game session, same heap state — once found, reuse. Would need an out-of-process cache (e.g., a temp file) since Frida sessions don't persist.
- **Auto-detect when scan is unneeded.** If the user just saved 30 seconds ago and the game hasn't reloaded a profile, the cached pointer is still valid. Check via signature on the cached address before re-scanning.
- **Make a CLI wrapper.** `rerw save-now` that takes care of the frida invocation, copies the script, parses output, returns success/failure with the new file's md5. Hides the Frida details from the user's normal workflow.
