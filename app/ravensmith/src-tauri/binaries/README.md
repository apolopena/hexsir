# Sidecar binaries

PyInstaller-bundled sidecars consumed by Tauri's `externalBin` mechanism.
Binaries themselves are gitignored — only this README and `.gitkeep` are
tracked.

## Naming

Files use Tauri's per-host target-triple suffix so the same `bundle.externalBin`
entry resolves to the host-native binary at build time:

```
binaries/
  rerw-x86_64-pc-windows-msvc.exe       # Windows (default + Superpowers)
  rerw-x86_64-unknown-linux-gnu         # Linux (default + Superpowers)
  frida-x86_64-pc-windows-msvc.exe      # Windows (Superpowers only)
  frida-x86_64-unknown-linux-gnu        # Linux (Superpowers only)
```

`tauri.conf.json` references the **basenames without the triple suffix**
(`binaries/rerw`, `binaries/frida`); Tauri resolves the host-appropriate
file at bundle time.

## Building

```bash
just ravensmith-build-rerw-sidecar       # rerw (PyInstaller from tools/rerw-src)
just ravensmith-build-frida-sidecar      # frida-tools (PyInstaller, Superpowers builds only)
```

Each script runs PyInstaller per-host (no cross-compile) and drops the
target-triple-named binary here. Re-run after any change to `tools/rerw-src/`,
any rerw dep bump, any change to `data/save-fields.yaml`, or any
`frida-tools` version bump.

## Why not committed

PyInstaller bundles are 10–50 MB each, host-specific, and rebuilt frequently.
Treating them as build artifacts (gitignored) keeps the repo small and
forces every developer to run the build script — which catches stale-bundle
classes of bugs that committing the artifact would mask.
