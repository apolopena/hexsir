"""Tests for run_task."""

import subprocess
from unittest.mock import patch

import pytest

from tree_lib import TaskEntry, run_task


class TestRunTask:
    """Tests for dynamic task execution."""

    def test_success_path(self, capsys):
        """Successful action prints tree_ok and returns result."""
        result = run_task(TaskEntry(label="Done", action=lambda: 42))
        assert result == 42
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "Done" in captured.out

    def test_completed_process_failure_default(self, capsys):
        """Failed CompletedProcess with default on_fail raises SystemExit."""
        proc = subprocess.CompletedProcess(
            args=["test"], returncode=1, stderr="bad thing\n"
        )
        with pytest.raises(SystemExit) as exc_info:
            run_task(TaskEntry(label="Build", action=lambda: proc))
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "✗" in captured.err
        assert "bad thing" in captured.err

    def test_exception_failure_default(self, capsys):
        """Exception with default on_fail raises SystemExit."""

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(SystemExit) as exc_info:
            run_task(TaskEntry(label="Deploy", action=fail))
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "✗" in captured.err
        assert "boom" in captured.err

    def test_custom_on_fail(self, capsys):
        """Custom on_fail callback receives cause and controls flow."""
        causes = []

        def my_handler(cause):
            causes.append(cause)

        run_task(
            TaskEntry(
                label="Test",
                action=lambda: (_ for _ in ()).throw(ValueError("oops")),
                on_fail=my_handler,
            )
        )
        assert len(causes) == 1
        assert isinstance(causes[0], ValueError)

    def test_spinner_flag(self, capsys):
        """spin=True wraps action in Spinner context manager."""
        with patch("tree_lib.dynamic.Spinner") as mock_spinner:
            mock_spinner.return_value.__enter__ = lambda s: s
            mock_spinner.return_value.__exit__ = lambda s, *a: None
            run_task(TaskEntry(label="Loading", action=lambda: "ok", spin=True))
        mock_spinner.assert_called_once()
        assert "Loading" in mock_spinner.call_args[0][0]

    def test_done_label_replacement(self, capsys):
        """Success message uses done_label when provided."""
        run_task(
            TaskEntry(
                label="Creating",
                action=lambda: "ok",
                done_label="Created my-repo",
            )
        )
        captured = capsys.readouterr()
        assert "Created my-repo" in captured.out
        assert "Creating" not in captured.out

    def test_async_guard_coroutine_function(self):
        """Async function raises TypeError before execution."""

        async def async_action():
            pass

        with pytest.raises(TypeError, match="does not support async"):
            run_task(TaskEntry(label="Async", action=async_action))

    def test_async_guard_coroutine_return(self):
        """Lambda returning coroutine raises TypeError."""

        async def coro():
            pass

        with pytest.raises(TypeError, match="returned a coroutine"):
            run_task(TaskEntry(label="Sneaky", action=lambda: coro()))

    def test_exit_code_override(self, capsys):
        """SystemExit uses custom exit_code."""
        with pytest.raises(SystemExit) as exc_info:
            run_task(
                TaskEntry(
                    label="Fail",
                    action=lambda: (_ for _ in ()).throw(RuntimeError("x")),
                    exit_code=42,
                )
            )
        assert exc_info.value.code == 42

    def test_is_last_connector(self, capsys):
        """is_last=True uses └─ connector on success."""
        run_task(TaskEntry(label="Final", action=lambda: True, is_last=True))
        captured = capsys.readouterr()
        assert "└─" in captured.out

    def test_indent_passed_through(self, capsys):
        """indent is passed to tree_ok."""
        run_task(TaskEntry(label="Indented", action=lambda: True, indent="  "))
        captured = capsys.readouterr()
        assert captured.out.startswith("  ")
