[← Back to findings](README.md)

# Held Dream Shards — bytefield reference

**Status:** confirmed
**Status notes:** active reference. Verified in lab 2026-05-01.
**Field:** `oCDtEntityCpntHeroControllerPersistentData` (HC) body, offset `+0x1D`, **float32 LE** (byte-misaligned).

The HUD-displayed Dream Shards spendable count. Authoritative direct-read field — the HUD reads this value verbatim and does **not** recompute it from `earned − spent`.

## Sources

- pre-policy — written before the Sources header was mandatory.

## Storage

| Property | Value |
|---|---|
| Containing class | `oCDtEntityCpntHeroControllerPersistentData` (single instance per save) |
| Body offset | `+0x1D` |
| Width / type | 4 bytes, float32 little-endian |
| Alignment | byte-misaligned (offset is odd; not 4-aligned) |
| Front-anchored | Yes — same offset across all chapters (verified ch2 / ch3 / epilogue) |

The walker `lib/hc_walker.py` exposes this as the `held_dream_shards` field.

## Adjacent fields in the per-run float block

The four floats at HC body `+0x11`, `+0x15`, `+0x19`, `+0x1D` form one contiguous run-state block, zeroed wholesale by mint:

| Offset | Walker name | Meaning |
|---|---|---|
| +0x11 | `damage_float_1` | Per-run damage stat (likely damage dealt; not yet rigorously confirmed) |
| +0x15 | `damage_float_2` | Per-run damage stat (likely damage taken; not yet rigorously confirmed) |
| +0x19 | `dream_shards_earned` | Total Dream Shards earned this run (= held + dream_shards_spent) |
| +0x1D | `held_dream_shards` | **This field.** HUD spendable count. |

The related `dream_shards_spent` (Dream Shards already spent at the dream tree) lives further into the HC body at a chapter-shifting offset (`+0x35D` ch2, `+0x65D` ch3, `+0x79D` epilogue) past the HeroIngredient vector, HMO vector, and three guid16 vectors. Resolved dynamically by the walker as `dream_shards_spent`.

## Cross-check with adjacent fields

In observed saves the relationship `held = earned − dream_shards_spent` holds:

| Save | Held (+0x1D) | Earned (+0x19) | Spent (dynamic) |
|---|---:|---:|---:|
| `proofs/geppetto/chapter2/laser-lenses_1` | 101.0 | 1091.0 | 990.0 |
| `proofs/geppetto/chapter3/laser_lenses_1` | 21.0  | 2041.0 | 2020.0 |

**This is not an invariant the game enforces on load.** The HUD reads `+0x1D` directly. Editing only `+0x1D` changes the displayed spendable count even when earned and spent disagree. Verified in lab `held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof`: golden source had earned=0 / spent=0 / held=0; we patched held=99.0 only; HUD on load showed **99**.

If you also care about score-page consistency or end-of-run conversion to Stars of Fate, edit earned and spent to match.

## Editing

Set held shards directly:

```bash
rerw write savefile shards <float> --source <save> --dest <dir>
```

Programmatically:

```python
from lib import cooked
from lib.setters import set_held_dream_shards

cf = cooked.parse_file(open(src,'rb').read())
old = set_held_dream_shards(cf, 50.0)
open(dst,'wb').write(cooked.encode_file(cf))   # auto-recomputes CRC32
```

Mint zeros this field along with the rest of the per-run float block (via `setters.zero_per_run_damage`).

## Verification source

Lab promotion record: `rw/saves/edits/golden/geppetto/chapter1/held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof/info.md`.

## Related

- `save-edit-pipeline.md` — full HC body schema and the broader save-edit pipeline.
- `tools/rerw-src/lib/hc_walker.py` — runtime walker exposing `held_dream_shards`, `dream_shards_earned`, `dream_shards_spent`.
- `tools/rerw-src/lib/setters.py` — `set_held_dream_shards` setter and `zero_per_run_damage` zeroer used by mint.
