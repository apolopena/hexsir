"""Tests for cipher library."""

from lib.cipher import decipher, encipher


def test_decipher_geppetto():
    """Deciphers Geppetto correctly."""
    assert decipher("Kqjjqiir") == "Geppetto"


def test_encipher_geppetto():
    """Enciphers Geppetto correctly."""
    assert encipher("Geppetto") == "Kqjjqiir"


def test_roundtrip():
    """Encipher then decipher returns original."""
    original = "Hero_Geppetto"
    assert decipher(encipher(original)) == original


def test_decipher_heroes():
    """Deciphers Heroes correctly."""
    assert decipher("Aqurqv") == "Heroes"


def test_decipher_entity_extension():
    """Deciphers entity.ot correctly."""
    assert decipher("qzidis.ri") == "entity.ot"


def test_preserves_non_alpha():
    """Non-alphabetic characters pass through unchanged."""
    assert (
        decipher("Aqur_Kqjjqiir!Aqur_Kqjjqiir.qzidis")
        == "Hero_Geppetto!Hero_Geppetto.entity"
    )
