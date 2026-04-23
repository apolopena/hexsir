from click.testing import Result


def assert_cli_ok(result: Result) -> None:
    """Assert a Click CLI invocation succeeded.

    Args:
        result: The `click.testing.Result` returned by `CliRunner.invoke(...)`.

    On failure, the assertion message includes the exit code, captured output,
    and captured exception.
    """
    assert result.exit_code == 0, (
        f"exit {result.exit_code}\n"
        f"--- output ---\n{result.output}\n"
        f"--- exception ---\n{result.exception!r}"
    )
