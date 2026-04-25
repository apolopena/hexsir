[← Back to tools](README.md)

# rerw

Ravenswatch-specific RE tool.

## Commands

### `rerw cipher <text>`

Encode plaintext to a ciphered filename.

```bash
./tools/rerw cipher "Geppetto"
# → Kqjjqiir
```

### `rerw decipher <text>`

Decode a ciphered filename to plaintext.

```bash
./tools/rerw decipher "Kqjjqiir"
# → Geppetto
```

### `rerw harvest`

Group for asset harvesting operations. Currently a stub — subcommands pending.

## Cipher Status

Substitution cipher is mostly complete. Six positions still unknown (rare characters): lowercase `j, q`; uppercase `O, S, Y, Z`. Unknown positions render as `#` (uppercase) or `%` (lowercase) in `cipher` output.

## Library

Cipher functions are exposed for reuse:

```python
from lib.cipher import encipher, decipher, PLAIN, CIPHER
```

Used internally by the `cipher` and `decipher` commands and available for future commands like `harvest`.

## Source

`tools/rerw-src/` — see [coding standards](../../../docs/tools/coding-standards.md) for tool conventions.
