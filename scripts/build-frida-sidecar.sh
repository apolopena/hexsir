#!/usr/bin/env bash
# Build the Frida REPL PyInstaller sidecar for the current host triple
# and stage tools/frida/rw_lab.js as the bundled default Frida script.
#
# frida-tools is installed into a throwaway uv venv under .run/ so this
# script does not touch the dev's permanent Python environment. The Frida
# REPL only exists inside the frida-tools Python distribution; bundling
# ships a single self-contained executable with no _frida.pyd / _frida.so
# companion file requirement.
#
# --collect-all flags absorb the documented gotcha: prompt_toolkit + frida
# + frida_tools have data files / dynamic imports that PyInstaller's
# static analyzer misses. See PRP-7 §"caveats.md →
# PyInstaller-bundling frida-tools".

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

OUT_DIR="$REPO_ROOT/app/ravensmith/src-tauri/binaries"
RES_DIR="$REPO_ROOT/app/ravensmith/src-tauri/resources"
OUT_NAME="frida-${TRIPLE}${SUFFIX}"
WORK_DIR="$REPO_ROOT/.run/frida-sidecar-build"
SOURCE_SCRIPT="$REPO_ROOT/tools/frida/rw_lab.js"

if [ ! -f "$SOURCE_SCRIPT" ]; then
    echo "Bundled default Frida script not found: $SOURCE_SCRIPT" >&2
    exit 1
fi

# Throwaway venv keeps frida-tools out of any permanent dev environment.
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

uv venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

uv pip install 'frida-tools>=13' pyinstaller

# PyInstaller needs a script to bundle, not a console-script entry point.
# A two-line shim that calls frida_tools.repl:main is the minimum surface.
cat > frida_entry.py <<'PY'
from frida_tools.repl import main

if __name__ == "__main__":
    main()
PY

pyinstaller \
    --onefile \
    --name "frida" \
    --collect-all frida \
    --collect-all frida_tools \
    --collect-all prompt_toolkit \
    --collect-all pygments \
    --noconfirm \
    --clean \
    frida_entry.py

mkdir -p "$OUT_DIR" "$RES_DIR"
install -m 755 "dist/frida${SUFFIX}" "$OUT_DIR/$OUT_NAME"

# Stage rw_lab.js as the bundled default Frida script. The Superpowers
# overlay's bundle.resources references "resources/rw_lab.js" — a relative
# path under src-tauri/, so the staged copy must live exactly here.
install -m 644 "$SOURCE_SCRIPT" "$RES_DIR/rw_lab.js"

# Smoke test: --version exits cleanly without needing a target process.
"$OUT_DIR/$OUT_NAME" --version

echo "✓ frida sidecar: $OUT_DIR/$OUT_NAME"
echo "✓ bundled script: $RES_DIR/rw_lab.js"
