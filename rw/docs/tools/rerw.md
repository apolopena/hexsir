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

### `rerw game-assets ls <path>`

List cooked game assets through GNU `ls`. The wrapper resolves decoded paths to
their ciphered on-disk equivalent, invokes `ls` on the real filesystem path, and
then deciphers path/name text in the `ls` output. Cooked-relative paths are
resolved against the default Ravenswatch `_Cooking` directory. The input may be
decoded or ciphered. If the input is a full cooked path, output entries are full
paths too.

```bash
./tools/rerw game-assets ls "3D/Scenery/"
./tools/rerw game-assets ls "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/3D/Scenery/"
```

Useful flags:

```bash
./tools/rerw game-assets ls --full "EntitySettings/Heroes/"
./tools/rerw game-assets ls --cooked-relative "/mnt/d/.../DarkTalesResources/_Cooking/FZ/Settings/"
./tools/rerw game-assets ls -t "/mnt/d/.../DarkTalesResources/_Cooking/FZ/Settings/"
./tools/rerw game-assets ls --raw "EntitySettings/Heroes/"
./tools/rerw game-assets ls --ciphered "MzidisFqiidzyv/Aqurqv/"
./tools/rerw game-assets ls -la --cooked-relative "/mnt/d/.../DarkTalesResources/_Cooking/FZ/Settings/"
```

`--cooked-relative` strips the install prefix through `_Cooking/`, so results
start at the cooked directory segment such as `FZ/Settings/...`.
`-t` / `--truncate-paths` keeps a short install hint, for example
`/mnt/d/.../DarkTalesResources/_Cooking/FZ/Settings/...`. Truncated paths are
output-only and are rejected as input. GNU `ls` output is used for metadata and
formatting, then decoded for display.

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

Used internally by the `cipher` and `decipher` commands and available for future commands like `harvest`.

## Source

`tools/rerw-src/` — see [coding standards](../../../docs/tools/coding-standards.md) for tool conventions.
