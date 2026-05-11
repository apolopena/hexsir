[← Back to docs](../README.md)

# Tools

Tools used for Ravenswatch RE work.

| Tool | Purpose |
|------|---------|
| [rerw](rerw.md) | Ravenswatch-specific RE operations |
| [hexsir](hexsir.md) | Generic binary probing |
| [mem-snapshot](../workflow/frida.md#memory-analysis-full-process-snapdiff) | Windows-only live memory diff for finding runtime field addresses; full workflow at `rw/scripts/windows/mem_snapshot.py` and folded into `workflow/frida.md` §Memory analysis |
| [rs / rs-shim](rs.md) | Live trainer (Windows shim + WSL Click CLI) for reading/writing runtime stats |

`rerw` and `hexsir` live in `tools/` at the repo root. `mem-snapshot` and
`rs-shim` are standalone Windows scripts at `rw/scripts/windows/`. The `rs`
Click CLI lives in the repo at `tools/rs-src/`.
