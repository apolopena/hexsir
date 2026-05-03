[← Back to findings](README.md)

# Talent picker — count override + rarity-weighting pipeline

**Status:** in-progress
**Created:** 2026-05-03

## Sources

- `Ravenswatch.exe` (Ghidra MCP — function decomp + byte-pattern hash xrefs)
- `rw/dumps/talent_weighting_ghidra_findings.md` — working notes from the Ghidra dig (this doc supersedes the Confirmed parts; the dump retains raw decompile excerpts).
- `tools/frida/rw_lab.js` — Frida hub script: `pickerCount(n)` / `unpatchPickerCount()` REPL commands.
- `rw/saves/mints/geppetto/chapter2/laser-lenses_1/romeo-pickscount0-all10-legendary/Profile_1.ob` — test save (Romeo, ch1, lvl 14, all 10 slots open + Legendary stamps; used for live picker-count verification).
- `rw/findings/rng-behavior.md` — TLS-PCG seed model that the picker reads from.

## Confirmed Findings

### Pipeline functions

Three functions form the talent-rarity pipeline (named in Ghidra):

| Function | RVA | Role |
|---|---|---|
| `SkillController_roll_proposed_skills` | `0x39c300` | Picks WHICH talents are offered, assembles per-tier weight vector, calls the rarity roll for each pick. |
| `talent_roll_tier_weighted` | `0x2e7b80` | Weighted PCG draw 0..3 → tier; reads per-tier coefficients from a registry record. |
| `talent_stamp_tier` | `0x2e7a40` | Writes the chosen tier onto the talent and mirrors into the 10 controller slot-tier shadows. |

Plus `is_skill_pick_free` @ `0x38d8c0` (reads "Free Reroll" stat to decide if a reroll skips its cost) and `SkillController_repropose_skills` @ `0x39ccb0` (reroll wrapper).

### Run-wide gameplay-modifier stats (hash → name)

Found via byte-pattern search of LE hash bytes against `register_gameplay_modifier_stats`:

| Hash | Display name | Read site | Effect |
|---|---|---|---|
| `0x1709d22b` | "Skill better quality chance" | `roll_proposed_skills` 0x39c8e2 | Looped 3× over property bag, summed into `local_138[1..3]` (per-tier input weight vector) for every proposal. |
| `0x1bfb2a14` | "Reset skill better quality chance" | `roll_proposed_skills` 0x39c982 / 0x39c9b2 / 0x39ca83 / 0x39caf2 | Conditional on controller-flag at `+0x1354`: if **0**, the property is consumed (one-shot bonus); if **non-zero**, it stacks into `local_138[iVar18+1..3]` BEFORE each per-pick roll → biases tier upward across the whole offered set. |
| `0x1871c2fa` | "Rare Skill Chance Modifier" (NGP category) | `talent_roll_tier_weighted` 0x2e7c29 | Read inside the per-pick roll, added directly onto `param_3[1]` (slot-1 weight). Per-pick. |
| `0x1a7a3166` | "Extra skill choice" | `roll_proposed_skills` (via `param_1+0x2f8` property bag) | Adds onto `local_148`, the count of talents to propose. Base 2 (or 4 for class-0 slot index). |
| `0x1aa49d8d` | "Free Reroll" | `is_skill_pick_free` | Number of free rerolls allowed; checked vs reroll-count at `(controller+0x1d48)+0x40`. |
| `0x1709d229` | "MO better quality chance" | sibling — items pipeline | Same role for items/MOs (not traced this session). |

### Per-tier coefficients (data-asset side)

In `talent_roll_tier_weighted`, `puVar11` is the registry entry whose vftable check against `DAT_141447830` returns true. Four per-tier scalars at:

- `puVar11[0x29]` (= byte offset `0x148`) — tier 0
- byte offset `0x14c` — tier 1
- `puVar11[0x2a]` (= byte offset `0x150`) — tier 2
- byte offset `0x154` — tier 3

Each used as `weight = scalar * input + scalar` (both coefficient and base). Roll formula:

```
local_48[i] = scalar[i] * param_3[i] + scalar[i]
total       = local_48[0] + local_48[1] + local_48[2] + local_48[3]
roll        = uniform_float_in_range_pcg(total)        // PCG, TLS state at +0xff3c
chosen_tier = first i where running_sum(local_48[..i]) >= roll
```

Then `if (chosen_tier < param_2) chosen_tier = param_2` (caller-supplied floor) → `talent_stamp_tier`.

### Picker count override — verified live

Two adjacent immediates compute how many talents the picker offers per level-up:

```
0x39c4cb : LEA ECX,[RBX+0x2]     ; iVar18 + 2  (non-zero class-index slots)
0x39c4e2 : ADD EBX, 0x4          ; iVar18 + 4  (class-0 slot)
```

Encoded as:

- `LEA ECX,[RBX+0x2]` = `8D 4B 02` → byte at `image+0x39c4cd` is the immediate `0x02`
- `ADD EBX, 0x4` = `83 C3 04` → byte at `image+0x39c4e4` is the immediate `0x04`

**`pickerCount(n)`** in `tools/frida/rw_lab.js` writes `n` to both bytes via `Memory.patchCode`. **`unpatchPickerCount()`** restores originals (saved on first apply).

**Verified in-game 2026-05-03** with `pickerCount(6)` against the Romeo Mint test save:

- Engine accepts the patched count without clamping or crashing.
- Picker UI accommodates the extra cards.
- UI clip at high N: the top card extends above the viewport (cards are rendered from a fixed anchor that grows upward). Cards are still selectable by scrolling/navigating up.
- Picker count is observed to be the EFFECTIVE count = `iVar18 + n` where `iVar18` is the value of the "Extra skill choice" stat at picker entry. With `iVar18 == 0` and `n == 6`, the picker offered exactly 6 cards.

Per-pick `local_148` clamp at `0x39c4ea` caps the count to the available candidate-pool size, so `pickerCount(N > pool_size)` silently degrades to `pool_size`.

### RNG path

Picker uses the TLS-state PCG (RXS-M-XS variant) at
`*(longlong*)ThreadLocalStoragePointer + 0xff3c`. Inline at
`0x39c93b`-`0x39c97d` in `roll_proposed_skills`. Same TLS slot the picker-seed solver targets — see `rng-behavior.md`.

### Guaranteed-legendary short-circuit

In `talent_roll_tier_weighted`:

```c
lVar3 = *(longlong *)(param_1 + 0x10);
if (*(int *)(lVar3 + 0x178) == 2) {
    uVar9 = 4;            // force tier index 4 (highest)
} else {
    /* normal weighted roll */
}
```

A flag at offset `+0x178` of the talent context (`param_1->[0x10]->+0x178`) short-circuits the weighted roll when set to `2`. Likely the path used by force-legendary pickups (Laser Lenses, chapter-completion bonuses).

## Unresolved

- **`controller + 0x1354` flag — writers + semantics.** Decides whether `0x1bfb2a14` "Reset skill better quality chance" is a one-shot consume vs a persistent stacking bonus. Not yet traced where this gets set; this is the closest thing to a "weight-the-whole-run-toward-rare-talents" mechanism.
- **Registry row dump for the per-tier scalars.** `DAT_141447830` keys the vftable lookup; haven't dumped the actual scalar values for the 4 tiers.
- **`+0x178 == 2` writers.** Identifying the gameplay event that sets the talent context to "force legendary" — probably tied to specific item pickups but unconfirmed.
- **NGP gating of `0x1871c2fa` "Rare Skill Chance Modifier".** Lives under the New Game Plus inspector category; haven't confirmed whether it's only active in NGP runs or always present at value 0.
- **Items / chest / Sandman shop pickers.** The same pattern presumably applies (TLS-PCG + per-feature picker entry function) — mechanically reachable per `rng-behavior.md`, just not yet hooked.

## Notes

The picker-count override is a **2-byte patch** with no scaffolding (interceptor-attach, callback, etc.) — the patch sites are clean immediate operands. This is the simplest "real game logic" Frida intervention in the lab to date; it sets a baseline for evaluating how invasive future picker patches need to be.

The discovery flow was: Ghidra string-search for "Picker"/"TalentPicker" → no hits → fell back to property-bag hash xrefs from `register_gameplay_modifier_stats` → identified the five hashes above by walking the registration call sites and pairing each `register_modifier_stat(puVar10, HASH, ...)` with its preceding string literal. That registry function is the canonical lookup for "what does hash X mean" and is worth keeping handy for any future modifier-stat investigations.
