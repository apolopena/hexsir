"""Dynamic tree — task execution with pass/fail reporting."""

import asyncio
import inspect
import subprocess
from typing import Any

from display_lib.output import Spinner, error

from .primitives import tree_fail, tree_ok
from .types import TaskEntry


def run_task(entry: TaskEntry) -> Any:
    """Execute a task and render pass/fail as a tree line.

    Failure detection (built-in):
        - action raises an exception → tree_fail
        - action returns CompletedProcess with non-zero returncode → tree_fail
        - All other returns → tree_ok

    Default failure handling (no on_fail):
        Prints stderr (CompletedProcess) or str(exception), then raises
        SystemExit(exit_code).

    Custom failure handling (on_fail provided):
        Callback receives the cause (exception or CompletedProcess).
        Can raise to abort, or return to continue.

    Async guard:
        Raises TypeError if action is async.

    Returns action()'s result on success.
    """
    # Pre-call async guard
    if inspect.iscoroutinefunction(entry.action):
        raise TypeError("run_task does not support async actions")

    try:
        if entry.spin:
            connector = "└─" if entry.is_last else "├─"
            with Spinner(f"{connector} {entry.label}"):
                result = entry.action()
        else:
            result = entry.action()

        # Post-call async guard (catches lambdas/partials returning coroutines)
        if asyncio.iscoroutine(result):
            result.close()
            raise TypeError("action returned a coroutine -- use a sync callable")

        # Check CompletedProcess failure
        if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
            raise _CompletedProcessFailure(result)

    except TypeError:
        # Let TypeError from async guards propagate
        raise
    except _CompletedProcessFailure as e:
        _handle_failure(entry, e.process)
        return  # only reached if on_fail doesn't raise
    except Exception as e:
        _handle_failure(entry, e)
        return  # only reached if on_fail doesn't raise

    # Success
    label = entry.done_label or entry.label
    tree_ok(label, is_last=entry.is_last, indent=entry.indent)
    return result


class _CompletedProcessFailure(Exception):
    """Internal: wraps a failed CompletedProcess for unified error handling."""

    def __init__(self, process: subprocess.CompletedProcess):
        self.process = process


def _handle_failure(entry: TaskEntry, cause) -> None:
    """Handle task failure — default or custom on_fail."""
    # Unwrap internal wrapper
    if isinstance(cause, _CompletedProcessFailure):
        cause = cause.process

    tree_fail(entry.label, is_last=entry.is_last, indent=entry.indent)

    if entry.on_fail:
        entry.on_fail(cause)
        return

    # Default: print error and exit
    if isinstance(cause, subprocess.CompletedProcess):
        stderr = cause.stderr.strip() if cause.stderr else ""
        if stderr:
            error(stderr)
    else:
        error(str(cause))
    raise SystemExit(entry.exit_code)
