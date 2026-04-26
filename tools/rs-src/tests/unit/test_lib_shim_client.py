"""Tests for lib.shim_client.

Mocks the socket layer to verify request framing, response parsing, and
exception translation. Does not require a running shim.
"""

import json
import socket
from unittest.mock import MagicMock, patch

import pytest

from lib import shim_client
from lib.errors import (
    ShimDisconnected,
    ShimProtocolError,
    ShimRPCError,
    ShimTimeout,
    ShimUnreachable,
)


def _fake_socket(recv_data: bytes | None = None,
                 connect_exc: Exception | None = None,
                 sendall_exc: Exception | None = None,
                 recv_exc: Exception | None = None):
    """Build a MagicMock that emulates socket.socket() for one call cycle."""
    mock = MagicMock(spec=socket.socket)
    if connect_exc:
        mock.connect.side_effect = connect_exc
    if sendall_exc:
        mock.sendall.side_effect = sendall_exc
    if recv_exc:
        mock.recv.side_effect = recv_exc
    elif recv_data is not None:
        chunks = [recv_data, b""]  # second recv returns "" → EOF
        mock.recv.side_effect = chunks
    return mock


def _patch_socket_factory(mock_sock):
    return patch("lib.shim_client.socket.socket", return_value=mock_sock)


def _stub_resolution():
    return patch.multiple(
        "lib.shim_client.config",
        shim_host=lambda explicit=None: "1.2.3.4",
        shim_port=lambda explicit=None: 8765,
    )


def test_call_success():
    resp_line = json.dumps({"id": 1, "result": {"ok": True}}) + "\n"
    sock = _fake_socket(recv_data=resp_line.encode())
    with _stub_resolution(), _patch_socket_factory(sock):
        result = shim_client.call("ping")
    assert result == {"ok": True}
    sock.connect.assert_called_once_with(("1.2.3.4", 8765))
    sent = sock.sendall.call_args[0][0]
    sent_obj = json.loads(sent.decode().strip())
    assert sent_obj["method"] == "ping"


def test_call_with_params():
    resp_line = json.dumps({"id": 1, "result": {"pid": 22768}}) + "\n"
    sock = _fake_socket(recv_data=resp_line.encode())
    with _stub_resolution(), _patch_socket_factory(sock):
        shim_client.call("attach", params={"process": "Ravenswatch.exe"})
    sent_obj = json.loads(sock.sendall.call_args[0][0].decode().strip())
    assert sent_obj["params"] == {"process": "Ravenswatch.exe"}


def test_connection_refused_raises_unreachable():
    sock = _fake_socket(connect_exc=ConnectionRefusedError("nope"))
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimUnreachable):
            shim_client.call("ping")


def test_connect_timeout_raises_shim_timeout():
    sock = _fake_socket(connect_exc=TimeoutError("connect timed out"))
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimTimeout):
            shim_client.call("ping")


def test_send_broken_pipe_raises_disconnected():
    sock = _fake_socket(sendall_exc=BrokenPipeError("pipe"))
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimDisconnected):
            shim_client.call("ping")


def test_recv_reset_raises_disconnected():
    sock = _fake_socket(recv_exc=ConnectionResetError("reset"))
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimDisconnected):
            shim_client.call("ping")


def test_empty_response_raises_protocol_error():
    sock = _fake_socket(recv_data=b"")
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimProtocolError):
            shim_client.call("ping")


def test_malformed_json_raises_protocol_error():
    sock = _fake_socket(recv_data=b"{not valid json}\n")
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimProtocolError):
            shim_client.call("ping")


def test_rpc_error_with_kind():
    err = json.dumps({"id": 1, "error": "ProcessNotFound: Ravenswatch.exe not found"}) + "\n"
    sock = _fake_socket(recv_data=err.encode())
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimRPCError) as exc:
            shim_client.call("attach")
    assert exc.value.kind == "ProcessNotFound"
    assert "not found" in str(exc.value)


def test_rpc_error_without_kind():
    err = json.dumps({"id": 1, "error": "something happened"}) + "\n"
    sock = _fake_socket(recv_data=err.encode())
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimRPCError) as exc:
            shim_client.call("attach")
    assert exc.value.kind is None


def test_response_missing_result_and_error_raises_protocol():
    err = json.dumps({"id": 1, "weird": "thing"}) + "\n"
    sock = _fake_socket(recv_data=err.encode())
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimProtocolError):
            shim_client.call("ping")
