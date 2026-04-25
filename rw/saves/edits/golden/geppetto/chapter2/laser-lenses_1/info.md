# Level-Change Detection — Memory Diff Test

Four Geppetto saves in the same chapter 2 / laser-lenses_1 context, differing
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

**Level GUID** (save format): `b5317efe6f4a95737325675793e600`
**Level offset** (this build): `0xf1ea` (int32 LE)

## Prerequisites (Windows)

- `mem_snapshot.py` copied or accessible at `C:\ravensmith\scripts\mem_snapshot.py`
- Working dir at `C:\ravensmith\snaps\` (or anywhere — pass via `--out-dir`)
- One-time: `py -m pip install pymem`
- Run the terminal **as Administrator** (`OpenProcess` requires SE_DEBUG_NAME)

## Process

See [mem-snapshot tool docs](../../../../docs/tools/mem-snapshot.md) for the
concept (diff, intersect) and output format. Test-specific steps — the first
grab becomes the baseline; here that's L5.

1. **Launch Ravenswatch.** Copy `level5\Profile_1.ob` into Ravenswatch's save
   folder, load in-game, pause:
   ```
   py C:\ravensmith\scripts\mem_snapshot.py grab level5 --out-dir C:\ravensmith\snaps
   ```
   (becomes the baseline)
2. **L8:** exit to main menu, copy `level8\Profile_1.ob`, load, pause:
   ```
   py C:\ravensmith\scripts\mem_snapshot.py grab level8 --out-dir C:\ravensmith\snaps
   ```
3. **L14:** exit, copy `level14\Profile_1.ob`, load, pause:
   ```
   py C:\ravensmith\scripts\mem_snapshot.py grab level14 --out-dir C:\ravensmith\snaps
   ```
4. **L17:** exit, copy `level17\Profile_1.ob`, load, pause:
   ```
   py C:\ravensmith\scripts\mem_snapshot.py grab level17 --out-dir C:\ravensmith\snaps
   ```
5. **Intersect:**
   ```
   py C:\ravensmith\scripts\mem_snapshot.py intersect --out-dir C:\ravensmith\snaps
   ```

## Validation

In `intersect.txt`, find the line whose `int32_le` column equals **17** (the
last grab was `level17`, so values come from `level17.snap`). That address is
the runtime Level integer. Several false positives are expected — disambiguate
by re-running with a different level value and checking which address tracks.

Copy `intersect.txt` into the repo at `rw/dumps/level-detect-<date>.txt`. The
`.snap` files stay Windows-local — they are gigabytes each.
