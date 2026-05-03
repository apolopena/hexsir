# Reference data

Tracked snapshots used by the rest of the project. Files here are not analysis prose; they're inputs that other tools read or that humans grep.

## Index

| File | Purpose |
|---|---|
| `tree-ciphered.txt` | The game's asset directory tree as `tree /A /F` produces it. Source of truth — game updates can change asset structure. |
| `tree-deciphered.txt` | The deciphered version of the tree (filenames passed through `rerw decipher`). Derived; regenerate after any tree-ciphered change. |
| `screenshots/` | In-game / debugger screenshots referenced by findings or per-save info. Add as needed; reference by relative path. |

## Regenerating the tree files

Generate `tree-ciphered.txt` from a Windows shell pointed at the game's asset root:

```
tree /A /F > tree-ciphered.txt
```

The `/A` flag forces ASCII line-drawing characters; without it, the box-drawing characters render inconsistently across editors.

Generate `tree-deciphered.txt` from the ciphered version:

```
rerw decipher --tree-file rw/ref/tree-ciphered.txt --out rw/ref/tree-deciphered.txt
```

Both files should be regenerated together after each game patch that touches asset names.

## Vocabulary

Terminology for talents, items, seeds, and indexing lives in [`../docs/terminology/README.md`](../docs/terminology/README.md).
