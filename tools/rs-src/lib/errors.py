"""Typed exception hierarchy for shim communication errors.

All exceptions raised by lib/shim_client.py inherit from ShimError so callers
can catch broadly or narrowly. The lib translates raw socket / JSON / RPC
errors into these types so command code can render distinct UX per category.
"""


class ShimError(Exception):
    """Base for all shim communication failures."""


class ShimUnreachable(ShimError):
    """Connection refused — the shim isn't running on the target host:port."""


class ShimTimeout(ShimError):
    """Connect or read timed out — shim is hung or network is slow."""


class ShimDisconnected(ShimError):
    """Connection closed mid-request — shim crashed or was killed."""


class ShimProtocolError(ShimError):
    """Shim returned malformed or empty data — likely a shim bug."""


class ShimRPCError(ShimError):
    """Shim returned a well-formed `{"error": "..."}` response.

    The string from the shim is preserved as the message; the optional `kind`
    captures the leading exception name (e.g. "ProcessNotFound") so callers
    can branch on it.
    """

    def __init__(self, message: str, kind: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind


class HostUnresolvable(ShimError):
    """Could not auto-detect the Windows host IP and no override was given."""
