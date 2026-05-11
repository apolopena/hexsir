"""Unit tests for output module."""

import asyncio

import pytest

from display_lib.output import (
    BLUE,
    BOLD,
    BRIGHT_GREEN,
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    NC,
    ORANGE,
    RED,
    YELLOW,
    AsyncSpinner,
    Spinner,
    _render_frame,
    dim,
    error,
    header,
    info,
    success,
    warn,
)


class TestColorConstants:
    """Tests for color constant values."""

    def test_red_escape(self):
        """RED should be 256-color escape for red."""
        assert RED == "\033[38;5;160m"

    def test_green_escape(self):
        """GREEN should be 256-color escape for green."""
        assert GREEN == "\033[38;5;2m"

    def test_bright_green_escape(self):
        """BRIGHT_GREEN should be 256-color escape."""
        assert BRIGHT_GREEN == "\033[38;5;34m"

    def test_yellow_escape(self):
        """YELLOW should be 256-color escape for yellow."""
        assert YELLOW == "\033[38;5;142m"

    def test_blue_escape(self):
        """BLUE should be 256-color escape for blue."""
        assert BLUE == "\033[38;5;25m"

    def test_magenta_escape(self):
        """MAGENTA should be ANSI escape for magenta."""
        assert MAGENTA == "\033[0;35m"

    def test_cyan_escape(self):
        """CYAN should be 256-color escape."""
        assert CYAN == "\033[38;5;73m"

    def test_orange_escape(self):
        """ORANGE should be 256-color escape."""
        assert ORANGE == "\033[38;5;208m"

    def test_nc_resets_color(self):
        """NC should reset color."""
        assert NC == "\033[0m"


class TestColorFunctions:
    """Tests for color output functions."""

    def test_success_prints_green(self, capsys):
        """success() should print green checkmark."""
        success("Done")
        captured = capsys.readouterr()
        assert GREEN in captured.out
        assert "✓" in captured.out
        assert "Done" in captured.out

    def test_error_prints_red(self, capsys):
        """error() should print red X to stderr."""
        error("Failed")
        captured = capsys.readouterr()
        assert RED in captured.err
        assert "✗" in captured.err
        assert "Failed" in captured.err

    def test_info_prints_blue(self, capsys):
        """info() should print blue text."""
        info("Note")
        captured = capsys.readouterr()
        assert BLUE in captured.out
        assert "Note" in captured.out

    def test_warn_prints_yellow(self, capsys):
        """warn() should print yellow text."""
        warn("Caution")
        captured = capsys.readouterr()
        assert YELLOW in captured.out
        assert "Caution" in captured.out

    def test_header_prints_magenta_bold(self, capsys):
        """header() should print magenta bold with === delimiters."""
        header("Title")
        captured = capsys.readouterr()
        assert MAGENTA in captured.out
        assert BOLD in captured.out
        assert "===" in captured.out
        assert "Title" in captured.out


class TestDimFunction:
    """Tests for dim text function."""

    def test_dim_wraps_text(self):
        """dim() should wrap text in DIM codes."""
        result = dim("timestamp")
        assert DIM in result
        assert NC in result
        assert "timestamp" in result

    def test_dim_returns_string(self):
        """dim() should return string (not print)."""
        result = dim("test")
        assert isinstance(result, str)


class TestSpinner:
    """Tests for Spinner context manager."""

    def test_spinner_creates_thread(self):
        """Spinner should create and start a thread."""
        spinner = Spinner("test")
        with spinner:
            assert spinner._thread is not None
            assert spinner._thread.is_alive()
        assert not spinner._thread.is_alive()

    def test_spinner_stops_cleanly(self):
        """Spinner should stop without errors."""
        with Spinner("test"):
            pass  # Just enter and exit


class TestRenderFrame:
    """Tests for shared spinner frame rendering."""

    def test_returns_string(self):
        """_render_frame returns a string."""
        import time

        result = _render_frame(0, "loading", time.monotonic())
        assert isinstance(result, str)

    def test_contains_message(self):
        """Frame contains the spinner message."""
        import time

        result = _render_frame(0, "loading", time.monotonic())
        assert "loading" in result

    def test_contains_spinner_char(self):
        """Frame contains a braille spinner character."""
        import time

        result = _render_frame(0, "test", time.monotonic())
        assert "⠋" in result

    def test_frame_cycles(self):
        """Different indices produce different frames."""
        import time

        start = time.monotonic()
        frame0 = _render_frame(0, "test", start)
        frame1 = _render_frame(1, "test", start)
        assert frame0 != frame1


class TestAsyncSpinner:
    """Tests for AsyncSpinner start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """start() creates a background task."""
        spinner = AsyncSpinner("test")
        await spinner.start()
        assert spinner._task is not None
        assert not spinner._task.done()
        spinner.stop()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """stop() cancels the background task."""
        spinner = AsyncSpinner("test")
        await spinner.start()
        spinner.stop()
        await asyncio.sleep(0.05)
        assert spinner._task.done()

    @pytest.mark.asyncio
    async def test_start_noop_if_active(self):
        """start() is a no-op if already spinning."""
        spinner = AsyncSpinner("test")
        await spinner.start()
        task1 = spinner._task
        await spinner.start()
        assert spinner._task is task1
        spinner.stop()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_noop_if_inactive(self):
        """stop() is a no-op if not spinning."""
        spinner = AsyncSpinner("test")
        spinner.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_repeated_start_stop(self):
        """Can start and stop multiple times."""
        spinner = AsyncSpinner("test")
        await spinner.start()
        spinner.stop()
        await asyncio.sleep(0.05)
        await spinner.start()
        spinner.stop()
        await asyncio.sleep(0.05)
        assert spinner._task.done()
