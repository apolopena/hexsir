#!/bin/bash
#
# Run test suites with flexible options
#
# Usage:
#   ./scripts/run-tests.sh              # all CLI tool tests
#   ./scripts/run-tests.sh -c           # all CLI tool tests (explicit)
#   ./scripts/run-tests.sh -c scafcli   # single tool tests
#   ./scripts/run-tests.sh -c shared-libs # shared lib tests
#   ./scripts/run-tests.sh --cli --list shared-libs  # print shared-lib dirs
#   ./scripts/run-tests.sh --cli --list all          # print all tool/shared-lib dirs
#   ./scripts/run-tests.sh -h           # show help
#
# Options:
#   -c, --cli [TARGET]  Run CLI tool tests (see below for valid targets)
#   -l, --list [TARGET] List CLI package dirs (requires -c/--cli; targets: shared-libs, tools, all, <tool-name>)
#   -h, --help          Show this help
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
RESET='\033[0m'

# CLI tools participating in shared CLI test runs
CLI_TOOLS=(
    "hexsir"
    "rerw"
    "scafcli"
)

# Defaults
RUN_CLI=false
LIST_MODE=false
CLI_TARGET=""

show_help() {
    echo "Run test suites with flexible options"
    echo ""
    echo "Usage:"
    echo "  ./scripts/run-tests.sh              # all CLI tool tests"
    echo "  ./scripts/run-tests.sh -c           # all CLI tool tests (explicit)"
    echo "  ./scripts/run-tests.sh -c scafcli   # single tool tests"
    echo "  ./scripts/run-tests.sh -c shared-libs # shared lib tests"
    echo "  ./scripts/run-tests.sh --cli --list shared-libs  # print shared-lib dirs"
    echo "  ./scripts/run-tests.sh --cli --list all          # print all tool/shared-lib dirs"
    echo ""
    echo "Options:"
    echo -n "  -c, --cli [TARGET]  Run CLI tool tests (targets: "
    printf '%s ' "${CLI_TOOLS[@]}"
    echo "shared-libs)"
    echo "  -l, --list [TARGET] List CLI package dirs (requires -c/--cli; targets: shared-libs, tools, all, <tool-name>)"
    echo "  -h, --help          Show this help"
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) show_help ;;
        --cli)
            RUN_CLI=true
            shift
            if [[ $# -gt 0 && "$1" != -* ]]; then
                CLI_TARGET="$1"
                shift
            fi
            ;;
        --list)
            LIST_MODE=true
            shift
            if [[ $# -gt 0 && "$1" != -* ]]; then
                CLI_TARGET="$1"
                shift
            fi
            ;;
        -*)
            flags="${1#-}"
            shift
            while [[ -n "$flags" ]]; do
                char="${flags:0:1}"
                flags="${flags:1}"
                case "$char" in
                    c)
                        RUN_CLI=true
                        if [[ -z "$flags" && $# -gt 0 && "$1" != -* ]]; then
                            CLI_TARGET="$1"
                            shift
                        fi
                        ;;
                    l)
                        LIST_MODE=true
                        if [[ -z "$flags" && $# -gt 0 && "$1" != -* ]]; then
                            CLI_TARGET="$1"
                            shift
                        fi
                        ;;
                    h) show_help ;;
                    *) echo "Unknown option: -$char"; show_help ;;
                esac
            done
            ;;
        *)
            echo "Unknown argument: $1"
            show_help
            ;;
    esac
done

# --list: print CLI package dirs and exit (sub-mode of -c/--cli)
if [ "$LIST_MODE" = true ]; then
    if [ "$RUN_CLI" != true ]; then
        echo "--list requires -c/--cli" >&2
        exit 2
    fi
    cd "$PROJECT_ROOT"
    case "$CLI_TARGET" in
        ""|all)
            for pyproject in tools/shared/*/pyproject.toml tools/*/pyproject.toml; do
                [ -f "$pyproject" ] || continue
                dirname "$pyproject"
            done
            ;;
        shared-libs)
            for pyproject in tools/shared/*/pyproject.toml; do
                [ -f "$pyproject" ] || continue
                dirname "$pyproject"
            done
            ;;
        tools)
            for pyproject in tools/*/pyproject.toml; do
                [ -f "$pyproject" ] || continue
                dirname "$pyproject"
            done
            ;;
        *)
            valid=false
            for t in "${CLI_TOOLS[@]}"; do
                [[ "$t" == "$CLI_TARGET" ]] && { valid=true; break; }
            done
            if [ "$valid" = true ]; then
                echo "tools/${CLI_TARGET}-src"
            else
                echo "Unknown --list target: $CLI_TARGET" >&2
                echo "Valid: $(printf '%s ' "${CLI_TOOLS[@]}")shared-libs tools all" >&2
                exit 1
            fi
            ;;
    esac
    exit 0
fi

# Default: run all CLI tests
if [ "$RUN_CLI" = false ]; then
    RUN_CLI=true
fi

# Track results
CLI_TOOL_NAMES=()
CLI_TOOL_RESULTS=()
CLI_TOOL_SUMMARIES=()

# Secure temp directory
TEMP_DIR=$(mktemp -d -p "${XDG_RUNTIME_DIR:-/tmp}" run-tests.XXXXXX)
chmod 700 "$TEMP_DIR"
trap "rm -rf '$TEMP_DIR'" EXIT

run_cli_tool_pytest() {
    local tool_dir="$1"
    local test_path="$2"
    shift 2
    local extra_args="$*"
    local log_file="$TEMP_DIR/output.log"
    local exit_file="$TEMP_DIR/exit_code"

    cd "$PROJECT_ROOT/tools/$tool_dir"
    script -q -c "PYTHONPATH=. .venv/bin/pytest $test_path $extra_args -v; echo \$? > $exit_file" "$log_file"
    LAST_RESULT=$(cat "$exit_file" 2>/dev/null || echo 1)
    LAST_SUMMARY=$(grep -oE '[0-9]+ passed|[0-9]+ failed|[0-9]+ error' "$log_file" 2>/dev/null | tr '\n' ', ' | sed 's/, $//')
    rm -f "$log_file" "$exit_file"
}

print_header() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${RESET}"
    echo -e " ${BOLD}$1${RESET}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${RESET}"
    echo ""
}

print_subheader() {
    echo ""
    echo -e "${CYAN}── $1 ──${RESET}"
    echo ""
}

run_cli_tool() {
    local display_name="$1"
    local tool_dir="$2"
    local test_path="$3"

    print_subheader "$display_name"
    run_cli_tool_pytest "$tool_dir" "$test_path"
    CLI_TOOL_NAMES+=("$display_name")
    CLI_TOOL_RESULTS+=("$LAST_RESULT")
    CLI_TOOL_SUMMARIES+=("$LAST_SUMMARY")
}

validate_cli_tools() {
    local name
    local seen=""
    for name in "${CLI_TOOLS[@]}"; do
        if [[ -z "$name" ]]; then
            echo -e "${RED}Empty CLI tool name in CLI_TOOLS${RESET}"
            exit 1
        fi
        if [[ ! "$name" =~ ^[a-z]+$ ]]; then
            echo -e "${RED}Invalid CLI tool name in CLI_TOOLS: $name${RESET}"
            exit 1
        fi
        if [[ " $seen " == *" $name "* ]]; then
            echo -e "${RED}Duplicate CLI tool name in CLI_TOOLS: $name${RESET}"
            exit 1
        fi
        seen="$seen $name"
    done
}

cli_target_exists() {
    local target="$1"
    local name
    for name in "${CLI_TOOLS[@]}"; do
        if [[ "$name" == "$target" ]]; then
            return 0
        fi
    done
    return 1
}

run_registered_cli_tools() {
    local target="${1:-}"
    local name
    for name in "${CLI_TOOLS[@]}"; do
        if [[ -n "$target" && "$name" != "$target" ]]; then
            continue
        fi
        run_cli_tool "$name" "${name}-src" "tests/"
    done
}

# ============================================================================
# CLI TOOL TESTS
# ============================================================================
if [ "$RUN_CLI" = true ]; then
    validate_cli_tools

    if [[ -n "$CLI_TARGET" && "$CLI_TARGET" != "shared-libs" ]] && ! cli_target_exists "$CLI_TARGET"; then
        echo -e "${RED}Unknown CLI target: $CLI_TARGET${RESET}"
        echo "Valid targets: $(printf '%s ' "${CLI_TOOLS[@]}")shared-libs"
        exit 1
    fi

    print_header "CLI TOOLS (tools/)"

    if [[ -z "$CLI_TARGET" || "$CLI_TARGET" == "shared-libs" ]]; then
        for pyproject in "$PROJECT_ROOT"/tools/shared/*/pyproject.toml; do
            [ -f "$pyproject" ] || continue
            lib_name=$(basename "$(dirname "$pyproject")")
            run_cli_tool "$lib_name" "shared/$lib_name" "tests/"
        done
    fi

    if [[ -z "$CLI_TARGET" ]]; then
        run_registered_cli_tools
    elif [[ "$CLI_TARGET" != "shared-libs" ]]; then
        run_registered_cli_tools "$CLI_TARGET"
    fi
fi

# ============================================================================
# SUMMARY
# ============================================================================
print_header "SUMMARY"

FAILED=false

print_result() {
    local name="$1"
    local result="$2"
    local summary="$3"

    if [ "$result" -eq 0 ]; then
        echo -e "  ${GREEN}✓${RESET} $name: ${GREEN}$summary${RESET}"
    elif [ "$result" -gt 0 ]; then
        echo -e "  ${RED}✗${RESET} $name: ${RED}$summary${RESET}"
        FAILED=true
    fi
}

if [ ${#CLI_TOOL_NAMES[@]} -gt 0 ]; then
    echo -e "${BOLD}CLI tools:${RESET}"
    for idx in "${!CLI_TOOL_NAMES[@]}"; do
        print_result "${CLI_TOOL_NAMES[$idx]}" "${CLI_TOOL_RESULTS[$idx]}" "${CLI_TOOL_SUMMARIES[$idx]}"
    done
    echo ""
fi

if [ "$FAILED" = true ]; then
    echo -e "${RED}Some tests failed${RESET}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${RESET}"
    exit 0
fi
