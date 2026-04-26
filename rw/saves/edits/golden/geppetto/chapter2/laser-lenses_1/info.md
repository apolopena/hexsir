# Level-Change Detection — Memory Diff Test

Five Geppetto saves in the same chapter 2 / laser-lenses_1 context, differing
only in the in-run **Level** value. Used to isolate the runtime memory address
of the Level integer via `mem_snapshot.py intersect`.

> **Chapter 2 context:** these saves were captured at the start of chapter 2,
> immediately after completing chapter 1.

## Saves

| Path | Level | CRC32 | Origin |
|------|------:|-------|--------|
| `level5/Profile_1.ob` | 5 | `0xB5C816B3` | Unaltered copy of `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` |
| `level8/Profile_1.ob` | 8 | `0xAA78B011` | Modded from `level5` via `mod_save.py --set Level 8` |
| `level14/Profile_1.ob` | 14 | `0xA4C5D44D` | Modded from `level5` via `mod_save.py --set Level 14` |
| `level17/Profile_1.ob` | 17 | `0x92474F7B` | Modded from `level5` via `mod_save.py --set Level 17` |
| `level20/Profile_1.ob` | 20 | `0x9BA49909` | Modded from `level5` via `mod_save.py --set Level 20` (disambiguator) |

**Level GUID** (save format): `b5317efe6f4a95737325675793e600`
**Level offset** (this build): `0xf1ea` (int32 LE)

## Prerequisites (Windows)

- `mem_snapshot.py` copied or accessible at `C:\ravensmith\scripts\mem_snapshot.py`
- Working dir at `C:\ravensmith\snaps\` (or anywhere — pass via `--out-dir`)
- One-time: `py -m pip install pymem`
- Run the terminal **as Administrator** (`OpenProcess` requires SE_DEBUG_NAME)

## Process

Disambiguating the runtime Level address requires **two intersects** — one
before the disambiguator level (L20) is added, and one after. The first
intersect narrows the field to a small set of value=17 candidates; the second
identifies which of them now tracks to value=20.

### 1. First four level grabs (L5 baseline + L8/L14/L17)

Copy each save into Ravenswatch's save folder, load in-game, pause, then run:

```
:: Clear any prior artifacts first
Remove-Item C:\ravensmith\snaps\* -Force

py C:\ravensmith\scripts\mem_snapshot.py grab level5  --out-dir C:\ravensmith\snaps
py C:\ravensmith\scripts\mem_snapshot.py grab level8  --out-dir C:\ravensmith\snaps
py C:\ravensmith\scripts\mem_snapshot.py grab level14 --out-dir C:\ravensmith\snaps
py C:\ravensmith\scripts\mem_snapshot.py grab level17 --out-dir C:\ravensmith\snaps
```

### 2. First intersect — values from `level17.snap`

```
py C:\ravensmith\scripts\mem_snapshot.py intersect --out-dir C:\ravensmith\snaps --out intersect_3-of-4.txt
```

Produces `intersect_3-of-4.txt` (35k+ candidate addresses, value column from
`level17.snap`).

### 3. Add the disambiguator (L20)

```
:: Copy level20\Profile_1.ob into save folder, load, pause:
py C:\ravensmith\scripts\mem_snapshot.py grab level20 --out-dir C:\ravensmith\snaps
```

### 4. Second intersect — values from `level20.snap`

```
py C:\ravensmith\scripts\mem_snapshot.py intersect --out-dir C:\ravensmith\snaps --out intersect_4-of-5.txt
```

Produces `intersect_4-of-5.txt` (smaller set, value column from `level20.snap`).

### 5. Copy results into the repo

From WSL:
```bash
cp /mnt/c/ravensmith/snaps/intersect_3-of-4.txt rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/
cp /mnt/c/ravensmith/snaps/intersect_3-of-4_console.txt rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/
cp /mnt/c/ravensmith/snaps/intersect_4-of-5.txt rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/
cp /mnt/c/ravensmith/snaps/intersect_4-of-5_console.txt rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/
```

> **Keep ALL `.snap` files on Windows until the experiment is fully done.**
> The baseline (`level5.snap`) is required for any future `grab` to compute
> its diff. The other snaps (level8/14/17/20) preserve the ability to look
> up values at any address in any of those states — useful if you decide to
> re-run intersect with a different value source, cross-reference values
> across states, or check candidate addresses retroactively. Disk cost is
> ~5 GB per snap. Delete only when the analysis is complete.

## Disambiguation

In `intersect_3-of-4.txt`, find addresses whose `int32_le` column equals **17**
(the latest grab when this file was written was `level17`). Expect a small
number of candidates — these are addresses where the level field *might* live.

For each candidate address, look it up in `intersect_4-of-5.txt`. The address
whose `int32_le` is now **20** is the runtime Level integer. The others are
coincidental memory locations that happened to hold 17 at one moment.

If no candidate tracks 17 → 20, the level may be encoded in a way the
4-byte-aligned int32 view doesn't reveal cleanly (1-byte field at a non-aligned
offset, embedded in a struct, etc.). Re-examine the diff data with byte-level
filters in that case.
