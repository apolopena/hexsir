[← Back to findings](README.md)

# Hero asset table

**Status:** confirmed
**Status notes:** active reference. Source data extracted from the deciphered asset tree.
**Created:** 2026-04-27

The 12 playable heroes shipped in the current Ravenswatch build, as resolved from `rw/ref/tree-deciphered.txt`. Useful as a reference for hero-record save edits — see `save-binary-format.md` for record format details.

## Heroes

The Geppetto hero record in chapter saves contains the path string `Heroes\Geppetto.herodef.ot` (length-prefixed ASCII; total path length = 26 bytes, encoded in a `u32` length prefix preceding it; the underlying cooked asset filename is `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen`). Other heroes follow the same pattern. Same-length save-path strings enable byte-for-byte swaps; different-length names require length-prefix update + body-shift handling.

| Hero | Save path string `Heroes\<N>.herodef.ot` (length) | Deciphered asset file | Swap from Geppetto |
|------|:---:|---|---|
| Aladdin | 25 | `Heroes/Aladdin.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 25`, body shifts −1 byte |
| Beowulf | 25 | `Heroes/Beowulf.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 25`, body shifts −1 byte |
| **Carmilla** | **26** | `Heroes/Carmilla.herodef.ot.DtHeroDefinition.gen` | **drop-in byte-swap, no shift** ✅ |
| Geppetto | 26 | `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` | (current) |
| Juliet | 24 | `Heroes/Juliet.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 24`, body shifts −2 bytes |
| **Melusine** | **26** | `Heroes/Melusine.herodef.ot.DtHeroDefinition.gen` | **drop-in byte-swap, no shift** ✅ |
| Merlin | 24 | `Heroes/Merlin.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 24`, body shifts −2 bytes |
| Piper | 23 | `Heroes/Piper.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 23`, body shifts −3 bytes |
| Red | 21 | `Heroes/Red.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 21`, body shifts −5 bytes |
| Romeo | 23 | `Heroes/Romeo.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 23`, body shifts −3 bytes |
| Snow_Queen | 28 | `Heroes/Snow_Queen.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 28`, body shifts +2 bytes |
| Sun_Wukong | 28 | `Heroes/Sun_Wukong.herodef.ot.DtHeroDefinition.gen` | length prefix `26 → 28`, body shifts +2 bytes |

**Two same-length swap candidates from a Geppetto save: Carmilla and Melusine.** These are byte-for-byte path replacements + CRC32 re-mint — no record-framing changes, no offset shifting in any subsequent record.

The full deciphered asset path (under the game install root) is `DarkTalesResources/_Cooking/Definitions/Heroes/<Name>.herodef.ot.DtHeroDefinition.gen`. The save records only the `Heroes\<Name>.herodef.ot` portion — no path prefix, no class suffix (`.DtHeroDefinition`), no `.gen` extension. The class name `DtHeroDefinition` (DarkTales-prefixed) is consistent with the `Dt`-prefixed type names visible in the type-registry portion of saves (`oCDtHeroProfileData`, etc., per the clean-save grep earlier).

## Source

Extraction from the deciphered asset tree:

```bash
grep -oE "Heroes/[A-Za-z_#%]+\.herodef\.ot" rw/ref/tree-deciphered.txt | sort -u
```

`tree-deciphered.txt` was generated 2026-04-27 from `rw/ref/tree-ciphered.txt` via `tools/rerw-src/lib/cipher.decipher`. The substitution cipher's six unknown positions (`j`, `q` lowercase; `O`, `S`, `Y`, `Z` uppercase) would render as `%` / `#` placeholders if any hero name contained them — none did, so the list is complete and reliable.

## Caveats

- **List is complete for the current game build only.** Patches that add or remove heroes will require regenerating the deciphered tree and re-extracting.
- **Path format is verified for Geppetto** (the only hero observed in proof saves). The other 11 entries are inferred from the asset-tree pattern; their actual presence in save records would only be confirmed by saves from runs of those heroes — which we don't have.
- **Hero-record swap mechanic is unverified.** Even a same-length byte-swap (`Geppetto` → `Carmilla`) is theoretical until a live test loads cleanly with the swapped hero.

## Sources

- `rw/ref/tree-deciphered.txt` — generated from `tree-ciphered.txt` via the rerw cipher lib.
- `rw/findings/save-binary-format.md` — record format details + verification status.
- `rw/saves/proofs/geppetto/{chapter2,chapter3,epilogue}/.../Profile_1.ob` — the only saves with a confirmed hero record (all Geppetto).
