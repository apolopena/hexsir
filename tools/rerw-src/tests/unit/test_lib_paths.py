"""Tests for lib.paths.get_root_dir."""

from pathlib import Path

import pytest

from lib.paths import get_root_dir


def test_returns_path_when_env_set(tmp_path: Path, monkeypatch):
    """CLI_ROOT_DIR pointing at a real dir is returned as a Path."""
    monkeypatch.setenv("CLI_ROOT_DIR", str(tmp_path))
    assert get_root_dir() == tmp_path


def test_exits_when_env_unset(monkeypatch, capsys):
    """Unset CLI_ROOT_DIR causes SystemExit(1) with a clear error."""
    monkeypatch.delenv("CLI_ROOT_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        get_root_dir()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "CLI_ROOT_DIR not set" in (captured.out + captured.err)


def test_exits_when_path_not_a_directory(tmp_path: Path, monkeypatch, capsys):
    """CLI_ROOT_DIR pointing at a non-dir path causes SystemExit(1)."""
    bogus = tmp_path / "does_not_exist"
    monkeypatch.setenv("CLI_ROOT_DIR", str(bogus))
    with pytest.raises(SystemExit) as exc:
        get_root_dir()
    assert exc.value.code == 1
