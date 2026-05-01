[← Back to tools](README.md)

# rerw

Ravenswatch-specific RE tool.

## Commands

### `rerw cipher [--path-aware] <text>`

Encode plaintext to a ciphered filename.

```bash
./tools/rerw cipher "Geppetto"
# → Kqjjqiir
```

Use `-p` / `--path-aware` for full cooked asset paths. It preserves everything
through `DarkTalesResources/_Cooking/` and transforms only the cooked asset
suffix.

```bash
./tools/rerw cipher -p "/mnt/d/.../DarkTalesResources/_Cooking/3D/Scenery/Common.fbx.Geometry.gen"
```

### `rerw decipher [--path-aware] <text>`

Decode a ciphered filename to plaintext.

```bash
./tools/rerw decipher "Kqjjqiir"
# → Geppetto
```

```bash
./tools/rerw decipher -p "/mnt/d/.../DarkTalesResources/_Cooking/3N/Fbqzqus/Common.hap.Kqrxqius.yqz"
```

### `rerw game-assets ls [options] [path] [GNU ls flags...]`

List cooked game assets through GNU `ls`. The wrapper resolves decoded paths to
their ciphered on-disk equivalent, invokes `ls` on the real filesystem path, and
then deciphers path/name text in the `ls` output. Cooked-relative paths are
resolved against the default Ravenswatch `_Cooking` directory. The input may be
decoded or ciphered. If the input is a full cooked path, output entries are full
paths too.

```bash
./tools/rerw game-assets ls "3D/Scenery/"
./tools/rerw game-assets ls "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/3D/Scenery/"
./tools/rerw game-assets ls "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/VZ/Fqiidzyv/" -l
```

Useful flags:

```bash
./tools/rerw game-assets ls --full "EntitySettings/Heroes/"
./tools/rerw game-assets ls --cooked-relative "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/FZ/Settings/"
./tools/rerw game-assets ls -t "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/FZ/Settings/"
./tools/rerw game-assets ls --raw "EntitySettings/Heroes/"
./tools/rerw game-assets ls --ciphered "MzidisFqiidzyv/Aqurqv/"
./tools/rerw game-assets ls -la --cooked-relative "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/FZ/Settings/"
```

`--cooked-relative` strips the install prefix through `_Cooking/`, so results
start at the cooked directory segment such as `FZ/Settings/...`.
`-t` / `--truncate-paths` keeps a short install hint, for example
`.../_Cooking/FZ/Settings/...`. Truncated paths are output-only and are rejected
as input. GNU `ls` output is used for metadata and formatting, then decoded for
display. The wrapper has first-class flags for `-l`, `-a`, and `-la`; other GNU
`ls` flags can be passed as extra arguments and are forwarded to `ls` after the
asset path is resolved.

### `rerw read savefile`

Print values from a Ravenswatch `Profile_1.ob` save file. With no field flags it
prints all registered scalar fields plus talent picks. With field flags it
prints only those fields.

```bash
./tools/rerw read savefile --source rw/saves/proofs/geppetto/clean/Profile_1.ob
./tools/rerw read savefile --source rw/saves/proofs/geppetto/clean/Profile_1.ob --chapter
./tools/rerw read savefile --source rw/saves/proofs/geppetto/clean/Profile_1.ob --level
./tools/rerw read savefile --source rw/saves/proofs/geppetto/clean/Profile_1.ob --talents -v
```

Options:

```text
--source FILE  Save file to read.
--chapter      Print the chapter field only.
--level        Print the level field only.
--talents      Print the 5 talent picks and their tiers.
-v, --verbose  Print file size, CRC, and GUID-location details.
```

### `rerw write savefile`

Edit registered save fields, recompute CRC32, and write `Profile_1.ob` into the
destination directory. Edits are staged atomically: one read, all requested
writes, one CRC update, one output file.

```bash
./tools/rerw write savefile \
  --source rw/saves/proofs/geppetto/clean/Profile_1.ob \
  --dest /tmp/rerw-save-out \
  --chapter 1 \
  --level 3 \
  --force

./tools/rerw write savefile \
  --source rw/saves/proofs/geppetto/clean/Profile_1.ob \
  --dest /tmp/rerw-save-out \
  --talent-slot 1 \
  --talent-id "Twin Dummies" \
  --tier Rare \
  --force
```

Options:

```text
--source FILE                Source save file to edit.
--dest DIRECTORY             Destination directory; writes Profile_1.ob there.
--chapter INTEGER            Set chapter: 0=ch1, 1=ch2, 2=ch3, 3=epilogue.
--level INTEGER              Set in-run hero level.
--talent-slot INTEGER RANGE  Talent slot 1..5.
--talent-id TEXT             Talent alias/name or 32-hex-char GUID.
--tier TEXT                  Common/Rare/Epic/Legendary or 0..3. Slots 1..4 only.
-f, --force                  Overwrite existing destination Profile_1.ob.
-v, --verbose                Print file load, GUID, and CRC details.
```

Current save-write scope: `write savefile` supports chapter, level, and talent
edits only. Item/magical-object writes are not wired into the CLI yet: there is
no `--item-slot` / `--item-id` flag, no `item_record` field type in
`save-fields.yaml`, and no `lib/item_edit.py` implementation. See
[`magical-objects.md`](../key-findings/magical-objects.md) for the verified item
record format and edit primitives.

### `rerw swap savefile`

Install a chosen save as the active Ravenswatch `Profile_1.ob`.

```bash
./tools/rerw swap savefile --source /tmp/rerw-save-out/Profile_1.ob
./tools/rerw swap savefile --source /tmp/rerw-save-out/Profile_1.ob --dest /mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save
```

The destination defaults to `$RERW_SAVEGAME_DIR` when set, otherwise
`/mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save`. The command always
writes the filename `Profile_1.ob` and overwrites any existing file; back up the
active save first.

### `rerw interactive`

Start the `rerw` interactive REPL.

```bash
./tools/rerw interactive
```

The REPL exposes the current Click-backed helper commands plus a `swap-savefile`
sub-mode for repeated save swaps.

### `rerw game-assets harvest`

Group for asset harvesting operations. Currently a stub — subcommands pending.

### `rerw harvest`

Moved under `rerw game-assets harvest`.

## Cipher Status

Substitution cipher is mostly complete. Three positions still unknown (rare
characters): lowercase `j, q`; uppercase `X`. Unknown positions render as `#`
(uppercase) or `%` (lowercase) in `cipher` output.

## Library

Cipher functions are exposed for reuse:

```python
from lib.cipher import encipher, decipher, PLAIN, CIPHER
```

Used internally by the `cipher`, `decipher`, and `game-assets ls` commands.

## Source

`tools/rerw-src/` — see [coding standards](../../../docs/tools/coding-standards.md) for tool conventions.
