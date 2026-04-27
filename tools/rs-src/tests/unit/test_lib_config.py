"""Tests for lib.config."""

from unittest.mock import mock_open, patch

import pytest

from lib import config
from lib.errors import HostUnresolvable


# ---- shim_host ----


def test_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("RS_SHIM_HOST", "10.0.0.1")
    assert config.shim_host("1.2.3.4") == "1.2.3.4"


def test_env_overrides_autodetect(monkeypatch):
    monkeypatch.setenv("RS_SHIM_HOST", "10.0.0.1")
    with patch("lib.config._detect_gateway", return_value="172.31.16.1"):
        assert config.shim_host() == "10.0.0.1"


def test_empty_env_falls_through_to_autodetect(monkeypatch):
    monkeypatch.setenv("RS_SHIM_HOST", "")
    with patch("lib.config._detect_gateway", return_value="172.31.16.1"):
        assert config.shim_host() == "172.31.16.1"


def test_autodetect_failure_raises(monkeypatch):
    monkeypatch.delenv("RS_SHIM_HOST", raising=False)
    with patch("lib.config._detect_gateway", return_value=None):
        with pytest.raises(HostUnresolvable):
            config.shim_host()


# ---- shim_port ----


def test_port_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("RS_SHIM_PORT", "9000")
    assert config.shim_port(8765) == 8765


def test_port_env_overrides_default(monkeypatch):
    monkeypatch.setenv("RS_SHIM_PORT", "9000")
    assert config.shim_port() == 9000


def test_port_default(monkeypatch):
    monkeypatch.delenv("RS_SHIM_PORT", raising=False)
    assert config.shim_port() == config.DEFAULT_PORT


def test_port_empty_env_falls_through_to_default(monkeypatch):
    monkeypatch.setenv("RS_SHIM_PORT", "")
    assert config.shim_port() == config.DEFAULT_PORT


# ---- shim_loc ----


def test_shim_loc_default(monkeypatch):
    monkeypatch.delenv("RS_SHIM_LOC", raising=False)
    assert config.shim_loc() == config.DEFAULT_SHIM_LOC


def test_shim_loc_env_overrides(monkeypatch):
    monkeypatch.setenv("RS_SHIM_LOC", "/tmp/custom_shim.py")
    assert config.shim_loc() == "/tmp/custom_shim.py"


def test_shim_loc_empty_env_falls_through_to_default(monkeypatch):
    monkeypatch.setenv("RS_SHIM_LOC", "")
    assert config.shim_loc() == config.DEFAULT_SHIM_LOC


# ---- _detect_gateway ----


def test_detect_gateway_from_ip_route():
    with patch(
        "lib.config.subprocess.check_output",
        return_value="default via 172.31.16.1 dev eth0 proto kernel",
    ):
        assert config._detect_gateway() == "172.31.16.1"


def test_detect_gateway_falls_back_to_resolv_conf():
    with (
        patch(
            "lib.config.subprocess.check_output",
            side_effect=FileNotFoundError("no `ip` command"),
        ),
        patch("builtins.open", mock_open(read_data="nameserver 10.0.0.1\n")),
    ):
        assert config._detect_gateway() == "10.0.0.1"


def test_detect_gateway_returns_none_when_all_fail():
    with (
        patch(
            "lib.config.subprocess.check_output",
            side_effect=FileNotFoundError("no `ip` command"),
        ),
        patch("builtins.open", side_effect=FileNotFoundError("no resolv.conf")),
    ):
        assert config._detect_gateway() is None
