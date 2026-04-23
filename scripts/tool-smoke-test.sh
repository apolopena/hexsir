#!/bin/bash
#
# Smoke test for a scaffolded CLI tool.
# Verifies install, --version, --help, then uninstalls.
#
# Usage: bash scripts/tool-smoke-test.sh <tool-name>
#

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

if [[ $# -ne 1 ]]; then
    echo "Usage: bash scripts/tool-smoke-test.sh <tool-name>"
    exit 1
fi

NAME="$1"
FAILED=false

# Always uninstall on exit
cleanup() {
    just tool-uninstall "$NAME" 2>/dev/null || true
}
trap cleanup EXIT

pass() { echo -e "  ${GREEN}✓${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; FAILED=true; }

echo -e "${BOLD}Smoke test: $NAME${RESET}"
echo ""

# Clean up stale install if present
if command -v "$NAME" &>/dev/null; then
    echo "Removing stale install..."
    just tool-uninstall "$NAME" 2>/dev/null || true
fi

# Install
echo "Installing..."
if just tool-install "$NAME" &>/dev/null; then
    pass "install"
else
    fail "install"
    echo -e "${RED}Cannot continue without install${RESET}"
    exit 1
fi

# --version
if output=$("$NAME" --version 2>&1) && echo "$output" | grep -qi "$NAME"; then
    pass "--version (${output})"
else
    fail "--version"
fi

# --help
if "$NAME" --help &>/dev/null; then
    pass "--help"
else
    fail "--help"
fi

echo ""
if [ "$FAILED" = true ]; then
    echo -e "${RED}Smoke test failed${RESET}"
    exit 1
else
    echo -e "${GREEN}Smoke test passed${RESET}"
fi
