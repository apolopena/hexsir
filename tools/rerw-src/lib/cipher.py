"""oEngine filename cipher for Ravenswatch.

Substitution cipher used on asset filenames inside _Cooking folder.
"""

PLAIN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CIPHER = "gabtqhynd%mlxzrj%uviwkopscWBSNMVKAXEIGHU#TPLFQJDR#C#"

# Remaining unknowns (# = unknown, % = unknown lowercase):
# Positions: 9(j), 16(q), 40(O), 44(S), 50(Y), 51(Z)


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
