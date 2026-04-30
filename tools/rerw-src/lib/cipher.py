"""oEngine filename cipher for Ravenswatch.

Substitution cipher used on asset filenames inside _Cooking folder.
"""

PLAIN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CIPHER = "gabtqhynd%mlxzrj%uviwkopscWBSNMVKAXEIGHUOTPLFQJDR#CZ"
COOKING_MARKER = "DarkTalesResources/_Cooking/"

# Position 40 (O) confirmed as identity: empirical match
#   `Hrtgl_Fgkq_Ou_Pwdi.qzidis.ri` → `Modal_Save_Or_Quit.entity.ot`
#   (cooked filename of GameUis\Modal\Modal_Save_Or_Quit.entity.ot, 2026-04-30)
#
# Position 51 (Z) confirmed as identity:
#   `EntitySettings/FZ` → `MzidisFqiidzyv/VZ`
#
# Remaining unknowns (# = unknown uppercase, % = unknown lowercase):
# Positions: 9(j), 16(q), 49(X)


def encipher(text: str) -> str:
    """Encode plaintext to ciphered filename."""
    result = []
    for char in text:
        idx = PLAIN.find(char)
        result.append(CIPHER[idx] if idx >= 0 else char)
    return "".join(result)


def decipher(text: str) -> str:
    """Decode ciphered filename to plaintext."""
    result = []
    for char in text:
        idx = CIPHER.find(char)
        result.append(PLAIN[idx] if idx >= 0 else char)
    return "".join(result)


def transform_cooked_path(text: str, transform) -> str:
    """Apply a cipher transform only after the cooked asset path marker."""
    if COOKING_MARKER not in text:
        return transform(text)
    prefix, suffix = text.split(COOKING_MARKER, 1)
    return prefix + COOKING_MARKER + transform(suffix)


def encipher_path(text: str) -> str:
    """Encode only the cooked asset suffix of a full path."""
    return transform_cooked_path(text, encipher)


def decipher_path(text: str) -> str:
    """Decode only the cooked asset suffix of a full path."""
    return transform_cooked_path(text, decipher)
