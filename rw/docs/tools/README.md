[← Back to docs](../README.md)

# Tools

Tools used for Ravenswatch RE work.

| Tool | Purpose |
|------|---------|
| [rerw](rerw.md) | Ravenswatch-specific RE operations |
| [hexsir](hexsir.md) | Generic binary probing |
| [mem-snapshot](mem-snapshot.md) | Windows-only live memory diff for finding runtime field addresses |
| [rs / rs-shim](rs.md) | Live trainer (Windows shim + WSL Click CLI) for reading/writing runtime stats |

`rerw` and `hexsir` live in `tools/` at the repo root. `mem-snapshot` and
`rs-shim` are standalone Windows scripts at `rw/scripts/windows/`. The `rs`
Click CLI lives in the repo at `tools/rs-src/`.
