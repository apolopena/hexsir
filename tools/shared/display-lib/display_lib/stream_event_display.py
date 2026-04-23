"""Shared event display for agent activity streams and monitor.

Used by both stream.py (AgentStream) and commands/monitor.py
to ensure consistent formatting of agent events.
"""

from datetime import datetime, timezone

from display_lib.output import BLUE, BRIGHT_GREEN, CYAN, GREEN, NC, RED, dim


def format_timestamp(timestamp: str, utc: bool = False) -> str:
    """Format an ISO timestamp for display."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if utc:
            utc_dt = dt.astimezone(timezone.utc)
            return dim(f"[{utc_dt.strftime('%H:%M:%S')} UTC] ")
        else:
            local_dt = dt.astimezone()
            return dim(f"[{local_dt.strftime('%I:%M:%S %p')}] ")
    except (ValueError, AttributeError):
        return ""


def format_model_info(
    model: str, data: dict, min_verbosity: int = 1, verbosity: int = 1
) -> str | None:
    """Format model/provider info for the start event.

    Returns formatted string or None if verbosity too low or no model.
    """
    if verbosity < min_verbosity or not model:
        return None

    provider = data.get("provider")
    verify_model = data.get("verify_model")
    verify_provider = data.get("verify_provider")
    temperature = data.get("temperature")

    if verify_provider and verify_provider != provider:
        provider_str = f"{dim('providers:')} {provider}, {verify_provider}  "
    else:
        provider_str = f"{dim('provider:')} {provider}  " if provider else ""

    if verify_model and verify_model != model:
        model_str = f"{dim('models:')} {model}, {verify_model}"
    else:
        model_str = f"{dim('model:')} {model}"

    temp_str = f"  {dim('temp:')} {temperature}" if temperature is not None else ""

    return f"   {provider_str}{model_str}{temp_str}"


def format_step_model(state: str, model: str, data: dict) -> str:
    """Format inline model info for draft_start/verify_start events."""
    if state in ("draft_start", "verify_start") and model:
        provider = data.get("provider", "")
        return f"  {dim(f'({provider}/{model})')}"
    return ""


def display_event(event: dict, utc: bool = False, verbosity: int = 1) -> str | None:
    """Display a formatted agent event.

    Args:
        event: Agent event dict from WebSocket
        utc: Show timestamps in UTC
        verbosity: 1=events, 2=details, 3=full

    Returns:
        'error' on boundary error, 'complete' on boundary complete, None otherwise
    """
    agent = event.get("agent", "?")
    state = event.get("state", "?")
    timestamp = event.get("timestamp", "")
    model = event.get("model", "")
    data = event.get("data", {})
    duration = data.get("duration_ms")

    time_str = format_timestamp(timestamp, utc)
    duration_str = f" ({duration}ms)" if duration else ""

    if state == "start":
        print(f"{time_str}{BLUE}[{agent}]{NC} {state}")
        model_line = format_model_info(model, data, verbosity=verbosity)
        if model_line:
            print(model_line)

    elif state in ("error", "parse_error") or state.endswith("_error"):
        error_msg = data.get("error")
        print(f"{time_str}{BLUE}[{agent}]{NC} {RED}\u2717{NC} {state}")
        if error_msg:
            print(f"           \u2514\u2500 {error_msg}")
        if state == "error":
            return "error"

    elif state == "complete":
        print(f"{time_str}{BLUE}[{agent}]{NC} {GREEN}done{NC}{duration_str}")
        return "complete"

    elif state.endswith("_complete"):
        print(
            f"{time_str}   \u2514\u2500 {BRIGHT_GREEN}\u2713{NC} {state}{duration_str}"
        )

    else:
        model_info = format_step_model(state, model, data)
        print(
            f"{time_str}   \u251c\u2500 {BRIGHT_GREEN}\u2713{NC} {state}{model_info}{duration_str}"
        )

    return None


def print_ws_connected() -> None:
    """Print WebSocket connected message."""
    print(
        f"{BRIGHT_GREEN}\u2713{NC} {GREEN}[ws] Connected to agent activity stream{NC}"
    )


def print_ws_closed_success() -> None:
    """Print WebSocket closed (success) message."""
    print(
        f"{BRIGHT_GREEN}\u2713 {GREEN}[ws] WebSocket connection closed (complete){NC}"
    )


def print_ws_closed_error(reason: str = "agent error") -> None:
    """Print WebSocket closed (error) message."""
    print(
        f"{RED}\u2717 {CYAN}[ws] WebSocket connection closed ({RED}{reason}{CYAN}){NC}"
    )


def print_ws_error(message: str) -> None:
    """Print WebSocket stream error message."""
    print(f"{RED}\u2717 {CYAN}[ws] Stream error: {message}{NC}")
