"""Tests for `dev sync-shim` command."""

from unittest.mock import patch

from click.testing import CliRunner

from commands.dev.sync_shim import sync_shim_cmd


def test_help():
    runner = CliRunner()
    result = runner.invoke(sync_shim_cmd, ["--help"])
    assert result.exit_code == 0
    assert (
        "Synced" in result.output
        or "RS_SHIM_LOC" in result.output
        or "Copy" in result.output
    )


def test_copies_source_to_dest(tmp_path):
    src = tmp_path / "rs_shim.py"
    src.write_text("# test shim\n")
    dest = tmp_path / "deploy" / "rs_shim.py"

    runner = CliRunner()
    with (
        patch("commands.dev.sync_shim.shim_source_path", return_value=src),
        patch("commands.dev.sync_shim.config.shim_loc", return_value=str(dest)),
    ):
        result = runner.invoke(sync_shim_cmd, [])

    assert result.exit_code == 0, result.output
    assert dest.exists()
    assert dest.read_text() == "# test shim\n"


def test_missing_source_aborts(tmp_path):
    src = tmp_path / "missing.py"
    dest = tmp_path / "deploy" / "rs_shim.py"

    runner = CliRunner()
    with (
        patch("commands.dev.sync_shim.shim_source_path", return_value=src),
        patch("commands.dev.sync_shim.config.shim_loc", return_value=str(dest)),
    ):
        result = runner.invoke(sync_shim_cmd, [])

    assert result.exit_code != 0
    assert not dest.exists()


def test_message_uses_display_path(tmp_path):
    """Output instructions should show Windows-style path when /mnt/c/... is the dest."""
    src = tmp_path / "rs_shim.py"
    src.write_text("x")
    dest = "/mnt/c/foo/rs_shim.py"  # WSL-style

    runner = CliRunner()
    with (
        patch("commands.dev.sync_shim.shim_source_path", return_value=src),
        patch("commands.dev.sync_shim.config.shim_loc", return_value=dest),
        patch("commands.dev.sync_shim.shutil.copyfile"),
        patch("pathlib.Path.mkdir"),
    ):
        result = runner.invoke(sync_shim_cmd, [])

    assert result.exit_code == 0
    assert "C:\\foo\\rs_shim.py" in result.output
