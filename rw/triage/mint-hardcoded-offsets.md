# Mint command uses hardcoded HC body offsets — fails on non-chapter-2 sources

**Status:** open, in progress.
**Created:** 2026-05-01

## The bug

`rerw mint savefile` writes to hardcoded HeroController body offsets (notably `+0x35D` for "dream-shards collected"). Those offsets were calibrated against the chapter-2 proof (`rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`, HC body = 873 bytes). Other proofs have substantially different HC body sizes:

| Proof | HC body size | Notes |
|---|---|---|
| chapter-2 laser-lenses_1 | 873 bytes | recipe was calibrated here |
| chapter-3 laser_lenses_1 | 1641 bytes | mint OUTPUT IS CORRUPT (parse-back fails at file offset 0xee86) |

When the mint runs on a chapter-3 source, the write to HC body+0x35D lands at a semantically-wrong position because variable-length sections earlier in the body (HeroIngredient vector, HeroMOPersistentData vector, etc.) push named fields around. Result: corrupted bytes that fail the cooked decoder's marker-walk and would fail the in-game loader's per-class deserialize.

The lab `rw/saves/edits/lab/mint-to-ch1__from-chapter3-laser_lenses_1-proof/Profile_1.ob` is the corrupted output. **DO NOT LOAD.** Kept for diagnostic reference.

## Why offsets shift

HC's `Serialize` (reverse-engineered as `serde_hero_controller_persistent_data` at image+0x380490) reads fields in a specific order. Some fields are fixed-size (GUIDs, primitives) but several are variable-length vectors:

- `serde_vec_oSDtHeroIngredient(this+0x98)` — N × 20-byte framed records
- `serde_vec_guid16(...)` — N × 16-byte GUIDs (multiple call sites)
- `serde_vec_hero_owned_mo_persistent_data(this+0xa8)` — N × 20-byte framed records (the HMO records — chapter-3 has 33+ of these vs chapter-2's 21)
- `serde_vec_string(this+0xd8)` — N × length-prefixed strings
- `serde_vec_32byte_element(this+0xc8)` — N × 32-byte elements

Any fixed-position write that lands AFTER any of these vectors will be in the wrong place if the source has different vector populations.

The mint already handles ONE such variable section correctly (the HeroIngredient vector at +0x21): it computes `post_vec = 0x25 + 20*N` for the feathers-consumed and stars-of-fate writes. But it does NOT handle the other variable sections — the dream-shards write at `+0x35D` is the first casualty.

## Three fix options

- **A. Gate the mint to chapter-2-shaped sources only.** Validate HC body size matches the chapter-2 reference (~873 bytes); error out otherwise with a clear message. Immediate, safe, but limits scope.
- **B. Add per-field dynamic offset for the specific fields the mint touches.** Each variable-length section before a target field needs to be parsed enough to compute its byte size, so the target field's actual file offset can be derived. Partial fix; tractable today.
- **C. Full HC wire-format parser.** Walk the HC body field-by-field per the serde, build a map of field-name -> file-offset, apply edits to resolved positions. Universal fix; more work but scales to any future field we want to edit.

User direction: implement C. Iterate until the mint succeeds on the chapter-3 source.

## Implementation plan for C

1. Add `lib/save_mint_wire.py` (or extend `lib/cooked.py`) with a function that parses an HC body and returns a `dict[str, (offset, length)]` field map.
2. Walk the serde call sequence in order. For each call:
   - Primitives (vtable[0x70/0x78/0x90/0xa8] etc.) advance the cursor by the known primitive size.
   - Vectors call into sub-walkers that consume the count u32 then each record.
   - Framed sub-objects (oSDtHeroIngredient, HeroMOPersistentData) consume `4 + 4 + body_size + 4` bytes per record, using `MARK_END` to find body size if it's not fixed.
3. Verify by:
   - Round-tripping the chapter-2 proof: parsed offsets for known fields must match our hardcoded values.
   - Parsing the chapter-3 proof: all fields must be locatable, no overflow.
4. Refactor `lib/save_mint.py` to use the field map instead of hardcoded offsets.
5. Re-run the mint on chapter-3 source. Output must parse cleanly.
6. Add unit tests for both chapter-2 and chapter-3 proof inputs.

## Cross-references

- `rw/key-findings/save-subsystem.md` — save subsystem RE
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — wire-format references
- `rw/key-findings/save-silencer-mechanism.md` — context for why deserialize failure trips the silencer
- HC serde decompile: `serde_hero_controller_persistent_data` at image+0x380490
