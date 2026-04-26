[← Back to tools](README.md)

# mem-snapshot

Windows-only Python script that captures the live writable memory of a running
Ravenswatch process and finds memory addresses that change in response to a
known change in game state. Used to locate the runtime address of save-file
fields (Level, Dream Shards, etc.).

Source: `rw/scripts/windows/mem_snapshot.py`. Runs on Windows because it uses
`pymem` + `OpenProcess`; copy it to a Windows-local path or run it from the
repo via the WSL UNC path.

## Setup

```powershell
py -m pip install pymem
```

Run the terminal **as Administrator** — `OpenProcess` needs `SE_DEBUG_NAME`.

## Concept

A **diff** is the list of memory addresses where two snapshots differ. Loading
a save changes thousands of addresses (HP, XP, position, RNG, level, etc.), so
a single diff is a wide net.

An **intersect** is the addresses present in *every* diff. Think of it as a
lineup: each diff is a list of suspects, and the intersect keeps only the
suspects who appear on all the lists. To isolate the runtime address of (say)
Level, you take diffs against several different level values — the actual
Level integer is the only thing that consistently changes in every comparison.

More diffs = stricter filter. Each one can only shrink (or hold) the surviving
set, never grow it. Three diffs is usually enough for a single field; 4–5
narrows further.

## Workflow

The first `grab` in an empty directory is the **baseline**. Every subsequent
`grab` captures and writes a diff against it. Files are never overwritten —
delete the `.snap` (and the matching `diff_<label>.txt`) by hand to redo.

Labels are optional. Without one, the script picks the next sequential
`grabNNN` (zero-padded).

### 1. Capture (required)

```powershell
py mem_snapshot.py grab clean   --out-dir C:\ravensmith\snaps
:: → clean.snap, marked baseline

py mem_snapshot.py grab level5  --out-dir C:\ravensmith\snaps
:: → level5.snap + diff_level5.txt

py mem_snapshot.py grab level8  --out-dir C:\ravensmith\snaps
py mem_snapshot.py grab level14 --out-dir C:\ravensmith\snaps
```

Each `grab` shows live progress (region count, bytes captured, %), then prints
a Type breakdown — `PRIVATE` (heap), `IMAGE` (writable globals in EXE/DLLs),
`MAPPED` (shared memory). A few dozen regions are typically skipped (guard
pages, kernel-protected memory); that's normal.

### 2. Lock in values (recommended)

Run `intersect` immediately after your main grabs while the `.snap` files are
still on disk:

```powershell
py mem_snapshot.py intersect --out-dir C:\ravensmith\snaps
:: → intersect.txt with int32_le / float32 / hex columns
```

This step is **cheap (~30s)** and produces a value-annotated `intersect.txt`.

> **Keep all `.snap` files until the experiment is fully done.**
> The baseline snap (named in `.baseline`) is required for any future
> `grab` to compute its diff — delete it and you can't extend the test
> without redoing every grab. The non-baseline snaps preserve the ability
> to read byte values at any address in any captured state — useful if you
> later want to re-run intersect with a different snap as the value source,
> cross-reference values across states, or check candidate addresses
> retroactively. Once an `intersect` has been run, only the values from
> *one* chosen snap get baked into its output; values from other snaps are
> only recoverable by re-running intersect against those snaps, which
> requires them to still be on disk. Disk cost: ~5 GB per snap. Delete
> only when the analysis is complete.

Skip this step only if you don't care about value annotations.

### 3. Noise filtering (optional)

If `intersect.txt` has too many candidate addresses to scan, take noise
samples to characterize background drift, then run `intersect-noisy`:

```powershell
:: with the game in the same paused state used for the level grabs:
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps   :: 2 minimum
py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps   :: 3+ for stable floor

py mem_snapshot.py intersect-noisy --out-dir C:\ravensmith\snaps
:: → intersect-noisy.txt (main intersect minus noise floor)
```

`grab-noisy` captures two snaps back-to-back into temp files, computes a noise
diff (`diff_noise_NNN.txt`), and deletes both temp snaps. Each noise sample is
independent — pool size doesn't need to match main grab count.

`intersect-noisy` requires ≥2 main diffs AND ≥2 noise diffs. It intersects the
noise diffs to a stable noise floor, then subtracts that from the main
intersect. If a `.snap` is still around it'll annotate values; otherwise the
output is bare addresses (cross-reference against `intersect.txt` from step 2
to recover values).

## Output

`intersect.txt` (and `intersect-noisy.txt`) looks like:

```
# 247 addresses changed in all 3 diffs
# values from level14.snap; addr  int32_le  float32  hex
* 0x00007ff812345020           14   1.961e-44  0e000000
  0x00007ff812345021            0   ...        ...
  0x00007ff812345022            0   ...        ...
  0x00007ff812345023            0   ...        ...
* 0x00007ff812345088          100   1.401e-43  64000000
...
```

- A `*` marks the **start of a run** (consecutive changed bytes). The lines
  without `*` are continuation bytes within the same run — a typical 4-byte
  int change shows as one `*` line plus 3 indented lines.
- `int32_le`, `float32`, and `hex` are the same 4 bytes interpreted three
  different ways. Values come from the most recently written non-baseline
  snap.

To find a known field (e.g., Level): scan the `int32_le` column for the value
matching your latest snap (e.g., `14` if `level14` was last). False positives
are common — random bytes can land on any small integer. To disambiguate, load
a different value (e.g. L20) and re-check those candidate addresses live in
x64dbg; the address that tracks is the field.

## Files written

In the output directory:

- `<label>.snap` per grab — full memory dump, multi-GB. Use a Windows-local
  dir, not the WSL repo. Keep all of them until the experiment is fully
  done: the baseline (named in `.baseline`) is required to extend the test
  with more grabs, and the others preserve the ability to look up values at
  any captured state.
- `.baseline` — single line containing the baseline snap's filename
- `diff_<label>.txt` per non-baseline grab — sorted list of changed addresses
- `diff_noise_NNN.txt` per `grab-noisy` — noise sample diffs (can be very
  large, often hundreds of MB)
- `.noise_tmp_*.snap` — temp files during a `grab-noisy` run; deleted on
  completion
- `intersect.txt` — main output from step 2. Worth copying into the repo at
  `rw/dumps/` (gitignored).
- `intersect-noisy.txt` — optional output from step 3. Same structure but
  filtered through the noise floor.
