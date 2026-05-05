# Tauri v2 — CLI Reference (relevant flags & env vars)

> **Source:** https://v2.tauri.app/reference/cli/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify how to pass Cargo features and config overlays at build/dev time. Confirm or refute `TAURI_FEATURES` env var.

## Cargo Features

Both `tauri dev` and `tauri build` accept:

```
-f, --features [<FEATURES>...]   List of cargo features to activate
                                  (space or comma separated for build)
```

Examples:

```bash
tauri dev -f feature1,feature2
tauri build -f feature1,feature2
tauri bundle -f feature1,feature2
```

## Config Overlay

```
-c, --config <CONFIG>   JSON strings or paths to JSON, JSON5 or TOML files
                        to merge with the default configuration file
```

Accepts either:

- a JSON string literal (inline overlay), or
- a path to a `.json` / `.json5` / `.toml` file.

The file/string is merged onto the base `tauri.conf.json` at build/dev time. **Platform-specific files** (`tauri.linux.conf.json` etc.) are still merged automatically; `-c` adds another layer on top.

## Documented Environment Variables

| Variable | Purpose |
|---|---|
| `CI=true` | Skip prompting for values |
| `TAURI_CLI_NO_DEV_SERVER_WAIT=` | Skip waiting for frontend dev server |
| `TAURI_CLI_PORT=` | Specify port for built-in dev server (default 1430) |
| `TAURI_DEV_HOST=` | Set during mobile dev when public network address is used |
| `TAURI_DEV_ROOT_CERTIFICATE_PATH=` | Path to certificate for HTTPS dev server |

## `TAURI_FEATURES` Environment Variable

> "No `TAURI_FEATURES` environment variable is documented in the official CLI reference."

**Verified absent.** Use the `-f`/`--features` CLI flag instead.

## Notes for PRP-7

- The wrapper script (`scripts/superpowers-env.sh`) cannot rely on `TAURI_FEATURES` env var; the `just` recipes must explicitly pass `-f superpowers` to `tauri build`/`tauri dev`.
- Same for config overlays: explicit `-c src-tauri/tauri.overlay.superpowers.json` instead of `TAURI_CONFIG` env.
- The wrapper still handles `VITE_SUPERPOWERS=true` for the Vite side (Vite reads its own env vars).

Recommended invocation pattern:

```just
ravensmith-build-superpowers: ravensmith-init ravensmith-build-rerw-sidecar ravensmith-build-frida-sidecar
    cd app/ravensmith && SUPERPOWERS=true bun run tauri build -- \
        -f superpowers \
        -c src-tauri/tauri.overlay.superpowers.json
```

The `SUPERPOWERS=true` env var is consumed by the wrapper to set `VITE_SUPERPOWERS=true`; Cargo features and config overlay are passed via explicit CLI flags.
