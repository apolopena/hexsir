"""Tests for swap_savefile command."""

from pathlib import Path

from click.testing import CliRunner
from commands.swap_savefile import SAVE_FILENAME, swap_savefile_cmd
from test_lib.cli import assert_cli_ok


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(swap_savefile_cmd, ["--help"])
    assert_cli_ok(result)


def test_missing_source_errors():
    """Without --source the command exits non-zero."""
    runner = CliRunner()
    result = runner.invoke(swap_savefile_cmd, [])
    assert result.exit_code != 0


def test_copy_to_dest(tmp_path: Path):
    """--source copies to <dest>/Profile_1.ob."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"abcd")
    dest = tmp_path / "save_dir"
    dest.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        swap_savefile_cmd, ["--source", str(src), "--dest", str(dest)]
    )
    assert_cli_ok(result)
    out = dest / SAVE_FILENAME
    assert out.exists()
    assert out.read_bytes() == b"abcd"


def test_overwrites_existing(tmp_path: Path):
    """An existing Profile_1.ob is overwritten."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"new")
    dest = tmp_path / "save_dir"
    dest.mkdir()
    (dest / SAVE_FILENAME).write_bytes(b"old")

    runner = CliRunner()
    result = runner.invoke(
        swap_savefile_cmd, ["--source", str(src), "--dest", str(dest)]
    )
    assert_cli_ok(result)
    assert (dest / SAVE_FILENAME).read_bytes() == b"new"


def test_env_var_default(tmp_path: Path, monkeypatch):
    """Without --dest, RERW_SAVEGAME_DIR is honored."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"data")
    dest = tmp_path / "via_env"
    dest.mkdir()
    monkeypatch.setenv("RERW_SAVEGAME_DIR", str(dest))

    runner = CliRunner()
    result = runner.invoke(swap_savefile_cmd, ["--source", str(src)])
    assert_cli_ok(result)
    assert (dest / SAVE_FILENAME).read_bytes() == b"data"


def test_dest_not_a_dir_errors(tmp_path: Path):
    """A nonexistent dest dir produces an error exit."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"x")
    dest = tmp_path / "does_not_exist"

    runner = CliRunner()
    result = runner.invoke(
        swap_savefile_cmd, ["--source", str(src), "--dest", str(dest)]
    )
    assert result.exit_code != 0


def test_default_fallback(tmp_path: Path, monkeypatch):
    """Without --dest and without env var, falls back to DEFAULT_SAVEGAME_DIR."""
    monkeypatch.delenv("RERW_SAVEGAME_DIR", raising=False)
    fallback_dir = tmp_path / "fallback_default"
    fallback_dir.mkdir()
    monkeypatch.setattr(
        "commands.swap_savefile.DEFAULT_SAVEGAME_DIR", str(fallback_dir)
    )

    src = tmp_path / "src.ob"
    src.write_bytes(b"fallback")

    runner = CliRunner()
    result = runner.invoke(swap_savefile_cmd, ["--source", str(src)])
    assert_cli_ok(result)
    assert (fallback_dir / SAVE_FILENAME).read_bytes() == b"fallback"


def test_dest_flag_overrides_env_var(tmp_path: Path, monkeypatch):
    """--dest wins when both --dest and RERW_SAVEGAME_DIR are set."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"x")
    env_dir = tmp_path / "env_dir"
    env_dir.mkdir()
    flag_dir = tmp_path / "flag_dir"
    flag_dir.mkdir()
    monkeypatch.setenv("RERW_SAVEGAME_DIR", str(env_dir))

    runner = CliRunner()
    result = runner.invoke(
        swap_savefile_cmd, ["--source", str(src), "--dest", str(flag_dir)]
    )
    assert_cli_ok(result)
    assert (flag_dir / SAVE_FILENAME).exists()
    assert not (env_dir / SAVE_FILENAME).exists()
