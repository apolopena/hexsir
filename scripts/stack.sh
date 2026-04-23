#!/bin/bash
# Stack management — start, stop, and check services
# Usage: ./scripts/stack.sh [up|down|restart|status]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_DIR="$PROJECT_ROOT/.run"
PID_FILE="$RUN_DIR/backend.pid"

# Colors (256-color, matches project standard)
RED='\033[38;5;160m'
GREEN='\033[38;5;34m'
YELLOW='\033[38;5;142m'
BLUE='\033[38;5;25m'
CYAN='\033[38;5;73m'
LIGHT_CYAN='\033[38;5;75m'
NC='\033[0m'

BACKEND_DIR="$PROJECT_ROOT/example-backend"
BACKEND_PYTHON="$BACKEND_DIR/tests/.venv/bin/python"
PORT=18765
URL="http://127.0.0.1:$PORT"

ensure_venv() {
    if [ ! -f "$BACKEND_PYTHON" ]; then
        echo -e "${RED}Backend venv not found.${NC}"
        echo -e "${CYAN}Fix: cd $BACKEND_DIR/tests && uv venv && uv pip install -r requirements.txt${NC}"
        exit 1
    fi
}

ensure_run_dir() {
    mkdir -p "$RUN_DIR"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(awk '{print $1}' "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # Stale PID file
        rm -f "$PID_FILE"
    fi
    return 1
}

port_pid() {
    # Return the PID holding the port, or empty string
    ss -tlnp 2>/dev/null | grep ":${PORT} " | grep -oP 'pid=\K[0-9]+' | head -1
}

get_uptime() {
    if [ ! -f "$PID_FILE" ]; then
        echo "unknown"
        return
    fi
    local start_epoch
    start_epoch=$(awk '{print $2}' "$PID_FILE")
    local now
    now=$(date +%s)
    local elapsed=$((now - start_epoch))

    if [ "$elapsed" -lt 60 ]; then
        echo "${elapsed}s"
    elif [ "$elapsed" -lt 3600 ]; then
        echo "$((elapsed / 60))m $((elapsed % 60))s"
    else
        echo "$((elapsed / 3600))h $((elapsed % 3600 / 60))m"
    fi
}

health_check() {
    curl -s -o /dev/null -w "%{http_code}" "$URL/health" 2>/dev/null || echo "000"
}

case "${1:-}" in
    up)
        echo -e "${LIGHT_CYAN}Stack — Starting${NC}"
        ensure_venv
        ensure_run_dir

        if is_running; then
            echo -e "  ${YELLOW}Already running (PID $(awk '{print $1}' "$PID_FILE"))${NC}"
            exit 0
        fi

        stale_pid=$(port_pid)
        if [ -n "$stale_pid" ]; then
            proc_cmd=$(ps -p "$stale_pid" -o args= 2>/dev/null || echo "")
            if echo "$proc_cmd" | grep -q "uvicorn"; then
                echo -e "  ${YELLOW}Stale backend on port $PORT (PID $stale_pid) — killing${NC}"
                kill "$stale_pid" 2>/dev/null
                sleep 1
                if [ -n "$(port_pid)" ]; then
                    echo -e "  ${RED}✗ Could not free port $PORT${NC}"
                    exit 1
                fi
            else
                proc_name=$(ps -p "$stale_pid" -o comm= 2>/dev/null || echo "unknown")
                echo -e "  ${RED}✗ Port $PORT is in use by another process: $proc_name (PID $stale_pid)${NC}"
                exit 1
            fi
        fi

        "$BACKEND_PYTHON" -m uvicorn app:app \
            --host 127.0.0.1 \
            --port "$PORT" \
            --app-dir "$BACKEND_DIR" \
            > "$RUN_DIR/backend.log" 2>&1 &

        local_pid=$!
        echo "$local_pid $(date +%s)" > "$PID_FILE"

        # Wait for health
        for _ in $(seq 1 30); do
            if [ "$(health_check)" = "200" ]; then
                echo -e "  ${GREEN}✓ Backend started${NC} (PID $local_pid)"
                echo -e "  ${URL}"
                exit 0
            fi
            sleep 0.2
        done

        echo -e "  ${RED}✗ Backend failed to start${NC}"
        echo -e "  ${CYAN}Check: cat $RUN_DIR/backend.log${NC}"
        kill "$local_pid" 2>/dev/null || true
        rm -f "$PID_FILE"
        exit 1
        ;;

    down)
        echo -e "${LIGHT_CYAN}Stack — Stopping${NC}"

        if ! is_running; then
            echo -e "  ${YELLOW}Not running${NC}"
            exit 0
        fi

        local_pid=$(awk '{print $1}' "$PID_FILE")
        kill "$local_pid" 2>/dev/null
        rm -f "$PID_FILE"
        echo -e "  ${GREEN}✓ Backend stopped${NC}"
        ;;

    restart)
        "$0" down
        sleep 1
        "$0" up
        ;;

    status)
        echo -e "${LIGHT_CYAN}Stack Status${NC}"
        echo ""

        if is_running; then
            local_pid=$(awk '{print $1}' "$PID_FILE")
            uptime=$(get_uptime)
            status_code=$(health_check)

            if [ "$status_code" = "200" ]; then
                echo -e "  example-backend: ${GREEN}✓ healthy${NC} (uptime: $uptime, PID $local_pid)"
            else
                echo -e "  example-backend: ${RED}✗ unhealthy${NC} (HTTP $status_code, PID $local_pid)"
            fi
            echo -e "  ${URL}"
        else
            echo -e "  example-backend: ${RED}✗ not running${NC}"
            echo -e "  ${CYAN}Fix: ./scripts/stack.sh up${NC}"
        fi
        ;;

    *)
        echo "Stack Management"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  up        Start the backend"
        echo "  down      Stop the backend"
        echo "  restart   Restart the backend"
        echo "  status    Show status and uptime"
        exit 1
        ;;
esac
