#!/usr/bin/env bash
# Build the rerw PyInstaller sidecar for the current host triple and drop
# it into app/ravensmith/src-tauri/binaries/. PyInstaller cannot
# cross-compile, so the host that runs this script *is* the bundle target.
#
# Workspace-editable shared libs (display-lib, repl-lib, tree-lib) live
# under tools/shared/ and are PyInstaller-invisible without --collect-all.
# See PRP-7 §"caveats.md → PyInstaller workspace-editable deps".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

case "$(uname -s)" in
    Linux*)
        TRIPLE="x86_64-unknown-linux-gnu"
        SUFFIX=""
        ;;
    MINGW*|MSYS*|CYGWIN*)
        TRIPLE="x86_64-pc-windows-msvc"
        SUFFIX=".exe"
        ;;
    *)
        echo "Unsupported host: $(uname -s)" >&2
        exit 1
        ;;
esac

RERW_SRC="$REPO_ROOT/tools/rerw-src"
OUT_DIR="$REPO_ROOT/app/ravensmith/src-tauri/binaries"
OUT_NAME="rerw-${TRIPLE}${SUFFIX}"
PYINSTALLER="$RERW_SRC/.venv/bin/pyinstaller"

if [ ! -x "$PYINSTALLER" ]; then
    echo "PyInstaller not found at $PYINSTALLER" >&2
    echo "Run: cd tools/rerw-src && uv sync --group dev" >&2
    exit 1
fi

cd "$RERW_SRC"

# --add-data data:data ships data/save-fields.yaml + data/heroes/ + the
# magical-/powerup-items YAML so lib.save_fields.load_fields() resolves at
# runtime inside the bundle.
"$PYINSTALLER" \
    --onefile \
    --name "rerw" \
    --add-data "data:data" \
    --collect-all display_lib \
    --collect-all repl_lib \
    --collect-all tree_lib \
    --collect-all prompt_toolkit \
    --copy-metadata rerw-src \
    --noconfirm \
    --clean \
    cli.py

mkdir -p "$OUT_DIR"
# install -m 755 forces executable permissions on the destination, which cp
# would inherit from a previously-staged 0-byte stub or stale prior bundle.
install -m 755 "dist/rerw${SUFFIX}" "$OUT_DIR/$OUT_NAME"

# Smoke test the bundled binary answers --version.
"$OUT_DIR/$OUT_NAME" --version

echo "✓ rerw sidecar: $OUT_DIR/$OUT_NAME"
