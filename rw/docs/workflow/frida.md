[← Back to workflow](README.md)

# Frida

Frida technique for Ravenswatch. Hook patterns, REPL reference, dump-and-compare, full-process memory snap/diff. The setup steps (installing Frida-tools on Windows, finding the right `frida.exe`, the WSL→Windows interop pattern) live in [`tools/frida/README.md`](../../../tools/frida/README.md); this chapter covers what to do once it's running.

## What this is for

Frida lets us hook live functions in the running game, read or write process memory, and trigger code paths without recompiling. The killer use case in this project is collapsing the save-edit verification loop from the natural ~20-minute chapter run down to ~5 seconds — Frida invokes `save_request_sync` directly, the worker thread writes `Profile_1.ob`, we inspect or diff. Beyond that, Frida is the cheapest path for hook tracing, hardware-breakpoint substitutes, and targeted memory inspection that doesn't require the game to be paused under a debugger.

## Concepts

### Image base and RVA

`Process.findModuleByName('Ravenswatch.exe').base` is the per-launch ASLR-randomized image base. Every static address in this project is recorded as an RVA (relative virtual address) — add it to the live image base to get a runtime pointer. Static addresses we cite throughout the findings are RVAs, e.g. `save_request_sync` lives at RVA `0x6797b0`.

### Static vs heap discovery

Some objects (typedesc-getters, vftables, RTTI strings) live in the image and can be located by scanning `.rdata` for known constants. Heap-allocated instances (`oCDtRootGs`, the live data source for the save subsystem) are not at any static address; they're discovered by scanning each writable heap region for a qword equal to a known vftable address. The `save_now.js` script does both.

### Hook patterns

- **Passive trace.** `Interceptor.attach(addr, { onEnter, onLeave })`. Used for measuring how often a function fires, what its first argument is on each call, what its return value looks like.
- **One-shot dump.** Same shape, but the hook self-detaches on first fire. Useful when the function is hot and you only want the first invocation's state.
- **Arm/disarm.** Hook installed on demand from the REPL via a `globalThis` function, detached on demand. Lets a long-running session add and remove tracing without restarting Frida.

### REPL vs script-load

Frida CLI has a **30-second script-load timeout**. A script that blocks for >30s during top-level execution is killed with `Failed to load script: timeout was reached`. Workaround: have the script define functions in `globalThis` so the load phase returns instantly, then drive them from stdin. Function calls have no timeout. Heap scans (~60-90 seconds) MUST be triggered this way.

## Recipes

### Trigger a save from outside the game

The pipeline is fully built — `tools/frida/save_now.js` exposes `globalThis.go()` which scans for the live `oCDtRootGs` instance and calls `save_request_sync`. Drive from WSL:

```bash
FRIDA="/mnt/c/Users/<USER>/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe"
cp /home/<USER>/repos/work/ravensmith/tools/frida/save_now.js /mnt/c/Users/<USER>/AppData/Local/Temp/save_now.js
printf 'go()\nexit\n' | "$FRIDA" -n Ravenswatch.exe -l 'C:\Users\<USER>\AppData\Local\Temp\save_now.js'
```

Expected output ends with:

```
[+] selected: 0x...
[+] triggering save: save_request_sync(NULL, 0x...)
[+] SAVE COMPLETE.
```

The worker thread is synchronous — the call busy-waits until the file write completes (~50-200ms). Caveat: the file written by this pipeline today is not yet a complete resumable run-state save; see [`frida-pipeline-hardware-breakpoint.md`](../../findings/frida-pipeline-hardware-breakpoint.md) for the open prep-function question.

### Interactive REPL toolkit

`tools/frida/repl.js` exposes inspection helpers: `scan()`, `dump()`, `field()`, `stats()`, `imageInfo()`, `typedesc()`. Drive interactively:

```bash
"$FRIDA" -n Ravenswatch.exe -l 'C:\...\Temp\repl.js'
# at the prompt:
imageInfo()        # base, size
scan(...)          # custom byte pattern
field(addr, off)   # qword read at address+off
```

The 90+ lines of inline doc comments in `tools/frida/rw_lab.js` are the canonical REPL command reference — read those rather than trying to maintain a copy here.

### Passive trace of the chapter-end save chain

`tools/frida/trace_save_dialog.js` installs hooks on modal-open, `GAME_END_*` handlers, save-result handlers, and `save_request_*`. The hot modal callback at `0x281b40` is opt-in via `hot()` — it fires continuously during modal lifetime and floods the log if always-on.

### Dump-and-compare (targeted)

The minimal pattern for "what byte changes when I do X":

1. Hook the function whose runtime state you want to capture.
2. In `onEnter`, dump the relevant memory region with `addr.readByteArray(size)` and write to a file in `/mnt/c/Users/<USER>/AppData/Local/Temp/`.
3. Trigger condition X in the game.
4. Trigger condition Y.
5. From WSL, diff the two dumps.

This is the lightweight version of the snap/diff workflow — you target a single struct or buffer rather than the whole process.

### Memory analysis (full-process snap/diff)

For finding where a known game-state value lives in process memory (e.g. the runtime address of in-run Level), the heavy-hitter is `rw/scripts/windows/mem_snapshot.py` — captures every writable region of the process and computes diffs against a baseline. Frida can drive the snap via the REPL, but the script also runs standalone via `pymem`. The script doesn't depend on Frida; it's documented here because it composes naturally with Frida-driven hooks during the same investigation session.

#### Setup (Windows-side, one-time)

```powershell
py -m pip install pymem
```

Run the terminal **as Administrator** — `OpenProcess` needs `SE_DEBUG_NAME`.

#### Diffs and intersects

A **diff** is the list of memory addresses where two snapshots differ. Loading a save changes thousands of addresses (HP, XP, position, RNG, level, etc.), so a single diff is a wide net.

An **intersect** is the addresses present in *every* diff. Each diff is a list of suspects, and the intersect keeps only the suspects who appear on all the lists. To isolate the runtime address of (say) Level, you take diffs against several different level values — the actual Level integer is the only thing that consistently changes in every comparison.

More diffs = stricter filter. Each one can only shrink (or hold) the surviving set, never grow it. Three diffs is usually enough for a single field; 4–5 narrows further.

#### Workflow

The first `grab` in an empty directory is the **baseline**. Every subsequent `grab` captures and writes a diff against it. Files are never overwritten — delete the `.snap` (and the matching `diff_<label>.txt`) by hand to redo. Labels are optional; without one the script picks the next sequential `grabNNN`.

```powershell
py mem_snapshot.py grab clean   --out-dir C:\ravensmith\snaps   :: baseline
py mem_snapshot.py grab level5  --out-dir C:\ravensmith\snaps   :: + diff_level5.txt
py mem_snapshot.py grab level8  --out-dir C:\ravensmith\snaps
py mem_snapshot.py grab level14 --out-dir C:\ravensmith\snaps

py mem_snapshot.py intersect    --out-dir C:\ravensmith\snaps
:: -> intersect.txt with int32_le / float32 / hex columns
```

The `intersect` step is **cheap (~30s)** and produces a value-annotated `intersect.txt`.

> **Keep all `.snap` files until the experiment is fully done.**
> The baseline (named in `.baseline`) is required for any future `grab` to compute its diff — delete it and you can't extend the test without redoing every grab. The non-baseline snaps preserve the ability to read byte values at any address in any captured state — useful if you later want to re-run intersect with a different snap as the value source. Disk cost: ~5 GB per snap. Delete only when the analysis is complete.

#### Disambiguation pattern

Two intersects rather than one. The first runs after enough grabs to narrow candidates (e.g. four levels: L5/L8/L14/L17). Pick a candidate by scanning the `int32_le` column for the most recent value. Add one more grab with a fresh disambiguator value (e.g. L20). Run a second intersect; the address whose `int32_le` is now `20` is the runtime field. Others were coincidental.

If no candidate tracks the disambiguator, the field may be encoded in a way the 4-byte-aligned int32 view doesn't reveal cleanly (1-byte field at a non-aligned offset, embedded in a struct, etc.). Re-examine the diff data with byte-level filters.

#### Noise filtering (optional)

If `intersect.txt` has too many candidate addresses to scan, take noise samples to characterize background drift, then run `intersect-noisy`:

```powershell
:: with the game in the same paused state used for the level grabs:
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps   :: 2 minimum
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps   :: 3+ for stable floor

py mem_snapshot.py intersect-noisy --out-dir C:\ravensmith\snaps
```

`grab-noisy` captures two snaps back-to-back into temp files, computes a noise diff, and deletes both temp snaps. `intersect-noisy` requires ≥2 main diffs AND ≥2 noise diffs.

#### Output format

```
# 247 addresses changed in all 3 diffs
# values from level14.snap; addr  int32_le  float32  hex
* 0x00007ff812345020           14   1.961e-44  0e000000
  0x00007ff812345021            0   ...        ...
* 0x00007ff812345088          100   1.401e-43  64000000
```

A `*` marks the start of a run (consecutive changed bytes). Continuation bytes are indented. `int32_le`, `float32`, and `hex` are the same 4 bytes interpreted three different ways.

### WSL log-access caveats

Frida scripts that write a diagnostic log live on the Windows side. WSL sees them via `/mnt/c/...`. Two gotchas:

- **`tail -f` does NOT follow Windows-process writes reliably from WSL.** The `/mnt/c` filesystem driver does not deliver inotify events for modifications made by Windows processes (frida.exe is a Windows process). `tail -f` will appear frozen on stale content. Use **`tail -F`** (capital F) — re-stats periodically. `cat` works any time. `wc -l` is a reliable size check.
- **`'w'`-mode truncation on script reload.** Scripts that open a log with mode `'w'` truncate prior content on every (re-)launch. Copy aside before re-attaching if you need the previous session.

## Gotchas

### REPL eats backslashes on `%load` reloads

Never reload a script from inside the REPL. After any edit, exit Frida and re-launch with a fresh one-liner. The REPL strips backslashes from Windows paths during `%load`, so your reload silently runs a stale or wrong script.

### Frida 17.9.3 API gotchas

These cost hours to figure out the first time:

- **`Memory.readByteArray(addr, size)` does NOT exist.** Returns "not a function". Use the NativePointer instance method instead: `addr.readByteArray(size)`.
- **Pattern syntax does NOT support `??` wildcards** in `Memory.scanSync`. Patterns like `?? ?? ?? ?? f6 7f 00 00` throw "invalid match pattern". Only literal hex bytes are accepted.
- **`Memory.scanSync` per-call overhead is significant** (~150-200ms per call regardless of range size). Don't call it once per heap range across thousands of ranges. Prefer bulk `addr.readByteArray(size)` + JS DataView loop, or batch ranges.
- **Calling `vtable[0]()` on random pointers is dangerous.** Random function calls with random pointer args can corrupt state and crash the game. Always pre-filter with strong structural signatures, or use exact byte-pattern matching on known function/vtable addresses.

### WSL UNC paths get backslash-mangled

Don't pass `\\wsl.localhost\...` paths directly to `frida.exe` args. Copy scripts to `/mnt/c/Users/<USER>/AppData/Local/Temp/` and pass the Windows path.

### Avoid broad heap reference scans during a chapter run

A 2026-04-29 attempt at recursive owner-discovery (find all references to all previous nodes) crashed the game without a fresh CrashDB. While the user is carrying a live run to chapter end, prefer narrow targeted reads, passive hooks, or WinDbg breakpoints over broad recursive Frida scans.

## Pointers

- **Setup:** [`tools/frida/README.md`](../../../tools/frida/README.md) — install steps, frida.exe path discovery, basic invocation.
- **Findings:** [`save-subsystem.md`](../../findings/save-subsystem.md), [`save-flow-diagrams.md`](../../findings/save-flow-diagrams.md), [`frida-pipeline-hardware-breakpoint.md`](../../findings/frida-pipeline-hardware-breakpoint.md).
- **Sibling chapters:** [`windbg.md`](windbg.md) (live-process debugging), [`ghidra.md`](ghidra.md) (static decompile).
- **Tools:** `tools/frida/save_now.js`, `tools/frida/repl.js`, `tools/frida/rw_lab.js`, `tools/frida/trace_save_dialog.js`, `rw/scripts/windows/mem_snapshot.py`.
- **Vocabulary:** [`../terminology/README.md`](../terminology/README.md).
