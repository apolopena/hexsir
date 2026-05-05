# Vendored Documentation Manifest

This directory holds documentation pulled from upstream sources to ground PRP
proposals and reduce reliance on unverified claims. Each pull records the
source URL, the timestamp at pull time (UTC), and a sha256 of the local file.

The pulled docs are **summaries** produced by the WebFetch tool, not raw HTML.
Where claims are load-bearing for a PRP, the relevant source URL is preserved
so the original can be re-fetched at any time to verify.

## Layout

```text
.ai/docs/
  MANIFEST.md           # this file
  tauri-v2/             # Tauri v2 documentation
  bun/                  # Bun-specific docs (lockfile, etc.)
  rw/                   # pre-existing Ravenswatch RE notes (not part of this pull)
```

## Pull batches

### Batch 2026-05-04 — PRP-7 verification pull

Triggered by PRP-7 peer review. Goal: verify version pins and Tauri v2
mechanism claims (`TAURI_CONFIG`, `TAURI_FEATURES`, capability auto-load
behavior, config overlays, sidecar capability syntax).

| File | Source URL | Pulled (UTC) | sha256 |
|---|---|---|---|
| `tauri-v2/sidecar.md` | https://v2.tauri.app/develop/sidecar/ | 2026-05-04T15:05Z | `4f27228852ece261ef999236c2b708d9553f2e029569bad4a25472c291b01210` |
| `tauri-v2/capabilities.md` | https://v2.tauri.app/security/capabilities/ | 2026-05-04T15:05Z | `bc249ae60715760dc60a421118a3e749959c2a06747880b138d38a346f9dbb7c` |
| `tauri-v2/config.md` | https://v2.tauri.app/reference/config/ | 2026-05-04T15:05Z | `3504f6cdf7b9a92e3ec9eda99da1a14c97a9d181e851937d2442fe3d64d89577` |
| `tauri-v2/cli.md` | https://v2.tauri.app/reference/cli/ | 2026-05-04T15:05Z | `4ddc185a9158782724de22ca189fe8d3bd0901adf448b31f99637a1b55c14e2e` |
| `tauri-v2/plugin-shell.md` | https://v2.tauri.app/plugin/shell/ | 2026-05-04T15:05Z | `0b5e8071222322f14d5722eaaad1f43f6684cea175a48c044c748bf18dec96f4` |
| `tauri-v2/plugin-dialog.md` | https://v2.tauri.app/plugin/dialog/ | 2026-05-04T15:05Z | `c7972e93a300f004206d13093eac121a4e3f98a4c52ee96b6031b95d786a7039` |
| `bun/lockfile.md` | https://bun.sh/docs/install/lockfile | 2026-05-04T15:05Z | `5c4083b015362a959a4bd7a4a5f7b4113ad13003a686f68d2b610108d8dd5cbd` |

### Batch findings (PRP-7 corrections)

- ❌ **`TAURI_CONFIG` env var does not exist.** PRP-7's overlay-via-env-var
  mechanism is invalid. Use the `-c`/`--config` CLI flag instead.
- ❌ **`TAURI_FEATURES` env var does not exist.** Use the `-f`/`--features`
  CLI flag.
- ⚠️ **`tauri.<flavor>.conf.json` auto-merge is platform-only.** Flavor names
  are restricted to `linux`, `windows`, `macos`, `ios`, `android`. Custom
  names (e.g., `tauri.superpowers.conf.json`) are not picked up. Use the
  `-c` flag to merge user-defined overlays.
- ⚠️ **Capabilities in `src-tauri/capabilities/` always auto-load.** A
  `superpowers.json` file there would be active in default builds. Must
  place outside that directory or define inline in the overlay.
- ✅ **Sidecar capability JSON syntax confirmed** (see `tauri-v2/sidecar.md`):
  `{"identifier": "shell:allow-execute", "allow": [{"name": "binaries/<n>",
  "sidecar": true}]}`.
- ✅ **`bun.lock` is the v1.2+ default**, replacing binary `bun.lockb`. PRP-7
  should pin recent bun (verified latest 1.3.13) and accept `bun.lock`.

### Version verification (npm view / cargo search, 2026-05-04)

NPM packages, ✅ = matches PRP-5 pin, ✏️ = updated:

| Package | PRP-5 / earlier guess | Verified latest | Status |
|---|---|---|---|
| `@tauri-apps/api` | 2.11.0 | 2.11.0 | ✅ |
| `@tauri-apps/cli` | 2.11.0 | 2.11.0 | ✅ |
| `@tauri-apps/plugin-dialog` | 2.7.1 | 2.7.1 | ✅ |
| `@tauri-apps/plugin-shell` | 2.3.1 (guess) | **2.3.5** | ✏️ |
| `vue` | 3.5.33 | 3.5.33 | ✅ |
| `vue-router` | 4.5.1 (guess) | **5.0.6** | ✏️ |
| `vite` | 8.0.10 | 8.0.10 | ✅ |
| `typescript` | 5.6.3 (guess) | **6.0.3** | ✏️ |
| `vue-tsc` | 2.1.10 (guess) | **3.2.8** | ✏️ |
| `@vitejs/plugin-vue` | 6.0.6 | 6.0.6 | ✅ |
| `tailwindcss` | 4.2.4 | 4.2.4 | ✅ |
| `@tailwindcss/vite` | 4.2.4 | 4.2.4 | ✅ |
| `@xterm/xterm` | 6.0.0 | 6.0.0 | ✅ |
| `@xterm/addon-fit` | 0.11.0 | 0.11.0 | ✅ |
| `create-tauri-app` | 4.6.2 | 4.6.2 | ✅ |
| `bun` | 1.1.38 (guess) | **1.3.13** | ✏️ |

Cargo crates:

| Crate | PRP-7 earlier | Verified latest | Status |
|---|---|---|---|
| `tauri` | 2.11.0 | 2.11.0 | ✅ |
| `tauri-build` | 2.6.0 | 2.6.0 | ✅ |
| `tauri-plugin-dialog` | 2.7.1 | 2.7.1 | ✅ |
| `tauri-plugin-shell` | 2.7.0 (guess) | **2.3.5** | ✏️ |
| `portable-pty` | 0.9.0 | 0.9.0 | ✅ |

## Re-pull policy

These docs drift over time. Before relying on a vendored doc:

1. Check the **Pulled (UTC)** column. If older than ~30 days for active
   reference work, re-pull and update the row.
2. If the upstream URL changes, leave the old file with a note and add a new
   row.
3. Manifest entries are immutable except for sha256/timestamp updates on
   re-pull. Do not edit the source URL on an existing row — add a new row.

## Tooling

The pulls use the `WebFetch` tool, which produces summaries (not raw HTML).
For raw upstream content, fetch the URL directly with `curl`/`wget`.
