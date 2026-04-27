"""Tests for lib.value_codec."""

import struct

import pytest

from lib import value_codec


def test_parse_addr_hex_with_prefix():
    assert value_codec.parse_addr("0x27cdcfe8668") == 0x27CDCFE8668


def test_parse_addr_hex_uppercase():
    assert value_codec.parse_addr("0x27CDCFE8668") == 0x27CDCFE8668


def test_parse_addr_decimal():
    assert value_codec.parse_addr("100") == 100


def test_parse_addr_invalid():
    with pytest.raises(ValueError):
        value_codec.parse_addr("not a number")


def test_default_length_explicit_wins():
    assert value_codec.default_length("int32", explicit=8) == 8


def test_default_length_typed_uses_size():
    assert value_codec.default_length("int32", explicit=None) == 4
    assert value_codec.default_length("int64", explicit=None) == 8
    assert value_codec.default_length("float32", explicit=None) == 4
    assert value_codec.default_length("float64", explicit=None) == 8
    assert value_codec.default_length("bool", explicit=None) == 1


def test_default_length_hex_fallback():
    assert value_codec.default_length("hex", explicit=None) == 4


def test_decode_hex_returns_string():
    assert value_codec.decode(b"\x05\x00\x00\x00", "hex") == "05000000"


def test_decode_int32():
    assert value_codec.decode(b"\x05\x00\x00\x00", "int32") == 5
    assert value_codec.decode(b"\xff\xff\xff\xff", "int32") == -1


def test_decode_uint32():
    assert value_codec.decode(b"\xff\xff\xff\xff", "uint32") == 0xFFFFFFFF


def test_decode_int64():
    assert value_codec.decode(b"\x05" + b"\x00" * 7, "int64") == 5


def test_decode_uint64():
    assert value_codec.decode(b"\xff" * 8, "uint64") == 0xFFFFFFFFFFFFFFFF


def test_decode_float32():
    raw = struct.pack("<f", 117.0)
    assert value_codec.decode(raw, "float32") == 117.0


def test_decode_float64():
    raw = struct.pack("<d", 117.5)
    assert value_codec.decode(raw, "float64") == 117.5


def test_decode_bool_true():
    assert value_codec.decode(b"\x01", "bool") is True


def test_decode_bool_false():
    assert value_codec.decode(b"\x00", "bool") is False


def test_decode_wrong_length_raises():
    with pytest.raises(ValueError, match="int32 requires 4 bytes"):
        value_codec.decode(b"\x05\x00", "int32")


def test_decode_bool_wrong_length_raises():
    with pytest.raises(ValueError, match="bool requires 1 byte"):
        value_codec.decode(b"\x01\x00", "bool")


def test_format_value_int():
    assert value_codec.format_value(5, "int32") == "5"


def test_format_value_float_keeps_trailing_zero():
    assert value_codec.format_value(117.0, "float32") == "117.0"


def test_format_value_bool():
    assert value_codec.format_value(True, "bool") == "true"
    assert value_codec.format_value(False, "bool") == "false"


def test_format_value_hex():
    assert value_codec.format_value("05000000", "hex") == "05000000"


def test_encode_int32_decimal():
    assert value_codec.encode("5", "int32") == b"\x05\x00\x00\x00"


def test_encode_int32_hex():
    assert value_codec.encode("0x10", "int32") == b"\x10\x00\x00\x00"


def test_encode_uint32_max():
    assert value_codec.encode("0xffffffff", "uint32") == b"\xff\xff\xff\xff"


def test_encode_float32():
    assert value_codec.encode("117.0", "float32") == struct.pack("<f", 117.0)


def test_encode_float64():
    assert value_codec.encode("117.5", "float64") == struct.pack("<d", 117.5)


def test_encode_bool_truthy():
    for v in ("1", "true", "TRUE", "t", "yes", "y"):
        assert value_codec.encode(v, "bool") == b"\x01"


def test_encode_bool_falsy():
    for v in ("0", "false", "FALSE", "f", "no", "n"):
        assert value_codec.encode(v, "bool") == b"\x00"


def test_encode_bool_invalid():
    with pytest.raises(ValueError):
        value_codec.encode("maybe", "bool")


def test_encode_hex_clean():
    assert value_codec.encode("deadbeef", "hex") == b"\xde\xad\xbe\xef"


def test_encode_hex_with_prefix():
    assert value_codec.encode("0xdeadbeef", "hex") == b"\xde\xad\xbe\xef"


def test_encode_hex_with_spaces():
    assert value_codec.encode("de ad be ef", "hex") == b"\xde\xad\xbe\xef"


def test_encode_hex_odd_length_raises():
    with pytest.raises(ValueError, match="even-length"):
        value_codec.encode("abc", "hex")


def test_type_names_complete():
    """All TYPE_SPECS keys are exposed via TYPE_NAMES."""
    assert set(value_codec.TYPE_NAMES) == set(value_codec.TYPE_SPECS.keys())
