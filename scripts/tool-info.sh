#!/usr/bin/env bash
# Tool discovery — source this file and call individual functions.
# Do not execute directly.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/../tools" && pwd)"

# List tool wrapper names (executable non-directory files in tools/)
list_names() {
    for f in "$TOOLS_DIR"/*; do
        [ -f "$f" ] && [ -x "$f" ] && basename "$f"
    done
    return 0
}

# Show local and installed versions for each tool
list_versions() {
    for name in $(list_names); do
        local_ver=$("$TOOLS_DIR/$name" --version 2>&1 || echo "error")
        if command -v "$name" &>/dev/null; then
            installed_ver=$("$name" --version 2>&1 || echo "error")
        else
            installed_ver="not installed"
        fi
        printf "%-12s  local: %-24s  global: %s\n" "$name" "$local_ver" "$installed_ver"
    done
}
