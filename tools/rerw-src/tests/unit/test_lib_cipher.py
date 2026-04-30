"""Tests for cipher library."""

from lib.cipher import decipher, decipher_path, encipher, encipher_path


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


def test_decipher_path_preserves_cooking_prefix():
    path = (
        "/mnt/d/steam-storage/steamapps/common/Ravenswatch/"
        "DarkTalesResources/_Cooking/3N/Fbqzqus/"
        "BgagCgyg!Arwvq_Fxgll_Sgujqi.hap.Kqrxqius.yqz"
    )
    assert decipher_path(path) == (
        "/mnt/d/steam-storage/steamapps/common/Ravenswatch/"
        "DarkTalesResources/_Cooking/3D/Scenery/"
        "BabaYaga!House_Small_Carpet.fbx.Geometry.gen"
    )


def test_encipher_path_preserves_cooking_prefix():
    path = (
        "/mnt/d/steam-storage/steamapps/common/Ravenswatch/"
        "DarkTalesResources/_Cooking/3D/Scenery/"
        "BabaYaga!House_Small_Carpet.fbx.Geometry.gen"
    )
    assert encipher_path(path) == (
        "/mnt/d/steam-storage/steamapps/common/Ravenswatch/"
        "DarkTalesResources/_Cooking/3N/Fbqzqus/"
        "BgagCgyg!Arwvq_Fxgll_Sgujqi.hap.Kqrxqius.yqz"
    )


def test_uppercase_z_identity_mapping():
    assert decipher("MzidisFqiidzyv/VZ") == "EntitySettings/FZ"
    assert encipher("EntitySettings/FZ") == "MzidisFqiidzyv/VZ"
