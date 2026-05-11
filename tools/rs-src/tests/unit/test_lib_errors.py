"""Tests for lib.errors hierarchy."""

import pytest

from lib.errors import (
    HostUnresolvable,
    ShimDisconnected,
    ShimError,
    ShimProtocolError,
    ShimRPCError,
    ShimTimeout,
    ShimUnreachable,
)


@pytest.mark.parametrize(
    "cls",
    [
        ShimUnreachable,
        ShimTimeout,
        ShimDisconnected,
        ShimProtocolError,
        ShimRPCError,
        HostUnresolvable,
    ],
)
def test_inherits_from_shim_error(cls):
    assert issubclass(cls, ShimError)


def test_shim_rpc_error_carries_kind():
    e = ShimRPCError("not attached; call attach first", kind="RuntimeError")
    assert str(e) == "not attached; call attach first"
    assert e.kind == "RuntimeError"


def test_shim_rpc_error_default_kind_is_none():
    e = ShimRPCError("x")
    assert e.kind is None
