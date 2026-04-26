"""Tests for lib.paths."""

from lib.paths import to_display_path


def test_wsl_c_drive():
    assert to_display_path("/mnt/c/foo/bar") == "C:\\foo\\bar"


def test_wsl_d_drive_lowercase_to_upper():
    assert to_display_path("/mnt/d/games/rs_shim.py") == "D:\\games\\rs_shim.py"


def test_wsl_uppercase_letter():
    # Some WSL configs allow /mnt/C/ — handle either case.
    assert to_display_path("/mnt/C/foo") == "C:\\foo"


def test_native_windows_path_unchanged():
    assert to_display_path("C:\\ravensmith\\scripts\\rs_shim.py") \
        == "C:\\ravensmith\\scripts\\rs_shim.py"


def test_posix_path_unchanged():
    assert to_display_path("/home/user/rs_shim.py") == "/home/user/rs_shim.py"


def test_relative_path_unchanged():
    assert to_display_path("scripts/rs_shim.py") == "scripts/rs_shim.py"


def test_empty_string():
    assert to_display_path("") == ""
