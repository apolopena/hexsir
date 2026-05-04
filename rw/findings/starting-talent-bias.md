[← Back to findings](README.md)

# Starting-talent bias — does elevated rarity steer subsequent rolls?

**Status:** in-progress
**Created:** 2026-05-03

## Sources

- `Ravenswatch.exe` (Ghidra MCP — function decompile + byte-pattern hash xrefs)
- `rw/findings/talent-picker-weighting.md` — prior dig that mapped the talent-tier weighting pipeline
- `rw/findings/rng-behavior.md` — TLS-PCG seed model and dual-storage tier model

## Hypothesis under test

Community report (paraphrased): *"if a hero's special starting talent starts above Common while the other starting talents stay at Common, all subsequent items and talents lean in the direction of the special one."*

Two distinct readings of "lean in the direction":

- **(A) Identity / category bias.** The starting talent's *theme/category/family* biases the **pool composition or selection probability** for later talent picks AND items. (e.g. starting with a Stars-themed Legendary makes future picks tilt Stars-themed.)
- **(B) Cross-system rarity carry.** The starting talent's *rarity tier* somehow leaks into the items picker (item drops, shop offers) — separately from any talent-side modifier.

This finding investigates both and reports the verdict.

## Verdict — short version

- **(A) Identity / category bias: NOT SUPPORTED.** No code path reads talent identity, category, theme, or any per-talent metadata field as input to weighted-random selection in either the talent picker or the items picker. Both pickers are identity-blind once the rarity tier is fixed: selection within a tier/bucket is uniform random over the candidate pool.
- **(B) Cross-system rarity carry: NOT SUPPORTED.** The items picker does not read SkillController state, slot-tier mirrors, starting-talent records, or any modifier registered by the talent system. Talent-side and items-side modifier hashes are cleanly separated siblings — neither system reads the other's stats.
- **A weaker, real effect does exist (per-slot rarity stickiness).** The talent picker stamps the new talent at the slot's *existing* tier when no re-roll condition is met. So a Legendary starting talent in slot N keeps stamping Legendary on subsequent picks **for that same slot only**. This is per-slot, not run-wide, and only affects rarity (not identity/theme). It does NOT cross over to items.

In short: the perceived "all items and talents lean toward the special starting talent" effect is not a coded mechanism. The closest real effect is per-slot rarity persistence within the talent system, which is constrained to the affected slot and does not influence item drops.

## Evidence

### Picker selection is identity-blind

`SkillController_roll_proposed_skills` @ `0x39c300` builds the candidate pool and runs Fisher-Yates partial selection:

```
pool = controller.pools[class_index]                  // selected by slot's class index, not identity
pool.filter_held()                                    // remove already-equipped (dedup)
pool.filter_previous_proposal(param_3)                // remove last reroll's picks (dedup)
loop count = local_148 picks:
  idx = pcg_step() % remaining_pool_size              // uniform random
  proposal.push(pool[idx]); swap+shrink
```

The PCG draw is uniform over `remaining_pool_size`. No weight, no per-talent identity input, no category check. This was already verified in `rng-behavior.md` for the seed-forcing harness; re-reading with the category-bias lens confirms there is no hidden category weight.

The only *deterministic* per-identity code in the picker is the secondary priority-insertion buffer (`puVar7` in the decompile, used for class-0 / class-{2,3} slots): pool entries whose data-definition flags satisfy `*(byte at +0xc0) != 0 || *(byte at +0x40) == 0` get sorted via `FUN_1402e8ae0` and prepended to the proposal before the random Fisher-Yates picks. The comparator (`FUN_1402e8ae0` @ `0x2e8ae0`) sorts by:

1. Primary: byte at `(data+0x10) + 0xc0` (a category/sort-key flag)
2. Secondary: integer extracted via vftable lookup against `DAT_1414483a0` (per-talent typed value lookup)
3. Tertiary: integer at `(data+0x10) + 0xcc`

These keys are **read entirely from the talent's data-definition** — registry-side static metadata. They do not read hero state, run state, currently-held talents, or starting-talent rarity. So the priority-insertion buffer's ordering is deterministic per the talent registry, not run-influenced.

### Tier-roll inputs are identity-blind

`talent_roll_tier_weighted` @ `0x2e7b80` reads:

- 4 per-tier coefficients from a registry record (vftable match against `DAT_141447830`)
- `0x1871c2fa` "Rare Skill Chance Modifier" (NGP), added to `param_3[1]` (Rare/slot-1 weight)
- The `+0x178 == 2` short-circuit (force-Legendary path)

No talent identity, no talent category, no starting-talent input. The roll is run on the per-pick weight vector that the caller (`roll_proposed_skills`) passed in — and the caller's adjustment of that vector reads ONLY:

- `0x1709d22b` "Skill better quality chance" (added 3× across slot-1..slot-3 weights, identity-agnostic)
- `0x1bfb2a14` "Reset skill better quality chance" (re-stacked when controller `+0x1354` flag is set)

Again: no identity, no category, no per-starting-talent input.

### Items picker is independent of the talent system

`MagicalObjectController_roll_proposed_objects` @ `0x2d4740` (renamed from `FUN_1402d4740`) is the items picker. It reads exactly two modifier hashes:

- `0x1709d229` "MO better quality chance" — one-shot probability to upgrade the rarity bucket
- `0x1893b9e4` "Extra MO Choice" — additive count modifier (sibling of "Extra skill choice")

Selection: it constructs an `oCDtEntityCpntMagicalObject::oCSearchFilter`, runs `mo_roll_rarity_bucket_weighted` (`FUN_1402d5230`, renamed) to pick a rarity bucket weighted across 6 buckets, then **draws uniform random with `tls_random_modulo()`** over the filtered pool for that bucket.

Crucially, the items picker reads:

- The encyclopedia scene context's modifier property bag
- The items controller's own settings fields (`param_1+0x1c8`, `+0x1d8`, `+0x1e0`, `+0x208`, etc.)
- The exclude-list of already-picked items (`param_1+0x240`)

It does **not** read:

- `controller+0x1d48` (the SkillController slot-tier mirror)
- `controller+0xff0..+0x1110` (currently-loaded talents)
- `controller+0x1170..+0x117c` (the per-tier histogram set by `SkillController_sync_slot_tiers_from_talents`)
- Any of the talent-side modifier hashes (`0x1709d22b`, `0x1bfb2a14`, `0x1871c2fa`, `0x1a7a3166`)

The only shared call is `is_skill_pick_free` (free-reroll cost check), and that decides whether a reroll skips its cost — it does not influence selection weights.

Verified by byte-pattern search on the LE-encoded hash constants:

| Hash | Read sites |
|---|---|
| `0x1709d22b` (Skill better quality chance) | only in `SkillController_roll_proposed_skills` |
| `0x1709d229` (MO better quality chance) | only in `MagicalObjectController_roll_proposed_objects` |
| `0x1bfb2a14` (Reset skill better quality chance) | 4 sites, all in `SkillController_roll_proposed_skills` |
| `0x1871c2fa` (Rare Skill Chance Modifier, NGP) | only in `talent_roll_tier_weighted` |
| `0x1a7a3166` (Extra skill choice) | only in `SkillController_roll_proposed_skills` |
| `0x1893b9e4` (Extra MO Choice) | only in `MagicalObjectController_roll_proposed_objects` |

The two systems are sealed off from each other at the modifier-stat layer.

### What the user is probably observing — per-slot rarity stickiness

Per `talent-picker-weighting.md`, for each picked talent the engine reads the slot's existing tier and branches:

```c
iVar18 = *(int*)(*(longlong*)(param_1 + 0x1d48) + 0x18 + local_f0 * 4);   // slot.tier mirror
if (iVar18 == 4)        roll_fresh();                  // sentinel = uninit, roll
else if (bonus_path)    roll_with_floor(iVar18);       // floor=current, can only go up
else                    talent_stamp_tier(new, iVar18);// STAMP slot's existing tier
```

`SkillController_sync_slot_tiers_from_talents` (`0x39bc80`) copies the loaded talent's tier byte (`+0x68`) into the slot-tier mirror at run start (and on every relevant equip change). So a starting Legendary in slot N produces `slot.tier[N] = 3`. Every subsequent pick rolled into slot N reads `iVar18 = 3`, bypasses both the fresh-roll and the bonus paths, and **stamps the new talent at Legendary** by default.

This produces a real, observable effect: "my Romeo started with one Legendary and that slot keeps offering Legendaries." But it is:

- **Per-slot, not run-wide.** Other slots with `slot.tier == 4` (no starting talent loaded for that slot, or sync resolved to 4) still roll fresh.
- **Rarity, not identity/category.** The new talent picked for the slot is uniform random within the per-class pool; only the *tier stamp* sticks.
- **Talent-only.** Items don't read this mirror.

So the felt phenomenon ("all my picks for this slot are Legendary") has a real cause, but it's not the bias the user described.

## Annotations applied this session

Renames in Ghidra (committed via `mcp__ghidra__rename_symbol`):

- `FUN_1402d4740` → `MagicalObjectController_roll_proposed_objects`
- `FUN_1402d5230` → `mo_roll_rarity_bucket_weighted`
- `FUN_1402d4200` → `MagicalObjectController_repropose_objects`

Plate comments added at:

- `0x1402d4740` — items picker summary, modifier hash list, "no talent state read" assertion.
- `0x1402d5230` — bucket-weighted-roll structure (6 buckets, override + asset weights).
- `0x14039c9eb` — pre-comment on the per-slot rarity-stickiness branch in the talent picker.

## Unresolved / next steps

- **`FUN_1402d3490` not yet named.** This appears to be the items-picker UI-flow / state-machine wrapper (mirror of the talent-side reroll harness). Want to confirm before renaming. It shares `is_skill_pick_free` with the talent path, suggesting a unified picker UI substrate.
- **Bucket-weight registry rows.** `mo_roll_rarity_bucket_weighted` reads weights from `param_1+0x128`. The actual values per items controller (Common bucket weight, Rare bucket weight, etc.) would let us simulate items rolls forward — useful for an items-side seed solver if ever wanted. Not blocking the current question.
- **Empirical confirmation.** Verdict above is read-only-from-binary. A Frida confirmation experiment would be: in the same chapter-2 mint save, run two sessions with seeded starting talents — one all-Common, one with a Legendary in slot 0 — and compare item drops + talent picks for slots 1..4 across many forced seeds. Prediction: identical distributions for slots 1..4 and identical item drops; only slot 0's tier stamps differ. If anyone reports otherwise it's a bug in the model, not the prediction.
- **Talent-picker secondary buffer.** The priority-insertion buffer (`puVar7` / `local_158`) sorted by `FUN_1402e8ae0` deserves a separate finding if its category-flag inputs ever interact with run state. Current read: registry-side metadata only, no run input.

## Notes on methodology

This dig used the queue-and-apply annotation pattern discussed at the start of the session — I held annotations until the picture was clear and applied at the end. In retrospect the session was solo and the standard "annotate on the spot" rule would have worked equally well here; the queue-and-apply pattern is more useful when multiple agents are digging in parallel against the same Ghidra instance, which was not the case.
