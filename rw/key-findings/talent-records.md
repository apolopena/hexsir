# Save: talent records

## What this doc is — for non-experts

**Plain-English summary.** When you pick talents during a Ravenswatch run, the game records two different things in the save: WHICH talent goes in each slot (a 16-byte ID per slot) and WHAT RARITY each talent has (a 1-byte rarity value per controller, plus 10 u32 per-slot rarity values). The picks-block format is the same across all chapters — `[u32 N count][N × 16-byte GUIDs]` — but the chapter-2 layout has a coincidental "sentinel pattern" that doesn't generalize. See "Picks-block locator" below.

**Rules of thumb when working with this finding:**

1. **Picks-block format is uniform: `[u32 N][N × 16-byte GUIDs]`.** Chapter 2 has N=5, chapter 3 has N=8, epilogue has N=10. Verified 2026-05-03 across all three Geppetto proofs by `rw/scripts/inspect_picks_block.py`. Picks accumulate forward across chapters (slot-1 GUID is identical in chapter-2, chapter-3, and epilogue proofs). `rerw write savefile talent --slot N --key K` and `talent-rarity --slot N --rarity X` accept any slot 1..10 (slot 5 is the ult and has no rarity).
2. **Rarity is stored in TWO places.** The per-controller rarity byte (in tag=0x10 records) drives the HUD display and the picker stamp when the slot's loaded talent is valid. The per-slot u32 array at talent-record `+0x35` (10 entries) drives the picker stamp when the slot's loaded talent is null/incompatible. Edit both via `rerw write savefile all-talent-rarities <rarity>`.
3. **Slot 5 is the ult slot. Slot 10 is the ult-upgrade.** Slot 5's rarity byte is always `0x04` (ult-marker). Slot 10 has rarity per the user's gameplay observation, contrary to what an earlier version of this doc claimed.
4. **Mint does NOT clear talent picks.** It zeroes per-run currencies, level, xp, scores, and a few other fields, but the talent records (tag=0x12 picks block + tag=0x10 rarity bytes + slot.rarity u32s) are passed through verbatim from the source proof.
5. **Hero-swap creates a hybrid state.** The save still has the old hero's talent GUIDs but the new hero's controller pool; the engine "translates" old GUIDs to new-hero equivalents. Side effect: if you hero-swap an epilogue save to a different hero, the engine may put the new hero's ult into engine-slot 0 (HUD slot 1) at runtime, distorting the level 5 picker behavior.

**Skip to the deeper sections for the byte layouts and editing primitives.**

---

Talent picks and rarity values are encoded in the save body as references to skill-controller GUIDs defined in each hero's `herodef.ot` binary. Two distinct record types carry the data:

- A **tag=0x12 talent record** holds the player's talent picks for the run, stored as N × 16-byte skill-controller GUIDs back-to-back near the end of the record (N = number of slots picked so far).
- 28 **tag=0x10 first-occurrence records** (one per skill controller) sit in the herodef-reference region near the hero record. Each carries that controller's rarity byte. The engine reads rarity from the tag=0x10 record matching the slot's *current* GUID — change a slot's GUID and the engine looks up rarity from the new talent's tag=0x10 record.

**Status:** verified end-to-end. Slots 1–5 swaps via the chapter-2 `laser-lenses_1` proof (talent-only swap to Trait Twins, rarity-only edit to Legendary, combined edit). Slots 6–10 swap verified 2026-05-03 via the epilogue `laser-lenses_1` proof (slot 6 → Twin Dummies, in-game HUD readback). Hero-specific verification is Geppetto only; cross-hero generality unverified.
**Created:** 2026-04-27

## Run leveling structure (player gameplay reference)

A Ravenswatch run uses 10 talent slots, but only 6 of them are actively chosen at "talent pick" milestones — and only slot 5 and slot 10 are ult-related. The full table:

| Level | Slot | Pick options | Has rarity? | Notes |
|------:|-----:|---|:-:|---|
| 1 | 1 | 4 starting talents (choose 1) | yes | hero's starting kit |
| 2 | 2 | 3 regular talents | yes | regular pick |
| 3 | 3 | 3 regular talents | yes | regular pick |
| 4 | 4 | 3 regular talents | yes | regular pick |
| 5 | 5 | Ultimate Power 1 or Ultimate Power 2 | **no** | one-of-two ult; rarity byte is `0x04` (ult-marker) |
| 6 | 6 | 3 regular talents | yes | regular pick |
| 7 | 7 | 3 regular talents | yes | regular pick |
| 8 | 8 | 3 regular talents | yes | regular pick |
| 9 | 9 | 3 regular talents | yes | regular pick |
| 10 | 10 | 2 ult upgrades, MUST match the L5 ult pick | **no** | constrained by slot 5 |

Slot-10 ult-upgrade constraint:
- If slot 5 = `Ultimate Power 1` → slot 10 must be `Ultimate 1 Upgrade 1` or `Ultimate 2 Upgrade 1` (the **suffix** number, not the prefix, identifies which base ult an upgrade pairs with)
- If slot 5 = `Ultimate Power 2` → slot 10 must be `Ultimate 1 Upgrade 2` or `Ultimate 2 Upgrade 2`

Verified 2026-04-29 via cross-reference against the Ravenswatch wiki for all 12 heroes: `Skill Controller Ultimate N Upgrade M` pairs with `Skill Controller Ultimate Power M` (the M suffix, not the N prefix). The prior version of this section had it backwards — corrected.

(For Geppetto. Each hero defines its own four ult-upgrade controllers in its herodef.)

The save records the talent-pick block with a count field. Layout is `[u32 N][N × 16-byte GUIDs]`, linear-append. **Verified 2026-05-03 across chapter-2 (N=5), chapter-3 (N=8), and epilogue (N=10) Geppetto proofs.** Picks carry forward across chapters: slot-1 GUID is identical across all three proofs.

## Talent record (tag=0x12)

Located by its stable 15-byte GUID `bf e7 f6 60 43 85 cb 48 87 f6 b4 b7 9f 68 12` (followed by separator byte `0xa5`). Same GUID across all Geppetto saves observed; presumed hero-independent (it identifies the talent-record type, not the hero).

Locate by `data.find(b'\x12\x00\x00\x00' + record_guid_15)`.

### Picks block — generalized layout

```
[u32 N]                        ← talents-picked count (was the "sentinel" anchor in chapter-2)
[N × 16-byte talent GUIDs]     ← slots 1..N, back-to-back at 16-byte intervals
[8 bytes: 0x00 padding]
[float ≈ 800–4000: timing accumulator, varies per save]
[8 bytes: 0x00 padding]
[4 bytes: 22 22 bb aa close marker]
```

Verified across all three Geppetto proofs (2026-05-03, `rw/scripts/inspect_picks_block.py`):

| Save | N | Picks-count u32 offset | Trailing float |
|------|--:|------------------------|---------------:|
| chapter-2 / laser-lenses_1 | 5 | 0xf12c | 990.0 |
| chapter-3 / laser_lenses_1 | 8 | 0xf598 | 2020.0 |
| epilogue / laser-lenses_1 | 10 | 0xf7d8 | 3700.0 |

### Picks-block locator (generalized)

The picks block sits inside the run-state record (the same tag=0x12 record that holds item records — see `magical-objects.md`). The bytes immediately preceding the picks count u32 are the **end of the set-bonus tracker** (`[u32 N items at threshold][N × 16-byte GUIDs]` per `magical-objects.md`).

**Why the chapter-2 sentinel `00 00 00 00 05 00 00 00` worked, and why it stops working:**

- Chapter-2 `laser-lenses_1` has **0 set-bonus items at threshold** → the tracker collapses to `[u32 = 0]` = 4 zero bytes → those 4 zeros sit immediately before the picks count u32 → pattern matches.
- Chapter-3 / epilogue have **N > 0 set-bonus items** → the 4 bytes before the picks count are the tail of the last tracker GUID (random-looking) → pattern does not match.

The sentinel is a chapter-2 coincidence, not a structural anchor. **Don't search for it.**

**Correct locator strategy:**

1. Locate the talent (run-state) record: `record_off = data.find(bytes([0x12,0,0,0]) + RECORD_GUID_15)`.
2. Walk the run-state body forward per `magical-objects.md`: items count → items records-array → set-bonus tracker (`[u32 N][N × 16-byte GUIDs]`).
3. The 4 bytes immediately after the tracker = the picks count u32. Read it as `M`.
4. Picks block = next `M × 16` bytes. Slot N (1-indexed) = picks_start + (N-1)*16.
5. After picks: `[8 zero][float][8 zero][22 22 bb aa]` close marker.

Alternative (simpler if items-side parsing is unavailable): walk **backward** from the close marker. The trailing structure is fixed: `[8 zero][float][8 zero][close]`. Past those 24 bytes the picks block ends; the 4 bytes before that are the last GUID's tail; back up 16 bytes per GUID until you find a u32 N at picks_count_off such that `picks_count_off + 4 + N*16 == picks_end`. This is what `rw/scripts/inspect_picks_block.py` does.

### Editing slot N's talent (primitive — needs CLI rewrite)

1. Locate the picks count via the strategy above.
2. Compute slot N's offset: `slot_N_off = picks_count_off + 4 + (N - 1) * 16`.
3. Write the new 16-byte skill-controller GUID at `slot_N_off`.
4. Recompute body CRC32 and write at offset `0x0C`.

The edit is constant-size — the picks block is `M × 16` bytes regardless of which talents are slotted. No body shift required as long as M is unchanged.

The current CLI (`rerw write savefile talent --slot N --key K`) still uses the chapter-2-only sentinel search and so fails on chapter-3 / epilogue saves. Open follow-up: rewrite the locator using the generalized strategy above. Tracked in the open-follow-up list at the end of this doc.

### All-10-slots-empty trick (verified 2026-05-02)

Setting picks count to 0 AND removing the 80-byte GUID block produces a save the engine treats as "no picks made yet." Combined with `level=14`, the engine fires picker invocations for all 10 HUD slots on level-up — no auto-ult-insertion side effect, no error 4 modal.

Procedure (applied AFTER any other talent edits):

1. Locate the picks-block sentinel as above.
2. Patch the count u32 (last 4 bytes of the 8-byte sentinel) from `5` to `0`.
3. Delete the 80 bytes (5 × 16) of GUID data immediately after the sentinel. File shrinks by 80 bytes.
4. Recompute CRC.

Verified-success golden using this recipe: `rw/saves/edits/golden/romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof/`. The CLI surface is `rerw write savefile clear-picks --source X --dest Y --force`.

### Other fields in the talent record (clarified 2026-05-02)

Beyond the 5-pick block, the record also contains:
- A header with timing/state floats (purpose unconfirmed).
- **10 u32 LE values at body+0x35..+0x5c — the per-slot rarity array.** Each value `[0..4]` is one slot's rarity (0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker / uninitialized). Earlier this doc claimed this region was a "parallel encoding the engine doesn't read for HUD rarity" — that was correct for HUD display but missed that the **picker** does read it: when a slot's loaded talent is null (e.g., after hero-swap incompatibility), the picker stamps the picked talent's rarity from this array rather than from the tag=0x10 byte. Empirically verified 2026-05-02 by editing all 10 entries to `3` and observing every picker proposal display Legendary regardless of which talent was selected. CLI: `rerw write savefile all-talent-rarities <rarity>` writes BOTH this array and the 28 tag=0x10 rarity bytes in one pass.
- A nested-record list of tag=0x1a records (21 in Save A, 11 in Save B). Each is 32 bytes (`marker + tag + 16-byte runtime GUID + u32 sequence counter + close`). **Identified 2026-04-29 as item pickup records, not talent-offer history.** Each record represents one item the player collected during the run; the 16-byte GUID matches a magical-object entity-component instance. See `magical-objects.md` for the full record format and verified SWAP edit primitive.

## Rarity record (tag=0x10, first-occurrence)

Each of the 28 Geppetto skill controllers has a tag=0x10 record in the herodef-reference region near the hero record. Each is 25 bytes:

```
[u32 = 0x10]             ← type tag
[16 bytes: talent GUID]   ← matches the herodef Skill Controller GUID
[byte = 0x01]             ← flag, constant; purpose unknown
[byte = TIER]             ← THIS is the rarity the engine reads for HUD display
[3 bytes: 0x00 padding]
```

So rarity is at `(talent_guid_first_occurrence_offset + 17)` — i.e., 16 bytes for the GUID + 1 byte for the `0x01` flag.

### Rarity value encoding (verified)

| Byte value | Rarity         | Notes |
|-----------:|--------------|-------|
| `0x00`     | Common       |       |
| `0x01`     | Rare         |       |
| `0x02`     | Epic         |       |
| `0x03`     | Legendary    | Verified by single-byte lab edit on Save A slot 1 (Dummy Ball Common → Legendary). |
| `0x04`     | ult-marker   | Set on Ultimate Power 1, Ultimate Power 2, Ultimate 2 Upgrade 1, Ultimate 2 Upgrade 2. The L5 ult slot has no real "rarity" in gameplay terms; this byte value is a structural placeholder. |

### Editing a slot's rarity (verified primitive)

The engine reads rarity from the tag=0x10 record matching the slot's **current** GUID. To change slot N's displayed rarity:

1. Look up the talent currently in slot N (via the talent-pick block above, or by trusting the caller).
2. Find the FIRST occurrence of that talent's GUID in the save: `first_off = data.find(talent_guid_16)` (the FIRST occurrence is in the tag=0x10 record region, at a lower offset than the talent-pick block's second occurrence).
3. Verify the pre-context: bytes `(first_off - 8) .. first_off` should equal `11 11 bb aa 10 00 00 00` (start marker + tag 0x10).
4. Write the new rarity byte at `first_off + 17`.
5. Recompute body CRC32 and write at offset `0x0C`.

If you're swapping the talent AND changing rarity in one operation, edit the talent-pick block first, then look up the NEW talent's tag=0x10 record and edit its rarity byte. The tag=0x10 record for the OLD talent doesn't need to change (the engine no longer reads from it for that slot).

### Per-controller rarity defaults in Save A

All 28 Geppetto skill controllers' tag=0x10 records carry a rarity byte even when the talent isn't a player pick. For Save A (`laser-lenses_1`), the rarity bytes are:

| Slot | Picked talent             | rarity byte | Rarity  |
|-----:|---------------------------|----------:|-------|
| 1    | Special Creates Dummy     | `0x00`    | Common (= "Dummy Ball" L1) |
| 2    | Passive Create Objects    | `0x02`    | Epic |
| 3    | Defense Laser Eyes        | `0x01`    | Rare (= "LaserLenses" L3) |
| 4    | Trait Max Health          | `0x00`    | Common |
| 5    | Ultimate Power 1          | `0x04`    | ult-marker |

Non-picked controllers in Save A also have non-default rarity bytes (e.g., `Special Regeneration: 0x03`, `Trait Nose Attack: 0x02`, `Attack Makes Dummies Attack: 0x01`). Most likely these record the player's prior level-up offers / observed rarities, not active picks.

## Skill-controller GUIDs (Geppetto, 28 total)

Extracted from `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` (located at `rw/harvested/Definitions/Heroes/Kqjjqiir.nqurtqh.ri.NiAqurNqhdzdidrz.yqz` after substitution-cipher decode). Format in herodef: `[u32 tag = 4][u32 = 0][u32 strlen][string "Skill Controller XXX"][16-byte GUID]`.

| idx | Skill Controller name              | GUID (16 bytes)                    | In-game name (verified) |
|----:|------------------------------------|------------------------------------|-------------------------|
| 0   | Attack Finisher                    | `e7763662f645ad4a85dc45e0e75ff312` |                         |
| 1   | Trait Attack Move                  | `21785d41837b5246b366746dd9c602f2` |                         |
| 2   | Trait Max Health                   | `8d4006d92172b447aee88ab1239aadf0` |                         |
| 3   | Ultimate Power 1                   | `f156f2f780a5544d8ea36e1cc8f0e4eb` | (one of two L5 ults)    |
| 4   | Ultimate Power 2                   | `c559438ca1eada438da879cd444c12d0` | Overclock               |
| 5   | Attack Makes Dummies Attack        | `c43347dac07d7f4fb2753bf41eec4aa0` |                         |
| 6   | Dash Deals Damage                  | `3eb79ea457a27c4cba0f4c3bb5d91e17` |                         |
| 7   | Special Creates Dummy              | `830f33de77f48c4f92169cdf1aa2a1d2` | Dummy Ball              |
| 8   | Trait Buff On Dummy Death          | `b0dca163180f834d91882149b98a0fb2` |                         |
| 9   | Trait Extra Charge                 | `135cfc3f6f4f214382ad7a1ef7bfc8a9` |                         |
| 10  | Trait Twins                        | `33cdbac4ce86134da99bc59a19021b6a` | Twin Dummies            |
| 11  | Defense Lightning                  | `6456dec2173ce941862604997a5740ea` |                         |
| 12  | Special Regeneration               | `cbf6b4ae2146e443b692afbafebbdb59` | Clockwork Medicine      |
| 13  | Trait Missiles                     | `e95ab3b1bef1a44aa4f9d97c9cc67c2a` |                         |
| 14  | Power Unstable                     | `b16d6d4efbabf9419d1ef8929840eeba` |                         |
| 15  | Power Overcharge                   | `be6943130657c54eb192f164d6de14ab` |                         |
| 16  | Attack Group Speed                 | `56e3027d194292418b86d128135e85e0` | Family Meeting          |
| 17  | Defense Laser Eyes                 | `6aec13fa8e2c314d88babb71a8e3c4df` | LaserLenses             |
| 18  | Special Pushback                   | `12399e775781ea489fac7990c12b5e72` |                         |
| 19  | Defense AOE                        | `59e150803ee1c241a888c588a0212de8` |                         |
| 20  | Passive Create Objects             | `d02382d89c13354dafb8d13ebc7c3f66` |                         |
| 21  | Trait Nose Attack                  | `ad0838845a9ac14c8f4936a6d8b763ba` | Sharp Noses             |
| 22  | Power Magnet                       | `12f93e1092efa64fa9d3002b4dfe4765` |                         |
| 23  | Trait Blast Construction           | `904b2028a8eb904aa3154773e72f6788` |                         |
| 24  | Ultimate 1 Upgrade 1               | `49c048d36106174286c73433919c150f` |                         |
| 25  | Ultimate 2 Upgrade 1               | `cab3e19fc15d1a4bb60c2deb994c7553` |                         |
| 26  | Ultimate 1 Upgrade 2               | `4433ba05e980cb468f7672b3f4921706` |                         |
| 27  | Ultimate 2 Upgrade 2               | `8167cd9f423b4042bc07135d68f4a5a3` |                         |

The "in-game name" column maps the herodef internal name to what the player sees in the talent UI. Verified mappings come from gameplay confirmation (Save A's known starting talent + run name) and Save B's all-known picks.

## Cross-hero generality (unverified)

The talent-record GUID `bfe7f660...12a5` is presumed hero-independent — it identifies the talent-record type in the OEngine schema, not Geppetto specifically. Each hero's herodef defines its own 28 skill controllers with hero-specific GUIDs.

The structure (tag=0x12 + 5 GUIDs at end + tag=0x10 records with rarity byte at GUID+17) is presumed to generalize. Verifying requires a non-Geppetto save proof. Not yet attempted.

## Verified golden artifacts

Saves at `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/`:

- `talent-slot1-to-twin-dummies/` — slot 1 GUID swap only (Special Creates Dummy → Trait Twins). Rarity remained Common (the engine read from Trait Twins' tag=0x10 record which had the default rarity 0).
- `talent-slot1-rarity-byte-to-legendary/` — single-byte rarity edit only (Special Creates Dummy rarity `0x00` → `0x03`). Slot 1 displayed Dummy Ball at Legendary.
- `talent-slot1-twin-dummies-legendary/` — combined: slot 1 GUID swap + rarity byte edit on Trait Twins' tag=0x10 record. Slot 1 displayed Twin Dummies at Legendary.

## Sources

- `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` (deciphered) — controller GUID source.
- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — Save A (talents: Dummy Ball / Passive Create Objects / LaserLenses / Trait Max Health / Ultimate Power 1; rarities: Common/Epic/Rare/Common/ult).
- `rw/saves/proofs/geppetto/chapter2/twin-dummies-all-legendary-talents/Profile_1.ob` — Save B (Twin Dummies / Family Meeting / Clockwork Medicine / Sharp Noses / Overclock; all 4 tiered = Legendary).
- `rw/dumps/geppetto/talent-record-decoded.txt` — exploration log including the body+0x35 false-lead investigation.
- `rw/key-findings/talents.md` — talent name reference (player-facing names).
- `rw/key-findings/save-binary-format.md` — overall save format conventions (CRC32, record markers).
