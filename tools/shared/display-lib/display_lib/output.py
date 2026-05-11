"""Terminal colors and output helpers."""

import asyncio
import sys
import threading
import time
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")

RED = "\033[38;5;160m"
GREEN = "\033[38;5;2m"
BRIGHT_GREEN = "\033[38;5;34m"
YELLOW = "\033[38;5;142m"
BLUE = "\033[38;5;25m"
MAGENTA = "\033[0;35m"
CYAN = "\033[38;5;73m"
ORANGE = "\033[38;5;208m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"  # No Color


def format_ok(msg: str) -> str:
    """Return green checkmark + green message string."""
    return f"{BRIGHT_GREEN}✓{NC} {GREEN}{msg}{NC}"


def format_fail(msg: str) -> str:
    """Return red cross + red message string."""
    return f"{RED}✗ {msg}{NC}"


def success(msg: str) -> None:
    """Print success message with bright green checkmark."""
    print(format_ok(msg))


def error(msg: str) -> None:
    """Print error message in red to stderr."""
    print(format_fail(msg), file=sys.stderr)


def info(msg: str) -> None:
    """Print info message in blue."""
    print(f"{BLUE}{msg}{NC}")


def warn(msg: str) -> None:
    """Print warning message with icon."""
    print(f"  {YELLOW}\u26a0 {msg}{NC}")


def header(msg: str) -> None:
    """Print header message in magenta bold."""
    print(f"{MAGENTA}{BOLD}=== {msg} ==={NC}")


def dim(msg: str) -> str:
    """Return dimmed text for inline use within a line.

    Unlike info(), error(), success() etc. which print a complete line,
    dim() returns a styled string for composing with other text:

        print(f"  {dim('thinking:')} {output}")
        print(f"  {dim('provider:')} {provider}  {dim('model:')} {model}")

    Use for secondary/metadata text — timestamps, labels, truncation notes.
    """
    return f"{DIM}{msg}{NC}"


# ---------------------------------------------------------------------------
# Spinners — shared rendering, three concurrency models
# ---------------------------------------------------------------------------

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _render_frame(i: int, message: str, start_time: float) -> str:
    """Render a single spinner frame string."""
    elapsed = time.monotonic() - start_time
    frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
    return f"\r  {CYAN}{frame}{NC} {message} {DIM}({elapsed:.0f}s){NC}  "


def _clear_spinner(message_len: int) -> None:
    """Clear a spinner line from the terminal."""
    sys.stdout.write(f"\r{' ' * (message_len + 20)}\r")
    sys.stdout.flush()


async def spin(label: str, coro: Awaitable[T]) -> T:
    """Run an async coroutine with a spinner showing elapsed time.

    Args:
        label: Text to show next to the spinner
        coro: Awaitable to execute

    Returns:
        The coroutine's return value
    """
    task = asyncio.ensure_future(coro)
    start = time.monotonic()
    i = 0

    while not task.done():
        sys.stdout.write(_render_frame(i, label, start))
        sys.stdout.flush()
        i += 1
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
        except asyncio.TimeoutError:
            pass
        except Exception:
            break

    _clear_spinner(len(label))
    return await task


class Spinner:
    """Threaded braille spinner for synchronous operations.

    Usage:
        with Spinner("Processing..."):
            do_work()
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _spin(self) -> None:
        i = 0
        start = time.monotonic()
        while not self._stop.is_set():
            sys.stdout.write(_render_frame(i, self._message, start))
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.08)
        _clear_spinner(len(self._message))

    def __enter__(self) -> "Spinner":
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()


class AsyncSpinner:
    """Async background spinner with start/stop lifecycle.

    Unlike Spinner (sync, context manager) and spin() (async, wraps one coro),
    AsyncSpinner supports repeated start/stop cycles for long-running async
    processes like WebSocket streams.

    Usage:
        spinner = AsyncSpinner("processing...")
        await spinner.start()
        # ... events arrive, time passes ...
        spinner.stop()
        # ... display something ...
        await spinner.start()
        # ... more waiting ...
        spinner.stop()
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self._task: asyncio.Task | None = None
        self._active = False
        self._start_time: float = 0

    async def start(self) -> None:
        """Start spinning in the background. No-op if already spinning."""
        if self._active:
            return
        self._active = True
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        """Stop spinning and clear the line. No-op if not spinning."""
        if not self._active:
            return
        self._active = False
        if self._task and not self._task.done():
            self._task.cancel()
        _clear_spinner(len(self._message))

    async def _run(self) -> None:
        """Animation loop."""
        try:
            i = 0
            while self._active:
                sys.stdout.write(_render_frame(i, self._message, self._start_time))
                sys.stdout.flush()
                i += 1
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
