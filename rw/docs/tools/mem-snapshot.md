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

```powershell
py mem_snapshot.py grab clean   --out-dir C:\ravensmith\snaps
:: → clean.snap, marked baseline

py mem_snapshot.py grab level5  --out-dir C:\ravensmith\snaps
:: → level5.snap + diff_level5.txt

py mem_snapshot.py grab level8  --out-dir C:\ravensmith\snaps
py mem_snapshot.py grab level14 --out-dir C:\ravensmith\snaps

py mem_snapshot.py intersect    --out-dir C:\ravensmith\snaps
:: → intersect.txt
```

Each `grab` shows live progress (region count, bytes captured, %), then prints
a Type breakdown — `PRIVATE` (heap), `IMAGE` (writable globals in EXE/DLLs),
`MAPPED` (shared memory). A few dozen regions are typically skipped (guard
pages, kernel-protected memory); that's normal.

## Output

`intersect.txt` looks like:

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

- `<label>.snap` per grab — full memory dump, multi-GB, gitignored space (use
  a Windows-local dir, not the WSL repo)
- `.baseline` — single line containing the baseline snap's filename
- `diff_<label>.txt` per non-baseline grab — sorted list of changed addresses
- `intersect.txt` — final output, the only file worth copying into the repo
  (`rw/dumps/`, gitignored)
