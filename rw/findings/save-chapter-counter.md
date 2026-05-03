[← Back to findings](README.md)

> **ARCHIVED 2026-04-27** — superseded by [`rw/findings/save-binary-format.md`](../save-binary-format.md).
> Preserved for historical detail. The chapter-counter facts are reproduced (with
> corrections) in the canonical key finding's "Verified editable fields" table —
> consult that for current claims. Note: this archived doc has an internal byte-
> count inconsistency on GUID B's ASCII span ("11 bytes" vs string `faultdef.ot&`
> which is 12 chars) and refers to `mod_save.py` as the canonical edit tool, both
> of which the canonical key finding corrects.

# Save: Chapter Counter
**Status:** archived


The Ravenswatch save format encodes the player's chapter progression via two
parallel int32 records keyed by 15-byte GUIDs. Both must be set to the same
target value. Editing both + recomputing the body's CRC32 produces a save that
loads at the targeted chapter while preserving all run-state (level, gear,
currency, items, talents).

Verified end-to-end 2026-04-27: a `chapter3` Geppetto save edited to
`chapter-counter = 0` loaded at the chapter 1 starting scene with the full
chapter-3 run-state intact. See
`rw/saves/edits/golden/geppetto/chapter1/laser_lenses_1/chapter-rewind-from-ch3/Profile_1.ob`.

## Records

Two parallel records hold the chapter value. Both progress in lockstep across
all observed saves; both must be edited together.

| Record | GUID (15 bytes hex) | Notes |
|--------|--------------------|-------|
| Counter A | `13fa8e2c314d88babb71a8e3c4df01` | Opaque ID. Not yet decoded. |
| Counter B | `6661756c746465662e6f7426ba4519` | First 11 bytes are ASCII `faultdef.ot&` — the tail of `All_Chapters.gamemodedefaultdef.ot.GameModeDefaultDefinition.gen` (deciphered via `rerw decipher`). Trailing 4 bytes `26 ba 45 19` look like a hash/index of the full asset path. |

Layout (both records identical):

    +0    GUID (15 bytes)
    +15   int32 LE — the chapter value

Locate by `data.find(guid)`; the value lives at GUID + 15. Offsets shift across
saves because save size grows with run-state — locate by GUID, not by absolute
offset.

## Value semantics — "chapters completed", not "current chapter"

| Value | State | Where it appears |
|------:|-------|------------------|
| (absent) | Chapter 1, no run in progress | `clean/Profile_1.ob` — both GUIDs are not present in the file |
| 0 | Chapter 1, run in progress | Verified: chapter-rewind from ch3 → ch1 with value=0 loads cleanly with run-state intact |
| 1 | Chapter 2 | `chapter2/laser-lenses_1/Profile_1.ob` |
| 2 | Chapter 3 | `chapter3/laser_lenses_1/Profile_1.ob` |
| 3 | Epilogue | `epilogue/laser-lenses_1/Profile_1.ob` |

Two distinct "chapter 1" states exist: **GUID absent** (clean profile, no run)
vs **GUID present with value 0** (run in progress, currently in chapter 1).
The chapter-rewind primitive produces the latter — the engine accepts an
existing run with the counter rewound rather than requiring a fresh run.

## Edit procedure

1. Read the save into a mutable buffer.
2. For each of the two GUIDs: locate via `data.find(guid)`, write target int32 LE at `guid_offset + 15`.
3. Recompute CRC32 of the body (`zlib.crc32(data[16:])`) and write it as int32 LE to offset `0x0C`.
4. Write the file back at the path the game expects (`Profile_1.ob`; never rename).
5. Install into the active save slot via `rerw swap savefile --source <modified>`.

Tool support: `rw/scripts/mod_save.py` implements steps 1–4 (CRC handling included). The chapter GUIDs are not yet registered in its `KNOWN_GUIDS` table — registering them as `ChapterCounterA` and `ChapterCounterB` is planned follow-up so the rewind reduces to `mod_save.py <save> --set ChapterCounterA 0 --set ChapterCounterB 0`.

## Run-state preservation

The chapter rewind preserves all run-coupled state observed so far:

- Hero level
- Equipment / talents
- Currencies (dream shards, stars of fate, keys, raven's feathers)
- Inventory items

No chapter-specific lock-out detected. The implication is the game's
run-state is not gated on the chapter counter; only the scene-load path
reads it. This makes the chapter counter a clean, isolated edit target.

## Stability of the GUIDs

The 15-byte GUID values are stable across all saves observed and across
saves of differing run lengths (chapter 2, chapter 3, epilogue). They are
compile-time-baked references to the underlying record schema, not
per-save random IDs.

What can invalidate them:

- A game patch that changes the underlying asset (`All_Chapters.gamemodedefaultdef.ot` recompiled with a different schema, or class rename). GUID B's `26 ba 45 19` tail would shift; GUID A's identity is unknown so impact unpredictable.
- Cross-hero stability not yet tested. Plausibly stable — the GameMode reference (Counter B) is per-game-mode, not per-hero — but unverified.

## Open: the hash tail

GUID B's trailing 4 bytes `26 ba 45 19` correlate to the asset path
`All_Chapters.gamemodedefaultdef.ot.GameModeDefaultDefinition.gen` or some
substring of it. The unknown GUID `b43eeb58d162fa41acef99d128f2cb`
(originally suspected to be ProfileDreamShards; identity disproven 2026-04-27,
see `rw/findings/save-binary-format.md` § "Misidentified") and the `Level`
GUID (`b5317efe6f4a95737325675793e600`) likely follow the same family —
ASCII-prefix or fully-hashed. Reversing this hash function would make it
possible to mint arbitrary GUIDs from asset paths, which is plausibly the
path to programmatic item / talent / ability editing (the unresolved
"in-run dream shards" / "stars of fate" / item-array fields documented in
`rw/findings/geppetto-save-analysis.md`).

Hash candidates to test: CRC32, FNV-1a, MurmurHash, Passtech-custom — and
the input domain to test: full asset path, deciphered class name, raw
ASCII basename. Pursuing this is its own work-track.

## Sources

- rw/findings/geppetto-save-analysis.md (initial chapter-counter pattern observation)
- rw/saves/proofs/geppetto/{chapter2,chapter3,epilogue}/.../Profile_1.ob (source data; identified the 1 → 2 → 3 progression)
- rw/saves/edits/golden/geppetto/chapter1/laser_lenses_1/chapter-rewind-from-ch3/Profile_1.ob (verified mod)
- rw/ref/tree-ciphered.txt (asset tree; deciphered via `rerw decipher` to identify GUID B as the All_Chapters GameMode reference)
- rw/scripts/mod_save.py (read / write / CRC tooling)
- tools/rerw (cipher / decipher / swap savefile install)
