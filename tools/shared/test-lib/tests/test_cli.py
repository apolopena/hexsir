"""Tests for test_lib.cli helpers."""

import click
from click.testing import CliRunner

from test_lib.cli import assert_cli_ok


@click.command()
def _ok_cmd():
    click.echo("ok")


@click.command()
def _fail_cmd():
    raise SystemExit(1)


def test_assert_cli_ok_passes_on_success():
    result = CliRunner().invoke(_ok_cmd)
    assert_cli_ok(result)


def test_assert_cli_ok_fails_on_nonzero_exit():
    result = CliRunner().invoke(_fail_cmd)
    try:
        assert_cli_ok(result)
        raised = False
    except AssertionError as exc:
        raised = True
        msg = str(exc)
        assert "exit 1" in msg
        assert "--- output ---" in msg
        assert "--- exception ---" in msg
    assert raised, "assert_cli_ok did not raise on non-zero exit"
