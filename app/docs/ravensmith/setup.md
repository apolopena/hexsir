# Ravensmith — Setup

**Scope.** Host prerequisites for building and running the Ravensmith
**Tauri app** (`app/ravensmith/`). Required only when working on the
desktop app — not needed for `rerw` CLI work, Ravenswatch
reverse-engineering (Ghidra / WinDbg / Frida), or any other tool in this
repo. The repo's general developer setup is in [`docs/README.md`](../../../docs/README.md);
this doc layers app-specific dependencies on top of that.

This is the **Phase 1** prereq layer (toolchains + system libs); the app
shell, Tauri config, and sidecar pipelines come from PRP-7's
implementation steps.

## Void Linux

Verified on Void glibc x86_64, kernel 6.6 (WSL2), 2026-05-05.

### Required versions

| Tool | Floor | Notes |
|---|---|---|
| Rust (rustc + cargo) | 1.77.2 | Tauri 2.11.0's `rust-version`. Installed via rustup; PATH lives at `~/.cargo/bin`. |
| `cargo-bloat` | any recent | Acceptance gate for default-build "no `portable-pty`" assertion. |
| bun | 1.3.13 | `packageManager: bun@1.3.13` in `app/ravensmith/package.json`. |
| just | 1.36.0+ | Recipe runner. Void package: `just`. |
| uv | repo-default | Drives `tools/rerw-src` and the sidecar PyInstaller venv. |
| PyInstaller | 6.10–6.x | Dev dep of `tools/rerw-src` only — do not install host-globally. |

### Install

```bash
# 1. Rust toolchain (per-user; ~/.cargo, ~/.rustup)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- \
    -y --default-toolchain stable --profile default
. "$HOME/.cargo/env"               # current shell only — rustup edits ~/.zshrc for new shells

# 2. cargo-bloat
cargo install cargo-bloat

# 3. Void system libs (Tauri webview + AppImage tooling)
sudo xbps-install -Su
sudo xbps-install -S libwebkit2gtk41-devel libayatana-appindicator-devel \
    librsvg-devel openssl-devel base-devel xdotool-devel xdg-utils \
    curl wget file fuse fuse3

# 4. PyInstaller in the rerw venv (no host-global install)
cd tools/rerw-src
uv add --group dev 'pyinstaller>=6.10,<7'
.venv/bin/pyinstaller --version
```

### Void package map

Names diverge from the Debian/Arch/Fedora lists in Tauri's official
prereqs page. Confirmed against `xq-api.voidlinux.org` on 2026-05-05:

| Tauri prereq (Debian/Fedora) | Void package |
|---|---|
| `libwebkit2gtk-4.1-dev` / `webkit2gtk4.1-devel` | `libwebkit2gtk41-devel` |
| `libayatana-appindicator3-dev` | `libayatana-appindicator-devel` (GTK3 build; the `-glib-devel` 2.0.x is the newer GLib2 variant — do not use it for Tauri 2) |
| `librsvg2-dev` / `librsvg2-devel` | `librsvg-devel` |
| `libssl-dev` | `openssl-devel` |
| `build-essential` / `c-development` | `base-devel` |
| `libxdo-dev` / `libxdo-devel` | `xdotool-devel` |
| `xdg-utils` | `xdg-utils` |
| AppImage runtime | `fuse` + `fuse3` (older AppImages need libfuse2-equivalent, newer ones need fuse3) |

### Verify

```bash
rustc --version          # >= 1.77.2
cargo bloat --version
bun --version            # 1.3.13
just --version
uv --version
tools/rerw-src/.venv/bin/pyinstaller --version
```

All six should answer cleanly. If any `xbps-install` line complains, query
the live name with `xbps-query -Rs <keyword>` — the `-devel` suffix
convention is consistent in Void.

### WSL2 caveat

WSLg (Windows 11 / recent Windows 10) provides the GUI surface — `just
ravensmith-dev` opens a window via WSLg automatically. Older WSL builds
without WSLg need an upgrade, not a workaround.

FUSE on WSL2 is not preinstalled by default; `fuse` + `fuse3` packages
above cover both AppImage execution and AppImage **build** (the bundler
touches FUSE during packaging, not just at runtime).
