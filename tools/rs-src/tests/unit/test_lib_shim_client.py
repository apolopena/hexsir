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


def _fake_socket(
    recv_data: bytes | None = None,
    connect_exc: Exception | None = None,
    sendall_exc: Exception | None = None,
    recv_exc: Exception | None = None,
):
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
    err = (
        json.dumps({"id": 1, "error": "ProcessNotFound: Ravenswatch.exe not found"})
        + "\n"
    )
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


# --- Session ---


class _MultiCallSocket:
    """Socket mock that returns a different response per .recv() cycle.

    Each item in `responses` is the bytes for one full reply (already
    newline-terminated). Tracks sendall payloads in `sent`.
    """

    def __init__(self, responses: list[bytes]):
        self._queue = list(responses)
        self.sent: list[bytes] = []
        self.connect = MagicMock()
        self.settimeout = MagicMock()
        self.close = MagicMock()
        self._current: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)
        # Prime the next response for recv().
        if self._queue:
            self._current = [self._queue.pop(0), b""]
        else:
            self._current = [b""]

    def recv(self, n: int) -> bytes:
        if not self._current:
            return b""
        return self._current.pop(0)


def test_session_holds_one_socket_across_calls():
    sock = _MultiCallSocket(
        [
            json.dumps({"id": 1, "result": {"v": 1}}).encode() + b"\n",
            json.dumps({"id": 2, "result": {"v": 2}}).encode() + b"\n",
            json.dumps({"id": 3, "result": {"v": 3}}).encode() + b"\n",
        ]
    )
    with _stub_resolution(), patch("lib.shim_client.socket.socket", return_value=sock):
        with shim_client.Session() as s:
            assert s.call("read", {"addr": 1, "length": 4}) == {"v": 1}
            assert s.call("read", {"addr": 2, "length": 4}) == {"v": 2}
            assert s.call("read", {"addr": 3, "length": 4}) == {"v": 3}
    # One connect, one close — single socket reused.
    sock.connect.assert_called_once_with(("1.2.3.4", 8765))
    sock.close.assert_called_once()
    # Three sends, monotonic ids.
    assert len(sock.sent) == 3
    ids = [json.loads(p.decode().strip())["id"] for p in sock.sent]
    assert ids == [1, 2, 3]


def test_session_close_on_exit():
    sock = _MultiCallSocket([])
    with _stub_resolution(), patch("lib.shim_client.socket.socket", return_value=sock):
        with shim_client.Session():
            pass
    sock.close.assert_called_once()


def test_session_call_outside_context_raises():
    s = shim_client.Session()
    with pytest.raises(Exception):  # ShimError or similar
        s.call("ping")


def test_session_connection_refused_raises_unreachable():
    sock = _fake_socket(connect_exc=ConnectionRefusedError("nope"))
    with _stub_resolution(), _patch_socket_factory(sock):
        with pytest.raises(ShimUnreachable):
            with shim_client.Session():
                pass


def test_session_send_failure_raises_disconnected():
    sock = MagicMock(spec=socket.socket)
    sock.sendall.side_effect = BrokenPipeError("pipe")
    with _stub_resolution(), patch("lib.shim_client.socket.socket", return_value=sock):
        with shim_client.Session() as s:
            with pytest.raises(ShimDisconnected):
                s.call("ping")


def test_session_rpc_error_propagates():
    err = json.dumps({"id": 1, "error": "ProcessNotFound: nope"}) + "\n"
    sock = _MultiCallSocket([err.encode()])
    with _stub_resolution(), patch("lib.shim_client.socket.socket", return_value=sock):
        with shim_client.Session() as s:
            with pytest.raises(ShimRPCError) as exc:
                s.call("attach")
    assert exc.value.kind == "ProcessNotFound"
