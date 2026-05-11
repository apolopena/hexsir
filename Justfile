# Task Runner — CLI Tool Workflows
# Install: cargo install just  OR  brew install just  OR  sudo apt install just

set shell := ["bash", "-euo", "pipefail", "-c"]

# Show available recipes
default:
    @just --list

# --- Tool Lifecycle ---

# Create a new CLI tool (scaffold + venv + deps)
tool-new *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{args}}" ]; then
        read -p "Tool name: " name
        read -p "Initial command: " command
        backend=""
        if [ -d "tools/shared/backend-lib" ]; then
            read -p "Include backend? [y/N]: " backend
        fi
        read -p "Include REPL? [y/N]: " repl
        flags=""
        [[ "$backend" =~ ^[yY] ]] && flags="$flags --include-backend"
        [[ "$repl" =~ ^[yY] ]] && flags="$flags --include-repl"
        ./tools/scafcli tool new "$name" "$command" $flags
    else
        ./tools/scafcli tool new {{args}}
    fi

# Initialize a tool's venv (fresh clone or dep change)
tool-init name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    echo "Initializing tools/$dir..."
    cd "tools/$dir" && uv sync --group dev
    echo "✓ tools/$dir ready"

# Initialize ALL tool venvs (fresh clone bootstrap)
tool-init-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        echo "Initializing $dir..."
        (cd "$dir" && uv sync --group dev)
    done
    echo "✓ All tool venvs ready"

# --- Tool Testing ---

# Run a specific tool's tests
tool-test name:
    ./scripts/run-tests.sh -c "{{name}}"

# Run all CLI tool tests
tool-test-all:
    ./scripts/run-tests.sh -c

# --- Tool Coverage ---

# Show test coverage for a tool
tool-coverage name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    cd "tools/$dir"
    output=$(uv run --with pytest-cov pytest tests/ --cov=. --cov-report=term-missing 2>&1) || true
    echo "$output"
    if echo "$output" | grep -q "skipped"; then
        echo ""
        echo -e "\033[2mNote: some tests were skipped. Coverage shown is lower than actual.\033[0m"
    fi

# Show test coverage for all tools and shared libraries
tool-coverage-all:
    #!/usr/bin/env bash
    set -euo pipefail
    tmpfile=$(mktemp)
    had_skips=false
    had_bumps=false
    trap "rm -f '$tmpfile'" EXIT
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if [ ! -d "$dir/.venv" ]; then continue; fi
        name=$(basename "$dir")
        echo "=== $name ==="
        output=$( (cd "$dir" && uv run --with pytest-cov pytest tests/ --color=yes --cov=. --cov-report=term-missing) 2>&1) || true
        echo "$output"
        # Check for bump_rating_threshold flag in pyproject.toml
        bump="false"
        if grep -q "^bump_rating_threshold = true" "$dir/pyproject.toml" 2>/dev/null; then
            bump="true"
            had_bumps=true
        fi
        echo "$output" | grep "^TOTAL" | awk -v n="$name" -v b="$bump" '{printf "%s %s %s\n", n, $NF, b}' >> "$tmpfile"
        if echo "$output" | grep -q "skipped"; then
            had_skips=true
        fi
        echo ""
    done
    BRIGHT_GREEN=$'\033[38;5;46m'
    GREEN=$'\033[38;5;28m'
    YELLOW=$'\033[38;5;142m'
    RED=$'\033[38;5;160m'
    MAGENTA=$'\033[0;35m'
    BOLD=$'\033[1m'
    NC=$'\033[0m'
    colorize() {
        # $1 = number, $2 = bump flag (true|false)
        local num=$1
        local bumped=$2
        if [ "$bumped" = "true" ]; then
            # Bumped bands: -10 across the board to account for integration code
            if [ "$num" -ge 80 ]; then
                color=$BRIGHT_GREEN label="exemplary"
            elif [ "$num" -ge 65 ]; then
                color=$GREEN label="commendable"
            elif [ "$num" -ge 50 ]; then
                color=$YELLOW label="acceptable"
            else
                color=$RED label="problematic"
            fi
        else
            if [ "$num" -ge 90 ]; then
                color=$BRIGHT_GREEN label="exemplary"
            elif [ "$num" -ge 75 ]; then
                color=$GREEN label="commendable"
            elif [ "$num" -ge 60 ]; then
                color=$YELLOW label="acceptable"
            else
                color=$RED label="problematic"
            fi
        fi
    }
    echo ""
    printf "%s" "${MAGENTA}${BOLD}"
    printf "%*s" $(( (48 + 23) / 2 )) "=== Coverage Summary ==="
    printf "%s\n" "${NC}"
    echo ""
    printf "%-24s %7s   %s\n" "Package" "Coverage" "Rating"
    printf -- "%-24s %7s   %s\n" "------------------------" "--------" "---------------"
    sum=0
    count=0
    while read -r name pct bump; do
        num=${pct%\%}
        sum=$((sum + num))
        count=$((count + 1))
        colorize "$num" "$bump"
        if [ "$bump" = "true" ]; then
            printf "%-24s %6s   ${color}(%s)${NC}*\n" "$name" "$pct" "$label"
        else
            printf "%-24s %6s   ${color}(%s)${NC}\n" "$name" "$pct" "$label"
        fi
    done < "$tmpfile"
    if [ "$count" -gt 0 ]; then
        avg=$((sum / count))
        colorize "$avg" "false"
        printf -- "%-24s %7s   %s\n" "------------------------" "--------" "---------------"
        printf "${BOLD}%-24s${NC} ${color}%6s${NC}   ${color}(%s)${NC}\n" "TOTAL (average)" "${avg}%" "$label"
    fi
    if [ "$had_bumps" = true ]; then
        echo ""
        echo -e "* \033[2mAdjusted for integration code that can't be reasonably tested.\033[0m"
    fi
    if [ "$had_skips" = true ]; then
        echo ""
        echo -e "\033[2mNote: some tests were skipped. Coverage shown is lower than actual.\033[0m"
    fi
    echo ""

# --- Tool Lint ---

# Lint a single tool (format + check)
tool-lint name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    cd "tools/$dir" && .venv/bin/ruff format . && .venv/bin/ruff check .

# Lint all tools (auto-discovers via pyproject.toml, skips tools without .venv)
tool-lint-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if [ ! -d "$dir/.venv" ]; then continue; fi
        echo "Linting $dir..."
        (cd "$dir" && .venv/bin/ruff format . && .venv/bin/ruff check .)
    done
    echo "✓ All tools pass lint"

# --- Environment Sync ---

# Update a tool's environment after pyproject.toml changes
tool-sync name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    cd "tools/$dir" && uv sync --group dev
    echo "✓ tools/$dir environment updated"

# Update all tool environments after pyproject.toml changes (shared libs first)
tool-sync-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if [ ! -d "$dir/.venv" ]; then continue; fi
        echo "Syncing $dir..."
        (cd "$dir" && uv sync --group dev)
    done
    echo "✓ All environments updated"

# --- Tool Discovery ---

# List tool names
tool-list:
    @source scripts/tool-info.sh && list_names

# Show local and installed versions for each tool
tool-versions:
    @source scripts/tool-info.sh && list_versions

# --- Tool Packaging ---

# Build a tool wheel (into tools/<dir>/dist/)
tool-build name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    cd "tools/$dir" && uv build
    echo "✓ Built tools/$dir/dist/"

# Build all installable tools
tool-build-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if ! grep -q '\[project\.scripts\]' "$dir/pyproject.toml" 2>/dev/null; then continue; fi
        echo "Building $(basename "$dir")..."
        (cd "$dir" && uv build)
    done
    echo "✓ All wheels in tools/*/dist/"

# Install a tool as a standalone CLI on PATH
tool-install name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    uv tool install "./tools/$dir" --force
    echo "✓ {{name}} installed"

# Install all installable tools
tool-install-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if ! grep -q '\[project\.scripts\]' "$dir/pyproject.toml" 2>/dev/null; then continue; fi
        echo "Installing $(basename "$dir")..."
        uv tool install "./$dir" --force
    done
    echo "✓ All tools installed"

# Uninstall a tool's global package
tool-uninstall name:
    uv tool uninstall "{{name}}-src"

# Uninstall all tool packages
tool-uninstall-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for dir in $(scripts/run-tests.sh --cli --list all); do
        if ! grep -q '\[project\.scripts\]' "$dir/pyproject.toml" 2>/dev/null; then continue; fi
        pkg=$(python3 -c "import tomllib; print(tomllib.load(open('$dir/pyproject.toml','rb'))['project']['name'])")
        echo "Uninstalling $pkg..."
        uv tool uninstall "$pkg" 2>/dev/null || true
    done
    echo "✓ All tools uninstalled"

# Rebuild + reinstall a tool after version bump
tool-rebuild name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir=$(just _get-tool-src-dir "{{name}}")
    uv tool install "./tools/$dir" --force
    echo "✓ $(./tools/{{name}} --version 2>&1)"

# Smoke test a tool (install, --version, --help, uninstall)
tool-smoke-test name:
    bash scripts/tool-smoke-test.sh {{name}}

# --- Internal ---

# Resolve a tool name to its source directory
_get-tool-src-dir name:
    #!/usr/bin/env bash
    if [ -d "tools/{{name}}-src" ]; then
        echo "{{name}}-src"
    elif [ -d "tools/shared/{{name}}" ]; then
        echo "shared/{{name}}"
    else
        echo "Unknown tool: {{name}}" >&2
        exit 1
    fi
